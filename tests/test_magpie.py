"""Magpie: profilo nel config, scelta del file, avvio/arresto solo se l'ha avviato Pozzo."""

from __future__ import annotations

import json
import types

import pytest

from pozzo.library import automation as A, magpie as M


def test_upsert_preserves_foreign_and_updates_own():
    foreign = {"name": "Altro", "packaged": False, "pathRule": "C:/x.exe", "classNameRule": "Y", "autoScale": 0, "scalingMode": 1, "extra": 5}
    conf = {"theme": 2, "scalingModes": [{"name": "Lanczos"}, {"name": "FSR"}, {"name": "Anime4K"}], "profiles": [{"scalingMode": 0}, foreign]}
    M.upsert_profile(conf, "C:/g/game.exe", "cls", "Gioco", "anime4k")
    M.upsert_profile(conf, "c:/G/GAME.exe", "cls", "Gioco", "fsr")  # stesso exe+classe: aggiorna, non duplica
    assert conf["theme"] == 2 and conf["profiles"][0] == {"scalingMode": 0} and conf["profiles"][1] == foreign
    assert len(conf["profiles"]) == 3
    p = conf["profiles"][2]
    assert (p["autoScale"], p["scalingMode"], p["classNameRule"], p["pathRule"]) == (1, 1, "cls", "c:/G/GAME.exe")
    M.upsert_profile(conf, "C:/g/game.exe", "other", "Gioco", "fsr")  # altra classe: profilo nuovo
    assert len(conf["profiles"]) == 4


def test_write_config_seeds_and_backs_up_once(tmp_path, monkeypatch):
    cfg = types.SimpleNamespace()
    monkeypatch.setattr(M.C, "settings_path", lambda c: tmp_path / "s.json")
    M.write_config(cfg, "C:/g.exe", "K", "G", "integer")
    path = tmp_path / "Magpie" / "config" / "config.json"
    conf = json.loads(path.read_text("utf-8"))
    assert conf["profiles"][0] == {"scalingMode": 0} and conf["profiles"][1]["scalingMode"] == 5
    assert not path.with_name("config.json.pozzo.bak").exists()
    M.write_config(cfg, "C:/h.exe", "K", "H", "fsr")
    bak = path.with_name("config.json.pozzo.bak")
    assert len(json.loads(bak.read_text("utf-8"))["profiles"]) == 2
    M.write_config(cfg, "C:/i.exe", "K", "I", "fsr")
    assert len(json.loads(bak.read_text("utf-8"))["profiles"]) == 2  # copia solo la prima volta
    assert len(json.loads(path.read_text("utf-8"))["profiles"]) == 4


def test_pick_asset_x64_stable():
    a = lambda n: {"name": n, "url": "u/" + n, "size": 1}  # noqa: E731
    rels = [{"tag": "v2-preview", "prerelease": True, "url": "", "assets": [a("Magpie-v2-preview-x64.zip")]},
            {"tag": "v1", "prerelease": False, "url": "", "assets": [a("Magpie-v1-ARM64.zip"), a("Magpie-v1-x64.zip")]}]
    r, asset = M.pick(rels)
    assert r["tag"] == "v1" and asset["name"] == "Magpie-v1-x64.zip"
    assert M.pick([{"tag": "v", "prerelease": False, "url": "", "assets": [a("Magpie-v-ARM64.zip")]}]) is None


def _scaler(monkeypatch, tmp_path, running):
    monkeypatch.setattr(M.C, "settings_path", lambda c: tmp_path / "s.json")
    monkeypatch.setattr(M, "running", lambda: running)
    monkeypatch.setattr(M, "write_config", lambda *a: None)
    popen = []

    class P:
        def __init__(self, *a, **k): popen.append(a); self.terminated = False
        def poll(self): return None
        def terminate(self): self.terminated = True
    monkeypatch.setattr(M.subprocess, "Popen", P)
    msgs = []
    s = M.Scaler(types.SimpleNamespace(), "G", "fsr", msgs.append, window=lambda pid: ("C:/g.exe", "cls") if pid == 7 else ("", ""))
    s.ok = True
    return s, popen, msgs


def test_start_stop_when_we_started(monkeypatch, tmp_path):
    s, popen, _ = _scaler(monkeypatch, tmp_path, running=False)
    s.start(99)  # primo piano di altri: niente
    assert not popen and not s.started
    s.start(7)
    s.start(7)
    assert len(popen) == 1 and popen[0][0][1] == "-t"
    p = s.proc
    s.stop()
    assert p.terminated and s.proc is None


def test_never_stops_magpie_already_open(monkeypatch, tmp_path):
    s, popen, msgs = _scaler(monkeypatch, tmp_path, running=True)
    s.start(7)
    s.stop()
    assert not popen and s.proc is None and msgs


def test_clean_magpie():
    assert A.clean({"magpie": "fsr"})["magpie"] == "fsr"
    assert "magpie" not in A.clean({"magpie": ""})
    with pytest.raises(ValueError):
        A.clean({"magpie": "evil"})
