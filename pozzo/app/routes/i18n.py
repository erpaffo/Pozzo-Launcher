"""Traduzioni dell'interfaccia."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ... import i18n as I


def build_router(ctx) -> APIRouter:
    router = APIRouter()

    @router.get("/api/i18n")
    def api_i18n_list():
        return {"languages": I.languages(), "rtl": sorted(I.RTL)}

    @router.get("/api/i18n/{lang}")
    def api_i18n(lang: str):
        if lang not in I.languages():
            raise HTTPException(404, "Lingua non disponibile")
        return {"lang": lang, "dir": "rtl" if lang in I.RTL else "ltr", "strings": I.catalog(lang)}

    return router
