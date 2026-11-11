"""Conversione dei giochi Switch 2 (cartella / NSP / NUP): stato del supporto e conversione a richiesta come job."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import i18n as I
from ... import switch2pack as S
from ...downloads.manager import default_dir


def build_router(ctx) -> APIRouter:
    router = APIRouter()
    cfg = ctx.cfg
    jobs: dict[str, dict] = {}  # id -> stato (status, pct, out, error); la pagina interroga come per /api/emulators/job
    cancels: dict[str, threading.Event] = {}
    lock = threading.Lock()

    def _roots() -> list[Path]:
        d = (cfg.app.get("downloads") or {}).get("dir")
        return [Path(x).resolve() for x in (cfg.roms, *getattr(cfg, "extra_roms", []), d or default_dir()) if x]

    def _inside(p: Path) -> bool:
        return any(r == p or r in p.parents for r in _roots())

    @router.get("/api/switch2/status")
    def api_switch2_status():
        ok, why = S.supported(cfg)
        return {"supported": ok, "reason": why, "formats": list(S.FORMATS), "min_version": "2.5.0"}

    @router.post("/api/switch2/convert")
    def api_switch2_convert(body: dict = Body(...)):
        fmt, raw = str(body.get("format") or ""), str(body.get("path") or "").strip().strip('"')
        if fmt not in S.FORMATS:
            raise HTTPException(400, I.tr("s.switch2.badFormat"))
        if not raw or not Path(raw).is_absolute():
            raise HTTPException(400, I.tr("s.emulators.fullPath"))
        src = Path(raw).resolve()  # niente «..» ne' link fuori dalle cartelle ROM/download
        if not _inside(src):
            raise HTTPException(400, I.tr("s.switch2.outside"))
        ok, why = S.supported(cfg)
        if not ok:
            raise HTTPException(400, why)
        with lock:
            if any(j["status"] == "running" for j in jobs.values()):
                raise HTTPException(409, I.tr("s.switch2.busy"))
            jid = uuid.uuid4().hex[:12]
            jobs[jid] = {"id": jid, "status": "running", "pct": 0, "out": "", "error": ""}
            cancels[jid] = ev = threading.Event()

        def run():
            j = jobs[jid]
            try:
                j["out"] = str(S.convert(src, fmt, src.parent, lambda d, n: j.update(pct=d), ev))
                j["status"] = "done"
            except InterruptedError:
                j["status"] = "cancelled"
            except Exception as e:  # noqa: BLE001 - il testo e' gia' per la persona
                j.update(status="error", error=str(e) or type(e).__name__)

        threading.Thread(target=run, daemon=True).start()
        return jobs[jid]

    @router.get("/api/switch2/job/{jid}")
    def api_switch2_job(jid: str):
        if jid not in jobs:
            raise HTTPException(404, I.tr("s.switch2.noJob"))
        return jobs[jid]

    @router.post("/api/switch2/job/{jid}/cancel")
    def api_switch2_cancel(jid: str):
        if jid not in jobs:
            raise HTTPException(404, I.tr("s.switch2.noJob"))
        cancels[jid].set()
        return jobs[jid]

    return router
