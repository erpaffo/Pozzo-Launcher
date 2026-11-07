"""Coda dei download: elenco, aggiunta, pausa/ripresa/annulla, impostazioni e stream degli aggiornamenti."""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ... import storelinks as SL
from .. import browserdl
from ...cache import Cache
from ...downloads import bandwidth, debrid, finish, hosts, install, multiup, resolvers
from ...downloads.engines import http as HTTP, steamcmd as STEAMCMD, torrent as TOR
from ...downloads.extract import queue_forecast
from ...downloads.manager import Manager
from ..apiv1 import sse
from ... import i18n as I


def _days(txt: str):
    """Giorni della pianificazione da un campo Form («0,1,2», 0 = lunedi'): None se non indicati."""
    if not (txt or "").strip():
        return None
    try:
        return [int(x) for x in txt.replace(" ", ",").split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, I.tr("s.downloads.days_invalid"))


def build_router(ctx) -> APIRouter:
    cfg = ctx.cfg
    router = APIRouter()

    def _playing() -> bool:
        """C'e' un gioco in corso? Lo sa il launcher, che la coda non importa: la risposta arriva da qui."""
        launcher = getattr(ctx, "launcher", None)
        st = (launcher.running() if launcher else None) or {}
        return st.get("status") in ("starting", "extracting", "running")

    mgr = Manager(cfg, ctx.events, playing=_playing)
    ctx.downloads = mgr
    bandwidth.configure(Path(cfg.cache))  # stesso downloads.db dello Store

    def _unshorten(url: str) -> str:  # accorciatori pubblicitari, come per il pulsante «Scarica» del dettaglio gioco
        c = Cache(cfg.cache)
        try:
            return SL.resolve(c, url)
        finally:
            c.close()

    resolvers.register(_unshorten, lambda u: I.tr("s.downloads.skip_ads") if SL.is_shortener(u) else "")
    resolvers.register(multiup.resolve, lambda u: I.tr("s.downloads.multiup") if multiup.is_page(u) else "")
    resolvers.register(debrid.resolver(lambda: mgr._raw()["debrid"]), lambda u: I.tr("s.downloads.debrid_unlock"))
    resolvers.register(hosts.resolve,  # pagina dell'host (datanodes, 1fichier…) -> file vero
                       lambda u: I.tr("s.downloads.find_file_on", host=hosts.host(u)) if hosts.is_host_page(u) else "")
    browserdl.SHOW["fn"] = lambda: bool(mgr.settings().get("show_browser"))  # finestra del browser visibile per seguirla
    mgr.on_completed = lambda t: (STEAMCMD.finish if t.type == "steamcmd" else finish.run)(t, mgr, ctx)  # estrae e mette il gioco in libreria
    def _queue_done(ok: int, failed: int):
        from ... import notify
        body = I.tr("s.notify.queueDoneBody", n=ok) + (" · " + I.tr("s.notify.queueDoneFailed", n=failed) if failed else "")
        notify.send(cfg, I.tr("s.notify.queueDone"), body)
    mgr.on_idle = _queue_done  # una sola notifica quando la coda si svuota, non una per file
    mgr.ctx = ctx  # subito: dopo un riavvio i task in attesa della scansione si ricontrollano (Manager.mark_ready)
    mgr.start()
    # alla chiusura: file .part chiusi e stato salvato prima dell'uscita immediata (os._exit non svuota i buffer)
    ctx.app.router.add_event_handler("shutdown", mgr.stop)

    @router.post("/api/links/mirrors")
    def api_links_mirrors(body: dict = Body(...)):
        """Tutti i mirror di una pagina MultiUp (anche dietro un accorciatore): la UI mostra un pulsante per host."""
        url = str(body.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            raise HTTPException(400, I.tr("s.downloads.link_invalid"))
        if SL.is_shortener(url):
            try:
                url = _unshorten(url)
            except Exception:  # noqa: BLE001 - il browser nascosto puo' fallire in mille modi: nessun dettaglio interno
                url = ""
            if not url or SL.is_shortener(url):
                return {"ok": False, "page": "", "name": "", "mirrors": [], "reason": I.tr("s.downloads.cannot_skip_ads")}
        r = multiup.mirrors(url)
        return {"ok": any(m["live"] for m in r["mirrors"]), **r}

    @router.get("/api/downloads")
    def api_downloads():
        return {"tasks": mgr.list(), "settings": mgr.settings()}

    @router.post("/api/downloads")
    def api_downloads_add(body: dict = Body(...)):
        links = [str(x) for x in body.get("links") or [body.get("source") or ""] if str(x).strip()][:50]
        if not links:
            raise HTTPException(400, I.tr("s.downloads.no_link"))
        out = []
        for u in links:
            try:
                # sha256/mirrors solo se il chiamante (catalogo, DAT, store) li conosce: add() li valida
                extra = {k: body[k] for k in ("sha256", "mirrors") if body.get(k)}
                if len(links) > 1:
                    extra.pop("sha256", None)  # un hash vale per un file solo
                out.append(mgr.add(u, body.get("save_path") or "", priority=body.get("priority") or 0,
                                   category=body.get("category") or "", start_at=body.get("start_at"),
                                   days=body.get("days"), **extra).view())
            except ValueError as e:
                raise HTTPException(400, str(e))
        return {"ok": True, "tasks": out}
    # la usa POST /m/api/downloads (remote/phone.py): con FastAPI recente app.routes non elenca le rotte dei router inclusi
    ctx.app.state.downloads_add = api_downloads_add

    def _act(tid: str, fn, *a):
        try:
            fn(tid, *a)
        except KeyError:
            raise HTTPException(404, I.tr("s.downloads.not_found"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @router.post("/api/downloads/pause-all")
    def api_downloads_pause_all():
        mgr.pause_all()
        return {"ok": True}

    @router.post("/api/downloads/resume-all")
    def api_downloads_resume_all():
        mgr.resume_all()
        return {"ok": True}

    @router.post("/api/downloads/alt-speed")
    def api_downloads_alt_speed(body: dict = Body(...)):
        return mgr.set_alt(bool(body.get("on")))

    @router.post("/api/downloads/debrid/{svc}/test")
    def api_downloads_debrid_test(svc: str):
        if svc not in debrid.SERVICES:
            raise HTTPException(404, I.tr("s.downloads.unknownService"))
        key = (mgr._raw()["debrid"].get(svc) or {}).get("key")
        if not key:
            return {"ok": False, "user": "", "premium": False, "expires": None, "error": I.tr("s.downloads.no_key")}
        return debrid.account(svc, key)

    @router.post("/api/downloads/{tid}/pause")
    def api_downloads_pause(tid: str):
        return _act(tid, mgr.pause)

    @router.post("/api/downloads/{tid}/resume")
    def api_downloads_resume(tid: str):
        return _act(tid, mgr.resume)

    @router.post("/api/downloads/{tid}/cancel")
    def api_downloads_cancel(tid: str, body: dict = Body(default={})):
        return _act(tid, mgr.cancel, bool(body.get("delete_files")))

    @router.post("/api/downloads/{tid}/priority")
    def api_downloads_priority(tid: str, body: dict = Body(...)):
        try:
            prio = int(body.get("priority") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, I.tr("s.downloads.priority_range"))
        return _act(tid, mgr.set_priority, prio)

    @router.post("/api/downloads/{tid}/move")
    def api_downloads_move(tid: str, body: dict = Body(...)):
        return _act(tid, mgr.move, body.get("to"))

    @router.post("/api/downloads/{tid}/schedule")
    def api_downloads_schedule(tid: str, body: dict = Body(...)):
        """«Avvia alle»: il download resta in coda e parte da solo (start_at vuoto = pianificazione annullata)."""
        return _act(tid, mgr.set_schedule, body.get("start_at"), body.get("days"))

    @router.post("/api/downloads/{tid}/limit")
    def api_downloads_limit(tid: str, body: dict = Body(...)):
        return _act(tid, mgr.set_limit, body.get("down") or 0, body.get("up") or 0)

    @router.get("/api/downloads/space")
    def api_downloads_space():
        """Spazio sui dischi della coda: dopo i download non finiti e dopo le estrazioni stimate (byte)."""
        with mgr.lock:
            tasks = list(mgr.tasks.values())
        return queue_forecast(tasks)

    @router.get("/api/downloads/stats")
    def api_downloads_stats():
        """Storico della banda: ultima ora per minuto, ultimi 30 giorni, host, totale (vedi downloads/bandwidth.py)."""
        return bandwidth.stats()

    @router.get("/api/downloads/{tid}/log")
    def api_downloads_log(tid: str, after: int = 0):
        """Registro del download, a pezzi: `after` = indice assoluto della prima riga che manca; `n` = righe scritte in tutto."""
        t = mgr.tasks.get(tid)
        if not t:
            raise HTTPException(404, I.tr("s.downloads.not_found"))
        lines, n = t.log_after(after)
        return {"lines": lines, "n": n, "from": n - len(lines)}

    @router.post("/api/downloads/{tid}/log/clear")
    def api_downloads_log_clear(tid: str):
        return _act(tid, mgr.log_clear)

    @router.post("/api/downloads/{tid}/recheck")
    def api_downloads_recheck(tid: str):
        return _act(tid, mgr.recheck)

    @router.post("/api/downloads/{tid}/reannounce")
    def api_downloads_reannounce(tid: str):
        return _act(tid, mgr.reannounce)

    @router.post("/api/downloads/{tid}/files")
    def api_downloads_files(tid: str, body: dict = Body(...)):
        prio = body.get("priorities")
        if not isinstance(prio, dict):
            raise HTTPException(400, I.tr("s.downloads.files_need_priorities"))
        try:
            return _act(tid, mgr.set_files, prio)
        except (TypeError, ValueError):
            raise HTTPException(400, I.tr("s.downloads.file_priority_invalid"))

    @router.post("/api/downloads/{tid}/sequential")
    def api_downloads_sequential(tid: str, body: dict = Body(...)):
        return _act(tid, mgr.set_sequential, bool(body.get("on")))

    @router.post("/api/downloads/torrent-file")
    async def api_downloads_torrent_file(file: UploadFile = File(...), save_path: str = Form(""),
                                         start_at: str = Form(""), days: str = Form("")):
        data = await file.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(400, I.tr("s.downloads.torrent_too_big"))
        if not TOR.available():
            raise HTTPException(400, I.tr("s.downloads.need_libtorrent"))
        try:
            TOR.lt.torrent_info(data)
        except RuntimeError:
            raise HTTPException(400, I.tr("s.downloads.torrent_invalid"))
        name = HTTP.safe_name(Path(file.filename or "upload").name)
        dest = mgr.uploads / f"{uuid.uuid4().hex[:8]}-{name.removesuffix('.torrent')}.torrent"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        try:
            return {"ok": True, "tasks": [mgr.add(str(dest), save_path, start_at=start_at,
                                                days=_days(days)).view()]}
        except ValueError as e:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, str(e))

    @router.post("/api/downloads/{tid}/open-folder")
    def api_downloads_open(tid: str):
        t = mgr.tasks.get(tid)
        if not t:
            raise HTTPException(404, I.tr("s.downloads.not_found"))
        folder = Path(t.save_path)
        # dopo l'estrazione il gioco sta altrove (cartella estratta o libreria) e l'archivio puo' non esserci piu'
        target = next((p for p in (t.options.get("placed"), t.name and folder / t.name) if p and Path(p).exists()), None)
        if sys.platform == "win32":
            # "/select," separato dal percorso: attaccati, con gli spazi Python li quota insieme ed Explorer apre Documenti
            subprocess.Popen(["explorer", "/select,", str(target)] if target else ["explorer", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # niente shell: il percorso viene dall'utente
        return {"ok": True}

    @router.post("/api/downloads/{tid}/install")
    def api_downloads_install(tid: str):
        """Avvia il setup del repack scaricato: a fine installazione il gioco entra in libreria da solo."""
        t = mgr.tasks.get(tid)
        if not t:
            raise HTTPException(404, I.tr("s.downloads.not_found"))
        try:
            install.start(t, mgr, ctx)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @router.post("/api/downloads/settings")
    def api_downloads_settings(body: dict = Body(...)):
        """Aggiornamento parziale; le chiavi debrid entrano ma non escono mai (solo key_set)."""
        try:
            return mgr.update_settings(body)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @router.get("/api/downloads/events")
    def api_downloads_events():
        """SSE: l'evento `downloads` porta i task cambiati (altri eventi dell'app passano sullo stesso flusso)."""
        return StreamingResponse(sse(ctx.events), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return router
