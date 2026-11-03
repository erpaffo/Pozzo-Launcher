"""Gioca con un amico: codice invito + netplay RetroArch (Fase 0, nessun server)."""

from __future__ import annotations

import getpass
import secrets
import time

from fastapi import APIRouter, Body, HTTPException

from ... import config as C, netplay as NP, platforms as P
from ...library import launcher as L
from ...remote.certs import lan_ips


def build_router(ctx) -> APIRouter:
    api_play, cfg, launcher, lib, user = ctx.api_play, ctx.cfg, ctx.launcher, ctx.lib, ctx.user
    router = APIRouter()
    active: dict = {}  # partita ospitata adesso (vuoto = nessuna)

    def _conf() -> dict:
        return dict(cfg.app.get("netplay") or {})

    def _nick(conf: dict) -> str:
        try:
            d = getpass.getuser()
        except Exception:
            d = ""
        return str(conf.get("nick") or d or "Giocatore")

    def _plan(g: dict) -> dict | None:
        p = P.PLATFORMS.get(g["key"].split("/")[0])
        try:
            return L.plan(cfg, p, user.profile(g["key"])) if p else None
        except L.LaunchError:
            return None

    def _play(g: dict, extra: list[str]):
        """Avvia con gli argomenti di netplay; se l'avvio fallisce non restano per il gioco successivo."""
        launcher.next_args = extra
        try:
            api_play(g["id"])
        except Exception:
            launcher.next_args = []
            raise

    @router.get("/api/party")
    def api_party():
        conf, hosts = _conf(), lan_ips()
        return {"nick": _nick(conf), "host": conf.get("host") or (hosts[0] if hosts else ""), "hosts": hosts,
                "port": int(conf.get("port") or NP.PORT), "active": active or None}

    @router.post("/api/party/invite")
    def api_party_invite(body: dict = Body(...)):
        g = lib.by_key.get(str(body.get("key") or ""))
        if not g:
            raise HTTPException(404, "Gioco non trovato in libreria")
        plan = _plan(g)
        emu = (plan or {}).get("emulator", "")
        if not plan or not NP.supported(emu):
            raise HTTPException(409, {"error": "no-netplay", "emulator": emu, "suggest": "stream"})
        conf, hosts = _conf(), lan_ips()
        nick = str(body.get("nick") or _nick(conf)).strip() or "Giocatore"
        host = str(body.get("host") or conf.get("host") or (hosts[0] if hosts else "")).strip()
        try:
            port = int(body.get("port") or conf.get("port") or NP.PORT)
            code = NP.encode({"v": 1, "k": g["key"], "e": emu, "c": plan.get("core") or "", "h": host, "p": port,
                              "n": nick, "x": int(time.time()) + NP.TTL})
            NP.decode(code)  # IP o porta sbagliati: errore qui, non dall'amico
        except (ValueError, TypeError) as e:
            raise HTTPException(400, str(e))
        conf.update(nick=nick, host=host, port=port)
        C.save_settings(cfg, app={"netplay": conf})
        cfg.app["netplay"] = conf
        _play(g, NP.args("host", port=port, nick=nick))
        ctx.discord.set_party({"id": "poz-" + secrets.token_hex(3), "size": [1, 2]})
        active.clear()
        active.update(key=g["key"], title=g["title"], host=host, port=port, code=code)
        return {"ok": True, "code": code, "title": g["title"], "host": host, "port": port}

    def _decode(body: dict) -> dict:
        try:
            return NP.decode(str(body.get("code") or "").strip())
        except ValueError as e:
            raise HTTPException(400, str(e))

    @router.post("/api/party/preview")
    def api_party_preview(body: dict = Body(...)):
        t = _decode(body)
        g = lib.by_key.get(t["k"])
        return {"title": g["title"] if g else t["k"], "nick": t["n"], "host": t["h"], "port": t["p"], "have": bool(g)}

    @router.post("/api/party/join")
    def api_party_join(body: dict = Body(...)):
        t = _decode(body)
        g = lib.by_key.get(t["k"])
        if not g:
            raise HTTPException(404, "Gioco non presente nella tua libreria")
        local = (_plan(g) or {}).get("core") or ""
        if t.get("c") and local != t["c"]:
            raise HTTPException(409, {"error": "core-mismatch", "local": local, "remote": t["c"]})
        _play(g, NP.args("join", host=t["h"], port=t["p"], nick=_nick(_conf())))
        return {"ok": True, "title": g["title"]}

    return router
