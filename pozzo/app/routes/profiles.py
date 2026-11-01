"""Profili utente."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from ... import config as C


def build_router(ctx) -> APIRouter:
    SY, cfg, launcher, user, user_of, users = ctx.SY, ctx.cfg, ctx.launcher, ctx.user, ctx.user_of, ctx.users
    router = APIRouter()

    # ------------------------------------------------------------ profili utente
    def _profiles_state():
        return {"profiles": SY.profiles(cfg), "active": next(k for k, v in users.items() if v is user.ud)}

    @router.get("/api/profiles")
    def api_profiles():
        return _profiles_state()

    @router.post("/api/profiles")
    def api_profile_new(body: dict = Body(...)):
        try:
            p = SY.add_profile(cfg, str(body.get("name") or ""))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {**_profiles_state(), "created": p}

    @router.post("/api/profiles/active")
    def api_profile_switch(body: dict = Body(...)):
        pid = str(body.get("id") or "")
        if not any(p["id"] == pid for p in SY.profiles(cfg)):
            raise HTTPException(404, "Profilo non trovato")
        if launcher.running().get("status") in ("starting", "extracting", "running"):
            raise HTTPException(409, "Chiudi il gioco in corso prima di cambiare profilo")
        user.ud, user.switches = user_of(pid), user.switches + 1
        cfg.app["profile"] = pid
        C.save_settings(cfg, app={"profile": pid})
        return _profiles_state()

    @router.patch("/api/profiles/{pid}")
    def api_profile_rename(pid: str, body: dict = Body(...)):
        try:
            SY.rename_profile(cfg, pid, str(body.get("name") or ""))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return _profiles_state()

    @router.delete("/api/profiles/{pid}")
    def api_profile_delete(pid: str):
        if pid == "default" or not any(p["id"] == pid for p in SY.profiles(cfg)):
            raise HTTPException(400, "Questo profilo non si elimina")
        if user.ud is users.get(pid):
            api_profile_switch({"id": "default"})
        if pid in users:
            users.pop(pid).db.close()
        moved = SY.delete_profile(cfg, pid)
        return {**_profiles_state(), "moved_to": str(moved) if moved else None}

    return router
