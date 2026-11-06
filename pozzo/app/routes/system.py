"""Info, spazio su disco, aggiornamenti, controllo di salute, token API, stato, ricostruzione."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter

from fastapi.responses import PlainTextResponse

from ... import backup as BK, config as C, platforms as P, telemetry
from ... import i18n as I
from ...library.build import build
from ..server import WINDOW_FOCUS, _REMOTE_DOWN, _plain


def build_router(ctx) -> APIRouter:
    SUN, _emu_row, _pregen_thumbs, cfg, job, launcher = ctx.SUN, ctx._emu_row, ctx._pregen_thumbs, ctx.cfg, ctx.job, ctx.launcher
    lib, state, user = ctx.lib, ctx.state, ctx.user
    router = APIRouter()

    # ------------------------------------------------------------ versione, novita' e aggiornamenti
    @router.get("/api/about")
    def api_about():
        from ... import __version__, updates
        return {"version": __version__, "changelog": updates.changelog(), "data_dir": str(C.settings_path(cfg).parent)}

    # ------------------------------------------------------------ registro errori locale (nessun invio)
    telemetry.set_path(C.settings_path(cfg).parent / "data" / "errors.log")

    @router.get("/api/system/errors")
    def api_system_errors():
        return {"errors": telemetry.recent()}

    @router.post("/api/system/errors/clear")
    def api_system_errors_clear():
        telemetry.clear()
        return {"ok": True}

    @router.get("/api/system/errors/export")
    def api_system_errors_export():
        return PlainTextResponse(telemetry.export_report())

    # ------------------------------------------------------------ spazio dei dati scaricati (cache)
    storage_cache: dict = {}

    def _dir_size(path: Path) -> tuple[int, int]:
        """(byte, file) di una cartella, senza seguire i collegamenti."""
        total = n = 0
        stack = [str(path)]
        while stack:
            try:
                with os.scandir(stack.pop()) as it:
                    for e in it:
                        try:
                            if e.is_dir(follow_symlinks=False):
                                stack.append(e.path)
                            elif e.is_file(follow_symlinks=False):
                                total += e.stat(follow_symlinks=False).st_size
                                n += 1
                        except OSError:
                            pass
            except OSError:
                pass
        return total, n

    @router.get("/api/storage")
    def api_storage(force: int = 0):
        """Dove stanno i metadati scaricati e quanto pesano: per cartella, console, fonte e store online."""
        if not force and storage_cache.get("t", 0) > time.time() - 120:
            return storage_cache["v"]
        from ...cache import Cache
        root = Path(cfg.cache)
        folders = []
        for e in sorted(root.iterdir(), key=lambda x: x.name):
            if e.is_dir():
                b, n = _dir_size(e)
            else:
                b, n = e.stat().st_size, 1
            folders.append({"name": e.name + ("/" if e.is_dir() else ""), "bytes": b, "files": n})
        folders.sort(key=lambda x: -x["bytes"])
        media = root / "media"
        plats: dict = defaultdict(lambda: {"media": 0, "files": 0, "types": {}, "db": 0, "rows": 0, "catalog": 0, "entries": 0})
        if media.is_dir():
            for pd in media.iterdir():
                if not pd.is_dir():
                    continue
                for td in pd.iterdir():
                    b, n = _dir_size(td) if td.is_dir() else (td.stat().st_size, 1)
                    d = plats[pd.name]
                    d["media"] += b
                    d["files"] += n
                    d["types"][td.name] = d["types"].get(td.name, 0) + b
        sources, kv = [], []
        c = Cache(cfg.cache)
        try:
            # il peso e' quello del testo salvato (le righe del database), non del file .db intero
            for plat, nrow, nb in c.db.execute(
                    "SELECT substr(key,1,instr(key,'/')-1), COUNT(*), SUM(length(value)+length(field)+length(key)) "
                    "FROM resources GROUP BY 1"):
                if plat:
                    plats[plat]["db"] += nb or 0
                    plats[plat]["rows"] += nrow
            for src, nrow, nb in c.db.execute(
                    "SELECT source, COUNT(*), SUM(length(value)+length(field)+length(key)) FROM resources GROUP BY source ORDER BY 3 DESC"):
                sources.append({"source": src, "rows": nrow, "bytes": nb or 0})
            labels = {"catalog": I.tr("s.system.kind.catalog"), "netmeta": I.tr("s.system.kind.netmeta"),
                      "storemeta": I.tr("s.system.kind.storemeta"), "store": I.tr("b.setup.step.stores"), "ports": I.tr("a.nav.ports"), "art": I.tr("f.media.label"),
                      "hltb": I.tr("s.system.kind.hltb"), "collart": I.tr("k.fonti.h.coll"), "size": I.tr("s.system.kind.size")}
            for k, nrow, nb in c.db.execute(
                    "SELECT substr(k,1,instr(k||':',':')-1), COUNT(*), SUM(length(v)) FROM kv GROUP BY 1 ORDER BY 3 DESC"):
                kv.append({"kind": k or "altro", "label": labels.get(k, k or I.tr("s.system.kind.other")), "rows": nrow, "bytes": nb or 0})
            try:
                for pid, nrow, nb in c.db.execute(
                        "SELECT json_extract(v,'$.pid'), COUNT(*), SUM(length(v)) FROM kv WHERE k LIKE 'catalog:%' GROUP BY 1"):
                    if pid:
                        plats[pid]["catalog"] += nb or 0
                        plats[pid]["entries"] += nrow
            except sqlite3.Error:
                pass
        finally:
            c.close()
        files = {n: (root / n).stat().st_size for n in ("cache.db", "library.db", "userdata.db") if (root / n).exists()}
        out = {"path": str(root), "total": sum(f["bytes"] for f in folders), "folders": folders, "files": files,
               "platforms": sorted(({"id": k, **v, "total": v["media"] + v["db"] + v["catalog"]} for k, v in plats.items()),
                                   key=lambda x: -x["total"]),
               "sources": sources, "kv": kv}
        storage_cache.update(t=time.time(), v=out)
        return out

    @router.get("/api/update")
    def api_update(force: int = 0):
        from ... import updates
        from ...cache import Cache
        c = Cache(cfg.cache)
        try:
            return {**updates.check(c, force=bool(force)), "install_kind": updates.install_kind()}
        finally:
            c.close()

    @router.post("/api/update/install")
    def api_update_install():
        """Scarica e installa la nuova versione in sottofondo; poi l'app si chiude e si riapre aggiornata."""
        from ... import updates
        from ...cache import Cache
        if updates.STATE["status"] != "running":
            def run():
                c = Cache(cfg.cache)
                try:  # 1,5 s perche' la pagina legga "riavvio" prima che il processo esca
                    updates.install(c, quit=lambda: threading.Timer(1.5, os._exit, args=(0,)).start())
                finally:
                    c.close()
            updates.STATE["status"] = "running"
            threading.Thread(target=run, daemon=True).start()
        return updates.STATE

    @router.get("/api/update/install")
    def api_update_install_state():
        from ... import updates
        return updates.STATE

    # ------------------------------------------------------------ salute: problemi da sistemare, in un posto solo
    @router.get("/api/health")
    def api_health():
        """Controlli veloci (nessuna richiesta in rete). Ogni voce: livello ok/warn/error, testo e, se c'e', l'azione
        dell'interfaccia che la risolve (fix: scheda delle impostazioni, scraping o copia dei dati)."""
        out = []

        def add(level, title, detail="", fix=None):
            out.append({"level": level, "title": title, "detail": detail, "fix": fix})

        def num(n):
            return f"{n:,}".replace(",", ".")

        def roms():
            roots = C.rom_roots(cfg)
            off = [r for r in roots if not r.exists()]
            if len(off) == len(roots):
                add("error", I.tr("s.system.roms_unreachable"), I.tr("s.system.roms_unreachable_detail", path=cfg.roms),
                    {"label": I.tr("s.system.change_folder"), "tab": "scan"})
            elif off:
                add("warn", I.tr("s.system.roms_some_unreachable", n=len(off)), ", ".join(map(str, off))
                    + I.tr("s.system.roms_some_tail"), {"label": "Nuovi giochi", "tab": "scan"})
            else:
                add("ok", I.tr("s.system.roms_ok"), ", ".join(map(str, roots)))

        def emulators():
            with lib.lock:
                pids = sorted({g["platform"] for g in lib.games if not g.get("store")} & set(P.PLATFORMS))
            bad = [r for r in (_emu_row(p) for p in pids) if not r["effective"]]
            if bad:
                add("warn", I.tr("s.system.emu_some_bad", n=len(bad)),
                    "; ".join(f"{r['name']}: {r['problem']}" for r in bad[:8]) + ("…" if len(bad) > 8 else ""),
                    {"label": I.tr("s.system.emulators"), "tab": "emu"})
            elif pids:
                add("ok", I.tr("s.system.emu_all_ready"), I.tr("b.setup.sum.consoles", n=len(pids)))

        def switch_keys():
            with lib.lock:
                has = any(g["platform"] == "switch" for g in lib.games)
            if not has:
                return
            from ... import switchmeta
            found = switchmeta.key_candidates(getattr(cfg, "switch_keys", ""))
            if found:
                add("ok", I.tr("s.system.keys_found"), str(found[0]))
            else:
                add("warn", I.tr("s.system.keys_missing"), I.tr("s.system.keys_missing_detail"))

        def library():
            with lib.lock:
                prim = [g for g in lib.games if g["is_primary"] and not g.get("store")]
            nodata = sum(1 for g in prim if not g["found"])
            nocover = sum(1 for g in prim if g["found"] and "cover" not in g["media"])
            fix = {"label": I.tr("s.system.complete_missing"), "scan": "missing"}
            if nodata:
                add("warn", I.tr("s.system.n_no_data", n=num(nodata)), I.tr("s.system.no_source"), fix)
            if nocover:
                add("warn", I.tr("s.system.n_no_cover", n=num(nocover)), "", fix)
            if not nodata and not nocover:
                add("ok", I.tr("s.system.all_have_data"), num(len(prim)))

        def missing_files():
            with lib.lock:
                rows = [(g["title"], g["files"]) for g in lib.games if g["files"] and not g.get("store")]
            gone = [t for t, fl in rows if not any(Path(f).exists() for f in fl)]
            if gone:
                add("warn", I.tr("s.system.n_files_missing", n=num(len(gone))),
                    ", ".join(gone[:6]) + ("…" if len(gone) > 6 else "") + I.tr("s.system.files_missing_tail"), {"label": "Nuovi giochi", "tab": "scan"})
            else:
                add("ok", I.tr("s.system.all_files_present"), num(len(rows)))

        def sources():
            from ...cache import Cache
            c = Cache(cfg.cache)
            try:
                fg = c.kv_get("freegames") or {}
            finally:
                c.close()
            errs = [e.split(":")[0] for e in fg.get("errors", []) if e != "reset"]
            down = [I.tr("s.system.images_from", h=h) for h, until in _REMOTE_DOWN.items() if until > time.time()]
            if errs or down:
                add("warn", I.tr("s.system.sources_down"), "; ".join(errs + down)
                    + I.tr("s.system.sources_tail"))

        def backups():
            last = BK.list_backups(cfg)
            if not last:
                add("warn", I.tr("s.system.no_backup"), "", {"label": I.tr("s.system.make_backup"), "backup": True})
                return
            days = int((time.time() - last[0]["time"]) / 86400)
            old = days >= 8
            add("warn" if old else "ok", I.tr("s.system.last_backup", when=I.tr("g.dash.save.today") if not days else I.tr("g.dash.save.days_ago", n=days)),
                last[0]["name"], {"label": I.tr("s.system.make_backup"), "backup": True} if old else None)

        def streaming():
            if not SUN.install_dir():
                return
            state, mode = SUN.service_state(), SUN.start_mode()
            fix = {"label": I.tr("i.remote.sun.start"), "sunshine": True}
            if state == "stopped":
                add("warn", I.tr("s.system.sunshine_stopped"),
                    I.tr("s.system.sunshine_stopped_detail"), fix)
            elif state == "running" and mode and mode != "auto":
                add("warn", I.tr("s.system.sunshine_no_autostart"), I.tr("s.system.sunshine_no_autostart_detail"), fix)
            elif state == "running":
                add("ok", I.tr("s.system.sunshine_ok"))

        for fn in (roms, emulators, switch_keys, library, missing_files, sources, backups, streaming):
            try:
                fn()
            except Exception as e:  # un controllo rotto non deve nascondere gli altri
                add("warn", I.tr("s.system.check_failed"), f"{fn.__name__}: {type(e).__name__}: {e}")
        order = {"error": 0, "warn": 1, "ok": 2}
        return {"items": sorted(out, key=lambda x: order[x["level"]])}

    @router.get("/api/api-token")
    def api_api_token():
        """Token dell'API locale per /api/v1, mostrato in Impostazioni › Info (solo dal PC: lo ferma LocalGuard).
        Chi sta sul PC puo' gia' leggere il file in <cache>/api-token: non e' un segreto contro l'utente."""
        from .. import apitoken
        return {"token": apitoken.get(cfg), "url": f"http://127.0.0.1:{int(cfg.app.get('port', 8765))}",
                "api": 1, "file": str(apitoken.path(cfg))}

    @router.post("/api/api-token")
    def api_api_token_new():
        """Nuovo token: chi usava quello vecchio deve essere riconfigurato."""
        from .. import apitoken
        apitoken.rotate(cfg)
        return api_api_token()

    @router.get("/api/status")
    def api_status():
        return {k: state[k] for k in ("building", "build_stats", "thumbs_total", "thumbs_done")} | {
            "build_log": state["build_log"][-8:], "has_library": bool(lib.games) or lib.built_at > 0,
            "built_at": lib.built_at, "user_rev": user.rev, "meta_rev": lib.meta_rev,
            "running": launcher.running().get("status") or "", "downloaded": state.get("downloaded")}

    @router.post("/api/focus")
    def api_focus():
        """Una seconda copia dell'app chiede di riportare in primo piano la finestra gia' aperta."""
        fn = WINDOW_FOCUS["fn"]
        if fn:
            fn()
        return {"window": bool(fn)}

    def _rebuild():
        if job["current"].status == "running":
            return
        state["building"], state["build_started"] = True, time.time()
        state["build_log"] = []
        try:
            state["build_stats"] = build(cfg, log=lambda m: state["build_log"].append(_plain(str(m))))
            lib.load()
            threading.Thread(target=_pregen_thumbs, daemon=True).start()
        except Exception as e:
            state["build_log"].append(I.tr("s.system.error", kind=type(e).__name__, msg=str(e)))
        finally:
            state["building"] = False

    @router.post("/api/rebuild")
    def api_rebuild():
        if not state["building"]:
            threading.Thread(target=_rebuild, daemon=True).start()
        return {"ok": True}

    vars(ctx).update(_rebuild=_rebuild)
    return router
