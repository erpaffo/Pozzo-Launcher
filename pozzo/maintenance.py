"""Manutenzione notturna: controlli di integrita, riprova delle copertine mancanti, aggiornamento store, backup.

Ogni passo e isolato: se uno fallisce gli altri girano comunque. Non cancella mai file dell'utente.
Le istantanee stanno in <cache>/maintenance/AAAA-MM-GG-HHMM.json (ultime 30).
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import threading
import time
from pathlib import Path

KEEP = 30


def _folder(cfg) -> Path:
    return Path(cfg.cache) / "maintenance"


def _games(cfg) -> list[sqlite3.Row]:
    p = Path(cfg.cache) / "library.db"
    if not p.exists():
        return []
    db = sqlite3.connect(p)
    db.row_factory = sqlite3.Row
    try:
        return db.execute("SELECT title, platform, files, media, verify FROM games "
                          "WHERE COALESCE(store,'') = '' AND files IS NOT NULL").fetchall()
    finally:
        db.close()


def _integrity(cfg, snap, cancel):
    from . import bios
    rows = _games(cfg)
    for r in rows:
        if cancel and cancel.is_set():
            break
        for f in json.loads(r["files"] or "[]"):
            if not Path(f).exists():
                snap["rom_missing"].append({"game": r["title"], "path": f})
    unknown = sum(1 for r in rows if r["verify"] == "sconosciuta")  # dump: dal DB, nessuna rilettura dei file
    for pid in sorted({r["platform"] for r in rows}):
        if cancel and cancel.is_set():
            break
        try:
            res = bios.check(pid)
        except ValueError:
            continue
        snap["bios_invalid"] += [{"console": pid, "file": i["file"], "motivo": i.get("motivo", "")}
                                 for i in res["items"] if i["required"] and not i["ok"]]
    return (f"{len(snap['rom_missing'])} ROM mancanti, {len(snap['bios_invalid'])} BIOS non validi, "
            f"{unknown} dump sconosciuti")


def _freeable(cfg):
    """Byte recuperabili dai doppioni, dal plugin pulizia; None se il plugin non c'e."""
    p = Path(__file__).resolve().parent.parent / "extensions" / "pulizia" / "backend.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location("_pozzo_pulizia", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return int(mod._report(cfg)["freeable"])


def _covers(cfg) -> int:
    n = 0
    for r in _games(cfg):
        try:
            if "cover" not in json.loads(r["media"] or "{}"):
                n += 1
        except ValueError:
            n += 1
    return n


def _watch(cancel, stop):
    """Inoltra `cancel` a un job che si ferma con stop(); ritorna l'evento che chiude il guardiano."""
    done = threading.Event()

    def w():
        while not done.is_set():
            if cancel is not None and cancel.is_set():
                stop()
                return
            done.wait(1)
    threading.Thread(target=w, daemon=True).start()
    return done


def _retry_covers(cfg, snap, cancel, j=None):
    from .app import jobs
    j = j or jobs.ScrapeJob(retry_missing=True)  # stessa modalita "missing" dello scraping pianificato
    done = _watch(cancel, j.cancel)
    try:
        j.run(cfg, lambda stats: None, None)
    finally:
        done.set()
    if j.status == "error":
        raise RuntimeError(j.phase or "scraping fallito")
    return j.status


def _stores(cfg, snap, cancel, j=None):
    from .app import jobs
    j = j or jobs.StoreRefreshJob()  # l'app passa la sua coda: niente due aggiornamenti store in parallelo
    done = _watch(cancel, j.stop_now)
    try:
        j.run(cfg, lambda stats: None)
    finally:
        done.set()
    if j.status == "error":
        raise RuntimeError(j.phase)
    return j.phase or j.status


def _backup(cfg, snap, cancel):
    from . import backup
    return backup.create(cfg, "notturno").name


def run(cfg, progress=None, cancel: threading.Event | None = None, scrape_job=None, store_job=None) -> dict:
    """scrape_job/store_job: i job dell'app da usare (cosi' l'interfaccia li vede e non ne parte un altro)."""
    snap = {"time": time.time(), "rom_missing": [], "bios_invalid": [], "covers_missing": 0,
            "freeable_bytes": None, "steps": []}
    steps = [("integrita", _integrity),
             ("copertine mancanti", lambda c, s, x: _retry_covers(c, s, x, scrape_job)),
             ("store", lambda c, s, x: _stores(c, s, x, store_job)), ("backup", _backup)]
    for name, fn in steps:
        if cancel and cancel.is_set():
            snap["steps"].append({"nome": name, "ok": False, "note": "annullato"})
            continue
        if progress:
            try:
                progress(name)
            except Exception:
                pass
        try:
            note = fn(cfg, snap, cancel)
            snap["steps"].append({"nome": name, "ok": True, "note": str(note or "")})
        except Exception as e:
            snap["steps"].append({"nome": name, "ok": False, "note": f"{type(e).__name__}: {e}"})
    for key, fn in (("covers_missing", _covers), ("freeable_bytes", _freeable)):  # a fine giro: contano i dati nuovi
        try:
            snap[key] = fn(cfg)
        except Exception as e:
            snap["steps"].append({"nome": key, "ok": False, "note": f"{type(e).__name__}: {e}"})
    d = _folder(cfg)
    d.mkdir(parents=True, exist_ok=True)
    out = d / (time.strftime("%Y-%m-%d-%H%M", time.localtime(snap["time"])) + ".json")
    out.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    for old in sorted(d.glob("*.json"))[:-KEEP]:
        old.unlink(missing_ok=True)
    return snap


def _key(x: dict):
    return (x.get("game"), x.get("path")) if "path" in x else (x.get("console"), x.get("file"))


def diff(prev: dict, cur: dict) -> dict:
    pr, cr = {_key(x): x for x in prev["rom_missing"]}, {_key(x): x for x in cur["rom_missing"]}
    pb, cb = {_key(x) for x in prev["bios_invalid"]}, {_key(x): x for x in cur["bios_invalid"]}
    pf, cf = prev.get("freeable_bytes"), cur.get("freeable_bytes")
    ok_before = {s["nome"] for s in prev["steps"] if s["ok"]}
    out = {"rom_nuove_mancanti": [v for k, v in cr.items() if k not in pr],
           "rom_ripristinate": [v for k, v in pr.items() if k not in cr],
           "bios_nuovi_invalidi": [v for k, v in cb.items() if k not in pb],
           "covers_delta": cur["covers_missing"] - prev["covers_missing"],
           "freeable_delta": None if pf is None or cf is None else cf - pf}
    failed_now = any(not s["ok"] and s["nome"] in ok_before for s in cur["steps"])
    out["peggiora"] = bool(out["rom_nuove_mancanti"] or out["bios_nuovi_invalidi"] or out["covers_delta"] > 0
                           or failed_now)
    return out


def _load(f: Path) -> dict | None:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest(cfg) -> dict:
    files = sorted(_folder(cfg).glob("*.json"))[-2:]
    snaps = [s for s in (_load(f) for f in files) if s]
    cur = snaps[-1] if snaps else None
    prev = snaps[-2] if len(snaps) > 1 else None
    return {"report": cur, "previous": prev, "diff": diff(prev, cur) if prev else None}


def history(cfg) -> list[dict]:
    out, prev = [], None
    for f in sorted(_folder(cfg).glob("*.json")):
        s = _load(f)
        if not s:
            continue
        out.append({"file": f.name, "time": s["time"], "peggiora": bool(prev and diff(prev, s)["peggiora"])})
        prev = s
    return out[::-1]
