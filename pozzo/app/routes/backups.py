"""Copie di sicurezza dei dati personali."""

from __future__ import annotations

import sys
import threading

from fastapi import APIRouter, Body, HTTPException

from ... import backup as BK
from ... import config as C
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

    @router.get("/api/backups/settings")
    def api_backup_settings():
        return BK.options(cfg)

    @router.post("/api/backups/settings")
    def api_backup_settings_set(body: dict = Body(...)):
        """Copia automatica settimanale (spenta di default), quante copie tenere (1-50), credenziali incluse o no."""
        upd = {}
        if "auto" in body:
            upd["backup_auto"] = bool(body["auto"])
        if "secrets" in body:
            upd["backup_secrets"] = bool(body["secrets"])
        if "keep" in body:
            try:
                upd["backup_keep"] = max(1, min(50, int(body["keep"])))
            except (TypeError, ValueError):
                raise HTTPException(400, I.tr("s.backups.bad_keep"))
        if upd:
            C.save_settings(cfg, app=upd)
        return BK.options(cfg)

    @router.post("/api/backups/preview")
    def api_backup_preview(body: dict = Body(...)):
        """Anteprima del ripristino: cosa verrebbe sovrascritto o creato. Non modifica niente."""
        try:
            r = BK.preview(cfg, body.get("name") or "")
            if r.get("runs_commands"):  # stesso avviso del ripristino, mostrato prima di confermare
                r["scripts_warning"] = I.tr("s.backups.scriptsWarning", n=r["runs_commands"])
            return r
        except (FileNotFoundError, ValueError, OSError) as e:
            raise HTTPException(400, str(e))

    @router.post("/api/backups/restore")
    def api_backup_restore(body: dict = Body(...)):
        if launcher.running().get("status") in ("starting", "extracting", "running"):
            raise HTTPException(409, I.tr("s.backups.close_game_first"))  # registrerebbe la partita sui dati vecchi
        if body.get("confirm") is not True:  # prima si mostra l'anteprima (/api/backups/preview), poi si conferma
            raise HTTPException(400, I.tr("s.backups.confirm_needed"))
        try:
            r = BK.restore(cfg, body.get("name") or "", user=user_of("default"),
                           profiles={k: v for k, v in users.items() if k != "default"})
            if r.get("runs_commands"):  # la copia puo' venire da altrove: si dice che ora girano suoi comandi
                r["scripts_warning"] = I.tr("s.backups.scriptsWarning", n=r["runs_commands"])
            return r
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(400, str(e))

    vars(ctx).update(api_backup_create=api_backup_create, api_backups=api_backups, api_backup_settings=api_backup_settings)
    return router
