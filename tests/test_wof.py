"""Compressione WOF: stima dal database CompactGUI, comando, DirectStorage, avanzamento. Esegui: pytest -q tests/test_wof.py"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pozzo.library import wof as W

DB = [
    {"GameName": "Counter-Strike", "FolderName": "Half-Life", "CompressionResults": [
        {"CompType": 0, "BeforeBytes": 1000, "AfterBytes": 700},
        {"CompType": 1, "BeforeBytes": 1000, "AfterBytes": 650},
        {"CompType": 3, "BeforeBytes": 1000, "AfterBytes": 400}]},
    {"GameName": "Vuoto", "CompressionResults": []},
]
# uscita tipica di `compact /c /s /i /exe:xpress8k`
SAMPLE = r"""
 Compressing files in C:\Giochi\Demo\

game.exe          1048576 :       524288 = 2.0 to 1 [OK]
data.pak          2097152 :      2097152 = 1.0 to 1 [OK]
locked.bin              0 :            0 = 1.0 to 1 [Errore di accesso]

2 files within 1 directories were compressed.
3 total bytes of data are stored in 2 bytes.
"""


def test_db_matching():
    idx = W.build_index(DB)
    assert "vuoto" not in idx
    for title in ("Counter-Strike", "counter strike", "Half-Life"):
        e = W.estimate(title, 10_000, idx)
        assert e["name"] == "Counter-Strike" and e["best"] == "lzx"
        assert e["savings"] == {"xpress4k": 3000, "xpress8k": 3500, "lzx": 6000}
    assert W.estimate("Gioco Sconosciuto Mai Visto", 10_000, idx) is None


def test_build_cmd():
    assert W.build_cmd("lzx") == ["compact", "/c", "/s", "/i", "/exe:lzx"]
    assert W.build_cmd() == ["compact", "/c", "/s", "/i", "/exe:xpress8k"]
    assert W.build_cmd(uncompress=True) == ["compact", "/u", "/s", "/i", "/exe"]
    with pytest.raises(ValueError):
        W.build_cmd("zip")


def test_dstorage(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "a.dll").write_bytes(b"x")
    assert not W.has_dstorage(tmp_path)
    (tmp_path / "bin" / "DStorage.DLL").write_bytes(b"x")
    assert W.has_dstorage(tmp_path) and W.count_files(tmp_path) == 2


def test_progress_parsing():
    assert sum(W.is_file_line(l) for l in SAMPLE.splitlines()) == 3
