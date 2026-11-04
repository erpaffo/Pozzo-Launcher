from types import SimpleNamespace

from pozzo import bios as BI, diagnose as DG


def _cfg(tmp_path, exe=True):
    e = tmp_path / "emu.exe"
    if exe:
        e.write_bytes(b"x")
    return SimpleNamespace(launch={"nes": {"emulator": "mesen", "exe": str(e)}}, emulators={}, cache=str(tmp_path / "cache"), app={})


def _game(tmp_path, rom=True):
    r = tmp_path / "a.nes"
    if rom:
        r.write_bytes(b"NES")
    return {"key": "nes/a", "platform": "nes", "files": [str(r)]}


def _nomes(res):
    return {c["nome"]: c for c in res["checks"]}


def test_all_ok(tmp_path):
    res = DG.diagnose(_cfg(tmp_path), _game(tmp_path))
    assert res["ok"] and res["probabile"] is None, res
    assert len(res["checks"]) == 6


def test_missing_rom(tmp_path):
    res = DG.diagnose(_cfg(tmp_path), _game(tmp_path, rom=False))
    assert not res["ok"] and res["probabile"] == 0
    assert "File non trovato" in res["checks"][0]["causa"]


def test_missing_exe(tmp_path):
    res = DG.diagnose(_cfg(tmp_path, exe=False), _game(tmp_path))
    c = _nomes(res)
    assert not c["Emulatore scelto"]["ok"] and "Installa" in c["Emulatore scelto"]["rimedio"]
    assert res["probabile"] == 1


def test_missing_bios(tmp_path, monkeypatch):
    monkeypatch.setattr(BI, "check", lambda cid, folder=None: {"console": cid, "items": [
        {"file": "scph5501.bin", "required": True, "found": False, "ok": False, "help_url": ""}], "ok": False})
    monkeypatch.setattr(BI, "_cartelle", lambda cid, f: [tmp_path / "bios"])
    res = DG.diagnose(_cfg(tmp_path), _game(tmp_path))
    c = _nomes(res)["BIOS richiesti"]
    assert not c["ok"] and "scph5501.bin" in c["causa"] and str(tmp_path / "bios") in c["causa"]
    assert res["probabile"] == 3


def test_never_raises(tmp_path):
    res = DG.diagnose(None, {"platform": "nes", "files": [str(tmp_path / "x.nes")]})
    assert not res["ok"]


def test_route_http(tmp_path):
    """GET /api/game/{id}/diagnose risponde con i controlli, senza avviare nulla."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fastapi.testclient import TestClient
    from test_apiv1 import make_library, tmp_cfg
    from pozzo.app.server import create_app
    rom = tmp_path / "game.gba"
    rom.write_bytes(b"x" * 100)
    make_library(tmp_path, rom)
    with TestClient(create_app(tmp_cfg(tmp_path, rom)), base_url="http://127.0.0.1:8765") as c:
        gid = c.get("/api/v1/games", params={"platform": "gba", "limit": 1}).json()["items"][0]["id"]
        r = c.get(f"/api/game/{gid}/diagnose")
        assert r.status_code == 200, r.text
        res = r.json()
        assert len(res["checks"]) == 6 and set(res) == {"checks", "probabile", "ok"}, res
        assert res["checks"][0]["ok"], res  # il file esiste
