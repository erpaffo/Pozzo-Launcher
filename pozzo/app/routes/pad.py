"""Pad Sony: batteria e barra luminosa (pozzo/remote/dualsense.py)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Body, HTTPException

from ...remote import dualsense

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def build_router(ctx) -> APIRouter:
    router = APIRouter()

    @router.get("/api/pad/battery")
    def api_pad_battery():
        return dualsense.read_battery()

    @router.post("/api/pad/led")
    def api_pad_led(body: dict = Body(...)):
        color = str(body.get("color") or "")
        if not HEX.match(color):
            raise HTTPException(400, "color")
        # in partita si scrive solo all'avvio e alla fine (force): il resto non deve toccare il pad
        if not body.get("force") and ctx.launcher.running().get("status") in ("starting", "extracting", "running"):
            return {"ok": False, "skipped": True}
        return {"ok": dualsense.set_led(color)}

    return router
