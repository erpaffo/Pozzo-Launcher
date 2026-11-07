"""Esportazione in Steam: lettura/scrittura di shortcuts.vdf, appid, idempotenza, rimozione, Steam aperto."""
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pozzo import steamshortcuts as SS

FOREIGN = {"appid": -1234567, "AppName": "Mio gioco \u00e8", "Exe": '"C:/x.exe"', "tags": {"0": "Altro"}, "LastPlayTime": 7}
ENT = {"name": "Sonic", "exe": '"C:/Pozzo/pozzo-cli.exe"', "start_dir": "C:/Pozzo", "opts": 'play --key "md/sonic"'}


@pytest.fixture
def steam(tmp_path, monkeypatch):
    monkeypatch.setattr(SS, "steam_running", lambda: False)
    cfg = tmp_path / "userdata" / "42" / "config"
    cfg.mkdir(parents=True)
    (cfg / "shortcuts.vdf").write_bytes(SS.dumps({"shortcuts": {"0": FOREIGN}}))
    return tmp_path


def read(steam):
    return SS.loads((steam / "userdata" / "42" / "config" / "shortcuts.vdf").read_bytes())["shortcuts"]


def test_roundtrip_bytes():
    raw = SS.dumps({"shortcuts": {"0": FOREIGN, "1": {"appid": 5, "tags": {}}}})
    assert SS.dumps(SS.loads(raw)) == raw
    assert SS.loads(raw)["shortcuts"]["0"]["AppName"] == FOREIGN["AppName"]
    with pytest.raises(ValueError):
        SS.loads(b"\x00a\x00\x07k\x00" + b"\0" * 8 + b"\x08\x08")  # uint64: non supportato


def test_appid():
    assert SS.appid("a", "bc") == (zlib.crc32(b"abc") | 0x80000000) == 0xB52441C2  # crc32("abc") = 0x352441c2
    assert SS.appid(ENT["exe"], "Sonic") >= 1 << 31


def test_export_keeps_foreign_and_is_idempotent(steam):
    SS.apply(steam, "42", [ENT])
    first = (steam / "userdata/42/config/shortcuts.vdf").read_bytes()
    r = SS.apply(steam, "42", [ENT])
    assert (steam / "userdata/42/config/shortcuts.vdf").read_bytes() == first
    s = read(steam)
    assert r == {"added": 1, "removed": 1, "kept": 1, "art": 0}
    assert s["0"] == FOREIGN and s["1"]["AppName"] == "Sonic" and s["1"]["LaunchOptions"] == ENT["opts"]
    assert s["1"]["appid"] < 0 and (s["1"]["appid"] & 0xFFFFFFFF) == SS.appid(ENT["exe"], "Sonic")
    assert list((steam / "userdata/42/config").glob("shortcuts.vdf.pozzo-bak-*"))


def test_remove_only_ours(steam):
    SS.apply(steam, "42", [ENT])
    r = SS.apply(steam, "42", [])
    assert r["removed"] == 1 and read(steam) == {"0": FOREIGN}


def test_refuses_when_steam_running(steam, monkeypatch):
    before = (steam / "userdata/42/config/shortcuts.vdf").read_bytes()
    monkeypatch.setattr(SS, "steam_running", lambda: True)
    with pytest.raises(SS.SteamRunning):
        SS.apply(steam, "42", [ENT])
    assert (steam / "userdata/42/config/shortcuts.vdf").read_bytes() == before
    assert not list((steam / "userdata/42/config").glob("*bak*"))


def test_art_copied_as_png(steam, tmp_path):
    from PIL import Image
    src = tmp_path / "c.jpg"
    Image.new("RGB", (4, 4)).save(src)
    r = SS.apply(steam, "42", [{**ENT, "art": {"p": src}}])
    aid = SS.appid(ENT["exe"], "Sonic")
    assert r["art"] == 1 and (steam / f"userdata/42/config/grid/{aid}p.png").exists()
