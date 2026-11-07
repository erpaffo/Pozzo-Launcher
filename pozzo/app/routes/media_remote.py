"""Telecomando del lettore Media: il telefono accoda comandi, il desktop li ritira (long-poll) e pubblica lo stato.
Tutto in memoria: niente su disco. Il telefono raggiunge solo command e GET state (cancello in remote/phone.py)."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections import deque

from fastapi import APIRouter, Body, HTTPException

CMDS = {"play", "pause", "toggle", "jump", "seek", "next", "prev", "volume", "mute", "fullscreen", "skip", "episodes", "close"}
ARG_RANGE = {"jump": (-3600, 3600), "seek": (0, 86400), "volume": (0, 1)}  # comandi con argomento numerico
MAX_QUEUE, CMD_TTL, STATE_TTL, POLL_WAIT, MAX_STATE = 20, 10.0, 8.0, 20.0, 4000


def _now() -> float:
    return time.monotonic()


def build_router(ctx) -> APIRouter:
    router = APIRouter()
    queue: deque = deque(maxlen=MAX_QUEUE)  # (numero, istante, cmd, arg)
    st = {"seq": 0, "state": {"active": False}, "at": 0.0}

    def _fresh(since: int) -> list[dict]:
        now = _now()
        return [{"n": n, "cmd": c, "arg": a} for n, t, c, a in queue if n > since and now - t <= CMD_TTL]

    @router.post("/api/media/remote/command")
    def command(body: dict = Body(...)):
        cmd, arg = body.get("cmd"), body.get("arg")
        if cmd not in CMDS:
            raise HTTPException(400, "Comando non valido")
        if cmd in ARG_RANGE:
            lo, hi = ARG_RANGE[cmd]
            if isinstance(arg, bool) or not isinstance(arg, (int, float)) or not math.isfinite(arg):
                raise HTTPException(400, "Argomento non valido")
            arg = min(hi, max(lo, arg))
        else:
            arg = None
        st["seq"] += 1
        queue.append((st["seq"], _now(), cmd, arg))
        return {"ok": True, "n": st["seq"]}

    @router.get("/api/media/remote/poll")
    async def poll(since: int = 0):
        if since > st["seq"]:  # il server e' ripartito: il desktop si riallinea
            return {"cmds": [], "last": st["seq"]}
        end = _now() + POLL_WAIT
        while True:
            cmds = _fresh(since)
            if cmds or _now() >= end:
                return {"cmds": cmds, "last": st["seq"]}
            await asyncio.sleep(0.25)

    @router.post("/api/media/remote/state")
    def state_set(body: dict = Body(...)):
        if len(json.dumps(body)) > MAX_STATE:
            raise HTTPException(413, "Stato troppo grande")
        st["state"], st["at"] = body, _now()
        return {"ok": True}

    @router.get("/api/media/remote/state")
    def state_get():
        if _now() - st["at"] > STATE_TTL or not st["state"].get("active"):
            return {"active": False}
        return st["state"]

    return router
