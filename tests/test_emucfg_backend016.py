"""Backend 0.16: adattatori ryujinx/eden, cataloghi, chiave PS3, disinstallazione e modalita' portatile. Nessuna rete."""
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import config, emucfg  # noqa: E402
from pozzo.emuadapters import ryujinx  # noqa: E402
from pozzo.library.gamekey import game_key  # noqa: E402

win_only = pytest.mark.skipif(sys.platform != "win32", reason="installer degli emulatori solo Windows")
TID = "0100ABCDEF012000"


@pytest.mark.parametrize("emu", ["ryujinx", "eden", "rpcs3"])
def test_catalogo_valido_e_supportato(emu):
    assert emucfg.catalog(emu)["presets"]
    assert emucfg.supported(emu) is True


def _eden():  # import tardivo: un errore in eden.py non deve fermare gli altri test
    from pozzo.emuadapters import eden
    return eden


@pytest.mark.parametrize("name", ["ryujinx", "eden"])
def test_target_titleid(name, tmp_path, monkeypatch):
    mod = ryujinx if name == "ryujinx" else _eden()
    monkeypatch.setenv("APPDATA", str(tmp_path / "ad"))
    exe = tmp_path / "emu" / "x.exe"
    assert mod.target(exe, TID).name in (f"{TID.upper()}.ini", "Config.json")
    for bad in (None, "", "123", "Z" * 16, TID + "0", 5):
        assert mod.target(exe, bad) is None


def test_ryujinx_target_minuscolo(tmp_path):
    t = ryujinx.target(tmp_path / "ryujinx.exe", TID)
    assert t.parent.name == TID.lower() and t.parent.parent.name == "games"
    assert ryujinx.target(None, TID) is None


def test_eden_target_portatile_e_appdata(tmp_path, monkeypatch):
    eden = _eden()
    monkeypatch.setenv("APPDATA", str(tmp_path / "ad"))
    exe = tmp_path / "eden.exe"
    assert eden.target(exe, TID) == tmp_path / "ad" / "eden" / "config" / "custom" / f"{TID}.ini"
    (tmp_path / "user").mkdir()
    assert eden.target(exe, TID) == tmp_path / "user" / "config" / "custom" / f"{TID}.ini"


@pytest.mark.parametrize("emu", ["ryujinx", "eden"])
def test_render_idempotente_dal_catalogo(emu):
    mod = ryujinx if emu == "ryujinx" else _eden()
    cat = emucfg.catalog(emu)
    for level, preset in cat["presets"].items():
        values = preset["values"]
        once = mod.render("", values)
        assert once.strip(), level
        assert mod.render(once, values) == once, f"{emu}/{level} non idempotente"


def test_ryujinx_render_conserva_e_rifiuta():
    out = json.loads(ryujinx.render('{"keep": 1, "a": 0}', {"g": {"a": "2", "b": '"Vulkan"', "c": "true"}}))
    assert out == {"keep": 1, "a": 2, "b": "Vulkan", "c": True}
    for bad in ("{rotto", "[1]"):
        with pytest.raises(ValueError):
            ryujinx.render(bad, {})


# --- chiave gioco PS3 ---
@pytest.mark.parametrize("name,exp", [("Gioco [BLUS30001].iso", "BLUS30001"), ("BCES00644", "BCES00644"),
                                      ("npub30001 demo.pkg", "NPUB30001"), ("Senza seriale.iso", None),
                                      ("XBLUS300011.iso", None)])
def test_ps3_da_nome(tmp_path, name, exp):
    assert game_key("ps3", tmp_path / name) == exp


def test_ps3_da_cartella(tmp_path):
    g = tmp_path / "Gioco senza serial"
    (g / "PS3_GAME").mkdir(parents=True)
    assert game_key("ps3", g) is None
    (g / "PS3_GAME" / "PARAM.SFO").write_bytes(b"\x00PSF..BLES01234\x00junk")
    assert game_key("ps3", g) == "BLES01234"
    assert game_key("ps3", tmp_path / "inesistente") is None


# --- uninstall / portable (Windows) ---
def _zip(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return b.getvalue()


def _installed(tmp: Path, monkeypatch):
    from pozzo import emuinstall as EI, ports as PT
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    monkeypatch.setattr(PT, "releases", lambda p, r, token="": [{"tag": "v0.1", "prerelease": False, "url": "", "assets": [
        {"name": "duckstation-windows-x64-release.zip", "url": "duckstation-windows-x64-release.zip", "size": 0}]}])
    monkeypatch.setattr(PT, "_download", lambda url, dest, progress=None, token="": Path(dest).write_bytes(
        _zip({"DuckStation/duckstation-qt-x64-ReleaseLTCG.exe": b"v", "DuckStation/lib.dll": b"d"})))
    monkeypatch.setattr(PT, "_running", lambda d: False)
    exe = Path(EI.install(cfg, "duckstation", say=lambda m: None))
    return EI, cfg, exe


@win_only
def test_uninstall_keep_data(tmp_path, monkeypatch):
    EI, cfg, exe = _installed(tmp_path, monkeypatch)
    d = exe.parent
    (d / "user").mkdir()
    (d / "user" / "save.bin").write_text("s")
    (d / "portable.txt").write_text("")
    for rel in ("memcards/x.mcd", "savestates/x.sav", "bios/b.bin"):
        (d / rel).parent.mkdir()
        (d / rel).write_text("s")
    EI.uninstall(cfg, "duckstation", keep_data=True)
    assert not exe.exists() and not (d / "lib.dll").exists()
    assert all((d / rel).is_file() for rel in ("memcards/x.mcd", "savestates/x.sav", "bios/b.bin"))
    assert (d / "user" / "save.bin").is_file() and (d / "portable.txt").exists()
    assert "duckstation" not in cfg.emulators and not EI.installed(cfg).get("duckstation")


def _fake_install(EI, cfg, tmp: Path, emu: str) -> Path:
    """Segna `emu` come installato da Pozzo con un exe finto (basta a installed())."""
    d = tmp / "emus" / emu
    d.mkdir(parents=True)
    (d / f"{emu}.exe").write_text("x")
    from pozzo import config as C
    C.save_settings(cfg, emulators={emu: str(d / f"{emu}.exe")},
                    app={"emu_installed": {**(cfg.app.get("emu_installed") or {}), emu: {"version": "", "dir": str(d)}}})
    return d


@win_only
def test_uninstall_ppsspp_tiene_memstick(tmp_path, monkeypatch):
    EI, cfg, _ = _installed(tmp_path, monkeypatch)
    d = _fake_install(EI, cfg, tmp_path, "ppsspp")
    sav = d / "memstick/PSP/SAVEDATA/ULUS10041DATA00/a.bin"
    sav.parent.mkdir(parents=True)
    sav.write_text("s")
    EI.uninstall(cfg, "ppsspp", keep_data=True)
    assert sav.is_file() and not (d / "ppsspp.exe").exists()


@win_only
def test_uninstall_appdata_condivisa(tmp_path, monkeypatch):
    EI, cfg, _ = _installed(tmp_path, monkeypatch)
    ad = tmp_path / "ad"
    monkeypatch.setenv("APPDATA", str(ad))
    sav = ad / "eden" / "salvataggio.bin"
    sav.parent.mkdir(parents=True)
    sav.write_text("s")
    _fake_install(EI, cfg, tmp_path, "eden")
    _fake_install(EI, cfg, tmp_path, "eglantine")
    EI.uninstall(cfg, "eglantine", keep_data=False)
    assert sav.is_file()  # eden la usa ancora
    assert "eden" in EI.installed(cfg) and "duckstation" in EI.installed(cfg)  # disinstallarne uno non cancella gli altri
    EI.uninstall(cfg, "eden", keep_data=False)
    assert not sav.parent.exists()  # ultimo a usarla: via


@win_only
def test_uninstall_appdata_non_condivisa(tmp_path, monkeypatch):
    EI, cfg, _ = _installed(tmp_path, monkeypatch)
    monkeypatch.setenv("APPDATA", str(tmp_path / "ad"))
    sav = tmp_path / "ad" / "eden" / "salvataggio.bin"
    sav.parent.mkdir(parents=True)
    sav.write_text("s")
    _fake_install(EI, cfg, tmp_path, "eglantine")
    EI.uninstall(cfg, "eglantine", keep_data=False)
    assert not sav.parent.exists()  # nessun altro la usa: via


@win_only
def test_uninstall_tutto(tmp_path, monkeypatch):
    EI, cfg, exe = _installed(tmp_path, monkeypatch)
    (exe.parent / "user").mkdir()
    EI.uninstall(cfg, "duckstation", keep_data=False)
    assert not exe.parent.exists()
    assert "duckstation" not in cfg.emulators and not EI.installed(cfg).get("duckstation")
    with pytest.raises(RuntimeError):
        EI.uninstall(cfg, "duckstation")


@win_only
def test_make_portable(tmp_path, monkeypatch):
    EI, cfg, exe = _installed(tmp_path, monkeypatch)
    monkeypatch.setenv("APPDATA", str(tmp_path / "ad"))
    mark = EI.make_portable(cfg, "duckstation")
    assert mark == exe.parent / "portable.txt" and mark.is_file()
    with pytest.raises(ValueError):
        EI.make_portable(cfg, "retroarch")


@win_only
def test_route_uninstall(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from pozzo.app.server import create_app
    EI, cfg, exe = _installed(tmp_path, monkeypatch)
    c = TestClient(create_app(cfg))
    assert c.post("/api/emulators/nonesiste/uninstall", json={}).status_code == 400
    assert c.post("/api/emulators/duckstation/uninstall", json={"keep_data": False}).status_code == 200
    assert not exe.parent.exists() and "duckstation" not in cfg.emulators
