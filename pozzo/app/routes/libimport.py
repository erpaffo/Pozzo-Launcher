"""Importa la libreria da altri launcher (Playnite, LaunchBox, Lutris, Heroic, Pegasus): vedi pozzo/importers."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from ... import i18n as I, importers as IMP
from ...importers.formats import PARSERS

ERR = {"path": "s.libimport.path", "notfile": "s.libimport.notfile", "ext": "s.libimport.ext",
       "toobig": "s.libimport.toobig", "json": "s.libimport.json", "xml": "s.libimport.xml",
       "sqlite": "s.libimport.sqlite", "format": "s.libimport.format", "notdir": "s.libimport.notdir"}


def build_router(ctx) -> APIRouter:
    lib, user = ctx.lib, ctx.user
    router = APIRouter()

    @router.post("/api/import/{fmt}")
    def api_import(fmt: str, body: dict = Body(...)):
        if fmt not in PARSERS:
            raise HTTPException(404, I.tr("s.libimport.fmtUnknown"))
        try:
            out = IMP.apply(user, lib, PARSERS[fmt](body.get("path")))
            if out.get("scripts_ignored"):  # gli script della fonte non vengono importati: lo si dice
                out["scripts_warning"] = I.tr("s.libimport.scriptsIgnored", n=out["scripts_ignored"])
            return out
        except IMP.ImportError_ as e:
            raise HTTPException(400, I.tr(ERR[str(e)]) if str(e) in ERR else str(e))
        except OSError as e:
            raise HTTPException(400, f"{type(e).__name__}: {e}")

    return router
