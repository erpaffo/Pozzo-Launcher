"""Test di pozzo.library.fastcopy: copia, progresso, annullo, spazio, pulizia."""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from pozzo.library import fastcopy as FC


def _cfg(tmp_path: Path, app: dict | None = None):
    return SimpleNamespace(cache=tmp_path / "c", app=app or {})


def _write(p: Path, n: int) -> bytes:
    p.parent.mkdir(parents=True, exist_ok=True)
    data = os.urandom(n)
    p.write_bytes(data)
    return data


def test_copia_file_singolo(tmp_path):
    src = tmp_path / "src" / "gioco.iso"
    data = _write(src, 1000)
    out = FC.copy(src, tmp_path / "ssd")
    assert out == tmp_path / "ssd" / "gioco.iso"
    assert out.read_bytes() == data
    assert src.exists()


def test_copia_con_siblings(tmp_path):
    d = tmp_path / "src"
    _write(d / "gioco.cue", 50)
    _write(d / "gioco.bin", 500)
    _write(d / "altro.bin", 10)
    out = FC.copy(d / "gioco.cue", tmp_path / "ssd")
    assert out == tmp_path / "ssd" / "gioco.cue"
    assert (tmp_path / "ssd" / "gioco.bin").exists()
    assert not (tmp_path / "ssd" / "altro.bin").exists()


def test_copia_cartella_annidata(tmp_path):
    src = tmp_path / "src" / "Game"
    _write(src / "a" / "b.dat", 100)
    _write(src / "c.dat", 100)
    (src / "vuota").mkdir()
    out = FC.copy(src, tmp_path / "ssd")
    assert out == tmp_path / "ssd" / "Game"
    assert (out / "a" / "b.dat").exists()
    assert (out / "c.dat").exists()
    assert (out / "vuota").is_dir()
    assert FC.same(out, src)


def test_progresso_crescente_e_finale(tmp_path, monkeypatch):
    monkeypatch.setattr(FC, "_PROGRESS_MIN_S", 0)
    src = tmp_path / "big.bin"
    _write(src, 20 * 1024 * 1024)
    valori = []
    FC.copy(src, tmp_path / "ssd", on_progress=lambda f, t: valori.append(f))
    assert len(valori) >= 2
    assert valori == sorted(valori)
    assert valori[-1] == 1.0


def test_annullo_a_meta_lascia_nessuna_copia(tmp_path, monkeypatch):
    monkeypatch.setattr(FC, "_PROGRESS_MIN_S", 0)
    src = tmp_path / "big.bin"
    _write(src, 40 * 1024 * 1024)
    cancel = threading.Event()

    def cb(frac, _testo):
        if frac >= 0.5:
            cancel.set()

    dest = tmp_path / "ssd"
    with pytest.raises(FC.FastCopyError, match="annullata"):
        FC.copy(src, dest, on_progress=cb, cancel=cancel)
    assert not (dest / "big.bin").exists()
    assert not dest.exists() or not any(dest.iterdir())


def test_spazio_insufficiente(tmp_path, monkeypatch):
    src = tmp_path / "gioco.iso"
    _write(src, 1000)
    monkeypatch.setattr(
        FC.shutil, "disk_usage", lambda p: SimpleNamespace(total=1, used=1, free=10)
    )
    dest = tmp_path / "ssd"
    with pytest.raises(FC.FastCopyError, match="Spazio insufficiente"):
        FC.copy(src, dest)
    assert not (dest / "gioco.iso").exists()


def test_remove_idempotente(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "src" / "gioco.cue"
    _write(src, 10)
    _write(src.with_suffix(".bin"), 10)
    out = FC.copy(src, FC.root(cfg) / "gioco")
    FC.remove(out, cfg)
    FC.remove(out, cfg)
    assert not out.exists()
    assert not (FC.root(cfg) / "gioco").exists()


def test_remove_non_tocca_fuori_da_root(tmp_path):
    cfg = _cfg(tmp_path)
    fuori = tmp_path / "fuori.iso"
    _write(fuori, 10)
    FC.remove(fuori, cfg)
    assert fuori.exists()


def test_purge_stale_pulisce_root(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "src"
    _write(src / "uno.iso", 10)
    _write(src / "due.iso", 10)
    FC.copy(src / "uno.iso", FC.root(cfg) / "uno")
    FC.copy(src / "due.iso", FC.root(cfg) / "due")
    assert FC.purge_stale(cfg) == 2
    assert not any(FC.root(cfg).iterdir())
    assert FC.purge_stale(cfg) == 0


def test_purge_stale_rifiuta_root_non_sicura(tmp_path):
    danger = tmp_path / "danger"
    keep = _write(danger / "keep.txt", 10)
    cfg = _cfg(tmp_path, {"fastcopy": {"dir": str(danger)}})
    assert FC.purge_stale(cfg) == 0
    assert (danger / "keep.txt").read_bytes() == keep


def test_copia_riusata_solo_se_uguale(tmp_path):
    src = tmp_path / "src"
    _write(src / "gioco.cue", 10)
    _write(src / "gioco.bin", 100)
    out = FC.copy(src / "gioco.cue", tmp_path / "fast" / "g")
    assert FC.same(out, src / "gioco.cue")
    with open(out.parent / "gioco.bin", "r+b") as f:  # copia interrotta: un file piu' corto
        f.truncate(50)
    assert not FC.same(out, src / "gioco.cue")
