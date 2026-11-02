"""Ricerca e gestione delle mod dei port installati."""

from __future__ import annotations

import zipfile

import httpx
from fastapi import APIRouter, Body, HTTPException

from ... import ports as PT
from ...cache import Cache


def build_router(ctx) -> APIRouter:
    cfg = ctx.cfg
    router = APIRouter()

    def _port(slug: str) -> dict:
        mod = PT.all_installed(cfg).get(slug)
        if not mod:
            raise HTTPException(404, "Port non installato")
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
            raise HTTPException(404, "Mod non trovata")
        try:
            installed = PT.install_mod(cfg, slug, selected)
        except (ValueError, OSError, RuntimeError, zipfile.BadZipFile, httpx.HTTPError) as error:
            raise HTTPException(400, f"Mod non installata: {error}") from error
        return installed.get("installed_mods") or {}

    @router.post("/api/mods/{slug}/{mod_id:path}/enabled")
    def api_mod_enabled(slug: str, mod_id: str, body: dict = Body(...)):
        _port(slug)
        if not isinstance(body.get("enabled"), bool):
            raise HTTPException(400, "Indica enabled come valore booleano")
        try:
            return PT.set_mod_enabled(cfg, slug, mod_id, body["enabled"]).get("installed_mods") or {}
        except KeyError as error:
            raise HTTPException(404, "Mod non installata") from error
        except (ValueError, OSError) as error:
            raise HTTPException(409, str(error)) from error

    @router.delete("/api/mods/{slug}/{mod_id:path}")
    def api_mod_remove(slug: str, mod_id: str):
        _port(slug)
        try:
            return PT.remove_mod(cfg, slug, mod_id).get("installed_mods") or {}
        except KeyError as error:
            raise HTTPException(404, "Mod non installata") from error
        except (ValueError, OSError) as error:
            raise HTTPException(409, str(error)) from error

    return router
