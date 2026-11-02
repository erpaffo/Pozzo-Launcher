"""Configurazione guidata del primo avvio e cartelle delle ROM."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from .. import jobs as J
from ... import config as C, ownership as OW, profilecfg as PC, stores as STORES
from ...library.build import build
from ..server import _plain


def build_router(ctx) -> APIRouter:
    _pregen_thumbs, api_scan_start, cfg, job, lib, state = ctx._pregen_thumbs, ctx.api_scan_start, ctx.cfg, ctx.job, ctx.lib, ctx.state
    router = APIRouter()

    # ------------------------------------------------------------ configurazione guidata (primo avvio)
    setup_state: dict = {"status": "idle", "phase": "", "log": []}

    def _setup_done() -> bool:
        return bool(cfg.app.get("setup_done")) or lib.built_at > 0

    def _setup_stores() -> list[dict]:
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            out = []
            for P_ in STORES.PROVIDERS:
                if P_.id in ("manual", "ports"):  # giochi aggiunti a mano e port PC non sono uno store da importare
                    continue
                try:
                    det = P_(cfg, c, None, lambda *a: None).detected()
                except Exception:
                    det = False
                out.append({"id": P_.id, "name": P_.name, "detected": det, "enabled": STORES.enabled(cfg, P_.id),
                            "login": P_.login})
            return out
        finally:
            c.close()

    @router.get("/api/setup")
    def api_setup():
        roms = Path(cfg.roms)
        return {"done": _setup_done(), "has_library": bool(lib.games) or lib.built_at > 0,
                "roms": str(roms) if roms.is_dir() else "", "data_dir": str(C.settings_path(cfg).parent),
                "accounts": {"ss_user": cfg.ss.get("user") or "", "ss_password": bool(cfg.ss.get("password")),
                             "igdb_id": cfg.igdb.get("client_id") or "", "igdb_secret": bool(cfg.igdb.get("client_secret")),
                             "rawg": bool(cfg.rawg.get("api_key")), "tgdb": bool(cfg.tgdb.get("api_key"))},
                "stores": _setup_stores(), "state": setup_state}

    @router.post("/api/setup/check-roms")
    def api_setup_check(body: dict = Body(...)):
        """Console trovate in una cartella, senza salvarla."""
        from dataclasses import replace as _replace

        from ...scanner import find_platform_dirs
        p = Path(os.path.expandvars(os.path.expanduser(str(body.get("path") or "").strip().strip('"'))))
        if not str(body.get("path") or "").strip() or not p.is_dir():
            raise HTTPException(400, "Cartella non trovata")
        found = find_platform_dirs(_replace(cfg, roms=p))
        rows = {}
        for plat, d in found:
            rows.setdefault(plat.id, {"id": plat.id, "name": plat.name, "folders": 0})
            rows[plat.id]["folders"] += 1
        return {"path": str(p.resolve()), "platforms": sorted(rows.values(), key=lambda r: r["name"].lower())}

    @router.post("/api/setup")
    def api_setup_save(body: dict = Body(...)):
        """Salva la configurazione; con start=true importa gli store, crea la libreria e
        (se richiesto) avvia lo scraping dei giochi nuovi in sottofondo."""
        sections: dict = {}
        roms = str(body.get("roms") or "").strip().strip('"')
        if roms:
            p = Path(os.path.expandvars(os.path.expanduser(roms)))
            if not p.is_dir():
                raise HTTPException(400, "Cartella delle ROM non trovata")
            sections["paths"] = {"roms": str(p.resolve())}
        acc = body.get("accounts") or {}
        ss = {k: v.strip() for k, v in (("user", acc.get("ss_user")), ("password", acc.get("ss_password"))) if v and v.strip()}
        if ss:
            sections["screenscraper"] = ss
        ig = {k: v.strip() for k, v in (("client_id", acc.get("igdb_id")), ("client_secret", acc.get("igdb_secret")))
              if v and v.strip()}
        if ig:
            sections["igdb"] = ig
        if (acc.get("rawg") or "").strip():
            sections["rawg"] = {"api_key": acc["rawg"].strip()}
        if (acc.get("tgdb") or "").strip():
            sections["thegamesdb"] = {"api_key": acc["tgdb"].strip()}
        stores = body.get("stores")
        if isinstance(stores, dict):
            sections["stores"] = {sid: {**dict(cfg.stores.get(sid, {})), "enabled": bool(on)}
                                  for sid, on in stores.items() if sid in STORES.BY_ID}
        sections["app"] = {"setup_done": True}
        C.save_settings(cfg, **sections)
        if body.get("start"):
            if setup_state["status"] == "running":
                raise HTTPException(409, "Configurazione gia' in corso")
            threading.Thread(target=_setup_run, args=(bool(body.get("scrape", True)),), daemon=True).start()
        return api_setup()

    def _setup_run(scrape: bool):
        say = lambda m: setup_state["log"].append(_plain(str(m)))  # noqa: E731
        setup_state.update(status="running", log=[], phase="Preparazione")
        try:
            sel = [s["id"] for s in _setup_stores() if s["enabled"] and s["detected"]]
            if sel:
                setup_state["phase"] = "Importazione dei giochi degli store"
                sj = J.StoreJob(only=sel)
                job["stores"] = sj
                sj.say = lambda m, _j=sj: (_j.log.append(_plain(m)), say(m))
                sj.run(cfg, lambda stats: lib.load())
            if not lib.built_at or not sel:
                setup_state["phase"] = "Creazione della libreria"
                state["build_log"] = []
                build(cfg, log=say)
                lib.load()
            threading.Thread(target=_pregen_thumbs, daemon=True).start()
            if scrape and Path(cfg.roms).is_dir():
                setup_state["phase"] = "Scraping dei metadati avviato in sottofondo"
                try:
                    api_scan_start({"mode": "new"})
                except HTTPException as e:
                    say(e.detail)
            setup_state.update(status="done", phase="Pronto")
        except Exception as e:
            setup_state.update(status="error", phase=f"Errore: {type(e).__name__}: {e}")
            say(setup_state["phase"])

    @router.post("/api/roms/extra")
    def api_roms_extra(body: dict = Body(...)):
        """Aggiunge (action=add) o toglie (action=remove) una cartella ROM aggiuntiva (es. un altro disco).
        Una cartella aggiunta qui e' PROPRIA del profilo attivo (la vede solo lui); quelle globali, aggiunte prima dei
        profili, restano di tutti e si tolgono come prima."""
        raw = str(body.get("path") or "").strip().strip('"')
        p = Path(os.path.expandvars(os.path.expanduser(raw)))
        shared = [str(x) for x in cfg.extra_roms]
        own = [str(x) for x in PC.get(cfg, "roms_extra", [])]
        if body.get("action") == "remove":
            if raw in own:
                PC.set(cfg, "roms_extra", [x for x in own if x != raw] or None)
            else:
                C.save_settings(cfg, paths={"extra_roms": [x for x in shared if x != raw]})
        else:
            if not raw or not p.is_dir():
                raise HTTPException(400, "Cartella non trovata")
            p = p.resolve()
            # confronto tra percorsi risolti: la stessa cartella puo' essere salvata in forma diversa (link, nome corto)
            if p == Path(cfg.roms).resolve() or any(Path(x).resolve() == p for x in [*shared, *own]):
                raise HTTPException(400, "Cartella gia' presente")
            PC.set(cfg, "roms_extra", [*own, str(p)])
        return {"extra": [{"path": str(r), "online": r.exists(), "own": mine} for r, mine in OW.visible_roots(cfg)]}

    @router.post("/api/roms")
    def api_roms(body: dict = Body(...)):
        """Cartella radice delle ROM scelta dall'app (salvata in settings.json)."""
        p = Path(os.path.expandvars(os.path.expanduser(str(body.get("path") or "").strip().strip('"'))))
        if not str(p) or not p.is_dir():
            raise HTTPException(400, "Cartella non trovata")
        C.save_settings(cfg, paths={"roms": str(p.resolve())})
        return {"root": str(cfg.roms)}

    vars(ctx).update(_setup_done=_setup_done)
    return router
