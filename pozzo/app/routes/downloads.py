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
from ...downloads import debrid, finish, hosts, install, multiup, resolvers
from ...downloads.engines import http as HTTP, torrent as TOR
from ...downloads.manager import Manager
from ..apiv1 import sse


def build_router(ctx) -> APIRouter:
    cfg = ctx.cfg
    router = APIRouter()
    mgr = Manager(cfg, ctx.events)
    ctx.downloads = mgr

    def _unshorten(url: str) -> str:  # accorciatori pubblicitari, come per il pulsante «Scarica» del dettaglio gioco
        c = Cache(cfg.cache)
        try:
            return SL.resolve(c, url)
        finally:
            c.close()

    resolvers.register(_unshorten, lambda u: "Salto la pubblicità (ouo.io)" if SL.is_shortener(u) else "")
    resolvers.register(multiup.resolve, lambda u: "Cerco i mirror su MultiUp" if multiup.is_page(u) else "")
    resolvers.register(debrid.resolver(lambda: mgr._raw()["debrid"]), "Sblocco il link con il servizio debrid")
    resolvers.register(hosts.resolve,  # pagina dell'host (datanodes, 1fichier…) -> file vero
                       lambda u: f"Cerco il file su {hosts.host(u)}" if hosts.is_host_page(u) else "")
    browserdl.SHOW["fn"] = lambda: bool(mgr.settings().get("show_browser"))  # finestra del browser visibile per seguirla
    mgr.on_completed = lambda t: finish.run(t, mgr, ctx)  # estrae e mette il gioco in libreria
    mgr.start()

    @router.post("/api/links/mirrors")
    def api_links_mirrors(body: dict = Body(...)):
        """Tutti i mirror di una pagina MultiUp (anche dietro un accorciatore): la UI mostra un pulsante per host."""
        url = str(body.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            raise HTTPException(400, "Link non valido")
        if SL.is_shortener(url):
            try:
                url = _unshorten(url)
            except Exception:  # noqa: BLE001 - il browser nascosto puo' fallire in mille modi: nessun dettaglio interno
                url = ""
            if not url or SL.is_shortener(url):
                return {"ok": False, "page": "", "name": "", "mirrors": [], "reason": "non riesco a saltare la pubblicità"}
        r = multiup.mirrors(url)
        return {"ok": any(m["live"] for m in r["mirrors"]), **r}

    @router.get("/api/downloads")
    def api_downloads():
        return {"tasks": mgr.list(), "settings": mgr.settings()}

    @router.post("/api/downloads")
    def api_downloads_add(body: dict = Body(...)):
        links = [str(x) for x in body.get("links") or [body.get("source") or ""] if str(x).strip()][:50]
        if not links:
            raise HTTPException(400, "Nessun link")
        out = []
        for u in links:
            try:
                out.append(mgr.add(u, body.get("save_path") or "", priority=body.get("priority") or 0,
                                   category=body.get("category") or "").view())
            except ValueError as e:
                raise HTTPException(400, str(e))
        return {"ok": True, "tasks": out}

    def _act(tid: str, fn, *a):
        try:
            fn(tid, *a)
        except KeyError:
            raise HTTPException(404, "Download non trovato")
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
            raise HTTPException(404, "Servizio sconosciuto")
        key = (mgr._raw()["debrid"].get(svc) or {}).get("key")
        if not key:
            return {"ok": False, "user": "", "premium": False, "expires": None, "error": "Nessuna chiave salvata"}
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
            raise HTTPException(400, "Priorita' non valida: da -2 a 2")
        return _act(tid, mgr.set_priority, prio)

    @router.post("/api/downloads/{tid}/move")
    def api_downloads_move(tid: str, body: dict = Body(...)):
        return _act(tid, mgr.move, body.get("to"))

    @router.post("/api/downloads/{tid}/limit")
    def api_downloads_limit(tid: str, body: dict = Body(...)):
        return _act(tid, mgr.set_limit, body.get("down") or 0, body.get("up") or 0)

    @router.get("/api/downloads/{tid}/log")
    def api_downloads_log(tid: str, after: int = 0):
        """Registro del download, a pezzi: `after` = indice assoluto della prima riga che manca; `n` = righe scritte in tutto."""
        t = mgr.tasks.get(tid)
        if not t:
            raise HTTPException(404, "Download non trovato")
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
            raise HTTPException(400, "Serve {\"priorities\": {\"indice\": priorita'}}")
        try:
            return _act(tid, mgr.set_files, prio)
        except (TypeError, ValueError):
            raise HTTPException(400, "Priorita' non valida: 0, 1, 4 o 7")

    @router.post("/api/downloads/{tid}/sequential")
    def api_downloads_sequential(tid: str, body: dict = Body(...)):
        return _act(tid, mgr.set_sequential, bool(body.get("on")))

    @router.post("/api/downloads/torrent-file")
    async def api_downloads_torrent_file(file: UploadFile = File(...), save_path: str = Form("")):
        data = await file.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(400, "File .torrent troppo grande")
        if not TOR.available():
            raise HTTPException(400, "Per i torrent serve libtorrent: installalo con «pip install libtorrent»")
        try:
            TOR.lt.torrent_info(data)
        except RuntimeError:
            raise HTTPException(400, "File .torrent non valido")
        name = HTTP.safe_name(Path(file.filename or "upload").name)
        dest = mgr.uploads / f"{uuid.uuid4().hex[:8]}-{name.removesuffix('.torrent')}.torrent"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        try:
            return {"ok": True, "tasks": [mgr.add(str(dest), save_path).view()]}
        except ValueError as e:
            dest.unlink(missing_ok=True)
            raise HTTPException(400, str(e))

    @router.post("/api/downloads/{tid}/open-folder")
    def api_downloads_open(tid: str):
        t = mgr.tasks.get(tid)
        if not t:
            raise HTTPException(404, "Download non trovato")
        folder = Path(t.save_path)
        if sys.platform == "win32":
            target = folder / t.name if t.status == "completed" and (folder / t.name).exists() else None
            subprocess.Popen(["explorer", f"/select,{target}"] if target else ["explorer", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # niente shell: il percorso viene dall'utente
        return {"ok": True}

    @router.post("/api/downloads/{tid}/install")
    def api_downloads_install(tid: str):
        """Avvia il setup del repack scaricato: a fine installazione il gioco entra in libreria da solo."""
        t = mgr.tasks.get(tid)
        if not t:
            raise HTTPException(404, "Download non trovato")
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
