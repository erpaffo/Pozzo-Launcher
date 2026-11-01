"""Hash delle ROM: calcolati una volta (cache path+size+mtime), ZIP letti dentro, file enormi saltati,
e salvati nella libreria (colonne crc, md5, sha1)."""

import hashlib
import sqlite3
import zipfile
import zlib
from pathlib import Path

from pozzo import config, scanner
from pozzo.cache import Cache
from pozzo.library.build import build


def _env(tmp: Path):
    (tmp / "roms" / "snes").mkdir(parents=True)
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\nfull_hash = true\n',
                                     encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    cfg.full_hash = True
    return cfg


def _scan(cfg):
    cache = Cache(cfg.cache)
    games = scanner.scan(cfg, cache, scanner.find_platform_dirs(cfg))
    return cache, games


def test_hash_cached_zip_and_library(tmp_path):
    cfg = _env(tmp_path)
    data = b"tiny rom" * 100
    (tmp_path / "roms" / "snes" / "Plain (USA).sfc").write_bytes(data)
    with zipfile.ZipFile(tmp_path / "roms" / "snes" / "Zipped (USA).zip", "w") as z:
        z.writestr("Zipped (USA).sfc", data + b"!")

    cache, games = _scan(cfg)
    assert len(games) == 2 and all(g.needs_hash for g in games)
    scanner.hash_games(cfg, cache, games, log=lambda *a: None)
    by = {g.path.suffix: g for g in games}
    assert by[".sfc"].crc == f"{zlib.crc32(data):08X}"
    assert by[".sfc"].sha1 == hashlib.sha1(data).hexdigest().upper()
    assert by[".zip"].sha1 == hashlib.sha1(data + b"!").hexdigest().upper(), "ZIP: hash del file dentro"
    cache.close()

    # nuova scansione: nulla da ri-hashare, gli hash arrivano dalla cache
    cache, games = _scan(cfg)
    assert not any(g.needs_hash for g in games)
    assert {g.path.suffix: g.sha1 for g in games} == {k: g.sha1 for k, g in by.items()}
    cache.close()

    build(cfg, log=lambda *a: None)
    db = sqlite3.connect(Path(cfg.cache) / "library.db")
    rows = dict(db.execute("SELECT title, sha1 FROM games WHERE platform='snes'").fetchall())
    md5s = {r[0] for r in db.execute("SELECT md5 FROM games WHERE platform='snes'")}
    db.close()
    assert sorted(rows.values()) == sorted(g.sha1 for g in by.values()), rows
    assert hashlib.md5(data).hexdigest().upper() in md5s


def test_huge_file_skipped(tmp_path):
    cfg = _env(tmp_path)
    cfg.max_hash_mb = 0  # tutto "enorme": niente lettura, niente errori
    (tmp_path / "roms" / "snes" / "Big (USA).sfc").write_bytes(b"x" * 10)
    cache, games = _scan(cfg)
    scanner.hash_games(cfg, cache, games, log=lambda *a: None)
    g = games[0]
    assert not g.crc and not g.sha1 and not g.needs_hash
    cache.close()
