"""Mapping controller per emulatore: tabelle, "solo se la config non esiste", applicazione a mano, router."""
from __future__ import annotations

import pytest
import yaml

from pozzo import controllerprofiles as CP
from pozzo.remote import emusetup


@pytest.fixture(autouse=True)
def _closed(monkeypatch, tmp_path):
    monkeypatch.setattr(emusetup, "_running", lambda names: False)
    # su Linux e macOS RPCS3 tiene la config nella cartella utente: una home finta per ogni test
    # (altrimenti il primo test la scrive nella home vera e i successivi la trovano gia' presente)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))


def _emus(tmp):
    d = {}
    for e in ("dolphin", "pcsx2", "duckstation", "rpcs3", "retroarch"):
        (tmp / e).mkdir()
        (tmp / e / "portable.txt").write_text("")
        (tmp / e / "portable.ini").write_text("") if e == "pcsx2" else None
        d[e] = str(tmp / e / f"{e}.exe")
    (tmp / "pcsx2" / "portable.ini").unlink()
    (tmp / "pcsx2" / "portable.txt").unlink()
    (tmp / "pcsx2" / "portable.ini").write_text("")
    return d


@pytest.mark.parametrize("t", list(CP.TYPES))
def test_every_emulator_every_type(tmp, t):
    emus = _emus(tmp)
    for emu in CP.SUPPORTED:
        r = CP.apply(emu, t, emus)  # config assente: si scrive
        text = open(r["file"], encoding="utf-8").read()
        assert text.strip(), emu
        if emu in ("pcsx2", "duckstation"):
            assert emusetup.ini_get(text, "Pad1", "Cross") == ("XInput-0/A" if t == "xbox" else "SDL-0/A")
        if emu == "dolphin":
            assert emusetup.ini_get(text, "GCPad1", "Device") == CP._DOLPHIN_DEV[t]
        if emu == "rpcs3":
            assert yaml.safe_load(text)["Player 1 Input"]["Config"]["Cross"]
        if emu == "retroarch":
            assert 'input_joypad_driver = "' + ("xinput" if t == "xbox" else "sdl2") + '"' in text


def test_never_overwrites_existing(tmp):
    emus = _emus(tmp)
    ini = CP._config_file("pcsx2", emus["pcsx2"])
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text("[Pad1]\nCross = mio\n")
    assert CP.auto_apply({"pcsx2": emus["pcsx2"]}, lambda *a: None) == []
    assert ini.read_text() == "[Pad1]\nCross = mio\n"
    with pytest.raises(RuntimeError):
        CP.apply("pcsx2", "xbox", emus)


def test_force_keeps_other_keys_and_backs_up(tmp):
    emus = _emus(tmp)
    ini = CP._config_file("pcsx2", emus["pcsx2"])
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_bytes(b"[UI]\r\nTheme = dark\r\n")
    r = CP.apply("pcsx2", "ps", emus, force=True)
    out = ini.read_bytes().decode()
    assert "Theme = dark" in out and "SDL-0/A" in out and "\r\n" in out
    assert r["backup"] and open(r["backup"], "rb").read() == b"[UI]\r\nTheme = dark\r\n"


def test_auto_apply_and_bad_input(tmp):
    emus = _emus(tmp)
    assert set(CP.auto_apply(emus, lambda *a: None, layout="switch")) == set(CP.SUPPORTED)
    assert CP.auto_apply(emus, lambda *a: None) == []  # seconda volta: le config ora esistono
    with pytest.raises(ValueError):
        CP.apply("cemu", "xbox", emus)
    assert CP.detect_type("ps4") == "ps4"


def test_router(tmp):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from pozzo.app.routes import controller_profiles
    app = FastAPI()
    app.include_router(controller_profiles.build_router(SimpleNamespace(cfg=SimpleNamespace(emulators=_emus(tmp)))))
    c = TestClient(app)
    assert {e["id"] for e in c.get("/api/controller-profiles").json()["emulators"]} == set(CP.SUPPORTED)
    assert c.post("/api/controller-profiles/apply", json={"emulator": "dolphin", "type": "xbox"}).status_code == 200
    assert c.post("/api/controller-profiles/apply", json={"emulator": "nope", "type": "xbox"}).status_code == 400


def test_auto_apply_solo_l_emulatore_installato(tmp_path, monkeypatch):
    from pozzo import controllerprofiles as CP
    seen = []
    monkeypatch.setattr(CP, "_config_file", lambda emu, exe: tmp_path / emu / "x.ini")
    monkeypatch.setattr(CP, "apply", lambda emu, t, emus, force=False: seen.append(emu))
    exes = {e: "x.exe" for e in CP.SUPPORTED}
    assert CP.auto_apply(exes, lambda m: None, layout="xbox", only="pcsx2") == ["pcsx2"] and seen == ["pcsx2"]


def test_rpcs3_mantiene_le_altre_chiavi():
    import yaml
    from pozzo import controllerprofiles as CP
    old = yaml.safe_dump({"Player 1 Input": {"Handler": "Null", "Vibration": {"Large": 1}, "Config": {"Start": "X", "Extra": "keep"}}})
    out = yaml.safe_load(CP._render("rpcs3", "xbox", old))["Player 1 Input"]
    assert out["Handler"] == "XInput" and out["Vibration"] == {"Large": 1}
    assert out["Config"]["Start"] == "Start" and out["Config"]["Extra"] == "keep"
