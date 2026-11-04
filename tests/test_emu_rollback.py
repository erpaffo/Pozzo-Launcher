import json
from types import SimpleNamespace

from pozzo import emuinstall as E


def _setup(tmp_path, monkeypatch, files):
    dest = tmp_path / "emus" / "rpcs3"
    dest.mkdir(parents=True)
    (dest / "rpcs3.exe").write_text("old")
    (dest / "config.yml").write_text("mine")
    cfg = SimpleNamespace(app={"emulators_dir": str(tmp_path / "emus"),
                               "emu_installed": {"rpcs3": {"version": "v1", "dir": str(dest)}}},
                          emulators={"rpcs3": str(dest / "rpcs3.exe")}, launch={})

    def stage(cfg, asset, name, progress=None):
        w = tmp_path / "emus" / ".tmp" / name
        (w / "files").mkdir(parents=True)
        for f in files:
            (w / "files" / f).write_text("new")
        return w / "files"

    monkeypatch.setattr(E, "_latest", lambda cfg, src: ("v2", {"name": "x.zip", "url": "u"}))
    monkeypatch.setattr(E, "_stage", stage)
    monkeypatch.setattr(E.PT, "_running", lambda d: False)
    monkeypatch.setattr(E.C, "save_settings", lambda cfg, **s: None)
    return cfg, dest


def test_failed_update_restores_original(tmp_path, monkeypatch):
    cfg, dest = _setup(tmp_path, monkeypatch, ["junk.txt"])
    real = E.shutil.copytree

    def boom(src, dst, **kw):  # la sovrascrittura si interrompe a meta'
        if kw.get("dirs_exist_ok"):
            real(src, dst, **kw)
            raise OSError("disco pieno")
        return real(src, dst, **kw)

    monkeypatch.setattr(E.shutil, "copytree", boom)
    try:
        E.install(cfg, "rpcs3", say=lambda *_: None)
        assert False, "doveva fallire"
    except OSError:
        pass
    assert (dest / "rpcs3.exe").read_text() == "old" and (dest / "config.yml").read_text() == "mine"
    assert not (dest / "junk.txt").exists()


def test_update_keeps_bak_and_records_version(tmp_path, monkeypatch):
    cfg, dest = _setup(tmp_path, monkeypatch, ["rpcs3.exe"])
    E.install(cfg, "rpcs3", say=lambda *_: None)
    assert (dest / "rpcs3.exe").read_text() == "new" and (dest / "config.yml").read_text() == "mine"
    assert (tmp_path / "emus" / "rpcs3.bak" / "rpcs3.exe").read_text() == "old"
    assert json.loads((tmp_path / "emus" / "versions.json").read_text())["installed"] == {"rpcs3": "v2"}
    cfg.app["emu_installed"]["rpcs3"]["version"] = "v2"
    assert E.check_updates(cfg)[0]["update"] is False
    E.rollback("rpcs3", cfg)
    assert (dest / "rpcs3.exe").read_text() == "old" and not (tmp_path / "emus" / "rpcs3.bak").exists()
