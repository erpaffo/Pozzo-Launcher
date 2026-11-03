"""Emulatori gia' installati sul PC (solo proposta: nulla viene salvato)."""

from __future__ import annotations

from fastapi import APIRouter

from ... import emudetect


def build_router(ctx) -> APIRouter:
    router = APIRouter()

    @router.get("/api/emulators/detected")
    def api_emulators_detected():
        cur = ctx.cfg.emulators
        return {"found": emudetect.detect_all(ctx.cfg), "configured": {k: v for k, v in cur.items() if isinstance(v, str)}}

    return router
