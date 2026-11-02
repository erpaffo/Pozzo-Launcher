"""Verifica dei dump: stato della ROM rispetto ai DAT No-Intro/Redump, calcolato alla costruzione della libreria."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException


def build_router(ctx) -> APIRouter:
    lib = ctx.lib
    router = APIRouter()

    @router.get("/api/game/{gid}/verify")
    def api_game_verify(gid: int):
        g = lib.by_id.get(gid)
        if not g:
            raise HTTPException(404, "Gioco non trovato")
        return {"status": g.get("verify") or "", "match_by": g.get("match_by") or ""}

    @router.get("/api/verify/report")
    def api_verify_report(console: str = ""):
        """Conteggi per stato e ROM non verificate (possibili hack, traduzioni o dump danneggiati)."""
        roms = [g for g in lib.games if not g.get("store") and (not console or g["platform"] == console)]
        counts = Counter(g.get("verify") or "non controllata" for g in roms)
        bad = [{"id": g["id"], "title": g["title"], "platform": g["platform"], "status": g.get("verify") or "",
                "match_by": g.get("match_by") or "", "file": (g["files"] or [""])[0]}
               for g in roms if g.get("verify") == "sconosciuta"]
        return {"total": len(roms), "counts": dict(counts), "unverified": bad}

    return router
