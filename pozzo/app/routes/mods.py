"""Ricerca e gestione delle mod: port installati e giochi PC della libreria (Thunderstore)."""

from __future__ import annotations

import threading
import zipfile

from pathlib import Path

import httpx
from fastapi import APIRouter, Body, HTTPException

from ... import gamemods as GM
from ... import modsites as MS
from ... import ports as PT
from ... import i18n as I
from ...cache import Cache


def build_router(ctx) -> APIRouter:
    cfg, lib, user = ctx.cfg, ctx.lib, ctx.user
    router = APIRouter()
    jobs: dict[int, dict] = {}  # gid -> installazione in corso o finita (una per gioco)
    jobs_lock = threading.Lock()

    @router.get("/api/game/{gid}/mod-sites")
    def api_game_mod_sites(gid: int):
        """Siti di mod per un titolo famoso della libreria (tabella curata, nessuna ricerca per gioco)."""
        g = lib.by_id.get(gid)
        if not g:
            raise HTTPException(404, I.tr("s.mods.gameNotFound"))
        return {"sites": MS.sites_for(g["title"], g.get("canonical") or "", platform=g["platform"])}

    # ------------------------------------------------------------ giochi PC della libreria
    def _game(gid: int) -> dict:
        """Il gioco sempre dalla libreria per id: nessun percorso arriva dalla richiesta."""
        if gid not in lib.by_id:
            raise HTTPException(404, I.tr("s.mods.gameNotFound"))
        return lib.game(gid)

    def _index(g: dict) -> dict:
        slug = GM.community(g)
        if not slug:
            raise HTTPException(404, I.tr("s.mods.notFound"))
        cache = Cache(cfg.cache)
        try:
            return {x["id"]: x for x in GM.catalog(cache, slug)}
        finally:
            cache.close()

    def _fail(error: Exception):
        """Errori delle mod dei giochi -> HTTP con testo tradotto."""
        if isinstance(error, KeyError):
            return HTTPException(404, I.tr("s.mods.notInstalled"))
        if isinstance(error, GM.ModError):
            return HTTPException(409, I.tr(error.key, **error.kw))
        return HTTPException(400, I.tr("s.mods.notInstalledErr", err=error))

    _ERRORS = (KeyError, ValueError, OSError, RuntimeError, zipfile.BadZipFile, httpx.HTTPError)

    def _installed(g: dict) -> dict:
        mods = user.game_mods(g["key"])
        return {i: {**r, "required_by": GM.needed_by(mods, i)} for i, r in mods.items()}

    @router.get("/api/game/{gid}/mods")
    def api_game_mods(gid: int, q: str = ""):
        """Mod installabili (Thunderstore + BepInEx) del gioco; se non si puo', solo i link ai siti."""
        g = _game(gid)
        slug = GM.community(g)
        sites = MS.sites_for(g["title"], g.get("canonical") or "", platform=g["platform"])
        folder = g.get("install_dir") or ""
        out = {"supported": bool(slug), "community": slug, "sites": sites, "installed": _installed(g),
               "game_installed": bool(folder) and Path(folder).is_dir(), "items": []}
        if not slug:
            return out
        index = _index(g)
        words = q.lower().split()
        for item in index.values():
            text = f"{item.get('name')} {item.get('owner')} {item.get('description')}".lower()
            if all(w in text for w in words):
                out["items"].append({**item, "installable": GM.installable(index, item["id"])})
                if len(out["items"]) >= 50:
                    break
        return out

    @router.post("/api/game/{gid}/mods/preview")
    def api_game_mods_preview(gid: int, body: dict = Body(...)):
        g = _game(gid)
        index = _index(g)
        if body.get("id") not in index:
            raise HTTPException(404, I.tr("s.mods.notFound"))
        try:
            return GM.preview(cfg, user, g, index, body["id"])
        except _ERRORS as error:
            raise _fail(error) from error

    @router.post("/api/game/{gid}/mods/install")
    def api_game_mods_install(gid: int, body: dict = Body(...)):
        """Installa in background (mod + dipendenze); lo stato si legge da /api/game/{gid}/mods/job."""
        g = _game(gid)
        index = _index(g)
        mod_id = body.get("id")
        if mod_id not in index:
            raise HTTPException(404, I.tr("s.mods.notFound"))
        try:  # errori certi (gioco non installato o aperto, loader non supportato) subito, non nel job
            GM._check(GM.game_dest(cfg, user, g))
            GM.plan(index, mod_id)
        except _ERRORS as error:
            raise _fail(error) from error
        with jobs_lock:  # due installazioni insieme scriverebbero negli stessi file del gioco
            if (jobs.get(gid) or {}).get("status") == "running":
                raise HTTPException(409, I.tr("s.mods.jobRunning"))
            job = jobs[gid] = {"id": max((j["id"] for j in jobs.values()), default=0) + 1, "status": "running",
                               "mod": mod_id, "log": [], "done": 0, "total": 0, "error": ""}

        def run():
            try:
                GM.install(cfg, user, g, index, mod_id, say=job["log"].append,
                           progress=lambda done, total: job.update(done=done, total=total))
                job["status"] = "done"
            except Exception as error:  # qualunque errore finisce nello stato del job, non nel vuoto
                job.update(status="error", error=_fail(error).detail)
        threading.Thread(target=run, daemon=True).start()
        return job

    @router.get("/api/game/{gid}/mods/job")
    def api_game_mods_job(gid: int):
        _game(gid)
        return jobs.get(gid) or {"id": 0, "status": "idle", "mod": "", "log": [], "done": 0, "total": 0, "error": ""}

    @router.post("/api/game/{gid}/mods/{mod_id}/enabled")
    def api_game_mod_enabled(gid: int, mod_id: str, body: dict = Body(...)):
        g = _game(gid)
        if not isinstance(body.get("enabled"), bool):
            raise HTTPException(400, I.tr("s.mods.enabledBool"))
        try:
            GM.set_enabled(cfg, user, g, mod_id, body["enabled"])
        except _ERRORS as error:
            raise _fail(error) from error
        return _installed(g)

    @router.delete("/api/game/{gid}/mods/{mod_id}")
    def api_game_mod_remove(gid: int, mod_id: str):
        g = _game(gid)
        try:
            GM.remove(cfg, user, g, mod_id)
        except _ERRORS as error:
            raise _fail(error) from error
        return _installed(g)

    # ------------------------------------------------------------ port
    def _port(slug: str) -> dict:
        mod = PT.all_installed(cfg).get(slug)
        if not mod:
            raise HTTPException(404, I.tr("s.mods.portNotInstalled"))
        return mod

    @router.get("/api/mods/{slug}")
    def api_mods(slug: str):
        mod = _port(slug)
        cache = Cache(cfg.cache)
        try:
            items = PT.mod_list(cache, mod.get("mods") or {}, mod.get("games") or [mod.get("name")],
                                mod.get("consoles") or [])
        finally:
            cache.close()
        sources = [{"provider": item.get("provider"), "url": item.get("sourceUrl")}
                   for item in (mod.get("mods") or {}).get("sources") or []
                   if isinstance(item, dict)]
        return {"items": items, "links": sources, "installed": mod.get("installed_mods") or {}}

    @router.post("/api/mods/{slug}/install")
    def api_mod_install(slug: str, body: dict = Body(...)):
        mod = _port(slug)
        cache = Cache(cfg.cache)
        try:
            items = PT.mod_list(cache, mod.get("mods") or {}, mod.get("games") or [mod.get("name")],
                                mod.get("consoles") or [])
        finally:
            cache.close()
        selected = next((item for item in items if item.get("id") == body.get("id")), None)
        if not selected:
            raise HTTPException(404, I.tr("s.mods.notFound"))
        try:
            installed = PT.install_mod(cfg, slug, selected)
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile, httpx.HTTPError) as error:
            raise HTTPException(400, I.tr("s.mods.notInstalledErr", err=error)) from error
        return installed.get("installed_mods") or {}

    @router.post("/api/mods/{slug}/{mod_id:path}/enabled")
    def api_mod_enabled(slug: str, mod_id: str, body: dict = Body(...)):
        _port(slug)
        if not isinstance(body.get("enabled"), bool):
            raise HTTPException(400, I.tr("s.mods.enabledBool"))
        try:
            return PT.set_mod_enabled(cfg, slug, mod_id, body["enabled"]).get("installed_mods") or {}
        except KeyError as error:
            raise HTTPException(404, I.tr("s.mods.notInstalled")) from error
        except (ValueError, OSError) as error:
            raise HTTPException(409, str(error)) from error

    @router.delete("/api/mods/{slug}/{mod_id:path}")
    def api_mod_remove(slug: str, mod_id: str):
        _port(slug)
        try:
            return PT.remove_mod(cfg, slug, mod_id).get("installed_mods") or {}
        except KeyError as error:
            raise HTTPException(404, I.tr("s.mods.notInstalled")) from error
        except (ValueError, OSError) as error:
            raise HTTPException(409, str(error)) from error

    return router
