"""Verifica DAT fixture e report hash, senza accessi di rete."""

from concurrent.futures import Future
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from pozzo import scanner
from pozzo.cache import Cache
from pozzo.dumpverify import migrate_schema, report
from pozzo.platforms import get
from pozzo.scanner import Game
from pozzo.sources.libretro import Index, Libretro


DAT = Path(__file__).parent / "fixtures" / "c3_hashes.dat"


def _index():
    index = Index()
    index.add_main(DAT.read_text(encoding="utf-8"))
    return index


def test_hash_match_precedes_name_and_report_statuses(tmp_path):
    index = _index()
    snes = get("snes")
    renamed = Game(tmp_path / "Renamed.sfc", snes, 14, 0,
                   crc="00000000", md5="1C1C98F1C388F99BAEA5FDDADE7CFA10",
                   sha1="FA09097C0637AB6D6DDE7FE81FC30773B79A7930")
    assert index.identify_match(renamed) == ("Fixture Game (USA)", "hash", "sha1")
    assert index.verify(renamed)["status"] == "verificata"

    changed = Game(tmp_path / "Same Name.sfc", snes, 15, 0,
                   crc="4A52F7CD", md5="85986940025FBFB03EC10F1129114CC0",
                   sha1="7371FDE43FD6D18412831960FD378A00F52DCE7D",
                   dat_crc="FA3ED6BC", dat_md5="1C1C98F1C388F99BAEA5FDDADE7CFA10",
                   dat_sha1="FA09097C0637AB6D6DDE7FE81FC30773B79A7930")
    assert index.identify_match(changed) == ("Same Name (USA)", "name", "")
    assert index.verify(changed) == {
        "status": "sconosciuta", "name": "Same Name (USA)", "match_by": "name", "hash_kind": ""
    }

    unknown = Game(tmp_path / "Unlisted.sfc", snes, 9, 0, crc="DEADBEEF")
    no_dat = Game(tmp_path / "No DAT.sfc", get("psx"), 9, 0, crc="DEADBEEF")
    result = report([renamed, changed, unknown, no_dat], {"snes": index})
    assert (result["total"], result["verificata"], result["sconosciuta"], result["nessun DAT"]) == (4, 1, 2, 1)
    assert result["items"][0]["match_by"] == "hash"
    assert index.verify(unknown)["status"] == "sconosciuta"

    empty = Index()
    assert empty.verify(unknown)["status"] == "nessun DAT"


def test_name_match_hashes_once_without_rereading_rom(tmp_path, monkeypatch):
    rom = tmp_path / "Same Name.sfc"
    rom.write_bytes(b"c3 fixture rom")
    game = Game(rom, get("snes"), rom.stat().st_size, rom.stat().st_mtime, needs_hash=True)
    cfg = SimpleNamespace(
        full_hash=True, max_hash_mb=16, hash_workers=1, io_workers=1, disk="ssd", regions=[],
        libretro={"thumbs_by_filename": True},
    )
    cache = Cache(tmp_path / "cache")
    libretro = Libretro.__new__(Libretro)
    libretro.cfg, libretro.cache, libretro.log = cfg, cache, lambda *args: None
    libretro.indexes = {"snes": _index()}

    calls = []
    real_hash_job = scanner._hash_job

    class ImmediateExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, fn, job):
            calls.append(job[0])
            future = Future()
            future.set_result(real_hash_job(job))
            return future

    monkeypatch.setattr(scanner, "ProcessPoolExecutor", ImmediateExecutor)
    hits = libretro.name_first([game])
    assert len(calls) == 1
    assert game.crc == "FA3ED6BC" and game.sha1 == "FA09097C0637AB6D6DDE7FE81FC30773B79A7930"
    assert game.match_by == "hash" and game.verify_status == "verificata"
    assert hits == [game] and not game.needs_hash
    assert libretro.indexes["snes"].verify(game)["status"] == "verificata"
    assert len(calls) == 1, "verifica/identificazione riusano gli hash appena calcolati"
    cache.close()


def test_match_by_migration_preserves_existing_library_and_is_idempotent(tmp_path):
    db = sqlite3.connect(tmp_path / "library.db")
    db.execute("CREATE TABLE games(id INTEGER PRIMARY KEY, title TEXT)")
    db.execute("INSERT INTO games(title) VALUES('Gioco esistente')")
    migrate_schema(db)
    migrate_schema(db)
    assert db.execute("SELECT title, match_by FROM games").fetchone() == ("Gioco esistente", "")
    assert [row[1] for row in db.execute("PRAGMA table_info(games)")].count("match_by") == 1
    db.close()


def test_legacy_name_dat_cache_does_not_skip_file_hash(tmp_path):
    rom = tmp_path / "roms" / "snes" / "Same Name.sfc"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"c3 fixture rom")
    cfg = SimpleNamespace(full_hash=True)
    cache = Cache(tmp_path / "cache")
    stat = rom.stat()
    cache.put_file(str(rom), stat.st_size, stat.st_mtime, {"dat_crc": "FA3ED6BC"})
    games = scanner.scan(cfg, cache, [(get("snes"), rom.parent)])
    assert len(games) == 1 and games[0].needs_hash
    cache.close()
