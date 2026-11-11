"""Copertine delle collezioni e collezioni intelligenti."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse

from .. import jobs as J
from ... import config as C
from ... import profilecfg as PC
from ... import i18n as I


def clean_filters(items: list, now_ms: int | None = None) -> list[dict]:
    """Normalizza i filtri salvati: nome, ricerca, filtri della barra, ordine e la vista (console/store/stato)."""
    now_ms = now_ms or int(time.time() * 1000)
    clean = []
    for it in items[:100]:
        f = it.get("f") if isinstance(it, dict) else None
        if not isinstance(f, dict) or not str(it.get("name") or "").strip():
            continue
        d = f.get("disc") if isinstance(f.get("disc"), dict) else {}
        v = f.get("view") if isinstance(f.get("view"), dict) else {}
        out = {**{k: str(f.get(k) or "")[:80] for k in ("lang", "sort", "group", "search", "inst")},
               "disc": {k: str(d.get(k) or "")[:40] for k in ("preset", "genre", "decade")}}
        if v.get("type") in ("all", "platform", "store", "status"):
            out["view"] = {"type": v["type"], "id": str(v.get("id") or "")[:60]}
        clean.append({"id": str(it.get("id") or "")[:40] or f"f{now_ms}{len(clean)}",
                      "name": str(it["name"]).strip()[:80], "f": out})
    return clean


def build_router(ctx) -> APIRouter:
    _claim, _thumb, cfg, events, job, lib = ctx._claim, ctx._thumb, ctx.cfg, ctx.events, ctx.job, ctx.lib
    user, view = ctx.user, ctx.view
    router = APIRouter()

    # ------------------------------------------------------------ immagini delle collezioni
    # icona: logo da Wikipedia, altrimenti il logo (wheel) del gioco piu' votato della collezione;
    # copertina: grafica (hero/fanart/screenshot) del gioco piu' votato, altrimenti l'immagine di Wikipedia
    art_state: dict = {"key": None, "map": {}, "rev": 0}
    ART_COVER = ("hero", "fanart", "screenshot", "header", "title")
    ART_ICON = ("wheel", "logo", "marquee")

    def _art_map() -> dict:
        key = (lib.built_at, art_state["rev"], len(user.edits()), len(user.collections()))  # anche collezioni modificate
        if art_state["key"] == key:
            return art_state["map"]
        from ...cache import Cache
        v = view()
        c = Cache(cfg.cache)
        try:
            wiki = {k[8:]: json.loads(val) for k, val in c.db.execute("SELECT k, v FROM kv WHERE k LIKE 'collart:%'")}
        finally:
            c.close()
        out = {}
        for slug, col in v["colls"].items():
            games = []
            for grp in col["groups"]:
                d = v["groups"].get(grp)
                g = lib.by_id.get(d["primary"]) if d else None
                if g and g.get("store") != "online":
                    games.append(g)
            games.sort(key=lambda g: (-(g.get("rating") or 0) * min(g.get("rating_count") or 1, 200), g["title"]))
            w = wiki.get(slug) or {}
            ent = {"page": w.get("page")}
            icon_g = next((g for g in games for k in ART_ICON if k in g["media"]), None)
            if w.get("icon"):
                ent["icon"] = ("file", w["icon"])
            elif icon_g:
                ent["icon"] = ("game", icon_g["id"], next(k for k in ART_ICON if k in icon_g["media"]))
            cov_g = next((g for g in games for k in ART_COVER if k in g["media"]), None)
            if cov_g:
                ent["cover"] = ("game", cov_g["id"], next(k for k in ART_COVER if k in cov_g["media"]))
            elif w.get("cover"):
                ent["cover"] = ("file", w["cover"])
            elif games and "cover" in games[0]["media"]:
                ent["cover"] = ("game", games[0]["id"], "cover")
            ent["poster"] = next((g["id"] for g in games if "cover" in g["media"]), None)
            out[slug] = ent
        art_state.update(key=key, map=out)
        return out

    @router.get("/coll-img/{slug}/{kind}")
    def coll_img(slug: str, kind: str, request: Request, w: int = 0):
        from fastapi.responses import RedirectResponse
        ent = _art_map().get(slug)
        src = (ent or {}).get(kind)
        if not src:
            raise HTTPException(404)
        if src[0] == "game":
            return RedirectResponse(f"/img/{src[1]}/{src[2]}" + (f"?w={w}" if w else ""), status_code=307)
        p = Path(cfg.cache) / "collart" / src[1]
        if not p.exists():
            raise HTTPException(404)
        if w and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            try:
                p = _thumb(p, min(max(w, 32), 1600))
            except Exception:
                pass
        return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})

    @router.get("/api/collart")
    def api_collart_state():
        st = job["collart"].state()
        m = _art_map()
        st["with_icon"] = sum(1 for e in m.values() if e.get("icon"))
        st["with_wiki"] = sum(1 for e in m.values() if e.get("icon", ("",))[0] == "file")
        st["total"] = len(m)
        return st

    @router.post("/api/collart")
    def api_collart_start(body: dict = Body(default={})):
        return _start_collart(body.get("mode", "missing") != "all")

    def _start_collart(only_missing=True):
        if job["collart"].status == "running":
            raise HTTPException(409, I.tr("s.collart.already_running"))
        v = view()
        cols = [(slug, c["name"]) for slug, c in v["colls"].items() if c["groups"]]
        j = J.CollArtJob(collections=cols, only_missing=only_missing)
        if not _claim("collart", j):
            raise HTTPException(409, I.tr("s.collart.already_running"))

        def after(_stats):
            art_state["rev"] += 1
            events.emit("collart_done", _stats)

        threading.Thread(target=j.run, args=(cfg, after), daemon=True).start()
        return j.state()

    @router.post("/api/collart/cancel")
    def api_collart_cancel():
        job["collart"].stop = True
        return job["collart"].state()

    def _collart_auto():
        time.sleep(45)  # dopo l'avvio: scarica in sottofondo le immagini mancanti delle collezioni
        try:
            if lib.games and job["collart"].status != "running":
                _start_collart(True)
        except Exception as e:
            print(f"Immagini collezioni: {e}")

    threading.Thread(target=_collart_auto, daemon=True).start()

    # ------------------------------------------------------------ collezioni intelligenti (regole salvate)
    @router.post("/api/smart")
    def api_smart_save(body: dict = Body(...)):
        items = body.get("items")
        if not isinstance(items, list):
            raise HTTPException(400, I.tr("s.collart.list_invalid"))
        clean = []
        for it in items[:200]:
            if not isinstance(it, dict) or not str(it.get("name") or "").strip():
                continue
            clean.append({"id": str(it.get("id") or "")[:40] or f"s{int(time.time() * 1000)}",
                          "name": str(it["name"]).strip()[:80], "icon": str(it.get("icon") or "⚡")[:4],
                          "rules": it.get("rules") if isinstance(it.get("rules"), dict) else {}})
        C.save_settings(cfg, app={"smart_collections": clean})
        cfg.app["smart_collections"] = clean
        return {"items": clean}

    # ------------------------------------------------------------ filtri salvati (combinazioni di filtri con nome, per profilo)
    def _saved_filters():
        v = PC.get(cfg, "saved_filters")
        if v is None and PC.active(cfg) == "default":  # prima erano globali in settings.json
            v = cfg.app.get("saved_filters")
        return v if isinstance(v, list) else []

    @router.get("/api/filters")
    def api_filters():
        return {"items": _saved_filters()}

    @router.post("/api/filters")
    def api_filters_save(body: dict = Body(...)):
        items = body.get("items")
        if not isinstance(items, list):
            raise HTTPException(400, I.tr("s.collart.list_invalid"))
        clean = clean_filters(items)
        PC.set(cfg, "saved_filters", clean)
        return {"items": clean}

    return router
