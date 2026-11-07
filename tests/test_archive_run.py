"""Archivi senza estrazione fissa: estrai, modifica, raccogli l'overlay, riestrai e riapplica."""

from __future__ import annotations

import zipfile
from types import SimpleNamespace

import pytest

from pozzo.library import archiverun as AR


def _cfg(tmp_path):
    return SimpleNamespace(app={"archive_run": {"dir": str(tmp_path / "run")}}, cache=tmp_path / "cache")


def _zip(tmp_path):
    z = tmp_path / "Game.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Game/game.exe", "exe")
        f.writestr("Game/save.dat", "v1")
    return z


def test_roundtrip_overlay(tmp_path):
    cfg, z = _cfg(tmp_path), _zip(tmp_path)
    r = AR.Run(cfg, tmp_path / "ud", "pc/1", z)
    root = r.prepare()
    assert (root / "save.dat").read_text() == "v1"
    (root / "save.dat").write_text("v2-changed")
    (root / "new.cfg").write_text("n")
    assert r.finish() is None and not r.dir.exists()
    r2 = AR.Run(cfg, tmp_path / "ud", "pc/1", z)
    root = r2.prepare()
    assert (root / "save.dat").read_text() == "v2-changed" and (root / "new.cfg").read_text() == "n"
    assert r2.finish() is None
    assert (tmp_path / "ud" / "run_overlay" / "pc_1" / "save.dat").exists()


def test_refuses_without_space(tmp_path, monkeypatch):
    monkeypatch.setattr("pozzo.downloads.extract.shutil.disk_usage", lambda p: SimpleNamespace(free=1, total=1, used=0))
    r = AR.Run(_cfg(tmp_path), tmp_path / "ud", "k", _zip(tmp_path))
    with pytest.raises(AR.ArchiveRunError, match="Spazio insufficiente"):
        r.prepare()
    assert not r.dir.exists()


def test_copy_failure_keeps_temp(tmp_path, monkeypatch):
    r = AR.Run(_cfg(tmp_path), tmp_path / "ud", "k", _zip(tmp_path))
    root = r.prepare()
    (root / "save.dat").write_text("changed")
    monkeypatch.setattr(AR.shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("disco pieno")))
    msg = r.finish()
    assert msg and "conservata" in msg and (root / "save.dat").read_text() == "changed"
    monkeypatch.undo()
    with pytest.raises(AR.ArchiveRunError, match="recuperare"):  # niente nuova estrazione sopra i file da salvare
        AR.Run(_cfg(tmp_path), tmp_path / "ud", "k", _zip(tmp_path)).prepare()


def test_enabled(tmp_path):
    z = _zip(tmp_path)
    assert AR.enabled({"auto": {"archive": True}}, z)
    assert not AR.enabled({"auto": {}}, z) and not AR.enabled({"auto": {"archive": True}}, tmp_path / "x.exe")
