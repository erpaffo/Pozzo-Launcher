"""Avvio da tasto, Sunshine/Moonlight, gioco in corso."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import config as C
from ... import i18n as I


def build_router(ctx) -> APIRouter:
    api_play, cfg, ds, launcher, lib, view = ctx.api_play, ctx.cfg, ctx.ds, ctx.launcher, ctx.lib, ctx.view
    router = APIRouter()

    @router.post("/api/play-key")
    def api_play_key(body: dict = Body(...)):
        g = lib.by_key.get(str(body.get("key") or ""))
        if not g:
            raise HTTPException(404, I.tr("s.stream.gameNotInLibrary"))
        api_play(g["id"])
        return {"ok": True, "title": g["title"], "id": g["id"]}

    # ------------------------------------------------------------ streaming con Sunshine / Moonlight
    from ...remote import sunshine as SUN

    def _sun_conf() -> dict:
        return dict(cfg.app.get("sunshine") or {})

    def _sun_save(conf: dict):
        cfg.app["sunshine"] = conf
        C.save_settings(cfg, app={"sunshine": conf})

    def _stream_games(limit: int) -> list[dict]:
        v = view()
        out, seen = [], set()

        def add(g):
            if g and g["grp"] not in seen and (g.get("installed") if g.get("store") else True) and g.get("store") != "online":
                seen.add(g["grp"])
                out.append({"key": g["key"], "title": g["title"], "id": g["id"]})
        prim = [lib.by_id.get(d["primary"]) for d in v["groups"].values()]
        gd = {g["grp"]: v["groups"][g["grp"]] for g in prim if g}
        for g in sorted((g for g in prim if g and gd[g["grp"]].get("status") == "playing"), key=lambda g: -gd[g["grp"]]["last_played"]):
            add(g)
        for g in sorted((g for g in prim if g and gd[g["grp"]]["favorite"]), key=lambda g: g["sort_title"] or ""):
            add(g)
        for g in sorted((g for g in prim if g and gd[g["grp"]]["last_played"]), key=lambda g: -gd[g["grp"]]["last_played"]):
            add(g)
        return out[:limit]

    @router.get("/api/sunshine")
    def api_sunshine():
        d = SUN.install_dir()
        conf = _sun_conf()
        st = {"installed": bool(d), "service": SUN.service_state(), "start_mode": SUN.start_mode() if d else "",
              "user": conf.get("user", ""),
              "has_password": bool(conf.get("password")), "count": conf.get("count", 24),
              "last": conf.get("last"), "web": SUN.API, "apps": None, "error": ""}
        if d and conf.get("user") and conf.get("password") and st["service"] != "stopped":
            try:
                s = SUN.Sunshine.from_conf(conf, _sun_save)
                try:
                    st["apps"] = [{"name": a.get("name"), "ours": SUN.ours(a)} for a in s.apps()]
                finally:
                    s.close()
            except Exception as e:
                st["error"] = str(e) if isinstance(e, PermissionError) else I.tr("s.stream.sunshineDown", kind=type(e).__name__)
        st["preview"] = [g["title"] for g in _stream_games(int(st["count"]))]
        return st

    @router.post("/api/sunshine")
    def api_sunshine_publish(body: dict = Body(...)):
        conf = _sun_conf()
        if body.get("user"):
            conf["user"] = str(body["user"]).strip()
        if body.get("password"):
            conf["password"] = str(body["password"])
            conf.pop("cert_sha256", None)  # nuove credenziali = si rifissa il certificato (Sunshine reinstallato)
        if body.get("reset_cert"):
            conf.pop("cert_sha256", None)
        if body.get("count") not in (None, ""):
            conf["count"] = max(0, min(100, int(body["count"])))
        C.save_settings(cfg, app={"sunshine": conf})
        cfg.app["sunshine"] = conf
        if not body.get("publish"):
            return api_sunshine()
        if not (conf.get("user") and conf.get("password")):
            raise HTTPException(400, I.tr("s.stream.credsRequired"))

        def cover_of(g):
            m = lib.by_id[g["id"]]["media"]
            rel = m.get("cover") or m.get("header")
            return Path(cfg.cache) / rel if rel and not rel.startswith("url:") else None
        try:
            r = SUN.publish(cfg, conf["user"], conf["password"], _stream_games(int(conf.get("count", 24))),
                            C.settings_path(cfg).parent / "sunshine", cover_of,
                            pin=conf.get("cert_sha256"), on_pin=lambda fp: conf.__setitem__("cert_sha256", fp))
        except PermissionError as e:
            raise HTTPException(401, str(e))
        except Exception as e:
            raise HTTPException(502, I.tr("s.stream.sunshineStart", err=f"{type(e).__name__}: {e}"))
        conf["last"] = {"time": time.time(), **r}
        C.save_settings(cfg, app={"sunshine": conf})
        return api_sunshine()

    @router.get("/api/stream/optimize")
    def api_stream_optimize():
        """Controlli sul PC per abbassare la latenza dello streaming (Sunshine, encoder, rete)."""
        try:
            return {"checks": SUN.optimize_checks()}
        except Exception as e:
            return {"checks": [{"level": "warn", "title": I.tr("s.stream.checkFailed"), "detail": f"{type(e).__name__}: {e}"}]}

    @router.post("/api/sunshine/start")
    def api_sunshine_start():
        if not SUN.start_service():
            raise HTTPException(409, I.tr("s.stream.startFailed"))
        return {"ok": True}

    @router.get("/api/running")
    def api_running():
        # dual: il telefono fa da schermo inferiore; can_pause: la sospensione dei processi esiste solo su Windows
        return {**launcher.running(), "dual": bool(ds["state"]), "can_pause": sys.platform == "win32"}

    @router.post("/api/running/stop")
    def api_running_stop():
        stopped = launcher.stop()
        return {"stopped": stopped, "found": launcher.stop_found}  # found=False: nessun processo trovato, interrotto solo nel launcher

    @router.post("/api/running/pause")
    def api_running_pause():
        return {"ok": launcher.pause()}

    @router.post("/api/running/resume")
    def api_running_resume():
        return {"ok": launcher.resume()}

    vars(ctx).update(SUN=SUN)
    return router
