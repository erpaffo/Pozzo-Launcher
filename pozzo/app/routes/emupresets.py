"""Preset delle impostazioni degli emulatori: stato per gioco, ripristino, scelta per console."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import config as C, emucfg, i18n as I, platforms as P
from ...library import launcher as L
from ...library.gamekey import game_key

NAME_KEYS = {"quality": "s.emupresets.quality", "performance": "s.emupresets.performance", "faithful": "s.emupresets.faithful"}
CHOICES = (*emucfg.LEVELS, emucfg.LEAVE)


def build_router(ctx) -> APIRouter:
    cfg, lib, user = ctx.cfg, ctx.lib, ctx.user
    router = APIRouter()

    def _target(gid: int):
        """((gioco, console, piano di avvio, chiave, file), "") oppure (None, motivo)."""
        g = lib.game(gid)
        p = P.PLATFORMS.get(g["platform"])
        if g.get("store") or not p:
            return None, I.tr("s.emupresets.unsupported")
        try:
            pl = L.plan(cfg, p, user.profile(g["key"]))
        except L.LaunchError as e:
            return None, str(e)
        if not pl:
            return None, I.tr("s.emupresets.noEmu")
        path = next((Path(f) for f in g["files"] if Path(f).exists()), None)
        gk = game_key(p.id, path) if path else None
        return (g, p, pl, gk, path), ""

    @router.get("/api/game/{gid}/emu-preset")
    def api_game_preset(gid: int):
        t, why = _target(gid)
        out = {"supported": False, "emulator": "", "game_id": None, "selection": "", "console_selection": "",
               "preview": None, "levels": [{"id": k, "name": I.tr(NAME_KEYS[k])} for k in emucfg.LEVELS], "note": why}
        if not t:
            return out
        g, p, pl, gk, _ = t
        gsel = (user.profile(g["key"]) or {}).get(L.PRESET_KEY) or ""
        csel = (cfg.app.get("emu_preset") or {}).get(p.id) or ""
        out.update(emulator=pl["emulator"], game_id=gk, selection=gsel, console_selection=csel)
        if not emucfg.supported(pl["emulator"]):
            out["note"] = I.tr("s.emupresets.unsupported")
        elif not gk:
            out["note"] = I.tr("s.emupresets.gameIdUnknown")
        else:
            try:
                out["preview"] = emucfg.preview(pl["emulator"], gk, gsel or None, csel or None)
                out["supported"] = True
            except (ValueError, OSError) as e:
                out["note"] = str(e)
        return out

    @router.post("/api/game/{gid}/emu-preset/restore")
    def api_game_preset_restore(gid: int):
        t, why = _target(gid)
        if not t:
            raise HTTPException(409, why[:1].upper() + why[1:])
        _, _, pl, gk, path = t
        if not gk:
            raise HTTPException(409, I.tr("s.emupresets.gameIdUnknown"))
        try:
            return {"restored": emucfg.restore_for_game(pl["emulator"], pl["exe"], gk, core=pl["core"], game_name=path.stem)}
        except emucfg.EmuCfgError as e:
            raise HTTPException(409, str(e))

    @router.get("/api/emu-presets")
    def api_console_presets():
        return dict(cfg.app.get("emu_preset") or {})

    @router.post("/api/emu-presets/console")
    def api_console_preset_set(body: dict = Body(...)):
        plat, preset = str(body.get("platform") or ""), str(body.get("preset") or "")
        if plat not in P.PLATFORMS:
            raise HTTPException(400, I.tr("s.emupresets.unknownConsole"))
        if preset not in CHOICES:
            raise HTTPException(400, I.tr("s.emupresets.badPreset"))
        cur = {**(cfg.app.get("emu_preset") or {}), plat: preset}
        C.save_settings(cfg, app={"emu_preset": cur})
        cfg.app["emu_preset"] = cur
        return cur

    return router
