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


def build_router(ctx) -> APIRouter:
    _missing, _pregen_thumbs, _rebuild, _refresh_manual, cfg, events = ctx._missing, ctx._pregen_thumbs, ctx._rebuild, ctx._refresh_manual, ctx.cfg, ctx.events
    job, lib, state, user = ctx.job, ctx.lib, ctx.state, ctx.user
    router = APIRouter()

    # ------------------------------------------------------------ fonti, limiti, database locali, pianificazione
    SOURCE_INFO = {
        "libretro": ("offline", "Identificazione per CRC/nome (No-Intro, Redump), franchise, immagini libretro"),
        "launchbox": ("offline", "Valutazioni della community, descrizioni, generi, ESRB, video, immagini e loghi"),
        "tgdb": ("offline", "Copia completa di TheGamesDB: descrizioni, giocatori, copertine (nessuna quota)"),
        "arcadedb": ("online", "Solo arcade (MAME): dati, immagini, video"),
        "igdb": ("online", "Descrizioni, valutazioni utenti e critica, franchise, copertine"),
        "screenscraper": ("online", "Ricerca per checksum, descrizioni in italiano, wheel, video (quota del tuo account)"),
        "rawg": ("online", "Valutazioni utenti e voto Metacritic (chiave gratuita, 20.000 richieste/mese)"),
        "thegamesdb": ("online", "API di TheGamesDB (quota mensile molto bassa: meglio la copia completa)"),
        "wikipedia": ("online", "Descrizioni, sviluppatori, editori, generi e anno da Wikipedia (italiano, poi inglese): "
                                "gratuita, senza chiave, solo per i dati ancora mancanti"),
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
                        raise HTTPException(400, f"{sid}: il ritmo deve essere maggiore di zero")
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
            raise HTTPException(409, "Aggiornamento gia' in corso")

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
                bulk_job["log"].append(f"Errore: {e}")
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

    @router.post("/api/platforms/custom")
    def api_custom_platform(body: dict = Body(...)):
        import re as _re
        name = (body.get("name") or "").strip()
        pid = _re.sub(r"[^a-z0-9_-]", "", (body.get("id") or name).lower().replace(" ", "-"))
        if not name or not pid:
            raise HTTPException(400, "Servono nome e identificativo")
        if pid in P.PLATFORMS and not P.PLATFORMS[pid].extra.get("custom"):
            raise HTTPException(409, f"«{pid}» esiste gia' tra le console incluse")
        exts = " ".join(e.lower().lstrip(".") for e in str(body.get("exts", "")).replace(",", " ").split())
        if not exts:
            raise HTTPException(400, "Indica almeno un'estensione dei file (es. iso chd)")
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
            raise HTTPException(409, "Uno scraping o un aggiornamento e' gia' in corso")

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
            raise HTTPException(404, "Nessun abbinamento da applicare (le cartelle sono cambiate?)")
        RL.apply(cfg, pairs, log=lambda m: None)
        threading.Thread(target=_rebuild, daemon=True).start()
        return {"applied": len(pairs)}

    @router.post("/api/folders")
    def api_folders(body: dict = Body(...)):
        folder, pid = (body.get("folder") or "").strip(), (body.get("platform") or "").strip()
        if not folder or (pid and pid not in P.PLATFORMS):
            raise HTTPException(400, "dati non validi")
        C.save_settings(cfg, platform_folders={folder: pid or None})
        return api_scan_preview()

    @router.post("/api/folders/add")
    def api_folders_add(body: dict = Body(...)):
        """Aggiunge la cartella dei giochi di una console e cerca solo i dati dei giochi nuovi.
        Per il PC ogni sottocartella con un .exe diventa un gioco aggiunto a mano."""
        pid = (body.get("platform") or "").strip()
        p = Path(os.path.expandvars(os.path.expanduser(str(body.get("path") or "").strip().strip('"'))))
        if pid not in P.PLATFORMS or not p.is_dir():
            raise HTTPException(400, "Console o cartella non valida")
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
            raise HTTPException(409, "Uno scraping o un aggiornamento e' gia' in corso")
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
