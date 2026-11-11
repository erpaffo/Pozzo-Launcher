"""Importa la libreria da altri launcher (Playnite, LaunchBox, Lutris, Heroic, Pegasus, Steam ROM Manager, RetroArch): vedi pozzo/importers."""

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

    def _run(fmt: str, body: dict, fn):
        if fmt not in PARSERS:
            raise HTTPException(404, I.tr("s.libimport.fmtUnknown"))
        try:
            out = fn(PARSERS[fmt](body.get("path")))
            if out.get("scripts_ignored"):  # gli script della fonte non vengono importati: lo si dice
                out["scripts_warning"] = I.tr("s.libimport.scriptsIgnored", n=out["scripts_ignored"])
            return out
        except IMP.ImportError_ as e:
            raise HTTPException(400, I.tr(ERR[str(e)]) if str(e) in ERR else str(e))
        except OSError as e:
            raise HTTPException(400, f"{type(e).__name__}: {e}")

    # dry-run: stessi parser, nessuna scrittura; la UI mostra i conteggi e chiede conferma prima di importare
    @router.post("/api/import/{fmt}/preview")
    def api_import_preview(fmt: str, body: dict = Body(...)):
        return _run(fmt, body, lambda recs: IMP.preview(user, lib, recs))

    @router.post("/api/import/{fmt}")
    def api_import(fmt: str, body: dict = Body(...)):
        return _run(fmt, body, lambda recs: IMP.apply(user, lib, recs))

    return router
