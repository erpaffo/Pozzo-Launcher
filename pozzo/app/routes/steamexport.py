"""Esporta in Steam: i giochi di Pozzo come collegamenti non-Steam (con copertine) che si avviano tramite Pozzo."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import i18n as I
from ... import platforms as P
from ... import steamshortcuts as SS
from ...remote.sunshine import launcher_cmd
from ...stores.steam import Steam

# tipo di immagine Pozzo -> tipo di immagine Steam (fanart come capsula larga se manca l'header)
ART = {"p": ("cover",), "wide": ("header", "fanart"), "hero": ("hero", "fanart"), "logo": ("logo",), "icon": ("icon",)}


def build_router(ctx) -> APIRouter:
    cfg, lib, view, user = ctx.cfg, ctx.lib, ctx.view, ctx.user
    router = APIRouter()

    def _steam() -> Steam:
        return Steam(cfg, None, None, print)

    def _file(rel: str | None) -> Path | None:
        """File locale di un'immagine; per quelle remote solo se gia' scaricate nella cache (niente rete)."""
        if not rel:
            return None
        if rel.startswith("url:"):
            h = hashlib.sha1(rel[4:].encode()).hexdigest()
            return next(iter((Path(cfg.cache) / "media" / "net").glob(f"{h}.*")), None)
        p = Path(cfg.cache) / rel
        return p if p.exists() else None

    @router.get("/api/steam-export")
    def api_info():
        s = _steam()
        p = s.path()
        if not p:
            return {"found": False, "users": [], "platforms": []}
        persona = {a["steamid"]: a["persona"] for a in s.account()["accounts"]}
        plats = sorted({g["platform"] for g in lib.games if not g.get("store")})
        return {"found": True, "running": SS.steam_running(), "users": SS.users(p, persona),
                "platforms": [{"id": x, "name": P.PLATFORMS[x].name if x in P.PLATFORMS else x} for x in plats]}

    def _target(account: str) -> Path:
        p = _steam().path()
        if not p:
            raise HTTPException(404, I.tr("s.steamx.notfound"))
        if account not in {u["id"] for u in SS.users(p)}:
            raise HTTPException(400, I.tr("s.steamx.badacct"))
        return p

    def _run(p: Path, account: str, entries: list[dict]):
        try:
            return SS.apply(p, account, entries)
        except SS.SteamRunning:
            raise HTTPException(409, I.tr("s.steamx.running"))
        except ValueError as e:
            raise HTTPException(500, I.tr("s.steamx.vdf", e=e))

    @router.post("/api/steam-export")
    def api_export(body: dict = Body(...)):
        p = _target(str(body.get("account") or ""))
        what, plats = body.get("what") or "all", set(body.get("platforms") or [])
        base, workdir = launcher_cmd(cfg)
        exe, pre = re.match(r'("[^"]*")\s*(.*)', base).groups()  # "<exe>" [-m pozzo] [-c cfg]
        v = view()["groups"]
        entries = []
        for d in v.values():
            g = lib.by_id.get(d["primary"])
            # solo giochi avviabili da qui: niente giochi online ne' degli store non installati
            if not g or d["hidden"] or g.get("store") == "online" or (g.get("store") and not g.get("installed")):
                continue
            if (what == "favorites" and not d["favorite"]) or (what == "platforms" and g["platform"] not in plats):
                continue
            media = {**g["media"], **user.media_overrides(g["key"])}
            art = {k: f for k, f in ((k, next((_file(media.get(m)) for m in ms if _file(media.get(m))), None))
                                     for k, ms in ART.items()) if f}
            entries.append({"name": g["title"], "exe": exe, "start_dir": workdir, "art": art,
                            "opts": f'{pre + " " if pre else ""}play --key "{g["key"]}"'})
        # shortcut: titoli uguali (stesso exe) darebbero lo stesso appid; resta solo il primo
        uniq = {}
        for e in entries:
            uniq.setdefault(SS.appid(e["exe"], e["name"]), e)
        entries = list(uniq.values())
        return {"ok": True, **_run(p, str(body["account"]), entries)}

    @router.delete("/api/steam-export")
    def api_remove(account: str):
        return {"ok": True, **_run(_target(account), account, [])}

    return router
