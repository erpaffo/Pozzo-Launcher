"""Impostazioni dell'app, temi, esperienze, plugin."""

from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from .. import extensions as X
from ... import config as C, profilecfg as PC
from ...library import automation as A, fastcopy as FC, launcher as L
from ... import i18n as I


DEFAULT_EXP_PROFILES = (
    {"id": "classico", "nome": "Classico", "experience": "catalog", "theme": "default", "animations": "normal"},
    {"id": "cinema-serata", "nome": "Cinema serata", "experience": "cinema", "theme": "default", "animations": "reduced"},
    {"id": "console-tv", "nome": "Console TV", "experience": "console", "theme": "default", "animations": "reduced"},
    {"id": "leggero", "nome": "Leggero", "experience": "catalog", "theme": "default", "animations": "off"},
)
EXP_PROFILE_ANIMATIONS = frozenset(("normal", "reduced", "off"))
EXP_PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}\Z")
WEBHOOK_EVENTS = ("gioco_avviato", "gioco_chiuso", "download_finito", "prezzo_sceso")
WEBHOOK_MAX = 20


def _webhook_url(value) -> str:
    url = str(value or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise HTTPException(400, I.tr("s.appsettings.webhookScheme"))
    return url


def _public_webhooks(hooks) -> list[dict]:
    """Webhook per il browser: il segreto non esce mai, solo has_secret."""
    return [{**{k: v for k, v in h.items() if k != "secret"}, "has_secret": bool(h.get("secret"))} for h in hooks or []]


def _old_secret(old_hooks, item: dict) -> str:
    """Segreto gia' salvato per la riga: si cerca per indirizzo originale («orig», dalla GET) o per indirizzo."""
    want = [str(item.get(k) or "").strip() for k in ("orig", "url")]
    return next((str(h.get("secret") or "") for u in want if u for h in old_hooks or [] if h.get("url") == u), "")


def _clean_webhooks(items, old_hooks=None) -> list[dict]:
    """secret vuoto = resta quello salvato; clear_secret = lo toglie; un valore nuovo lo sostituisce."""
    if not isinstance(items, list):
        raise HTTPException(400, I.tr("s.appsettings.webhooksNotList"))
    if len(items) > WEBHOOK_MAX:
        raise HTTPException(400, I.tr("s.appsettings.webhookMax", n=WEBHOOK_MAX))
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(400, I.tr("s.appsettings.webhookInvalid"))
        events = item.get("events") or []
        if not isinstance(events, list) or not all(e in WEBHOOK_EVENTS for e in events):
            raise HTTPException(400, I.tr("s.appsettings.webhookEventUnknown"))
        hook = {
            "url": _webhook_url(item.get("url")),
            "events": [e for e in WEBHOOK_EVENTS if e in events],  # ordine fisso, senza duplicati
            "enabled": bool(item.get("enabled", True)),
        }
        secret = "" if item.get("clear_secret") else (str(item.get("secret") or "").strip() or _old_secret(old_hooks, item))
        if secret:
            hook["secret"] = secret
        out.append(hook)
    return out


def build_router(ctx) -> APIRouter:
    cfg, plugin_errors, thumbs_dir = ctx.cfg, ctx.plugin_errors, ctx.thumbs_dir
    router = APIRouter()

    def _exp_profiles() -> list[dict]:
        saved = PC.get(cfg, "exp_profiles")
        if not isinstance(saved, list):
            return [dict(item) for item in DEFAULT_EXP_PROFILES]
        return [
            {key: item[key] for key in ("id", "nome", "experience", "theme", "animations")}
            for item in saved
            if isinstance(item, dict)
            and all(isinstance(item.get(key), str) for key in ("id", "nome", "experience", "theme", "animations"))
            and EXP_PROFILE_ID.fullmatch(item["id"])
            and item["nome"].strip()
        ]

    def _resolved_exp_profile(item: dict) -> dict:
        experiences = {x["id"] for x in X.list_experiences() if x.get("available")}
        themes = {x["id"] for x in X.list_themes(cfg)}
        return {
            "experience": item["experience"] if item["experience"] in experiences else "catalog",
            "theme": item["theme"] if item["theme"] in themes else "default",
            "animations": item["animations"] if item["animations"] in EXP_PROFILE_ANIMATIONS else "normal",
        }

    def _exp_profiles_state() -> dict:
        presets = _exp_profiles()
        experiences = {x["id"] for x in X.list_experiences() if x.get("available")}
        themes = {x["id"] for x in X.list_themes(cfg)}
        current = {
            "experience": PC.get(cfg, "experience", "catalog"),
            "theme": PC.get(cfg, "theme", "default"),
            "animations": PC.get(cfg, "exp_animations"),
        }
        current_resolved = {
            "experience": current["experience"] if isinstance(current["experience"], str)
            and current["experience"] in experiences else "catalog",
            "theme": current["theme"] if isinstance(current["theme"], str) and current["theme"] in themes else "default",
            "animations": current["animations"] if isinstance(current["animations"], str)
            and current["animations"] in EXP_PROFILE_ANIMATIONS else None,
        }
        active = next((p["id"] for p in presets if _resolved_exp_profile(p) == current_resolved), None)
        return {"profiles": presets, "active": active, "animations": current["animations"]}

    # ------------------------------------------------------------ temi, plugin, link esterni
    @router.get("/api/extensions")
    def api_extensions():
        themes = X.list_themes(cfg)
        active = PC.get(cfg, "theme", "default")
        if not isinstance(active, str) or active not in {t["id"] for t in themes}:
            active = "default"
        exp = PC.get(cfg, "experience", "catalog")  # come X.active_experience, ma del profilo
        if exp not in {i["id"] for i in X.list_experiences() if i.get("available")}:
            exp = "catalog"
        return {"themes": themes, "active_theme": active, "active_experience": exp,
                "experiences": X.list_experiences(),
                "plugins": X.list_plugins(cfg, plugin_errors), "load_total_ms": X.LOAD_TOTAL_MS,
                **X.media_registry(),
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
        if body.get("splash") is False:
            conf["splash"] = False  # default acceso: si salva solo lo spento
        C.save_settings(cfg, app={"launch": conf})
        cfg.app["launch"] = conf
        return conf

    @router.get("/api/app/scripts")
    def api_scripts():
        return cfg.app.get(A.GLOBAL_KEY) or {}

    @router.post("/api/app/scripts")
    def api_scripts_save(body: dict = Body(...)):
        """Script globali su gioco avviato, gioco chiuso, download finito (stesse variabili POZZO_* dei profili)."""
        conf = {k: str(body.get(k) or "").strip() for k in A.GLOBAL_EVENTS.values()}
        conf = {k: v for k, v in conf.items() if v}
        C.save_settings(cfg, app={A.GLOBAL_KEY: conf})
        cfg.app[A.GLOBAL_KEY] = conf
        return conf

    # ------------------------------------------------------------ copia veloce da disco
    def _fastcopy_default() -> Path:
        return Path(cfg.cache) / "fastcopy"

    def _fastcopy_state() -> dict:
        fc = cfg.app.get("fastcopy") or {}
        raw = fc.get("dir") if isinstance(fc.get("dir"), str) else ""
        delete_after = fc.get("delete_after")
        effective = Path(raw).expanduser() if raw else _fastcopy_default()
        free_gb = None
        try:  # spazio libero della cartella, o del primo genitore esistente
            probe = next(p for p in (effective, *effective.parents) if p.exists())
            free_gb = round(shutil.disk_usage(probe).free / 1024 ** 3, 1)
        except (OSError, StopIteration):
            pass
        return {"dir": raw, "delete_after": delete_after if isinstance(delete_after, bool) else True,
                "default_dir": str(_fastcopy_default()), "free_gb": free_gb}

    def _fastcopy_check_dir(raw: str) -> str:
        p = Path(raw).expanduser().resolve()
        if p.parent == p:
            raise HTTPException(400, I.tr("s.appsettings.fastcopyRoot"))
        if p == Path.home().resolve():
            raise HTTPException(400, I.tr("s.appsettings.fastcopyHome"))
        for r in C.rom_roots(cfg):  # le copie si svuotano: mai dentro (o sopra) la libreria
            r = r.expanduser().resolve()
            if p == r or r in p.parents or p in r.parents:
                raise HTTPException(400, I.tr("s.appsettings.fastcopyInLibrary"))
        try:
            if p.exists():
                if not p.is_dir():
                    raise HTTPException(400, I.tr("s.appsettings.pathIsFile"))
                # a fine gioco la cartella puo' essere svuotata: non toccare cartelle altrui
                if any(p.iterdir()) and not (p / FC.MARKER).exists():
                    raise HTTPException(400, I.tr("s.appsettings.folderNotEmpty"))
            p.mkdir(parents=True, exist_ok=True)
            (p / FC.MARKER).touch()  # ora e' nostra: purge_stale la puo' svuotare
        except OSError as e:
            raise HTTPException(400, I.tr("s.appsettings.folderUnusable", err=e.strerror or e))
        return str(p)

    @router.get("/api/app/fastcopy")
    def api_fastcopy_get():
        return _fastcopy_state()

    @router.post("/api/app/fastcopy")
    def api_fastcopy_save(body: dict = Body(...)):
        """Cartella della copia veloce e cancellazione a fine partita. I campi non inviati restano."""
        fc = dict(cfg.app.get("fastcopy") or {})
        if "delete_after" in body:
            if not isinstance(body["delete_after"], bool):
                raise HTTPException(400, I.tr("s.appsettings.deleteAfterBool"))
            fc["delete_after"] = body["delete_after"]
        if "dir" in body:
            if not isinstance(body["dir"], str):
                raise HTTPException(400, I.tr("s.appsettings.folderInvalid"))
            raw = body["dir"].strip()
            if raw:
                fc["dir"] = _fastcopy_check_dir(raw)
            else:  # vuota = cartella predefinita
                fc.pop("dir", None)
        C.save_settings(cfg, app={"fastcopy": fc})
        cfg.app["fastcopy"] = fc
        return _fastcopy_state()

    @router.get("/api/app/crash-fallback")
    def api_crash_get():
        return {"mode": cfg.app.get("crash_fallback", "propose")}

    @router.post("/api/app/crash-fallback")
    def api_crash_set(body: dict = Body(...)):
        """Crash all'avvio: propose un'alternativa, la applica da sola o non fa niente."""
        mode = str(body.get("mode") or "")
        if mode not in ("propose", "apply", "off"):
            raise HTTPException(400, "crash_fallback: propose, apply o off")
        C.save_settings(cfg, app={"crash_fallback": mode})
        cfg.app["crash_fallback"] = mode
        return api_crash_get()

    @router.get("/api/library/watch")
    def api_watch_get():
        """Stato del rilevamento automatico delle cartelle ROM (impostazioni › Libreria)."""
        return ctx.watcher.status()

    @router.post("/api/app/watch-roms")
    def api_watch_set(body: dict = Body(...)):
        """Acceso/spento a caldo: il watcher rilegge l'impostazione a ogni passaggio."""
        on = bool(body.get("enabled"))
        conf = {**(cfg.app.get("watch_roms") if isinstance(cfg.app.get("watch_roms"), dict) else {}), "enabled": on}
        C.save_settings(cfg, app={"watch_roms": conf})
        cfg.app["watch_roms"] = conf
        return ctx.watcher.status()

    @router.get("/api/app/merge-stores")
    def api_merge_get():
        from ...library.build import DEFAULT_STORE_PREF
        return {"enabled": cfg.app.get("merge_stores") is not False, "order": cfg.app.get("store_order") or DEFAULT_STORE_PREF}

    @router.post("/api/app/merge-stores")
    def api_merge_set(body: dict = Body(...)):
        """Vale dalla prossima ricostruzione della libreria (le voci salvate non si toccano)."""
        conf = {"merge_stores": bool(body.get("enabled"))}
        if "order" in body:
            conf["store_order"] = [x.strip().lower() for x in body["order"] if isinstance(x, str) and x.strip()]
        C.save_settings(cfg, app=conf)
        cfg.app.update(conf)
        return api_merge_get()

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
            notify.send(cfg, "Pozzo Launcher", I.tr("s.appsettings.notifyOn"))
        return {"enabled": on}

    @router.get("/api/webhooks")
    def api_webhooks_get():
        return {"webhooks": _public_webhooks(cfg.app.get("webhooks"))}

    @router.post("/api/webhooks")
    def api_webhooks_set(body: dict = Body(...)):
        hooks = _clean_webhooks(body.get("webhooks"), cfg.app.get("webhooks"))
        C.save_settings(cfg, app={"webhooks": hooks})
        cfg.app["webhooks"] = hooks
        return {"webhooks": _public_webhooks(hooks)}

    @router.post("/api/webhooks/test")
    def api_webhooks_test(body: dict = Body(...)):
        from ... import webhooks  # modulo scritto a parte: importato solo quando serve
        url = _webhook_url(body.get("url"))
        secret = "" if body.get("clear_secret") else (str(body.get("secret") or "").strip()
                                                      or _old_secret(cfg.app.get("webhooks"), body))
        ok, msg = webhooks.send_test(url, secret or None)
        return {"ok": bool(ok), "msg": msg}

    @router.get("/api/app/power")
    def api_power_get():
        from ... import power
        return {"after_jobs": cfg.app.get("after_jobs") or "none", "modes": list(power.MODES), **power.pending()}

    @router.get("/api/app/start-bigpicture")
    def api_startbp_get():
        return {"enabled": bool(cfg.app.get("start_bigpicture", False))}

    @router.post("/api/app/start-bigpicture")
    def api_startbp_set(body: dict = Body(...)):
        on = bool(body.get("enabled"))
        C.save_settings(cfg, app={"start_bigpicture": on})
        cfg.app["start_bigpicture"] = on
        return {"enabled": on}

    @router.post("/api/app/power")
    def api_power_set(body: dict = Body(...)):
        """Cosa fare al termine delle operazioni lunghe: niente, sospendi o spegni il PC."""
        from ... import power
        mode = str(body.get("after_jobs") or "none")
        if mode not in power.MODES:
            raise HTTPException(400, I.tr("s.appsettings.choiceInvalid"))
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
            raise HTTPException(400, I.tr("s.appsettings.platformMissing"))
        cur = [p for p in (cfg.app.get("hide_dlc") or []) if p != pid]
        if body.get("hide"):
            cur.append(pid)
        C.save_settings(cfg, app={"hide_dlc": cur})
        return {"hide_dlc": cfg.app.get("hide_dlc") or []}

    @router.get("/api/app/video-snap")
    def api_video_snap_get():
        return {"enabled": bool(cfg.app.get("video_snap")), "max_mb": int(cfg.app.get("video_max_mb") or 30)}

    @router.post("/api/app/video-snap")
    def api_video_snap_set(body: dict = Body(...)):
        """«Scarica video snap»: spento di default (disco e banda). max_mb e' il tetto per file (5-500)."""
        upd = {"video_snap": bool(body.get("enabled"))}
        if "max_mb" in body:
            upd["video_max_mb"] = max(5, min(500, int(body["max_mb"] or 30)))
        C.save_settings(cfg, app=upd)
        return api_video_snap_get()

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
            raise HTTPException(404, I.tr("s.appsettings.themeNotFound"))
        PC.put(cfg, "theme", tid, mirror=True)
        return {"ok": True}

    @router.post("/api/app/experience")
    def api_experience(body: dict = Body(...)):
        experience = body.get("experience")
        if not isinstance(experience, str) or experience not in {
            x["id"] for x in X.list_experiences() if x.get("available")
        }:
            raise HTTPException(400, I.tr("s.appsettings.expInvalid"))
        PC.put(cfg, "experience", experience, mirror=True)
        return {"experience": experience}

    @router.get("/api/exp-profiles")
    def api_exp_profiles():
        return _exp_profiles_state()

    @router.post("/api/exp-profiles")
    def api_exp_profiles_save(body: dict = Body(...)):
        name = body.get("nome")
        experience = body.get("experience")
        theme = body.get("theme")
        animations = body.get("animations")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40:
            raise HTTPException(400, I.tr("s.appsettings.nameInvalid"))
        if not isinstance(experience, str) or experience not in {
            x["id"] for x in X.list_experiences() if x.get("available")
        }:
            raise HTTPException(400, I.tr("s.appsettings.expInvalid"))
        if not isinstance(theme, str) or theme not in {x["id"] for x in X.list_themes(cfg)}:
            raise HTTPException(400, I.tr("s.appsettings.themeInvalid"))
        if not isinstance(animations, str) or animations not in EXP_PROFILE_ANIMATIONS:
            raise HTTPException(400, I.tr("s.appsettings.animInvalid"))

        presets = _exp_profiles()
        profile_id = body.get("id")
        if profile_id is None:
            slug = unicodedata.normalize("NFKD", name.strip().lower()).encode("ascii", "ignore").decode("ascii")
            slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-") or "profilo"
            profile_id = f"{slug[:28]}-{uuid.uuid4().hex[:8]}"
        elif not isinstance(profile_id, str) or not EXP_PROFILE_ID.fullmatch(profile_id):
            raise HTTPException(400, I.tr("s.appsettings.profileIdInvalid"))

        preset = {"id": profile_id, "nome": name.strip(), "experience": experience,
                  "theme": theme, "animations": animations}
        presets = [p for p in presets if p["id"] != profile_id]
        presets.append(preset)
        PC.set(cfg, "exp_profiles", presets)
        return _exp_profiles_state()

    @router.delete("/api/exp-profiles")
    def api_exp_profiles_delete(body: dict = Body(...)):
        profile_id = body.get("id")
        if not isinstance(profile_id, str) or not EXP_PROFILE_ID.fullmatch(profile_id):
            raise HTTPException(400, I.tr("s.appsettings.profileIdInvalid"))
        presets = _exp_profiles()
        remaining = [p for p in presets if p["id"] != profile_id]
        if len(remaining) == len(presets):
            raise HTTPException(404, I.tr("s.appsettings.presetNotFound"))
        PC.set(cfg, "exp_profiles", remaining)
        return _exp_profiles_state()

    @router.post("/api/exp-profiles/activate")
    def api_exp_profiles_activate(body: dict = Body(...)):
        profile_id = body.get("id")
        preset = next((p for p in _exp_profiles() if p["id"] == profile_id), None)
        if preset is None:
            raise HTTPException(404, I.tr("s.appsettings.presetNotFound"))
        resolved = _resolved_exp_profile(preset)
        PC.put(cfg, "experience", resolved["experience"], mirror=True)
        PC.put(cfg, "theme", resolved["theme"], mirror=True)
        PC.set(cfg, "exp_animations", resolved["animations"])
        return {"active": profile_id, **resolved}

    @router.post("/api/app/plugin")
    def api_plugin_toggle(body: dict = Body(...)):
        if body.get("id") == X.STORE_ID:
            raise HTTPException(400, I.tr("s.appsettings.extStoreAlwaysOn"))
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
            raise HTTPException(400, I.tr("s.appsettings.onlyWebLinks"))
        webbrowser.open(url_)
        return {"ok": True}

    return router
