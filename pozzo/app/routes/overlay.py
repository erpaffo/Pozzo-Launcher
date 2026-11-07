"""Overlay in gioco: pagine, stato e impostazioni (la finestra e' in pozzo/overlay.py)."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import HTMLResponse

from ... import config as C, i18n as I
from ... import overlay as OV
from ..server import STATIC, _asset_version


def build_router(ctx) -> APIRouter:
    cfg, launcher, lib, ov = ctx.cfg, ctx.launcher, ctx.lib, ctx.overlay
    router = APIRouter()

    def _page(name: str) -> HTMLResponse:
        html = (STATIC / name).read_text(encoding="utf-8").replace("{{v}}", _asset_version())
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @router.get("/overlay")
    def overlay_page():
        return _page("overlay.html")

    @router.get("/overlay/toast")
    def overlay_toast_page():
        return _page("overlay-toast.html")

    @router.get("/api/overlay/state")
    def api_overlay_state():
        run = launcher.running()
        g = lib.by_key.get(run.get("key") or "")
        return {"running": run.get("status") == "running", "paused": bool(run.get("paused")), "gid": g["id"] if g else None,
                "title": (g or {}).get("title") or run.get("title") or "", "started": run.get("started"),
                "settings": OV.settings(cfg)}

    @router.post("/api/overlay/toggle")
    def api_overlay_toggle():
        return {"ok": ov.toggle()}

    @router.post("/api/overlay/hide")
    def api_overlay_hide():
        return {"ok": ov.hide()}

    @router.post("/api/overlay/settings")
    def api_overlay_settings(body: dict = Body(...)):
        try:
            cur = OV.clean(body, OV.settings(cfg))
        except ValueError:
            raise HTTPException(400, I.tr("s.shots.hotkeyInvalid"))
        C.save_settings(cfg, app={"overlay": cur})
        cfg.app["overlay"] = cur
        return {"settings": cur}

    return router
