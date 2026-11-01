"""Profili utente."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from ... import config as C
from ... import profilecfg as PC


def build_router(ctx) -> APIRouter:
    SY, cfg, launcher, user, user_of, users, discord = ctx.SY, ctx.cfg, ctx.launcher, ctx.user, ctx.user_of, ctx.users, ctx.discord
    router = APIRouter()
    limiter = PC.PinLimiter()
    unlocked: set[str] = set()  # profili con PIN sbloccato da quando il server e' partito

    # ------------------------------------------------------------ profili utente
    def _profiles_state():
        return {"profiles": SY.profiles(cfg), "active": next(k for k, v in users.items() if v is user.ud)}

    def _locked_out(pid: str):
        """PIN di un profilo protetto: il cambio (o la modifica del PIN) passa solo dopo lo sblocco."""
        if any(p["id"] == pid and p["locked"] for p in SY.profiles(cfg)) and pid not in unlocked:
            raise HTTPException(403, "Profilo protetto da PIN: sbloccalo prima")

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

    @router.post("/api/profiles/{pid}/unlock")
    def api_profile_unlock(pid: str, body: dict = Body(...)):
        """Sblocca il profilo per questa sessione del server. Dopo PC.PIN_TRIES errori si aspetta PC.PIN_WAIT secondi."""
        if not any(p["id"] == pid for p in SY.profiles(cfg)):
            raise HTTPException(404, "Profilo non trovato")
        wait = limiter.wait(pid)
        if wait:
            raise HTTPException(429, f"Troppi tentativi: riprova tra {wait} secondi", headers={"Retry-After": str(wait)})
        stored = next((p for p in cfg.app.get("profiles") or [] if p.get("id") == pid), {}).get("pin_hash")
        if not stored or PC.check_pin(stored, str(body.get("pin") or "")):
            limiter.ok(pid)
            unlocked.add(pid)
            return _profiles_state()
        limiter.fail(pid)
        raise HTTPException(403, "PIN errato")

    @router.post("/api/profiles/active")
    def api_profile_switch(body: dict = Body(...)):
        pid = str(body.get("id") or "")
        if not any(p["id"] == pid for p in SY.profiles(cfg)):
            raise HTTPException(404, "Profilo non trovato")
        if launcher.running().get("status") in ("starting", "extracting", "running"):
            raise HTTPException(409, "Chiudi il gioco in corso prima di cambiare profilo")
        _locked_out(pid)
        user.ud, user.switches = user_of(pid), user.switches + 1
        cfg.app["profile"] = pid
        C.save_settings(cfg, app={"profile": pid})
        discord.conf()  # la presenza su Discord segue le impostazioni del nuovo profilo
        return _profiles_state()

    @router.patch("/api/profiles/{pid}")
    def api_profile_edit(pid: str, body: dict = Body(...)):
        """Nome, icona, colore e PIN (pin "" toglie il PIN). Le voci mancanti restano come sono."""
        if not any(p["id"] == pid for p in SY.profiles(cfg)):
            raise HTTPException(404, "Profilo non trovato")
        if "pin" in body:
            _locked_out(pid)
        try:
            if "name" in body:
                SY.rename_profile(cfg, pid, str(body.get("name") or ""))
            SY.update_profile(cfg, pid, avatar=None if "avatar" not in body else str(body.get("avatar") or ""),
                              color=None if "color" not in body else str(body.get("color") or ""),
                              pin=None if "pin" not in body else str(body.get("pin") or ""))
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
