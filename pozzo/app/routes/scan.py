"""Fonti, scansione delle cartelle, console personalizzate, ricollegamento."""

from __future__ import annotations

import os
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from .. import jobs as J
from ... import config as C, platforms as P, profilecfg as PC, relink as RL
from ... import i18n as I


MAINT_DEFAULT = {"enabled": False, "day": 6, "time": "03:00"}  # day: lunedi' = 0, domenica = 6
_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _maint_settings(raw, strict: bool = False) -> dict:
    """Impostazioni della manutenzione: quelle non valide tornano al predefinito (o 400 se strict)."""
    out = dict(MAINT_DEFAULT)
    raw = raw if isinstance(raw, dict) else {}
    checks = {
        "enabled": lambda v: isinstance(v, bool),
        "day": lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 6,
        "time": lambda v: isinstance(v, str) and _HHMM.fullmatch(v) is not None,
    }
    for key, ok in checks.items():
        if key in raw:
            if ok(raw[key]):
                out[key] = raw[key]
            elif strict:
                raise HTTPException(400, I.tr("s.scan.settingInvalid", name=key))
    return out


def maintenance_due(now, settings: dict, last_run: str) -> bool:
    """Manutenzione dovuta adesso? Giorno giusto, ora passata (anche tardi, se l'app era chiusa), non ancora fatta oggi."""
    if not settings.get("enabled") or now.weekday() != settings.get("day") or last_run == now.strftime("%Y-%m-%d"):
        return False
    hh, mm = (int(x) for x in settings.get("time", "03:00").split(":"))
    return now.hour * 60 + now.minute >= hh * 60 + mm


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _maint_summary(d: dict) -> str:
    """Riepilogo in italiano delle sole voci peggiorate rispetto al giro precedente."""
    parts = []
    if n := len(d.get("rom_nuove_mancanti") or []):
        parts.append(_n(n, I.tr("s.scan.romOne"), I.tr("s.scan.romMany")))
    if n := len(d.get("bios_nuovi_invalidi") or []):
        parts.append(_n(n, I.tr("s.scan.biosOne"), I.tr("s.scan.biosMany")))
    if (n := d.get("covers_delta") or 0) > 0:
        parts.append(_n(n, I.tr("s.scan.coverOne"), I.tr("s.scan.coverMany")))
    if (b := d.get("freeable_delta") or 0) > 0:  # byte: piu' spazio sprecato in doppioni
        size = f"{b / 1024 ** 3:.1f} GB" if b >= 1024 ** 3 else f"{max(1, round(b / 1024 ** 2))} MB"
        parts.append(I.tr("s.scan.dupesSpace", size=size.replace('.', ',')))
    return I.tr("s.scan.maintSummary", parts=", ".join(parts) or I.tr("s.scan.maintCheckFailed"))


def maintenance_execute(cfg, job=None, state=None, lib=None, claim=None) -> bool:
    """Un giro di manutenzione. L'avviso parte solo se, rispetto al giro precedente, la situazione e' peggiorata.
    Con i job dell'app (job/state/claim): non parte se c'e' gia' uno scraping, una ricostruzione o un aggiornamento
    store, e occupa lo slot dello scraping cosi' l'utente non ne avvia un secondo. False = non partita."""
    from ... import maintenance as M, notify as N  # modulo a parte: importato solo quando serve
    kw, sj = {}, None
    if job is not None:
        if (state or {}).get("building") or job["store_refresh"].status == "running":
            return False
        from .. import jobs as _J
        sj = _J.ScrapeJob(retry_missing=True, title=I.tr("s.scan.maintTitle"))
        if not (claim or (lambda n, j: True))("current", sj):
            return False
        if claim is None:
            job["current"] = sj
        kw = {"scrape_job": sj, "store_job": job["store_refresh"]}
    try:
        prev = (M.latest(cfg) or {}).get("report")  # ultimo giro salvato, prima di farne uno nuovo
        cur = M.run(cfg, **kw)
    finally:
        if sj is not None and sj.status == "running":  # passo saltato o annullato: lo slot non resta occupato
            sj.status, sj.phase = "cancelled", I.tr("s.scan.maintInterrupted")
        if lib is not None:
            lib.load()  # scraping/store hanno riscritto la libreria
    if prev is not None:  # primo giro: niente da confrontare
        d = M.diff(prev, cur)
        if d.get("peggiora"):
            N.send(cfg, "Pozzo Launcher", _maint_summary(d))
    return True


def build_router(ctx) -> APIRouter:
    _missing, _pregen_thumbs, _rebuild, _refresh_manual, cfg, events = ctx._missing, ctx._pregen_thumbs, ctx._rebuild, ctx._refresh_manual, ctx.cfg, ctx.events
    job, lib, state, user = ctx.job, ctx.lib, ctx.state, ctx.user
    router = APIRouter()

    # ------------------------------------------------------------ fonti, limiti, database locali, pianificazione
    SOURCE_INFO = {
        "libretro": ("offline", I.tr("s.scan.srcLibretro")),
        "launchbox": ("offline", I.tr("s.scan.srcLaunchbox")),
        "tgdb": ("offline", I.tr("s.scan.srcTgdb")),
        "arcadedb": ("online", I.tr("s.scan.srcArcadedb")),
        "igdb": ("online", I.tr("s.scan.srcIgdb")),
        "screenscraper": ("online", I.tr("s.scan.srcScreenscraper")),
        "rawg": ("online", I.tr("s.scan.srcRawg")),
        "thegamesdb": ("online", I.tr("s.scan.srcThegamesdb")),
        "wikipedia": ("online", I.tr("s.scan.srcWikipedia")),
    }
    bulk_job: dict = {"status": "idle", "log": []}

    def _sources_state():
        from ...bulk import BULK
        from ...policy import Ledger, policy_for
        from ...sources import SOURCES
        ledger = Ledger(Path(cfg.cache) / "cache.db")
        try:
            usage = ledger.snapshot()
        finally:
            ledger.close()
        order = list(cfg.sources) + [x for x in SOURCES if x not in cfg.sources]
        rows = []
        for sid in order:
            kind, desc = SOURCE_INFO.get(sid, ("online", ""))
            pol = policy_for(cfg, sid)
            rows.append({"id": sid, "kind": kind, "description": desc, "enabled": sid in cfg.sources,
                         "policy": {"rate": pol.rate, "daily": pol.daily, "monthly": pol.monthly},
                         "usage": usage.get(sid, {"today": 0, "month": 0}),
                         "needs_key": sid in ("rawg", "igdb", "screenscraper", "thegamesdb"),
                         "has_key": bool({"rawg": cfg.rawg.get("api_key"), "igdb": cfg.igdb.get("client_id"),
                                          "screenscraper": cfg.ss.get("devid"), "thegamesdb": cfg.tgdb.get("api_key")}.get(sid, True))})
        return {"sources": rows, "bulk": [B(cfg.cache).status() for B in BULK.values()], "bulk_job": bulk_job,
                "schedule": cfg.app.get("schedule", {"enabled": False, "time": "03:00", "mode": "missing"}),
                "schedule_last": cfg.app.get("schedule_last", "")}

    @router.get("/api/sources")
    def api_sources():
        return _sources_state()

    @router.post("/api/sources")
    def api_sources_save(body: dict = Body(...)):
        from ...sources import SOURCES
        sections = {}
        if isinstance(body.get("order"), list):
            order = [x for x in body["order"] if x in SOURCES]
            if order:
                sections["scrape"] = {"sources": order}
                cfg.sources = order
        if isinstance(body.get("limits"), dict):
            from ...policy import DEFAULTS, Policy
            lim = {}
            for sid, v in body["limits"].items():
                base = Policy(sid, *DEFAULTS[sid]) if sid in DEFAULTS else Policy(sid)
                clean = {}
                for k in ("rate", "daily", "monthly"):
                    raw_v = v.get(k)
                    val = (float(raw_v) if k == "rate" else int(float(raw_v))) if raw_v not in (None, "") else 0
                    if k == "rate" and val <= 0:
                        raise HTTPException(400, I.tr("s.scan.rateMin", sid=sid))
                    if val != getattr(base, k):  # si salvano solo i valori cambiati rispetto ai predefiniti
                        clean[k] = val
                lim[sid] = clean or None
                if not clean:
                    cfg.limits.pop(sid, None)
            sections["limits"] = lim
        if "rawg_key" in body:
            sections["rawg"] = {"api_key": (body["rawg_key"] or "").strip() or None}
        if isinstance(body.get("schedule"), dict):
            sch = body["schedule"]
            sections["app"] = {"schedule": {"enabled": bool(sch.get("enabled")), "time": str(sch.get("time") or "03:00")[:5],
                                            "mode": sch.get("mode") if sch.get("mode") in ("new", "missing") else "missing"}}
        C.save_settings(cfg, **sections)
        return _sources_state()

    @router.post("/api/bulk/{bid}/refresh")
    def api_bulk_refresh(bid: str):
        from ...bulk import BULK
        if bid not in BULK:
            raise HTTPException(404)
        if bulk_job["status"] == "running":
            raise HTTPException(409, I.tr("s.scan.bulkBusy"))

        def run():
            import asyncio as _a
            from ...net import make_client
            bulk_job.update(status="running", log=[], id=bid)

            async def go():
                async with make_client() as client:
                    return await BULK[bid](cfg.cache).ensure(client, log=lambda m: bulk_job["log"].append(str(m)), force=True)
            try:
                bulk_job["status"] = "done" if _a.run(go()) else "error"
            except Exception as e:
                bulk_job["log"].append(I.tr("s.scan.errorPrefix", err=e))
                bulk_job["status"] = "error"
        threading.Thread(target=run, daemon=True).start()
        return {"ok": True}

    @router.post("/api/scan/plan")
    def api_scan_plan(body: dict = Body(default={})):
        from ...cache import Cache
        from ...pipeline import plan
        from ...scanner import find_platform_dirs, scan
        c = Cache(cfg.cache)
        try:
            targets = find_platform_dirs(cfg)
            plats = [p for p in (body.get("platforms") or []) if p in P.PLATFORMS]
            if plats:
                targets = [t for t in targets if t[0].id in plats]
            games = scan(cfg, c, targets)
            for g in games:
                g.needs_hash = False
            mode = body.get("mode") or "new"
            return {"plan": plan(cfg, c, games, cfg.sources, refresh=mode == "all", retry_missing=mode == "missing"),
                    "games": len(games)}
        finally:
            c.close()

    def _scheduler():
        """Scraping automatico all'ora scelta (se l'app e' aperta), una volta al giorno, entro i limiti."""
        import datetime as _dt
        while True:
            time.sleep(60)
            try:
                sch = cfg.app.get("schedule") or {}
                if not sch.get("enabled"):
                    continue
                now = _dt.datetime.now()
                today = now.strftime("%Y-%m-%d")
                hh, mm = (int(x) for x in str(sch.get("time", "03:00")).split(":")[:2])
                if now.hour * 60 + now.minute < hh * 60 + mm or cfg.app.get("schedule_last") == today:
                    continue
                if job["current"].status == "running" or state["building"] or job["stores"].status == "running":
                    continue
                C.save_settings(cfg, app={"schedule_last": today})
                api_scan_start({"mode": sch.get("mode", "missing")})
            except Exception as e:
                print(f"Pianificazione: {e}")

    threading.Thread(target=_scheduler, daemon=True).start()

    # ------------------------------------------------------------ manutenzione notturna (pozzo/maintenance.py)
    maint_lock = threading.Lock()  # una sola manutenzione alla volta: pulsante e pianificazione

    def _maint_busy() -> bool:
        """Gioco, download o scraping in corso: la manutenzione aspetta."""
        launcher = getattr(ctx, "launcher", None)
        if launcher is not None and launcher.running().get("status") in ("starting", "extracting", "running"):
            return True
        dl = getattr(ctx, "downloads", None)  # il gestore dei download nasce piu' avanti in ORDER
        if dl is not None and any(t.get("status") == "running" for t in dl.list()):
            return True
        return (job["current"].status == "running" or bool(state["building"])
                or job["store_refresh"].status == "running")

    def _maint_locked_run():
        """Chiamare solo con maint_lock acquisito: lo rilascia alla fine."""
        try:
            if not maintenance_execute(cfg, job, state, lib, ctx._claim):
                print("Manutenzione: scraping o aggiornamento store in corso, saltata")
        except Exception as e:
            print(f"Manutenzione: {e}")
        finally:
            maint_lock.release()

    def _maint_scheduler():
        """Come lo scraping pianificato, ma se c'e' un gioco o un download in corso riprova nei minuti dopo, per 2 ore."""
        import datetime as _dt
        blocked = None  # da quando la manutenzione e' dovuta ma bloccata
        while True:
            time.sleep(60)
            try:
                now = _dt.datetime.now()
                st = _maint_settings(cfg.app.get("maintenance"))
                if not maintenance_due(now, st, cfg.app.get("maintenance_last", "")):
                    blocked = None
                    continue
                if maint_lock.locked() or _maint_busy():
                    blocked = blocked or now
                    if now - blocked >= _dt.timedelta(hours=2):  # troppo tardi: salta il giorno
                        C.save_settings(cfg, app={"maintenance_last": now.strftime("%Y-%m-%d")})
                        blocked = None
                    continue
                blocked = None
                C.save_settings(cfg, app={"maintenance_last": now.strftime("%Y-%m-%d")})
                if maint_lock.acquire(blocking=False):
                    _maint_locked_run()  # gia' in un thread di sfondo: resta qui
            except Exception as e:
                print(f"Manutenzione pianificata: {e}")

    threading.Thread(target=_maint_scheduler, daemon=True).start()

    @router.get("/api/maintenance")
    def api_maintenance_get():
        from ... import maintenance as M
        return {"settings": _maint_settings(cfg.app.get("maintenance")), "latest": M.latest(cfg),
                "running": maint_lock.locked()}

    @router.post("/api/maintenance/settings")
    def api_maintenance_settings(body: dict = Body(...)):
        clean = _maint_settings({**_maint_settings(cfg.app.get("maintenance")), **body}, strict=True)
        C.save_settings(cfg, app={"maintenance": clean})
        cfg.app["maintenance"] = clean
        return {"settings": clean}

    @router.post("/api/maintenance/run")
    def api_maintenance_run():
        if job["current"].status == "running" or state["building"] or job["store_refresh"].status == "running":
            raise HTTPException(409, I.tr("s.scan.scrapeBusyRetry"))
        if not maint_lock.acquire(blocking=False):
            raise HTTPException(409, I.tr("s.scan.maintBusy"))
        threading.Thread(target=_maint_locked_run, daemon=True).start()
        return {"ok": True}

    @router.get("/api/maintenance/history")
    def api_maintenance_history():
        from ... import maintenance as M
        return {"history": M.history(cfg)}

    @router.post("/api/platforms/custom")
    def api_custom_platform(body: dict = Body(...)):
        import re as _re
        name = (body.get("name") or "").strip()
        pid = _re.sub(r"[^a-z0-9_-]", "", (body.get("id") or name).lower().replace(" ", "-"))
        if not name or not pid:
            raise HTTPException(400, I.tr("s.scan.nameIdRequired"))
        if pid in P.PLATFORMS and not P.PLATFORMS[pid].extra.get("custom"):
            raise HTTPException(409, I.tr("s.scan.platformExists", pid=pid))
        exts = " ".join(e.lower().lstrip(".") for e in str(body.get("exts", "")).replace(",", " ").split())
        if not exts:
            raise HTTPException(400, I.tr("s.scan.extRequired"))
        item = {"id": pid, "name": name, "exts": exts, "aliases": [a.strip() for a in body.get("aliases", []) if a.strip()],
                "cd": bool(body.get("cd")), "dir_games": bool(body.get("dir_games")),
                "igdb": str(body.get("igdb") or ""), "ss": str(body.get("ss") or "")}
        items = [x for x in C.read_settings(cfg).get("custom_platforms", []) if x.get("id") != pid] + [item]
        C.set_setting(cfg, "custom_platforms", items)
        return {"ok": True, "id": pid}

    @router.delete("/api/platforms/custom/{pid}")
    def api_custom_platform_delete(pid: str):
        items = [x for x in C.read_settings(cfg).get("custom_platforms", []) if x.get("id") != pid]
        C.set_setting(cfg, "custom_platforms", items)
        P.unregister_custom(pid)
        return {"ok": True}

    # ------------------------------------------------------------ scraping dall'app
    @router.get("/api/platforms")
    def api_platforms():
        return [{"id": p.id, "name": p.name, "custom": bool(p.extra.get("custom")), "exts": " ".join(p.exts),
                 "aliases": list(p.aliases)} for p in sorted(P.PLATFORMS.values(), key=lambda x: x.name.lower()) if not p.virtual]

    @router.get("/api/scan/preview")
    def api_scan_preview():
        with lib.lock:
            files = {f for g in lib.games for f in g["files"]}
            incomplete: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            for g in lib.games:
                if not g["is_primary"]:
                    continue
                if not g["found"]:
                    incomplete[g["platform"]][0] += 1
                elif _missing(g):
                    incomplete[g["platform"]][1] += 1
        try:
            return J.preview(cfg, files, {k: tuple(v) for k, v in incomplete.items()})
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))

    def _relink_busy():
        if state["building"] or job["current"].status == "running":
            raise HTTPException(409, I.tr("s.scan.scrapeUpdateBusy"))

    @router.get("/api/relink/plan")
    def api_relink_plan():
        """Giochi i cui file non esistono piu' e cartelle nuove che sembrano la stessa cosa rinominata."""
        _relink_busy()
        pairs = RL.plan(cfg, log=lambda m: None)
        return {"pairs": [{"old": o, "new": n, "title": t, "path": p} for o, n, t, p in pairs]}

    @router.post("/api/relink/apply")
    def api_relink_apply(body: dict = Body(...)):
        _relink_busy()
        want = set(body.get("new") or [])
        # l'abbinamento si ricalcola qui: il client sceglie solo quali applicare, non le chiavi da spostare
        pairs = [x for x in RL.plan(cfg, log=lambda m: None) if x[1] in want]
        if not pairs:
            raise HTTPException(404, I.tr("s.scan.relinkNone"))
        RL.apply(cfg, pairs, log=lambda m: None)
        threading.Thread(target=_rebuild, daemon=True).start()
        return {"applied": len(pairs)}

    @router.post("/api/folders")
    def api_folders(body: dict = Body(...)):
        folder, pid = (body.get("folder") or "").strip(), (body.get("platform") or "").strip()
        if not folder or (pid and pid not in P.PLATFORMS):
            raise HTTPException(400, I.tr("s.scan.dataInvalid"))
        C.save_settings(cfg, platform_folders={folder: pid or None})
        return api_scan_preview()

    @router.post("/api/folders/add")
    def api_folders_add(body: dict = Body(...)):
        """Aggiunge la cartella dei giochi di una console e cerca solo i dati dei giochi nuovi.
        Per il PC ogni sottocartella con un .exe diventa un gioco aggiunto a mano."""
        pid = (body.get("platform") or "").strip()
        p = Path(os.path.expandvars(os.path.expanduser(str(body.get("path") or "").strip().strip('"'))))
        if pid not in P.PLATFORMS or not p.is_dir():
            raise HTTPException(400, I.tr("s.scan.consoleFolderInvalid"))
        if pid == "windows":
            skip = re.compile(r"unins|setup|redist|crash|install|dxsetup|vcredist|launcher_helper", re.I)
            added = 0
            for sub in sorted(x for x in p.iterdir() if x.is_dir()):
                exes = [f for f in sub.glob("*.exe") if not skip.search(f.name)]
                if exes:
                    exe = max(exes, key=lambda f: f.stat().st_size)
                    before = len(user.manual_games())
                    user.add_manual(sub.name, str(exe), [], str(sub))
                    added += len(user.manual_games()) - before
            if added:
                _refresh_manual()
            return {"added": added}
        p = p.resolve()
        shared = [str(x) for x in cfg.extra_roms]
        own = [str(x) for x in PC.get(cfg, "roms_extra", [])]  # la cartella e' PROPRIA del profilo attivo
        if p != Path(cfg.roms).resolve() and str(p) not in shared and str(p) not in own:
            PC.set(cfg, "roms_extra", [*own, str(p)])
        C.save_settings(cfg, platform_folders={str(p): pid})
        return api_scan_start({"platforms": [pid]})

    @router.post("/api/scan")
    def api_scan_start(body: dict = Body(default={})):
        cur = job["current"]
        if cur.status == "running" or state["building"]:
            raise HTTPException(409, I.tr("s.scan.scrapeUpdateBusy"))
        plats = [p for p in (body.get("platforms") or []) if p in P.PLATFORMS] or None
        mode = body.get("mode") or ("all" if body.get("refresh") else "new")
        keys, title = None, ""
        if body.get("game"):  # pulsante "Cerca dati mancanti" nel dettaglio: tutte le versioni del gioco
            g = lib.get(int(body["game"]))
            keys = [m["key"] for m in lib.groups[g["grp"]]]
            plats, title, mode = [g["platform"]], g["title"], body.get("mode") or "missing"
        j = J.ScrapeJob(platforms=plats, refresh=mode == "all", retry_missing=mode == "missing", keys=keys, title=title)
        job["current"] = j

        def after(stats):
            state["build_stats"] = stats
            lib.load()
            events.emit("scrape_finished", stats)
            events.emit("library_built", stats)
            threading.Thread(target=_pregen_thumbs, daemon=True).start()

        def found(stats):  # file trovati: subito in libreria, senza attendere i metadati
            lib.load()
            events.emit("library_built", stats)

        threading.Thread(target=j.run, args=(cfg, after, found), daemon=True).start()
        return j.state()

    @router.get("/api/scan")
    def api_scan_state():
        return job["current"].state()

    @router.post("/api/scan/cancel")
    def api_scan_cancel():
        job["current"].cancel()
        return job["current"].state()

    vars(ctx).update(api_scan_start=api_scan_start, bulk_job=bulk_job)
    return router
