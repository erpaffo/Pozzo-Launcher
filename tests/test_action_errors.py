"""Errori d'azione strutturati (C2): codice stabile accanto al testo per emulatore mancante e ROM assente.

Esegui: PYTHONUTF8=1 python tests/test_action_errors.py   (o pytest)
"""
import os
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import platforms as P  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from pozzo.library import launcher as L  # noqa: E402
from test_apiv1 import BASE, make_library, tmp_cfg  # noqa: E402


def test_launch_error_compatible():
    plain = L.LaunchError("testo")
    assert str(plain) == "testo" and plain.code == "" and plain.details == {}
    e = L.LaunchError("x", "emulator_missing", {"platform": "gba"})
    assert str(e) == "x" and e.code == "emulator_missing" and e.details == {"platform": "gba"}


def test_launcher_codes(tmp: Path):
    from pozzo import config as C
    cfg = C.Config()
    with pytest.raises(L.LaunchError) as ex:
        L.Launcher(cfg, lambda *a, **k: None).launch("k", "T", P.get("gba"), tmp / "a.gba")
    assert ex.value.code == "emulator_missing" and str(ex.value).startswith("Nessun emulatore configurato per ")
    assert ex.value.details["platform"] == "gba"
    with pytest.raises(L.LaunchError) as ex:
        L.resolve_target(P.get("gba"), tmp)
    assert ex.value.code == "rom_folder_missing" and ex.value.details["path"] == str(tmp)


def _play(tmp: Path, rom_exists: bool, emulator: bool):
    rom = tmp / "game.gba"
    if rom_exists:
        rom.write_bytes(b"x" * 100)
    make_library(tmp, rom)
    cfg = tmp_cfg(tmp, rom)
    if not emulator:
        cfg.emulators, cfg.launch = {}, {}
    with TestClient(create_app(cfg), base_url=BASE) as c:
        gid = sqlite3.connect(tmp / "library.db").execute("SELECT id FROM games WHERE key='gba/AAA'").fetchone()[0]
        return c.post(f"/api/game/{gid}/play", json={})


def test_play_without_emulator(tmp: Path):
    r = _play(tmp, True, False)
    body = r.json()
    assert r.status_code == 409 and body["code"] == "emulator_missing", body
    assert body["detail"].startswith("Nessun emulatore configurato per ") and body["details"]["platform"] == "gba"


def test_play_rom_missing(tmp: Path):
    r = _play(tmp, False, True)
    body = r.json()
    assert r.status_code == 404 and body["code"] == "rom_folder_missing", body
    assert body["detail"].startswith("File del gioco non trovato") and body["details"]["path"] == str(tmp)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
