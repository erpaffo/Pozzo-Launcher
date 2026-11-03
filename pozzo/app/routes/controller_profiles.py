"""Mapping predefinito del controller per gli emulatori: stato e applicazione a mano (Impostazioni › Controller)."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from ... import controllerprofiles as CP


def build_router(ctx) -> APIRouter:
    cfg = ctx.cfg
    router = APIRouter()

    @router.get("/api/controller-profiles")
    def api_cp_status():
        return {"detected": CP.detect_type(), "types": CP.TYPES, "emulators": CP.status(cfg.emulators)}

    @router.post("/api/controller-profiles/apply")
    def api_cp_apply(body: dict = Body(...)):
        try:
            return CP.apply(str(body.get("emulator") or ""), str(body.get("type") or CP.detect_type()), cfg.emulators, force=True)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except (RuntimeError, OSError) as e:
            raise HTTPException(409, str(e))

    return router
