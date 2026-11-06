"""Screenshot dei giochi."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from ... import config as C, stores as STORES
from ... import i18n as I
from ...library import launcher as L


def build_router(ctx) -> APIRouter:
    SC, _thumb, cfg, launcher, lib, shots = ctx.SC, ctx._thumb, ctx.cfg, ctx.launcher, ctx.lib, ctx.shots
    router = APIRouter()

    # ------------------------------------------------------------ schermate
    def _shot_payload(s: dict) -> dict:
        g = lib.by_key.get(s["key"])
        return {**s, "url": f"/shots/{s['id']}", "game": g["id"] if g else None, "title": g["title"] if g else s["key"],
                "platform": (g.get("store") or g["platform"]) if g else ""}

    @router.get("/api/game/{gid}/shots")
    def api_game_shots(gid: int):
        g = lib.get(gid)
        return {"shots": [_shot_payload(s) for s in shots.list([m["key"] for m in lib.groups[g["grp"]]])]}

    @router.get("/api/shots")
    def api_shots():
        out = []
        for s in shots.list():
            g = lib.by_key.get(s["key"])
            if g:  # la versione principale del gioco, per raggruppare le schermate di tutte le versioni
                prim = next((m for m in lib.groups[g["grp"]] if m.get("is_primary")), g)
                out.append({**_shot_payload(s), "game": prim["id"], "title": prim["title"],
                            "platform": prim.get("store") or prim["platform"]})
            else:
                out.append(_shot_payload(s))
        return {"shots": out, "folder": str(shots.root), "settings": SC.settings(cfg)}

    @router.get("/shots/{sid}")
    def shot_file(sid: int, w: int = 0):
        p = shots.path(sid)
        if not p or not p.exists():
            raise HTTPException(404)
        if w:
            try:
                p = _thumb(p, min(max(w, 64), 1600))
            except Exception:
                pass
        return FileResponse(p, headers={"Cache-Control": "public, max-age=604800"})

    @router.delete("/api/shots/{sid}")
    def api_shot_delete(sid: int):
        shots.delete(sid)
        return {"ok": True}

    @router.post("/api/shots/open")
    def api_shot_open(body: dict = Body(default={})):
        p = shots.path(int(body["id"])) if body.get("id") else shots.root
        if not p or not p.exists():
            shots.root.mkdir(parents=True, exist_ok=True)
            p = shots.root
        if sys.platform == "win32" and p.is_file():
            subprocess.Popen(["explorer", "/select,", str(p)])
        else:
            L.open_uri(str(p if p.is_dir() else p.parent))
        return {"ok": True}

    @router.post("/api/shots/import-steam")
    def api_shots_steam():
        prov = STORES.BY_ID.get("steam")
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            root = prov(cfg, c, None, lambda *a: None).path() if prov else None
        finally:
            c.close()
        if not root:
            raise HTTPException(400, I.tr("s.shots.steamNotFound"))
        keys = {g["key"].split(":", 1)[1]: g["key"] for g in lib.games if g.get("store") == "steam"}
        n = SC.import_steam(shots, Path(root), keys)
        return {"imported": n}

    @router.post("/api/shots/settings")
    def api_shots_settings(body: dict = Body(...)):
        cur = SC.settings(cfg)
        if "hotkey" in body:
            hk = str(body.get("hotkey") or "").strip().lower()
            if hk and not SC.parse_hotkey(hk):
                raise HTTPException(400, I.tr("s.shots.hotkeyInvalid"))
            cur["hotkey"] = hk
        for k in ("pad", "import_emulator"):
            if k in body:
                cur[k] = bool(body[k])
        C.save_settings(cfg, app={"screenshots": cur})
        cfg.app["screenshots"] = cur
        return {"settings": cur}

    @router.post("/api/running/screenshot")
    def api_running_shot():
        return {"ok": launcher.screenshot()}

    return router
