"""Cache delle risposte delle fonti dati: statistiche, svuotamento, pulizia delle righe scadute all'avvio."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import cachepolicy as P
from ... import i18n as I
from ...boot import BOOT
from ...cache import Cache
from ...net import HttpCache
from ...bulk.launchbox import LaunchBoxDB


def build_router(ctx) -> APIRouter:
    cfg = ctx.cfg
    router = APIRouter()
    db_path = lambda: Path(cfg.cache) / "cache.db"  # noqa: E731

    def stats() -> dict:
        h = HttpCache(db_path())
        c = Cache(cfg.cache)
        try:
            out = h.stats()
            for src, prefix in P.KV_SOURCES.items():
                out[src] = c.kv_stats(prefix, P.ttls(src)[0])
            out["launchbox"] = LaunchBoxDB(cfg.cache).cache_stats()  # bulk su file, non righe di cache.db
        finally:
            h.close()
            c.close()
        return out

    @router.get("/api/cache/sources")
    def api_cache_sources():
        return {"sources": stats(), "ttl": {s: {"found": p, "missing": n} for s, (p, n) in P.TTL.items()}}

    @router.post("/api/cache/sources/clear")
    def api_cache_sources_clear(body: dict = Body(default={})):
        src = body.get("source")
        if src is not None and not isinstance(src, str):
            raise HTTPException(400, I.tr("s.cache_sources.source_type"))
        h = HttpCache(db_path())
        c = Cache(cfg.cache)
        try:
            n = h.invalidate(src or None)
            for s, prefix in P.KV_SOURCES.items():
                if not src or src == s:
                    n += c.kv_delete(prefix)
            if not src or src == "launchbox":
                n += LaunchBoxDB(cfg.cache).clear()
        finally:
            h.close()
            c.close()
        return {"removed": n}

    def purge_when_ready():
        """Righe scadute: si tolgono solo a UI pronta, in background, per non rallentare l'avvio."""
        end = time.monotonic() + 600
        while not BOOT.snapshot()["ready"] and time.monotonic() < end:
            time.sleep(2)
        try:
            h = HttpCache(db_path())
            c = Cache(cfg.cache)
            try:
                h.purge_expired()
                for s, prefix in P.KV_SOURCES.items():
                    c.kv_delete(prefix, P.ttls(s)[0])
            finally:
                h.close()
                c.close()
        except Exception:  # pulizia facoltativa: mai un errore all'avvio
            pass

    threading.Thread(target=purge_when_ready, daemon=True, name="cache-purge").start()
    return router
