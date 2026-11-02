"""Profili utente."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from ... import config as C
from ... import profilecfg as PC


def build_router(ctx) -> APIRouter:
    SY, cfg, launcher, user, user_of, users, discord = ctx.SY, ctx.cfg, ctx.launcher, ctx.user, ctx.user_of, ctx.users, ctx.discord
    router = APIRouter()
    limiter = PC.PinLimiter()
    unlocked: set[str] = set()  # profili con PIN sbloccato da quando il server e' partito

    # ------------------------------------------------------------ profili utente
    def _ask(n: int) -> bool:
        """«Chi gioca?» all'avvio: impostazione app.ask_profile, di default acceso se i profili sono 2 o piu'."""
        v = cfg.app.get("ask_profile")
        return bool(v) if v is not None else n >= 2

    def _profiles_state():
        """`active` e' il profilo di QUESTO dispositivo (cookie gs_profile), senza cookie quello del server."""
        profiles = SY.profiles(cfg)
        pid = PC.active(cfg)
        return {"profiles": profiles, "active": pid if any(p["id"] == pid for p in profiles) else "default",
                "ask": _ask(len(profiles))}

    def _locked_out(pid: str):
        """PIN di un profilo protetto: il cambio (o la modifica del PIN) passa solo dopo lo sblocco."""
        if any(p["id"] == pid and p["locked"] for p in SY.profiles(cfg)) and pid not in unlocked:
            raise HTTPException(403, "Profilo protetto da PIN: sbloccalo prima")

    def _remembered(request: Request) -> bool:
        """Questo dispositivo entra sempre con lo stesso profilo (cookie gs_remember): niente «Chi gioca?» all'avvio. Se il
        profilo ha un PIN non ancora sbloccato in questa sessione del server, si chiede comunque."""
        if request.cookies.get("gs_remember") != "1":
            return False
        pid = request.cookies.get("gs_profile")
        p = next((x for x in SY.profiles(cfg) if x["id"] == pid), None)
        return bool(p) and (not p["locked"] or pid in unlocked)

    def _device_cookies(r: JSONResponse, pid: str | None, remember: bool | None) -> JSONResponse:
        """gs_profile (profilo di questo dispositivo) e gs_remember (non chiedere piu'), entrambi per un anno."""
        opts = {"max_age": 365 * 86400, "httponly": True, "samesite": "lax", "path": "/"}
        if pid:
            r.set_cookie("gs_profile", pid, **opts)
        if remember is True:
            r.set_cookie("gs_remember", "1", **opts)
        elif remember is False:
            r.delete_cookie("gs_remember", path="/")
        return r

    @router.get("/api/profiles")
    def api_profiles(request: Request):
        return {**_profiles_state(), "remembered": _remembered(request)}

    @router.post("/api/profiles/remember")
    def api_profile_remember(body: dict = Body(...)):
        """{remember: bool}: questo dispositivo entra sempre con il profilo in uso (true) o chiede ogni volta (false)."""
        on = bool(body.get("remember"))
        return _device_cookies(JSONResponse({"remembered": on}), PC.active(cfg) if on else None, on)

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

    def _switch(pid: str, pin=None, cookie: bool = True, force: bool = False, remember: bool | None = None):
        """Cambia il profilo di questo dispositivo (cookie gs_profile) e quello del server (telefono, thread di sfondo).
        PIN: serve se il profilo ne ha uno e non e' stato gia' sbloccato (POST /api/profiles/{id}/unlock)."""
        if not any(p["id"] == pid for p in SY.profiles(cfg)):
            raise HTTPException(404, "Profilo non trovato")
        if launcher.running().get("status") in ("starting", "extracting", "running"):
            raise HTTPException(409, "Chiudi il gioco in corso prima di cambiare profilo")
        if not force and any(p["id"] == pid and p["locked"] for p in SY.profiles(cfg)) and pid not in unlocked:
            wait = limiter.wait(pid)
            if wait:
                return JSONResponse({"error": "rate", "detail": f"Troppi tentativi: riprova tra {wait} secondi"}, 429,
                                    headers={"Retry-After": str(wait)})
            stored = next((p for p in cfg.app.get("profiles") or [] if p.get("id") == pid), {}).get("pin_hash")
            if pin is None or not PC.check_pin(stored, str(pin)):
                if pin is not None:
                    limiter.fail(pid)
                return JSONResponse({"error": "pin", "detail": "PIN errato" if pin is not None else "Serve il PIN"}, 403)
            limiter.ok(pid)
            unlocked.add(pid)  # PIN giusto: sbloccato per questa sessione del server, come con /unlock
        user.ud, user.switches = user_of(pid), user.switches + 1
        cfg.app["profile"] = pid
        C.save_settings(cfg, app={"profile": pid})
        discord.conf()  # la presenza su Discord segue le impostazioni del nuovo profilo
        r = JSONResponse({"active": pid})
        return _device_cookies(r, pid, remember) if cookie else r

    @router.post("/api/profiles/active")
    def api_profile_switch(body: dict = Body(...)):
        """{id, pin?, remember?} -> 200 {"active": id} + cookie gs_profile; con remember true/false anche gs_remember
        (questo dispositivo non chiede piu' / torna a chiedere). 403 {"error":"pin"}; 429 + Retry-After; 404; 409."""
        remember = body.get("remember")
        return _switch(str(body.get("id") or ""), body.get("pin"), remember=remember if isinstance(remember, bool) else None)

    @router.post("/api/profiles/ask")
    def api_profiles_ask(body: dict = Body(...)):
        """Mostra (o no) la schermata «Chi gioca?» all'avvio."""
        C.save_settings(cfg, app={"ask_profile": bool(body.get("ask"))})
        cfg.app["ask_profile"] = bool(body.get("ask"))
        return {"ask": bool(body.get("ask"))}

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
            _switch("default", cookie=False, force=True)  # il profilo eliminato era quello del server; i cookie vecchi cadono su "default"
        if pid in users:
            users.pop(pid).db.close()
        moved = SY.delete_profile(cfg, pid)
        return {**_profiles_state(), "moved_to": str(moved) if moved else None}

    return router
