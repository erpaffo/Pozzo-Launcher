"""Impostazioni del profilo del dispositivo (non segrete) e cartelle ROM proprie del profilo."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from .. import extensions as X
from ... import config as C, profilecfg as PC


def build_router(ctx) -> APIRouter:
    cfg = ctx.cfg
    router = APIRouter()
    ALLOWED = ("theme", "experience", "ask_profile", "exp_animations")  # mai segreti: account e chiavi non passano da qui

    def _state() -> dict:
        n = len(PC.profile_ids(cfg))
        ask = cfg.app.get("ask_profile")
        return {"theme": PC.get(cfg, "theme", "default"), "experience": PC.get(cfg, "experience", "catalog"),
                "ask_profile": bool(ask) if ask is not None else n >= 2,
                "roms_extra": PC.get(cfg, "roms_extra", []),
                "exp_animations": PC.get(cfg, "exp_animations")}

    @router.get("/api/profile/settings")
    def api_profile_settings():
        return _state()

    @router.post("/api/profile/settings")
    def api_profile_settings_set(body: dict = Body(...)):
        bad = [k for k in body if k not in ALLOWED]
        if bad:
            raise HTTPException(400, f"Impostazioni non consentite: {', '.join(bad)}")
        if "theme" in body and body["theme"] not in {t["id"] for t in X.list_themes(cfg)}:
            raise HTTPException(404, "Tema non trovato")
        if "experience" in body and body["experience"] not in {x["id"] for x in X.list_experiences() if x.get("available")}:
            raise HTTPException(404, "Esperienza non trovata")
        if "exp_animations" in body and body["exp_animations"] not in ("normal", "reduced", "off"):
            raise HTTPException(400, "Impostazione animazioni non valida")
        for k in ("theme", "experience"):
            if k in body:
                PC.put(cfg, k, body[k], mirror=True)
        if "exp_animations" in body:
            PC.set(cfg, "exp_animations", body["exp_animations"])
        if "ask_profile" in body:
            C.save_settings(cfg, app={"ask_profile": bool(body["ask_profile"])})
            cfg.app["ask_profile"] = bool(body["ask_profile"])
        return _state()

    @router.post("/api/profile/roms")
    def api_profile_roms(body: dict = Body(...)):
        """Aggiunge (action=add) o toglie (action=remove) una cartella ROM PROPRIA del profilo attivo: solo lui vede
        quei giochi. Le cartelle globali (Impostazioni › Cartelle ROM) sono di tutti. Poi serve ricostruire la libreria."""
        raw = str(body.get("path") or "").strip().strip('"')
        cur = [str(x) for x in PC.get(cfg, "roms_extra", [])]
        if body.get("action") == "remove":
            cur = [x for x in cur if x != raw]
        else:
            p = Path(os.path.expandvars(os.path.expanduser(raw)))
            if not raw or not p.is_dir():
                raise HTTPException(400, "Cartella non trovata")
            if str(p.resolve()) not in cur:
                cur.append(str(p.resolve()))
        PC.set(cfg, "roms_extra", cur or None)
        return {"roms_extra": cur}

    return router
