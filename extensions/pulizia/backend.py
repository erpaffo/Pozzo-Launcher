"""Pulizia: file doppi fisici nella libreria (stesso contenuto, anche in cartelle diverse).

GET  /plugin-api/pulizia/dup-files
     -> {"groups": [{"hash", "size", "files": [{"path", "game", "region", "dev", "same_volume_as_first", "is_hardlink"}],
                     "keep": indice del file da tenere}], "freeable": byte recuperabili}
POST /plugin-api/pulizia/dup-apply  body {"hash", "keep": path, "action": "hardlink"|"delete", "paths": [facoltativo]}
     -> {"hash", "keep", "action", "results": [{"path", "ok", "error", "freed"}], "freed"}
"""

import hashlib
import json
import os
import secrets
import sqlite3
import threading
from collections import defaultdict
from pathlib import Path

from fastapi import Body, HTTPException

from pozzo.config import rom_roots
from pozzo.scanner import regions_of
from pozzo.sources.base import pick_region

MIN_SIZE = 1 << 20  # sotto 1 MB non vale la pena
CHUNK = 1 << 20
_LOCK = threading.Lock()  # una scansione alla volta: niente doppio hashing in parallelo


def _digest(path: str) -> str:
    h = hashlib.blake2b()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _roots(cfg) -> list[str]:
    return [os.path.normcase(os.path.realpath(r)) for r in rom_roots(cfg) if r and os.path.isdir(r)]


def _inside(p: str, roots: list[str]) -> str | None:
    """Percorso reale (normalizzato) se p sta dentro una cartella della libreria, altrimenti None."""
    rp = os.path.normcase(os.path.realpath(p))
    for r in roots:
        try:
            if os.path.commonpath([rp, r]) == r and rp != r:
                return rp
        except ValueError:  # drive diversi su Windows
            pass
    return None


def _library_files(cfg, roots: list[str]) -> list[tuple[str, str, os.stat_result]]:
    """(path, titolo, stat) dei file dei giochi posseduti, dentro le cartelle ROM, >= MIN_SIZE, senza doppioni."""
    db_path = Path(cfg.cache) / "library.db"
    if not db_path.exists():
        return []
    db = sqlite3.connect(db_path)
    try:
        rows = db.execute("SELECT title, files FROM games WHERE files IS NOT NULL "
                          "AND COALESCE(store,'') != 'online'").fetchall()
    finally:
        db.close()
    seen: dict[str, tuple[str, str, os.stat_result]] = {}

    def add(p: str, title: str):
        key = os.path.normcase(os.path.realpath(p))
        if key in seen or _inside(p, roots) is None:
            return
        try:
            st = os.stat(p)
        except OSError:
            return
        if os.path.isfile(p) and st.st_size >= MIN_SIZE:
            seen[key] = (p, title or "", st)

    for title, files in rows:
        for p in json.loads(files or "[]"):
            if os.path.isdir(p):
                for dp, _, fns in os.walk(p):
                    for fn in fns:
                        add(os.path.join(dp, fn), title)
            else:
                add(p, title)
    return list(seen.values())


def _cache_file(cfg) -> Path:
    return Path(cfg.cache) / "pulizia" / "dup-hash.json"


def _load_cache(cfg) -> dict:
    try:
        return json.loads(_cache_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cfg, data: dict):
    f = _cache_file(cfg)
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, f)
    except OSError:
        pass  # shortcut: la cache e' solo un'accelerazione, se non si scrive si riscansiona; nessun dato perso


def _scan(cfg) -> list[tuple[str, int, list]]:
    """Gruppi di file con lo stesso hash: [(hash, size, [(path, titolo, stat), ...])]. Solo size uguali, poi hash."""
    by_size = defaultdict(list)
    for item in _library_files(cfg, _roots(cfg)):
        by_size[item[2].st_size].append(item)
    old = _load_cache(cfg)
    fresh: dict[str, str] = {}  # solo le voci viste ora: la cache non cresce all'infinito
    groups = []
    for size, items in by_size.items():
        if len(items) < 2:
            continue
        by_hash = defaultdict(list)
        for it in items:
            key = f"{it[0]}|{it[2].st_size}|{it[2].st_mtime_ns}"
            try:
                if key not in fresh:
                    fresh[key] = old.get(key) or _digest(it[0])
            except OSError:
                continue  # file bloccato o sparito durante la scansione
            by_hash[fresh[key]].append(it)
        groups += [(h, size, same) for h, same in by_hash.items() if len(same) > 1]
    _save_cache(cfg, fresh)
    return groups


def _region(name: str, prefs: list[str]) -> str:
    rs = regions_of(name)
    return min(rs, key=lambda r: prefs.index(r) if r in prefs else len(prefs), default="")


def _same_file(a: os.stat_result, b: os.stat_result) -> bool:
    return bool(a.st_ino) and a.st_ino == b.st_ino and a.st_dev == b.st_dev


def _report(cfg) -> dict:
    prefs = list(getattr(cfg, "regions", None) or [])
    groups, freeable = [], 0
    for h, size, items in _scan(cfg):
        items = sorted(items, key=lambda it: it[0])
        keep_path = pick_region([{"region": _region(p, prefs), "text": p} for p, _, _ in items], prefs)
        keep_i = next(i for i, it in enumerate(items) if it[0] == keep_path)
        keep_st, first_st = items[keep_i][2], items[0][2]
        files = [{"path": p, "game": t, "region": _region(p, prefs), "dev": st.st_dev,
                  "same_volume_as_first": st.st_dev == first_st.st_dev,
                  "is_hardlink": i != keep_i and _same_file(st, keep_st)}
                 for i, (p, t, st) in enumerate(items)]
        # ogni inode distinto recupera una copia: gli hardlink gia' fatti non contano
        inodes = {(st.st_dev, st.st_ino) if st.st_ino else (p,) for p, _, st in items}
        freeable += size * (len(inodes) - 1)
        groups.append({"hash": h, "size": size, "files": files, "keep": keep_i,
                       "_free": size * (len(inodes) - 1)})
    groups.sort(key=lambda g: (-g.pop("_free"), -g["size"]))
    return {"groups": groups, "freeable": freeable}


def _unchanged(path: str, ref: os.stat_result) -> bool:
    """Il file da tenere esiste ancora ed e' lo stesso verificato via hash (stesso inode, dimensione, mtime)."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    return _same_file(st, ref) and st.st_size == ref.st_size and st.st_mtime_ns == ref.st_mtime_ns


def _relink(keep: str, target: str):
    """Sostituisce target con un hardlink a keep: prima il link temporaneo, poi replace atomico."""
    tmp = f"{target}.{secrets.token_hex(4)}.tmp"
    try:
        os.link(keep, tmp)
        os.replace(tmp, target)
    except OSError:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def register(gs):

    @gs.route("dup-files")
    def dup_files():
        with _LOCK:
            return _report(gs.cfg)

    @gs.route("dup-apply", methods=("POST",))
    def dup_apply(body: dict = Body(...)):
        h, keep, action = body.get("hash"), body.get("keep"), body.get("action")
        only = body.get("paths")
        if not isinstance(h, str) or not isinstance(keep, str) or action not in ("hardlink", "delete"):
            raise HTTPException(400, "richiesta non valida: servono hash, keep e action (hardlink|delete)")
        if only is not None and not (isinstance(only, list) and all(isinstance(x, str) for x in only)):
            raise HTTPException(400, "paths deve essere una lista di percorsi")
        with _LOCK:
            cfg = gs.cfg
            roots = _roots(cfg)
            group = next((g for g in _scan(cfg) if g[0] == h), None)
            if group is None:
                raise HTTPException(404, "gruppo non trovato: la libreria e' cambiata, ricarica la lista")
            _, size, items = group
            keep_real = _inside(keep, roots)
            member = {os.path.normcase(os.path.realpath(p)): p for p, _, _ in items}
            if keep_real is None or keep_real not in member:
                raise HTTPException(400, "keep non e' un file del gruppo dentro le cartelle della libreria")
            if not os.path.isfile(keep_real) or _digest(keep_real) != h:
                raise HTTPException(409, "il file da tenere non corrisponde piu' all'hash: ricarica la lista")
            kst = os.stat(keep_real)
            targets = [p for p, _, _ in items if os.path.normcase(os.path.realpath(p)) != keep_real]
            if only is not None:
                wanted = {os.path.normcase(os.path.realpath(p)) for p in only}
                targets = [p for p in targets if os.path.normcase(os.path.realpath(p)) in wanted]

            results = []
            for p in targets:
                res = {"path": p, "ok": False, "error": None, "freed": 0}
                try:
                    real = _inside(p, roots)
                    st = os.stat(real) if real else None
                    if real is None:
                        res["error"] = "fuori dalle cartelle della libreria"
                    elif not os.path.isfile(real):
                        res["error"] = "non e' un file"
                    elif st.st_size != size or _digest(real) != h:
                        res["error"] = "contenuto diverso dal gruppo"
                    elif _same_file(st, kst):
                        res["ok"] = True  # gia' lo stesso file fisico: niente da fare
                    elif not st.st_ino or not kst.st_ino:
                        # senza inode non si distingue un alias (es. share di rete e unita' mappata) dal file da tenere
                        res["error"] = "identita' del file non verificabile su questo disco"
                    elif not _unchanged(keep_real, kst):
                        res["error"] = "il file da tenere e' cambiato o sparito: operazione interrotta"
                    elif action == "hardlink":
                        if st.st_dev != kst.st_dev:
                            res["error"] = "volumi diversi"
                        else:
                            _relink(keep_real, real)
                            res.update(ok=True, freed=size)
                    else:
                        os.remove(real)
                        res.update(ok=True, freed=size)
                except OSError as e:
                    res["error"] = str(e)
                results.append(res)

        return {"hash": h, "keep": keep, "action": action, "results": results,
                "freed": sum(r["freed"] for r in results)}
