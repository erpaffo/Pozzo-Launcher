"""Giochi aggiunti a mano."""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import stores as STORES
from ...library.build import build
from ... import i18n as I


def build_router(ctx) -> APIRouter:
    cfg, events, lib, user = ctx.cfg, ctx.events, ctx.lib, ctx.user
    router = APIRouter()

    @router.post("/api/manual")
    def api_manual_add(body: dict = Body(...)):
        import shlex
        if body.get("kind") == "browser":
            return _add_browser_game(body)
        exe = (body.get("exe") or "").strip().strip('"')
        if not exe or not Path(exe).is_file():
            raise HTTPException(400, I.tr("s.manual.select_exe"))
        title = (body.get("title") or "").strip() or Path(exe).stem
        args = [a.strip('"') for a in shlex.split(body.get("args") or "", posix=False)]
        kind = "app" if body.get("kind") == "app" else "game"
        mid = user.add_manual(title, exe, args, (body.get("cwd") or "").strip(), kind)
        return _refresh_manual(mid)

    def _add_browser_game(body: dict):
        """Gioco browser: URL http/https pubblico; titolo e metadati (Open Graph) letti dalla pagina.
        Se la pagina non e' raggiungibile il gioco si aggiunge lo stesso e l'errore torna in `warning`."""
        from urllib.parse import urlsplit
        from ...webmeta import WebMetaError, fetch_meta, validate_url
        try:
            url = validate_url(body.get("url") or "")
        except WebMetaError as e:
            raise HTTPException(400, str(e))
        meta, warning = {}, None
        try:
            meta = fetch_meta(url)
        except WebMetaError as e:
            warning = I.tr("s.manual.meta_unread", err=str(e))
        title = (body.get("title") or "").strip() or meta.get("title") or urlsplit(url).hostname
        mid = user.add_manual(title, url, [], "", "browser", meta)
        return {**_refresh_manual(mid), "warning": warning}

    @router.delete("/api/manual/{key:path}")
    def api_manual_delete(key: str):
        g = lib.by_key.get(key)
        if not g or g.get("store") != "manual":
            raise HTTPException(404)
        user.delete_manual(int(key.split(":", 1)[1]))
        return _refresh_manual()

    @router.post("/api/manual/dedupe")
    def api_manual_dedupe():
        removed = user.dedupe_manual()
        if removed:
            _refresh_manual()
        return {"removed": removed}

    manual_busy = {"n": 0}

    @router.get("/api/manual/state")
    def api_manual_state():
        """True finche' copertina e metadati dei giochi appena aggiunti a mano sono in cerca."""
        return {"busy": manual_busy["n"] > 0}

    def _refresh_manual(new_id: int | None = None):
        """Giochi aggiunti a mano: il gioco entra subito in libreria (aggiornamento solo delle voci a mano,
        senza riscansionare le ROM); copertina e metadati si cercano dopo, in background, solo per quel gioco."""
        import asyncio
        from ...cache import Cache
        from ...library.build import update_manual
        from ...stores import meta

        def apply():
            if not update_manual(cfg):  # libreria mai costruita: serve la costruzione completa
                build(cfg)
            lib.load()
            events.emit("library_built", {})

        def refresh(images: bool, key: str | None = None):
            cache = Cache(cfg.cache)
            try:
                asyncio.run(STORES.refresh(cfg, cache, only=["manual"], images=images))
                if key:
                    meta.search(cfg, cache, only_keys={key})  # database offline: veloce
            finally:
                cache.close()

        def later(key):
            try:
                refresh(True, key)
                apply()
            except Exception as e:  # il gioco e' gia' in libreria: la ricerca dei dati puo' fallire senza danni
                print(f"Dati del gioco aggiunto a mano: {type(e).__name__}: {e}")
            finally:
                manual_busy["n"] -= 1

        refresh(False)
        apply()
        key = f"windows/manual:{new_id}" if new_id else None
        if key:
            manual_busy["n"] += 1
            threading.Thread(target=later, args=(key,), daemon=True).start()
        return {"ok": True, "key": key}

    vars(ctx).update(_refresh_manual=_refresh_manual)
    return router
