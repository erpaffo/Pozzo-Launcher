"""Gioca nel browser (EmulatorJS e Ruffle): pagina, ROM, BIOS, file dell'emulatore e salvataggi."""

from __future__ import annotations

import json
import mimetypes

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from ... import i18n as I, webplay as W
from ..server import STATIC
from .images import file_response

MIME = {".js": "text/javascript", ".css": "text/css", ".wasm": "application/wasm", ".json": "application/json",
        ".data": "application/octet-stream"}
STRINGS = ("preparing", "downloading", "error", "noBios")


def build_router(ctx) -> APIRouter:
    cfg, lib, user = ctx.cfg, ctx.lib, ctx.user
    router = APIRouter()

    def _game(gid: int) -> tuple[dict, dict]:
        """(gioco, piano) dalla libreria: 404 se non c'e', 403 se non si gioca nel browser. Mai un percorso dalla richiesta."""
        g = lib.get(gid)
        pl = W.plan(g)
        if not pl:
            raise HTTPException(403, "Questo gioco non si puo' avviare nel browser")
        return g, pl

    @router.get("/api/webplay/platforms")
    def api_platforms():
        """Console che si giocano nel browser (menu del gioco); i .swf si riconoscono dalla scheda (webplay)."""
        return {"platforms": sorted(W.CORES)}

    @router.get("/play/{gid}")
    def play_page(gid: int):
        g, pl = _game(gid)
        rom = W.rom_file(g)
        cfgjs = {"gid": gid, "title": g["title"], "name": rom.name, **pl,
                 "bios": f"/api/play/{gid}/bios/{b.name}" if (b := W.bios_file(g["platform"])) else "",
                 "needBios": g["platform"] == "psx",
                 "t": {k: I.tr("w.play." + k) for k in STRINGS}}
        html = (STATIC / "play.html").read_text(encoding="utf-8").replace(
            "__PLAY__", json.dumps(cfgjs).replace("</", "<\\/")).replace("__TITLE__", g["title"].replace("<", "&lt;"))
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @router.get("/api/play/{gid}/status")
    def play_status(gid: int):
        return W.status(cfg, _game(gid)[1])

    @router.post("/api/play/{gid}/prepare")
    def play_prepare(gid: int):
        return W.prepare(cfg, _game(gid)[1])

    @router.get("/api/play/{gid}/rom/{name}")
    def play_rom(gid: int, name: str):  # name serve solo al browser (estensione): il file lo sceglie la libreria
        rom = W.rom_file(_game(gid)[0])
        if not rom or not rom.is_file():
            raise HTTPException(404, "File del gioco non trovato")
        return file_response(rom)

    @router.get("/api/play/{gid}/bios/{name}")
    def play_bios(gid: int, name: str):
        b = W.bios_file(_game(gid)[0]["platform"])
        if not b:
            raise HTTPException(404, "BIOS non trovato")
        return file_response(b)

    @router.get("/play-assets/{rel:path}")
    def play_assets(rel: str):
        p = W.asset(cfg, rel)
        if not p:
            raise HTTPException(404)
        return file_response(p, media_type=MIME.get(p.suffix) or mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                             headers={"Cache-Control": "public, max-age=86400"})

    def _kind(kind: str) -> str:
        if kind not in ("sram", "state"):
            raise HTTPException(400, "Tipo di salvataggio non valido")
        return kind

    @router.get("/api/play/{gid}/save")
    def save_get(gid: int, kind: str = "sram"):
        data = user.web_save(_game(gid)[0]["key"], _kind(kind))
        if data is None:
            raise HTTPException(404, "Nessun salvataggio")
        return Response(data, media_type="application/octet-stream", headers={"Cache-Control": "no-store"})

    @router.post("/api/play/{gid}/save")
    async def save_put(gid: int, request: Request, kind: str = "sram"):
        g, _ = _game(gid)
        _kind(kind)
        if int(request.headers.get("content-length") or 0) > W.MAX_SAVE:
            raise HTTPException(413, "Salvataggio troppo grande")
        data = await request.body()
        if not data or len(data) > W.MAX_SAVE:
            raise HTTPException(400, "Salvataggio vuoto o troppo grande")
        user.set_web_save(g["key"], kind, data)
        return {"ok": True, "size": len(data)}

    return router
