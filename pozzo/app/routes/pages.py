"""Pagine HTML e icone."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from ..server import STATIC, _asset_version


def build_router(ctx) -> APIRouter:
    cfg, = ctx.cfg,
    router = APIRouter()

    # ------------------------------------------------------------ icone di console e store
    from ..icons import Icons
    icons = Icons(cfg.cache)
    ICON_TYPES = {".svg": "image/svg+xml", ".ico": "image/x-icon", ".png": "image/png", ".jpg": "image/jpeg",
                  ".webp": "image/webp", ".gif": "image/gif"}

    def _icon_response(p):
        if not p:
            raise HTTPException(404)
        # sandbox: un SVG scaricato da un sito puo' contenere script, che qui girerebbero con l'accesso alle API
        return FileResponse(p, media_type=ICON_TYPES.get(p.suffix, "image/png"),
                            headers={"Cache-Control": "public, max-age=86400", "Content-Security-Policy": "sandbox"})

    @router.get("/icons/platform/{pid}")
    def icon_platform(pid: str):
        return _icon_response(icons.platform(pid))

    @router.get("/icons/store/{sid}")
    def icon_store(sid: str):
        return _icon_response(icons.store(sid))

    @router.get("/icons/site")
    def icon_site(url: str):
        if not url.startswith(("http://", "https://")):
            raise HTTPException(400)
        return _icon_response(icons.site(url, badge=("🌐", "#2d5a8c")))

    @router.get("/")
    def index():
        html = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{v}}", _asset_version())
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @router.get("/bigpicture")
    def bigpicture():
        html = (STATIC / "bigpicture.html").read_text(encoding="utf-8").replace("{{v}}", _asset_version())
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    return router
