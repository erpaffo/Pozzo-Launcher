"""Libreria condivisa (server): API per gli ospiti (dietro PhoneGate, ruolo "lib") e gestione dal PC (solo in locale)."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from ... import platforms as P, webplay as W
from ...remote import libshare as LS
from ...remote.phone import COOKIE, _qr_svg
from ..server import STATIC

NOSNIFF = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}


def build_router(ctx) -> APIRouter:
    cfg, lib, user, hub = ctx.cfg, ctx.lib, ctx.user, ctx.phone_hub
    router = APIRouter()

    def _ok(gid: int) -> bool:
        g = lib.by_id.get(gid)
        return bool(g and LS.shared(cfg, g))

    hub.lib_game_ok = _ok  # il cancello lo chiede per /play/N, /api/play/N/... e download/copertine

    def _guest(request: Request) -> dict:
        """Ospite della libreria che fa la richiesta (il cancello lo ha gia' riconosciuto: qui si ricontrolla)."""
        dev = getattr(request.state, "phone_device", None)
        d = next((d for d in hub.conf["devices"] if d["id"] == dev), None)
        if not d or d.get("kind") != "lib":
            raise HTTPException(403, "Riservato agli ospiti della libreria")
        return d

    def _game(gid: int) -> dict:
        g = lib.by_id.get(gid)
        if not g or not LS.shared(cfg, g):  # stesso errore se non esiste o non e' condiviso: non si scopre cosa c'e'
            raise HTTPException(403, "Gioco non condiviso")
        return g

    def _local(request: Request):
        if request.client is None or request.client.host not in ("127.0.0.1", "::1", "testclient"):
            raise HTTPException(403)

    # ------------------------------------------------------------ per gli ospiti
    @router.get("/l")
    @router.get("/l/")
    def l_index():
        return FileResponse(STATIC / "l" / "index.html", headers={"Cache-Control": "no-cache"})

    @router.post("/l/api/pair")
    def l_pair(request: Request, body: dict = Body(...)):
        """Entra con il codice dell'invito. Il browser riceve il cookie; Pozzo (client=true) anche il token."""
        try:
            token = LS.pair(hub, str(body.get("code") or ""), str(body.get("name") or ""))
        except ValueError as e:
            raise HTTPException(403, str(e))
        dev = hub.device_for(token)
        r = JSONResponse({"ok": True, **({"token": token} if body.get("client") else {})})
        r.set_cookie(COOKIE, token, max_age=max(60, int(dev["exp"] - dev["created"])), httponly=True,
                     secure=request.url.scheme == "https", samesite="strict", path="/")
        return r

    @router.get("/l/api/me")
    def l_me(request: Request):
        d = _guest(request)
        return {"name": d["name"], "exp": d["exp"]}

    @router.post("/l/api/logout")
    def l_logout(request: Request):
        d = _guest(request)
        hub.revoke(d["id"])
        r = Response(status_code=204)
        r.delete_cookie(COOKIE, path="/")
        return r

    @router.get("/api/lib-share/list")
    def lib_list(request: Request):
        _guest(request)
        out = []
        for g in sorted(lib.games, key=lambda g: g["title"].lower()):
            if not LS.shared(cfg, g):
                continue
            one = LS.single_file(g)
            out.append({"id": g["id"], "ref": LS.ref(g), "title": g["title"], "platform": g["platform"],
                        "size": g.get("size") or 0, "kind": "file" if one else "zip",
                        "name": one.name if one else "", "play": bool(W.plan(g)),
                        "cover": f"/api/lib-share/cover/{g['id']}" if _cover(g) else ""})
        return {"games": out}

    def _cover(g: dict) -> Path | None:
        rel = {**g["media"], **user.media_overrides(g["key"])}.get("cover")
        if not rel or rel.startswith("url:"):  # copertine remote non ancora scaricate: niente
            return None
        base = Path(cfg.cache).resolve()
        p = (base / rel).resolve()
        return p if p.is_file() and base in p.parents else None

    @router.get("/api/lib-share/cover/{gid}")
    def lib_cover(gid: int, request: Request):
        _guest(request)
        p = _cover(_game(gid))
        if not p:
            raise HTTPException(404)
        return FileResponse(p, headers={"Cache-Control": "private, max-age=3600"})

    @router.get("/api/lib-share/download/{gid}")
    def lib_download(gid: int, request: Request):
        """ROM sola: il file, con Range (si riprende). Cartella o piu' file: zip ZIP_STORED al volo, senza Range."""
        d = _guest(request)
        g = _game(gid)
        one = LS.single_file(g)
        if not LS.take(d["id"]):
            raise HTTPException(429, "Un download alla volta", headers={"Retry-After": "30"})
        try:
            items = [] if one else LS.entries(g)
            if not one and not items:
                raise HTTPException(404, "File del gioco non trovati")
            if one:
                size = one.stat().st_size
                try:
                    rng = LS.parse_range(request.headers.get("range"), size)
                except ValueError:
                    LS._free(d["id"])
                    return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
                start, end = rng or (0, size - 1)
                name = one.name
                headers = {**NOSNIFF, "Accept-Ranges": "bytes", "Content-Length": str(max(0, end - start + 1))}
                if rng:
                    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
                body = LS.file_chunks(one, start, end, d["id"])
                status = 206 if rng else 200
            else:
                name = (re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", g["title"]).strip() or "gioco") + ".zip"
                headers, body, status = {**NOSNIFF, "Accept-Ranges": "none"}, LS.zip_chunks(items, d["id"]), 200
        except Exception:
            LS._free(d["id"])
            raise
        headers["Content-Disposition"] = "attachment; filename=\"download\"; filename*=UTF-8''" + quote(name, safe="")
        return StreamingResponse(body, status_code=status, media_type="application/octet-stream", headers=headers)

    # ------------------------------------------------------------ gestione dal PC (solo in locale)
    def _state() -> dict:
        c = LS.conf(cfg)
        plats: dict[str, dict] = {}
        for g in lib.games:
            if not g.get("store") and g.get("files"):
                p = plats.setdefault(g["platform"], {"id": g["platform"], "name": getattr(P.PLATFORMS.get(g["platform"]), "name", g["platform"]), "n": 0})
                p["n"] += 1
        up = hub.lib_upnp
        return {**c, "platform_list": sorted(plats.values(), key=lambda p: p["name"].lower()),
                "invites": LS.invites(hub), "running": hub.running(), "error": hub.error,
                "urls": [u.removesuffix("/m/") + "/l/" for u in hub.urls()],
                "external": f"{up['external_ip']}:{up['port']}" if up and up.get("external_ip") else "",
                "upnp_on": bool(up), "count": sum(1 for g in lib.games if LS.shared(cfg, g))}

    @router.get("/api/libshare")
    def api_libshare(request: Request):
        _local(request)
        return _state()

    @router.get("/api/libshare/games")
    def api_libshare_games(request: Request, q: str = ""):
        """Giochi che si possono condividere (cerca per titolo): max 40 risultati."""
        _local(request)
        q = q.strip().lower()
        sel = set(LS.conf(cfg)["games"])
        rows = [{"key": g["key"], "title": g["title"], "platform": g["platform"], "on": g["key"] in sel}
                for g in lib.games if not g.get("store") and g.get("files") and (not q or q in g["title"].lower())]
        rows.sort(key=lambda r: (not r["on"], r["title"].lower()))
        return {"games": rows[:40]}

    @router.post("/api/libshare")
    def api_libshare_set(request: Request, body: dict = Body(...)):
        _local(request)
        kw = {}
        if "platforms" in body:
            kw["platforms"] = sorted({str(x) for x in body["platforms"] if x in P.PLATFORMS})
        if "games" in body:
            kw["games"] = sorted({str(x) for x in body["games"]})[:5000]
        if kw:
            LS.save_conf(cfg, **kw)
        return _state()

    @router.post("/api/libshare/invite")
    def api_libshare_invite(request: Request, body: dict = Body(...)):
        """Nuovo invito (accende il server HTTPS se serve). Codice e link si vedono solo in questa risposta."""
        _local(request)
        if not hub.running() and not hub.start(ctx.app):
            raise HTTPException(500, hub.error or "Server di rete non avviato")
        try:
            days = float(body.get("days") or 30)
        except (TypeError, ValueError):
            raise HTTPException(400, "Durata non valida")
        inv, code = LS.new_invite(hub, str(body.get("name") or ""), days)
        up = hub.lib_upnp
        base = f"https://{up['external_ip']}:{up['port']}" if up and up.get("external_ip") else hub.base_url()
        link = f"{base}/l/#code={code}"
        return {**_state(), "new": {"id": inv["id"], "code": f"{code[:5]}-{code[5:]}", "link": link, "qr": _qr_svg(link)}}

    @router.delete("/api/libshare/invites/{iid}")
    def api_libshare_revoke(request: Request, iid: str):
        _local(request)
        LS.revoke_invite(hub, iid)
        return _state()

    @router.post("/api/libshare/internet")
    def api_libshare_internet(request: Request, body: dict = Body(...)):
        """Apre (o chiude) la porta sul router con UPnP. Spento di default: la libreria resta nella rete di casa."""
        _local(request)
        on = bool(body.get("on"))
        res = {"on": False, "error": ""}
        if on:
            if not hub.running() and not hub.start(ctx.app):
                raise HTTPException(500, hub.error or "Server di rete non avviato")
            res = LS.open_upnp(hub)
        else:
            LS.close_upnp(hub)
        LS.save_conf(cfg, internet=res["on"])
        return {**_state(), "upnp_error": res["error"]}

    return router
