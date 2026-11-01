"""Stato dell'avvio per la schermata di caricamento (splash): GET /api/boot."""

from __future__ import annotations

from fastapi import APIRouter

from ...boot import BOOT


def build_router(ctx) -> APIRouter:
    router = APIRouter()

    @router.get("/api/boot")
    def api_boot():
        return BOOT.snapshot()

    return router
