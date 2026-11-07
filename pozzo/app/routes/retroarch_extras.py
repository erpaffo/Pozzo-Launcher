"""Pannello RetroArch nella scheda gioco: bezel, shader, cheat (per gioco o come predefinito del core)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from ... import emuadapters, i18n as I, platforms as P, retroarch_extras as X
from ...library import launcher as L
from ...library.gamekey import game_key


def build_router(ctx) -> APIRouter:
    cfg, lib, user = ctx.cfg, ctx.lib, ctx.user
    router = APIRouter()

    def _ctx(gid: int):
        """Percorsi del gioco; 409 con il motivo se non è un gioco RetroArch con retroarch.cfg noto."""
        g = lib.game(gid)
        p = P.PLATFORMS.get(g["platform"])
        try:
            pl = None if g.get("store") or not p else L.plan(cfg, p, user.profile(g["key"]))
        except L.LaunchError as e:
            raise HTTPException(409, str(e))
        if not pl or pl["emulator"] != "retroarch" or not pl.get("core"):
            raise HTTPException(409, I.tr("f.raextra.notRetroarch"))
        path = next((Path(f) for f in g["files"] if Path(f).exists()), None)
        gk = game_key(p.id, path) if path else None
        t = emuadapters.get("retroarch").target(pl["exe"], gk, core=pl["core"], game_name=path.stem) if path else None
        if not t:
            raise HTTPException(409, I.tr("f.raextra.noCfg"))
        stem, core = t.name[:-4], pl["core"]
        base = t.parents[2]
        return {"p": p, "base": base, "stem": stem, "core": core, "game": t, "console": t.with_name(core + ".cfg"),
                "gslang": t.with_name(stem + ".slangp"), "cslang": t.with_name(core + ".slangp"),
                "cht": X.cheats_dir(base) / core / (stem + ".cht")}

    @router.get("/api/game/{gid}/retroarch")
    def api_state(gid: int):
        c = _ctx(gid)
        return {"core": c["core"],
                "bezel": {"game": X.current_bezel(c["game"]), "console": X.current_bezel(c["console"])},
                "shader": {"game": X.current_shader(c["gslang"], c["base"]), "console": X.current_shader(c["cslang"], c["base"]),
                           "options": X.list_shaders(c["base"])}}

    @router.get("/api/game/{gid}/retroarch/bezels")
    def api_bezels(gid: int):
        try:
            return X.bezels_for(_ctx(gid)["p"])
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 - rete/GitHub
            raise HTTPException(502, str(e))

    @router.get("/api/retroarch/bezel-preview")
    def api_bezel_preview(id: str):
        try:
            return FileResponse(X.bezel_file(id, "png"), headers={"Cache-Control": "max-age=86400"})
        except ValueError:
            raise HTTPException(400, "bezel")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, str(e))

    @router.post("/api/game/{gid}/retroarch")
    def api_set(gid: int, body: dict = Body(...)):
        c = _ctx(gid)
        cons = body.get("scope") == "console"
        try:
            if "bezel" in body:  # null = eredita, "" = nessuno, altrimenti id
                b = body["bezel"]
                X.set_bezel(c["console" if cons else "game"], None if b is None else str(b))
            if "shader" in body:
                X.set_shader(c["cslang" if cons else "gslang"], c["base"], str(body["shader"] or ""))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, str(e))
        return {"ok": True}

    @router.get("/api/game/{gid}/retroarch/cheats")
    def api_cheats(gid: int):
        c = _ctx(gid)
        lib_names = c["p"].libretro
        if not lib_names:
            return {"file": None, "entries": []}
        try:
            for name in lib_names:
                files = X.cheat_files(name)
                f = X.match_cheat(c["stem"], files)
                if f:
                    break
            else:
                return {"file": None, "entries": []}
            entries = X.parse_cht(X.cheat_text(name, f))
        except Exception as e:  # noqa: BLE001 - 404 = nessun elenco per questa console
            raise HTTPException(502, str(e))
        if c["cht"].is_file():  # le scelte già fatte vincono sul file scaricato
            done = X.parse_cht(c["cht"].read_text("utf-8-sig", "replace"))
            if len(done) == len(entries):
                for e, d in zip(entries, done):
                    e["enable"] = d["enable"]
        return {"file": f, "entries": entries}

    @router.post("/api/game/{gid}/retroarch/cheats")
    def api_cheats_set(gid: int, body: dict = Body(...)):
        c = _ctx(gid)
        got = api_cheats(gid)
        if not got["file"]:
            raise HTTPException(404, I.tr("f.raextra.noCheats"))
        on = {int(i) for i in body.get("enabled", []) if isinstance(i, int)}
        X.write_cheats(c["cht"], got["entries"], on)
        X.merge_cfg(c["game"], {"cheat_apply_after_load": "true"})
        return {"ok": True}

    return router
