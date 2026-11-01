"""Salvataggi dei giochi."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from ... import config as C, platforms as P, ports as PT
from ...library import launcher as L


def build_router(ctx) -> APIRouter:
    cfg, events, launcher, lib, user = ctx.cfg, ctx.events, ctx.launcher, ctx.lib, ctx.user
    router = APIRouter()

    # ------------------------------------------------------------ salvataggi dei giochi (versioni e rollback)
    from ...library import saves as SV
    from ...library import ludusavi as LM

    def _saves_of(g: dict) -> dict:
        """Salvataggi del gioco con l'emulatore che lo avvierebbe adesso: trovati (paths), condivisi con altri giochi
        (shared), e le cartelle dove cercarli se non ce ne sono (roots). all = quelli da copiare, manuali compresi."""
        manual = SV.resolved_manual(cfg, g["key"])
        # nome del gioco nella cartella delle copie (come in Ludusavi); per le console con la console, contro gli omonimi
        r = {"emulator": "", "paths": [], "shared": [], "roots": [],
             "name": g["title"] if g.get("store") else f"{g['title']} ({P.PLATFORMS[g['platform']].name if g['platform'] in P.PLATFORMS else g['platform']})"}
        if g.get("store") == "ports":  # port PC: con portable.txt i salvataggi stanno nella sua cartella
            m = PT.all_installed(cfg).get(g["key"].split(":", 1)[1])
            r.update(emulator="Port e app", paths=PT.user_files(Path(m["folder"]), m) if m else [],
                     roots=[Path(m["folder"])] if m else [])
        elif g.get("store"):  # gioco PC: percorsi dal manifest di Ludusavi, manuali o rilevati dalla partita
            r.update(emulator=g["store"], roots=[Path(g["install_dir"])] if g.get("install_dir") else [])
            man = LM.load(cfg)
            sid = g["key"].split(":", 1)[-1]
            name = man and LM.find(man, g["store"], sid, g["title"], g.get("install_dir") or "")
            if name:
                root = ""
                if g["store"] == "steam":
                    from ...stores.steam import Steam
                    root = str(Steam(cfg, None, None, print).path() or "")
                r.update(name=name, emulator="Ludusavi", paths=LM.save_paths(man, name, g["store"], sid, g.get("install_dir") or "", root))
        else:
            p = P.PLATFORMS.get(g["platform"])
            try:
                pl = L.plan(cfg, p, user.profile(g["key"])) if p else None
            except L.LaunchError:
                pl = None
            if pl:
                rom = Path(g["files"][0]) if g.get("files") else None
                tid = ""
                if g["platform"] == "switch":
                    from ...cache import Cache
                    c = Cache(cfg.cache)
                    try:
                        tid = ((c.all_resources([g["key"]]).get(g["key"]) or {}).get("nsp") or {}).get("titleid") or ""
                    finally:
                        c.close()
                found, shared = SV.game_saves(pl["emulator"], pl.get("exe"), rom_stem=rom.stem if rom else "",
                                              title_id=tid, ids=SV.game_ids(g["platform"], rom),
                                              rom_dir=str(rom.parent) if rom else "")
                r.update(emulator=pl["emulator"], paths=found, shared=shared,
                         roots=SV.data_roots(pl["emulator"], pl.get("exe")) + ([Path(pl["exe"]).parent] if pl.get("exe") else []))
        r["all"] = SV._uniq(r["paths"] + r["shared"] + manual)
        return r

    def _size(paths: list[Path]) -> int:
        return sum(f.stat().st_size for p in paths for f in ([p] if p.is_file() else p.rglob("*")) if f.is_file())

    @router.get("/api/game/{gid}/saves")
    def api_saves(gid: int):
        g = lib.get(gid)
        s = _saves_of(g)
        return {"emulator": s["emulator"], "supported": SV.supported(s["emulator"]) or bool(s["paths"]),
                "paths": [str(x) for x in s["paths"]], "shared": [str(x) for x in s["shared"]],
                "manual": SV.manual_paths(cfg, g["key"]), "suggested": SV.suggestions(cfg, g["key"]),
                "session": SV.session_point(cfg, g["key"]), "items": SV.list_backups(cfg, g["key"])}

    @router.post("/api/game/{gid}/saves")
    def api_saves_backup(gid: int):
        g = lib.get(gid)
        s = _saves_of(g)
        before = (SV.list_backups(cfg, g["key"])[:1] or [{}])[0].get("name")
        out = SV.backup(cfg, g["key"], g["title"], s["all"], name=s["name"]) if s["all"] else None
        if not out:
            raise HTTPException(404, "Nessun salvataggio trovato per questo gioco: aggiungi a mano la cartella dove "
                                     f"li tiene ({s['emulator'] or 'emulatore non configurato'})")
        return {"name": out.name, "unchanged": out.name == before}

    @router.post("/api/game/{gid}/saves/restore")
    def api_saves_restore(gid: int, body: dict = Body(...)):
        g = lib.get(gid)
        if launcher.running().get("status") in ("starting", "extracting", "running"):
            raise HTTPException(409, "Chiudi il gioco prima di ripristinare i salvataggi")  # l'emulatore li riscriverebbe
        try:
            return SV.restore(cfg, g["key"], body.get("name") or "")
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(400, str(e))

    @router.get("/api/game/{gid}/saves/diff")
    def api_saves_diff(gid: int, name: str):
        try:
            return SV.diff(cfg, lib.get(gid)["key"], name)
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(400, str(e))

    @router.post("/api/game/{gid}/saves/meta")
    def api_saves_meta(gid: int, body: dict = Body(...)):
        try:
            SV.set_meta(cfg, lib.get(gid)["key"], body.get("name") or "",
                        pinned=None if body.get("pinned") is None else bool(body["pinned"]), note=body.get("note"))
        except FileNotFoundError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @router.post("/api/game/{gid}/saves/delete")
    def api_saves_delete(gid: int, body: dict = Body(...)):
        SV.delete(cfg, lib.get(gid)["key"], body.get("name") or "")
        return {"ok": True}

    @router.get("/api/app/save-dir")
    def api_save_dir():
        return {"save_dir": cfg.app.get("save_dir") or "", "default": str(Path(cfg.cache) / "saves"),
                "manifest": LM.path(cfg).is_file()}

    @router.post("/api/app/save-dir")
    def api_save_dir_set(body: dict = Body(...)):
        """Cartella delle copie dei salvataggi (es. quella di Ludusavi, per condividere le copie). Vuota = predefinita.
        Le copie gia' fatte restano dove sono: l'indice di ogni gioco ricorda solo il nome della sua cartella."""
        raw = str(body.get("save_dir") or "").strip().strip('"')
        if raw:
            p = Path(raw)
            if not p.is_absolute():
                raise HTTPException(400, "Serve un percorso completo")
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise HTTPException(400, f"Cartella non utilizzabile: {e}")
        C.save_settings(cfg, app={"save_dir": raw})
        if raw:
            cfg.app["save_dir"] = raw
        return api_save_dir()

    @router.post("/api/game/{gid}/saves/paths")
    def api_saves_paths(gid: int, body: dict = Body(...)):
        try:
            return {"manual": SV.set_paths(cfg, lib.get(gid)["key"], [str(x) for x in body.get("paths") or []])}
        except ValueError as e:
            raise HTTPException(400, str(e))

    @router.post("/api/game/{gid}/saves/suggest")
    def api_saves_suggest(gid: int, body: dict = Body(...)):
        try:
            SV.answer_suggestion(cfg, lib.get(gid)["key"], str(body.get("path") or ""), bool(body.get("accept")))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    save_t0: dict[str, float] = {}  # chiave -> inizio partita, per riconoscere i file cambiati giocando

    def _auto_backup(st: dict, reason: str) -> dict | None:
        g = lib.by_key.get(st.get("key") or "")
        if not g or not cfg.app.get("save_backups", True):
            return None
        s = _saves_of(g)
        if s["all"] and _size(s["all"]) <= 1 << 30:  # oltre 1 GB solo a mano: non si riempie il disco in silenzio
            SV.backup(cfg, g["key"], g["title"], s["all"], reason, name=s["name"])
        return s

    def _saves_before_game(st: dict):
        """Prima che il gioco parta: la versione a cui tornare se la partita va male."""
        try:
            _auto_backup(st, "prima-della-partita")
        except Exception as e:  # una copia mancata non deve impedire di giocare
            print(f"copia dei salvataggi non riuscita: {type(e).__name__}: {e}", file=sys.stderr)
        save_t0[st.get("key") or ""] = time.time()

    def _saves_after_game(st: dict):
        """A fine partita: nuova versione; se il gioco non ha salvataggi noti, propone le cartelle cambiate giocando."""
        try:
            s = _auto_backup(st, "dopo-partita")
            t0 = save_t0.pop(st.get("key") or "", None)
            if s is None or s["all"] or not t0:
                return
            roots = list(s["roots"])
            if lib.by_key[st["key"]].get("store"):  # giochi PC: le cartelle dove Windows tiene i salvataggi
                env = [os.environ.get(k) for k in ("APPDATA", "LOCALAPPDATA")]
                roots += [Path.home() / "Saved Games", SV._docs(), *(Path(x) for x in env if x)]
                if env[1]:
                    roots.append(Path(env[1]).parent / "LocalLow")
            found = SV.changed_since(roots, t0, exclude=[Path(cfg.cache), SV.backup_root(cfg)])
            if found:
                SV.suggest(cfg, st["key"], found)
        except Exception as e:  # una copia mancata non deve disturbare
            print(f"copia dei salvataggi non riuscita: {type(e).__name__}: {e}", file=sys.stderr)

    events.on("game_launching", _saves_before_game)
    events.on("game_stopped", lambda st: threading.Thread(target=_saves_after_game, args=(st,), daemon=True).start())

    vars(ctx).update(api_saves=api_saves, api_saves_backup=api_saves_backup, api_saves_restore=api_saves_restore)
    return router
