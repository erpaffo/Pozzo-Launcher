"""Aggiunta rapida di giochi gia' sul disco a library.db, senza ricostruire la libreria.

Serve ai download: build() rilegge tutte le cartelle e rifa tutta la libreria (secondi o minuti, cresce con il numero
di giochi e di voci online); qui si tocca solo la riga del gioco nuovo, con lo stesso codice di build() (scanner.game_at,
pipeline.load_cached, build._game_row, build._regional_groups): stessa chiave, stessi campi di una scansione normale.
Costo: indipendente dalla libreria; l'unica lettura del file e' l'impronta (CRC) che la scansione normale metterebbe
nella chiave, al massimo max_hash_mb e salvata in cache (la scansione dopo la trova).

Non fa (lo fa la prossima ricostruzione): collezioni automatiche, franchise, metadati (la ricerca parte a parte),
raggruppamento per codice prodotto/IGDB (qui solo per nome del file), altre voci online dello stesso gioco.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from .. import platforms as P
from ..cache import Cache
from ..matching import normalize
from ..ownership import file_owners
from ..pipeline import load_cached
from ..scanner import _ignored, clean_title, find_platform_dirs, game_at, hash_one
from .build import INSERT_GAME, _game_row, _regional_groups
from .ratings import combine
from .sizes import game_size

_LOCK = threading.Lock()  # una scrittura alla volta su library.db


def _entry(p: P.Platform, dirs: list[Path], f: Path) -> tuple[Path, bool] | None:
    """La voce che list_entries darebbe per questo file: il file, o (console dir_games) la sua sottocartella."""
    home = [d for d in dirs if f.is_relative_to(d)]
    if not home:
        return None
    d = max(home, key=lambda x: len(x.parts))
    rel = f.relative_to(d)
    if p.dir_games and len(rel.parts) > 1:
        return (d / rel.parts[0], True) if not _ignored(d / rel.parts[0]) else None
    return f, False


def add_games(cfg, platform_id: str, paths: list[Path], drop_key: str | None = None) -> list[str] | None:
    """Mette in library.db i giochi dei file `paths` (gia' dentro una cartella console) e toglie la voce online
    `drop_key` che sostituiscono (il suo link allo store passa al gioco). Ritorna le chiavi, None se la libreria non
    esiste ancora o i file non stanno in una cartella console (serve la scansione normale)."""
    dest = Path(cfg.cache) / "library.db"
    p = P.PLATFORMS.get(platform_id)
    if not dest.exists() or not p:
        return None
    try:
        dirs = [d for q, d in find_platform_dirs(cfg) if q.id == p.id]
    except FileNotFoundError:
        return None
    entries = list(dict.fromkeys(e for f in paths if (e := _entry(p, dirs, Path(f)))))
    if not entries:
        return None
    cache = Cache(cfg.cache)
    try:
        games = [g for path, is_dir in entries if (g := game_at(cfg, cache, p, path, is_dir))]
        for g in games:
            hash_one(cfg, cache, g)
        load_cached(cfg, cache, games)
        merged = {g.key: g for g in games}
        res = cache.all_resources(list(merged))
        groups, primary = _regional_groups(cfg, merged, res)
        rows = {g.key: (g, combine(res.get(g.key, {})), game_size(g.path, g.is_dir, cache) or None) for g in games}
    finally:
        cache.close()
    with _LOCK:
        db = sqlite3.connect(dest, timeout=30)
        try:
            pages = "[]"
            if drop_key and (r := db.execute("SELECT store_pages FROM games WHERE key=? AND store='online'", (drop_key,)).fetchone()):
                pages = r[0] or "[]"
            for key, (g, comb, size) in rows.items():
                old = db.execute("SELECT files FROM games WHERE key=?", (key,)).fetchone()
                if old:  # lo stesso gioco e' gia' in libreria (altra cartella): si aggiunge il file
                    files = list(dict.fromkeys([*json.loads(old[0] or "[]"), str(g.path)]))
                    db.execute("UPDATE games SET files=? WHERE key=?", (json.dumps(files, ensure_ascii=False), key))
                    continue
                grp, prim = groups[key], key in primary
                # shortcut: altra versione dello stesso gioco = stesso titolo del file sulla stessa console (come
                # il raggruppamento "f:" di build); codice prodotto e IGDB aspettano la ricostruzione
                fid = "" if g.stem.startswith("[BIOS]") else normalize(g.search_name)
                for og, fl in (db.execute("SELECT grp, files FROM games WHERE platform=? AND store IS NULL", (p.id,)) if fid else ()):
                    if normalize(clean_title(Path((json.loads(fl or "[]") or [""])[0]).stem)) == fid:
                        grp, prim = og, False
                        break
                row = _game_row(g, [str(g.path)], grp, prim, comb, size, json.loads(pages))
                db.execute(INSERT_GAME, row)
                db.execute("CREATE TABLE IF NOT EXISTS game_owners(key TEXT, owner TEXT, PRIMARY KEY(key, owner))")
                db.executemany("INSERT OR IGNORE INTO game_owners VALUES(?,?)",
                               [(key, o) for os_ in file_owners(cfg, {key: [str(g.path)]}).values() for o in os_])
                if g.verify_status or g.match_by:
                    db.execute("UPDATE games SET verify=?, match_by=? WHERE key=?", (g.verify_status or None, g.match_by or None, key))
            if drop_key:
                db.execute("DELETE FROM games WHERE key=? AND store='online'", (drop_key,))
            db.execute("INSERT OR REPLACE INTO meta VALUES('built_at', ?)", (str(time.time()),))
            db.execute("INSERT OR REPLACE INTO meta VALUES('games', (SELECT COUNT(*) FROM games))")
            db.commit()
        finally:
            db.close()
    return list(rows)
