"""Riduci spazio su disco: compressione WOF della cartella di un gioco PC installato (solo Windows)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import i18n as I
from ...cache import Cache
from ...library import wof as W
from ...library.sizes import dir_size


def build_router(ctx) -> APIRouter:
    cfg, lib = ctx.cfg, ctx.lib
    router = APIRouter()
    jobs: dict[int, W.Job] = {}  # un lavoro per gioco; l'ultimo resta consultabile finche' non ne parte un altro

    def folder_of(gid: int) -> Path:
        g = lib.get(gid)
        d = Path(g["install_dir"]) if g.get("install_dir") and g.get("store") not in (None, "online", "manual") else None
        if not W.supported() or not d or not d.is_dir():
            raise HTTPException(400, I.tr("s.wof.unavailable"))
        return d

    @router.get("/api/game/{gid}/wof")
    def api_wof(gid: int):
        d = folder_of(gid)
        size, est = dir_size(d), None
        c = Cache(cfg.cache)
        try:
            est = W.estimate(lib.get(gid)["title"], size, W.load_index(c))
        except Exception:  # offline o database illeggibile: resta la sola misura
            pass
        finally:
            c.close()
        j = jobs.get(gid)
        return {"folder": str(d), "size": size, "dstorage": W.has_dstorage(d), "estimate": est,
                "algos": W.ALGOS, "default": W.DEFAULT_ALGO, "job": j.state() if j else None}

    @router.post("/api/game/{gid}/wof")
    def api_wof_start(gid: int, body: dict = Body(default={})):
        d = folder_of(gid)
        if jobs.get(gid) and jobs[gid].status == "running":
            raise HTTPException(409, I.tr("s.wof.busy"))
        undo = body.get("action") == "uncompress"
        algo = body.get("algo") or W.DEFAULT_ALGO
        if not undo and algo not in W.ALGOS:
            raise HTTPException(400, I.tr("s.wof.badAlgo"))
        if not undo and W.has_dstorage(d) and not body.get("confirm_dstorage"):
            raise HTTPException(409, I.tr("s.wof.dstorage"))
        jobs[gid] = W.Job(d, algo, undo)
        return jobs[gid].state()

    @router.get("/api/game/{gid}/wof/job")
    def api_wof_job(gid: int):
        j = jobs.get(gid)
        return j.state() if j else {"status": "idle", "done": 0, "total": 0, "error": ""}

    @router.delete("/api/game/{gid}/wof")
    def api_wof_cancel(gid: int):
        if gid in jobs:
            jobs[gid].cancel()
        return {"ok": True}

    return router
