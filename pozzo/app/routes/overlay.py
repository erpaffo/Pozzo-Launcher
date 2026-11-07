"""Overlay in gioco: pagine, stato e impostazioni (la finestra e' in pozzo/overlay.py)."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import HTMLResponse

from ... import config as C, i18n as I
from ... import overlay as OV
from ...emuadapters import retroarch as RA
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

    @router.get("/overlay/hud")
    def overlay_hud_page():
        return _page("overlay-hud.html")

    def _ra(run):
        """RetroArch in esecuzione: (exe, comandi di rete attivi), altrimenti None. Gli altri emulatori non hanno comandi (v1)."""
        if run.get("status") != "running" or run.get("emulator_id") != RA.NAME or not run.get("exe"):
            return None
        return run["exe"], RA.net_ready(run["exe"])

    @router.get("/api/overlay/state")
    def api_overlay_state():
        run = launcher.running()
        g = lib.by_key.get(run.get("key") or "")
        ra = _ra(run)
        return {"running": run.get("status") == "running", "paused": bool(run.get("paused")), "gid": g["id"] if g else None,
                "title": (g or {}).get("title") or run.get("title") or "", "started": run.get("started"),
                "emu": {"id": RA.NAME, "ready": ra[1]} if ra else None, "settings": OV.settings(cfg)}

    @router.get("/api/overlay/stats")
    def api_overlay_stats():
        import psutil
        b = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None  # None su un PC fisso
        return {"started": launcher.running().get("started"),  # l'HUD fa una richiesta sola ogni 2 s
                "cpu": round(psutil.cpu_percent(interval=None)), "ram": round(psutil.virtual_memory().percent),
                "battery": {"percent": round(b.percent), "plugged": bool(b.power_plugged)} if b else None}

    @router.post("/api/overlay/emu")
    def api_overlay_emu(body: dict = Body(...)):
        ra = _ra(launcher.running())
        if not ra:
            raise HTTPException(409, I.tr("o.overlay.emuNone"))
        if not ra[1]:
            raise HTTPException(409, I.tr("o.overlay.emuOff"))
        if not RA.command(ra[0], body.get("action")):
            raise HTTPException(400, "action")
        return {"ok": True}

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
        ov.apply_hud()
        return {"settings": cur}

    return router
