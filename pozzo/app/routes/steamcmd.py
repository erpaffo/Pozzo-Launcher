"""Steam senza il client: account di SteamCMD e download dei giochi posseduti (solo app desktop, non il telefono)."""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Body, HTTPException

from ...downloads.engines import steamcmd as SC
from ... import i18n as I


def build_router(ctx) -> APIRouter:
    cfg = ctx.cfg
    router = APIRouter()

    @router.get("/api/steamcmd")
    def api_steamcmd_status():
        return SC.status(cfg)

    @router.post("/api/steamcmd/login")
    async def api_steamcmd_login(body: dict = Body(...)):
        # la password passa di qui solo per arrivare a SteamCMD: non si salva ne' si scrive in nessun log
        r = await asyncio.to_thread(SC.login, cfg, str(body.get("user") or ""), str(body.get("password") or ""),
                                    str(body.get("guard") or ""))
        if not r["ok"]:
            raise HTTPException(401 if r["code"] in ("guard", "guard_bad", "password") else 400, r["error"], headers={"X-Steamcmd": r["code"]})
        return {"ok": True, **SC.status(cfg)}

    @router.post("/api/steamcmd/logout")
    def api_steamcmd_logout():
        SC.logout(cfg)
        return {"ok": True, **SC.status(cfg)}

    @router.post("/api/steamcmd/install")
    def api_steamcmd_install(body: dict = Body(...)):
        g = ctx.lib.game(int(body.get("game_id") or 0))
        m = re.search(r"/(\d+)$", g.get("install_uri") or "") if g.get("store") == "steam" else None
        if not m:
            raise HTTPException(400, I.tr("s.steamcmd.notSteam"))
        user = SC.account(cfg)
        if not user:
            raise HTTPException(401, I.tr("s.steamcmd.needLogin"))
        mgr = ctx.downloads
        t = mgr.add(f"steamcmd://{m[1]}", SC.folder_for(mgr.settings()["dir"], g["title"], m[1]), steamcmd=True,
                    name=g["title"], appid=m[1], user=user, game_id=g["id"])
        return {"ok": True, "task": t.view()}

    return router
