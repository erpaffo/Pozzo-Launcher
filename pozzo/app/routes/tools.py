"""Strumenti sui giochi: elenco dei compatibili, avvio come job, annulla, e adozione del file prodotto."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import i18n as I
from ...downloads.manager import default_dir
from ...tools import adopt as A, jobs as J, space
from ...tools.impl import load


def build_router(ctx) -> APIRouter:
    router = APIRouter()
    cfg = ctx.cfg
    load()

    def _roots() -> list[Path]:
        d = (cfg.app.get("downloads") or {}).get("dir")
        return [Path(x).resolve() for x in (cfg.roms, *getattr(cfg, "extra_roms", []), d or default_dir()) if x]

    def _inside(p: Path) -> bool:
        return any(r == p or r in p.parents for r in _roots())

    def _path(raw, key="path") -> Path:
        raw = str(raw or "").strip().strip('"')
        if not raw or not Path(raw).is_absolute():
            raise HTTPException(400, I.tr("s.tools.badPath"))
        p = Path(raw).resolve()  # niente «..» né link fuori dalle cartelle ROM/download
        if not _inside(p):
            raise HTTPException(400, I.tr("s.tools.outside"))
        return p

    def _binary_ready(t: J.Tool) -> bool:
        if not t.binary:
            return True
        try:
            from ...tools import binaries
            return binaries.path(cfg, t.binary) is not None
        except Exception:  # modulo assente o binario non scaricabile: la UI mostra «verrà scaricato»
            return False

    @router.get("/api/tools")
    def api_tools(platform: str = "", path: str = ""):
        """Strumenti compatibili con un gioco (platform+path), oppure tutti se mancano."""
        rows = []
        for t in J.TOOLS.values():
            if platform and path and t.needs_game:
                try:
                    if not t.applies(platform, Path(path)):
                        continue
                except OSError:
                    continue
            rows.append({"id": t.id, "name": t.name, "needs_game": t.needs_game, "binary": t.binary,
                         "binary_ready": _binary_ready(t)})
        return {"tools": rows, "busy": any(j["status"] == "running" for j in J.JOBS.values())}

    @router.get("/api/tools/drives")
    def api_tools_drives():
        """Lettori ottici per il dump: [{id, label}] (vuoto se il modulo dump non c'è o non vede lettori)."""
        try:
            from ...tools.impl import dump
            return {"drives": dump.drives()}
        except Exception:
            return {"drives": []}

    @router.post("/api/tools/run")
    def api_tools_run(body: dict = Body(...)):
        t = J.TOOLS.get(str(body.get("tool") or ""))
        if not t:
            raise HTTPException(404, I.tr("s.tools.unknown"))
        pid = str(body.get("platform") or "")
        src = _path(body.get("path")) if t.needs_game else Path()
        dst = _path(body.get("dst")) if body.get("dst") else None
        if t.needs_game and not t.applies(pid, src):
            raise HTTPException(400, I.tr("s.tools.notApplicable"))
        if not t.needs_game and not dst:
            raise HTTPException(400, I.tr("s.tools.badPath"))
        opts = {**(body.get("options") or {}), "cfg": cfg, "platform": pid}
        try:
            return J.start(t.id, src if t.needs_game else "", dst, opts, pid)
        except space.NoSpace as e:
            raise HTTPException(507, str(e))
        except J.Busy:
            raise HTTPException(409, I.tr("s.tools.busy"))

    @router.get("/api/tools/job/{jid}")
    def api_tools_job(jid: str):
        if jid not in J.JOBS:
            raise HTTPException(404, I.tr("s.tools.noJob"))
        return J.public(J.JOBS[jid])

    @router.post("/api/tools/job/{jid}/cancel")
    def api_tools_cancel(jid: str):
        if jid not in J.JOBS:
            raise HTTPException(404, I.tr("s.tools.noJob"))
        J.cancel(jid)
        return J.public(J.JOBS[jid])

    @router.post("/api/tools/job/{jid}/adopt")
    def api_tools_adopt(jid: str, body: dict = Body(...)):
        """Il file prodotto diventa quello del gioco. move_old: l'originale va nel Cestino (mai cancellato)."""
        j = J.JOBS.get(jid)
        if not j or j["status"] != "done" or not j.get("out"):
            raise HTTPException(404, I.tr("s.tools.noJob"))
        try:
            return A.adopt(cfg, j["platform"], _path(j["src"]), _path(j["out"]), bool(body.get("move_old")))
        except (ValueError, OSError) as e:
            raise HTTPException(400, str(e))

    return router
