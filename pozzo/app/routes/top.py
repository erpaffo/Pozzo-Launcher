"""Durate HowLongToBeat in blocco e classifiche dei giochi migliori."""

from __future__ import annotations

import threading

from fastapi import APIRouter, Body, HTTPException

from ... import i18n as I
from .. import jobs as J


def build_router(ctx) -> APIRouter:
    _claim, cfg, events, job, lib = ctx._claim, ctx.cfg, ctx.events, ctx.job, ctx.lib
    router = APIRouter()

    # ------------------------------------------------------------ HowLongToBeat
    @router.post("/api/hltb")
    def api_hltb_start(body: dict = Body(default={})):
        j = J.HltbJob(only_missing=body.get("mode", "missing") != "all")
        if not _claim("hltb", j):
            raise HTTPException(409, I.tr("s.top.hltbBusy"))

        def after(stats):
            lib.load()
            events.emit("library_built", stats)

        threading.Thread(target=j.run, args=(cfg, after), daemon=True).start()
        return j.state()

    @router.get("/api/hltb")
    def api_hltb_state():
        from ...cache import Cache
        st = job["hltb"].state()
        c = Cache(cfg.cache)
        try:
            st["known"] = c.db.execute("SELECT COUNT(*) FROM kv WHERE k LIKE 'hltb:%'").fetchone()[0]
        finally:
            c.close()
        st["with_hltb"] = sum(1 for g in lib.games if g.get("hltb") and g.get("is_primary"))
        return st

    @router.post("/api/hltb/cancel")
    def api_hltb_cancel():
        job["hltb"].stop = True
        return job["hltb"].state()

    # ------------------------------------------------------------ migliori giochi (Top 100 per console, globale 100/1000)
    @router.get("/api/top")
    def api_top(pid: str = "all", limit: int = 100):
        from ... import topgames
        limit = max(1, min(limit, topgames.GLOBAL))
        with lib.lock:
            games = list(lib.games)
        items = topgames.global_(games, limit) if pid == "all" else topgames.local(games, pid, min(limit, topgames.LOCAL))
        return {"pid": pid, "items": items, "job": job["top"].state()}

    @router.post("/api/top/fetch")
    def api_top_fetch(body: dict = Body(default={})):
        pid = body.get("pid") or "all"
        j = J.TopGamesJob(pids=[] if pid == "all" else [pid])
        if not _claim("top", j):
            raise HTTPException(409, I.tr("s.top.topBusy"))

        def after(stats):
            lib.load()
            events.emit("library_built", stats)

        threading.Thread(target=j.run, args=(cfg, after), daemon=True).start()
        return j.state()

    @router.get("/api/top/state")
    def api_top_state():
        return job["top"].state()

    @router.post("/api/top/cancel")
    def api_top_cancel():
        job["top"].stop = True
        return job["top"].state()

    return router
