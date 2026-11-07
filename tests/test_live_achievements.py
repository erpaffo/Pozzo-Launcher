"""Obiettivi dal vivo: parser Goldberg/CODEX, differenza degli sblocchi, abbinamento dell'appid, ciclo di sondaggio."""

import time
import types
from pathlib import Path

from pozzo import liveach as LA

GB = '{"ACH_ONE": {"earned": true, "earned_time": 200}, "ACH_TWO": {"earned": false, "earned_time": 0}, "NewAch": {"earned": true, "earned_time": 100}}'
CODEX = "[ACH_ONE]\nAchieved=1\nUnlockTime=300\n[ACH_TWO]\nAchieved=0\nUnlockTime=0\n[ACH_THREE]\nHaveAchieved=1\n"


def test_parsers():
    assert LA.parse_json(GB) == {"ACH_ONE": 200, "NewAch": 100}
    assert LA.parse_ini(CODEX) == {"ACH_ONE": 300, "ACH_THREE": 0}


def test_diff_orders_by_time():
    assert LA.new_unlocks({"ACH_ONE": 1}, {"ACH_ONE": 1, "B": 9, "A": 5}) == ["A", "B"]
    assert LA.new_unlocks({"x": 1}, {"x": 1}) == []


def test_appid_matching_and_files():
    assert LA.appid_of("windows/steam:220") == "220"
    assert LA.appid_of("windows/epic:abc") is None and LA.appid_of("gba/AAA") is None and LA.appid_of(None) is None
    fs = LA.candidate_files("220", {"APPDATA": "C:/A", "PUBLIC": "C:/P"})
    assert Path("C:/A/Goldberg SteamEmu Saves/220/achievements.json") in fs
    assert Path("C:/P/Documents/Steam/CODEX/220/achievements.ini") in fs
    assert Path("C:/A/EMPRESS/220/remote/achievements.json") in fs


def test_pretty():
    assert LA.pretty("ACH_FIRST_KILL") == "First Kill" and LA.pretty("NewAchievement") == "New Achievement"


def test_unreadable_file_is_empty(tmp_path):
    f = tmp_path / "achievements.json"
    f.write_text("{rotto", "utf-8")
    assert LA.read_unlocked(f) == {} and LA.read_unlocked(tmp_path / "no.ini") == {}


def test_session_notifies_only_new_unlocks(tmp_path, monkeypatch):
    monkeypatch.setattr(LA, "POLL", 0.05)
    f = tmp_path / "achievements.json"
    f.write_text('{"ACH_ONE": {"earned": true, "earned_time": 1}}', "utf-8")
    got = []
    ov = types.SimpleNamespace(toast=got.append)
    cfg = types.SimpleNamespace(app={})
    live = LA.LiveAch(cfg, ov, files=lambda a: [f], schema=lambda k, a: {"ACH_TWO": {"name": "Due", "description": "d", "icon": "u"}})
    live.game_started({"key": "windows/steam:220"})
    time.sleep(0.3)
    assert got == []  # base di partenza: l'obiettivo gia' sbloccato non avvisa
    f.write_text('{"ACH_ONE": {"earned": true, "earned_time": 1}, "ACH_TWO": {"earned": true, "earned_time": 2}}', "utf-8")
    time.sleep(0.5)
    live.game_stopped()
    assert [g["text"] for g in got] == ["Due"] and got[0]["sound"] == "soft"
