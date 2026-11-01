"""Impostazioni dell'app, temi, esperienze, plugin."""

from __future__ import annotations

import os
import sys
import threading

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from .. import extensions as X
from ... import config as C
from ...library import launcher as L


def build_router(ctx) -> APIRouter:
    cfg, plugin_errors, thumbs_dir = ctx.cfg, ctx.plugin_errors, ctx.thumbs_dir
    router = APIRouter()

    # ------------------------------------------------------------ temi, plugin, link esterni
    @router.get("/api/extensions")
    def api_extensions():
        themes = X.list_themes(cfg)
        active = cfg.app.get("theme", "default")
        if not isinstance(active, str) or active not in {t["id"] for t in themes}:
            active = "default"
        return {"themes": themes, "active_theme": active, "active_experience": X.active_experience(cfg),
                "experiences": X.list_experiences(),
                "plugins": X.list_plugins(cfg, plugin_errors),
                "paths": {"themes": str(X.user_dir(cfg, "themes")), "plugins": str(X.user_dir(cfg, "plugins"))}}

    @router.get("/api/app/launch")
    def api_launch_opts():
        return cfg.app.get("launch") or {}

    @router.post("/api/app/launch")
    def api_launch_opts_save(body: dict = Body(...)):
        """Script prima/dopo ogni gioco e chiusura del launcher dello store a fine partita."""
        conf = {k: str(body.get(k) or "").strip() for k in L.SCRIPT_KEYS}
        conf = {k: v for k, v in conf.items() if v}
        if body.get("close_launcher"):
            conf["close_launcher"] = True
        C.save_settings(cfg, app={"launch": conf})
        cfg.app["launch"] = conf
        return conf

    @router.get("/api/app/notify")
    def api_notify_get():
        return {"enabled": cfg.app.get("notify") is not False, "available": sys.platform == "win32"}

    @router.post("/api/app/notify")
    def api_notify_set(body: dict = Body(...)):
        on = bool(body.get("enabled"))
        C.save_settings(cfg, app={"notify": on})
        cfg.app["notify"] = on
        if on:
            from ... import notify
            notify.send(cfg, "Pozzo Launcher", "Notifiche attive: prezzi, giochi gratis e lavori finiti.")
        return {"enabled": on}

    @router.get("/api/app/power")
    def api_power_get():
        from ... import power
        return {"after_jobs": cfg.app.get("after_jobs") or "none", "modes": list(power.MODES), **power.pending()}

    @router.post("/api/app/power")
    def api_power_set(body: dict = Body(...)):
        """Cosa fare al termine delle operazioni lunghe: niente, sospendi o spegni il PC."""
        from ... import power
        mode = str(body.get("after_jobs") or "none")
        if mode not in power.MODES:
            raise HTTPException(400, "Scelta non valida")
        C.save_settings(cfg, app={"after_jobs": mode})
        cfg.app["after_jobs"] = mode
        return api_power_get()

    @router.post("/api/app/power/abort")
    def api_power_abort():
        from ... import power
        return {"cancelled": power.cancel(), **power.pending()}

    @router.post("/api/app/duplicates")
    def api_duplicates(body: dict = Body(...)):
        C.save_settings(cfg, app={"skip_duplicates": bool(body.get("skip"))})
        return {"skip_duplicates": cfg.app.get("skip_duplicates", True)}

    @router.post("/api/app/hide-dlc")
    def api_hide_dlc(body: dict = Body(...)):
        """Nasconde le DLC di una console (una per console: le console non hanno tutte lo stesso catalogo)."""
        pid = str(body.get("platform") or "")
        if not pid:
            raise HTTPException(400, "Piattaforma mancante")
        cur = [p for p in (cfg.app.get("hide_dlc") or []) if p != pid]
        if body.get("hide"):
            cur.append(pid)
        C.save_settings(cfg, app={"hide_dlc": cur})
        return {"hide_dlc": cfg.app.get("hide_dlc") or []}

    @router.post("/api/app/quit")
    def api_quit():
        """Chiude l'app dal menu File (solo dal PC: il telefono non ha accesso a questa rotta)."""
        threading.Timer(0.5, os._exit, args=(0,)).start()
        return {"ok": True}

    @router.post("/api/cache/thumbs/clear")
    def api_thumbs_clear():
        """Elimina le miniature delle immagini: si rigenerano da sole quando servono. Gli originali non si toccano."""
        import shutil
        n = sum(1 for _ in thumbs_dir.rglob("*.webp")) if thumbs_dir.exists() else 0
        shutil.rmtree(thumbs_dir, ignore_errors=True)
        return {"removed": n}

    @router.post("/api/app/theme")
    def api_theme(body: dict = Body(...)):
        tid = body.get("theme") or "default"
        if tid not in {t["id"] for t in X.list_themes(cfg)}:
            raise HTTPException(404, "Tema non trovato")
        C.save_settings(cfg, app={"theme": tid})
        return {"ok": True}

    @router.post("/api/app/experience")
    def api_experience(body: dict = Body(...)):
        experience = body.get("experience")
        if not isinstance(experience, str) or experience not in {
            x["id"] for x in X.list_experiences() if x.get("available")
        }:
            raise HTTPException(400, "Profilo di esperienza non valido")
        C.save_settings(cfg, app={"experience": experience})
        return {"experience": experience}

    @router.post("/api/app/plugin")
    def api_plugin_toggle(body: dict = Body(...)):
        if body.get("id") == X.STORE_ID:
            raise HTTPException(400, "Lo store delle estensioni resta sempre attivo")
        disabled = set(cfg.app.get("disabled_plugins", []))
        (disabled.discard if body.get("enabled") else disabled.add)(body.get("id"))
        C.save_settings(cfg, app={"disabled_plugins": sorted(disabled)})
        return {"ok": True}

    @router.get("/themes/{tid}/{rel:path}")
    def theme_static(tid: str, rel: str):
        f = X.theme_file(cfg, tid, rel)
        if not f:
            raise HTTPException(404)
        return FileResponse(f, headers={"Cache-Control": "no-cache"})

    @router.get("/experiences/{experience_id}/{rel:path}")
    def experience_static(experience_id: str, rel: str):
        f = X.experience_file(experience_id, rel)
        if not f:
            raise HTTPException(404)
        media = "text/javascript" if f.suffix == ".js" else None
        return FileResponse(f, media_type=media, headers={"Cache-Control": "no-cache"})

    @router.get("/plugins/{pid}/{rel:path}")
    def plugin_static(pid: str, rel: str):
        f = X.plugin_file(cfg, pid, rel)
        if not f:
            raise HTTPException(404)
        media = "text/javascript" if f.suffix == ".js" else None
        return FileResponse(f, media_type=media, headers={"Cache-Control": "no-cache"})

    @router.post("/api/open")
    def api_open(body: dict = Body(...)):
        """Apre un link web nel browser predefinito (solo http/https)."""
        import webbrowser
        url_ = str(body.get("url") or "")
        if not url_.startswith(("https://", "http://")):
            raise HTTPException(400, "Sono ammessi solo link web")
        webbrowser.open(url_)
        return {"ok": True}

    return router
