"""Copie di sicurezza dei dati personali."""

from __future__ import annotations

import sys
import threading

from fastapi import APIRouter, Body, HTTPException

from ... import backup as BK
from ... import i18n as I


def build_router(ctx) -> APIRouter:
    cfg, launcher, user_of, users = ctx.cfg, ctx.launcher, ctx.user_of, ctx.users
    router = APIRouter()

    # ------------------------------------------------------------ copie di sicurezza dei dati utente
    def _auto_backup():
        try:
            BK.auto(cfg)
        except Exception as e:  # una copia mancata non deve impedire l'avvio
            print(f"backup automatico non riuscito: {type(e).__name__}: {e}", file=sys.stderr)

    threading.Thread(target=_auto_backup, daemon=True).start()

    @router.get("/api/backups")
    def api_backups():
        return {"folder": str(BK.folder(cfg)), "items": BK.list_backups(cfg)}

    @router.post("/api/backups")
    def api_backup_create():
        return {"name": BK.create(cfg).name}

    @router.post("/api/backups/restore")
    def api_backup_restore(body: dict = Body(...)):
        if launcher.running().get("status") in ("starting", "extracting", "running"):
            raise HTTPException(409, I.tr("s.backups.close_game_first"))  # registrerebbe la partita sui dati vecchi
        try:
            return BK.restore(cfg, body.get("name") or "", user=user_of("default"),
                              profiles={k: v for k, v in users.items() if k != "default"})
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(400, str(e))

    vars(ctx).update(api_backup_create=api_backup_create, api_backups=api_backups)
    return router
