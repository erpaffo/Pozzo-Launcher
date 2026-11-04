"""Pulizia, file doppi fisici: gruppi per hash, hardlink reale, percorsi fuori dalla libreria rifiutati.

Esegui: python -m pytest tests/test_pulizia_dupfiles.py
"""

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pozzo import config as C  # noqa: E402


class FakeGS:
    def __init__(self, cfg):
        self.cfg, self.routes = cfg, {}
        self.settings = {}
        self.log = print

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.routes[path] = fn
            return fn
        return deco


def _load_backend():
    spec = importlib.util.spec_from_file_location("ext_pulizia_backend", ROOT / "extensions" / "pulizia" / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _env(t: Path):
    roms = t / "roms"
    (roms / "snes").mkdir(parents=True)
    (roms / "n64").mkdir(parents=True)
    big = os.urandom(2 << 20)
    other = bytearray(big)
    other[-1] ^= 1  # stessa dimensione, contenuto diverso
    (roms / "snes" / "Mario (USA).sfc").write_bytes(big)
    (roms / "n64" / "Mario (Europe).z64").write_bytes(big)
    (roms / "n64" / "Mario (Japan).z64").write_bytes(bytes(other))
    (roms / "snes" / "piccolo (USA).sfc").write_bytes(b"x" * 1000)  # sotto 1 MB: ignorato
    (roms / "n64" / "piccolo (USA).z64").write_bytes(b"x" * 1000)
    outside = t / "fuori"
    outside.mkdir()
    (outside / "copia.sfc").write_bytes(big)  # uguale ma fuori dalle cartelle ROM: non deve comparire

    cfg = C.Config(roms=roms, cache=t / "cache")
    cfg.config_path = t / "config.toml"
    cfg.app = {}
    (t / "cache").mkdir()
    db = sqlite3.connect(t / "cache" / "library.db")
    db.execute("CREATE TABLE games(id INTEGER PRIMARY KEY, title TEXT, files TEXT, store TEXT)")
    files = [("Mario", [str(roms / "snes" / "Mario (USA).sfc")]),
             ("Mario", [str(roms / "n64" / "Mario (Europe).z64")]),
             ("Mario Japan", [str(roms / "n64" / "Mario (Japan).z64")]),
             ("piccolo", [str(roms / "snes" / "piccolo (USA).sfc"), str(roms / "n64" / "piccolo (USA).z64")]),
             ("Fuori", [str(outside / "copia.sfc")])]
    for i, (title, fs) in enumerate(files, 1):
        db.execute("INSERT INTO games VALUES(?,?,?,NULL)", (i, title, json.dumps(fs)))
    db.commit()
    db.close()
    return cfg, roms, outside


def test_pulizia_dupfiles(tmp_path=None):
    t = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp())
    cfg, roms, outside = _env(t)
    mod = _load_backend()
    gs = FakeGS(cfg)
    mod.register(gs)

    # gruppi: solo i due Mario identici (size >= 1 MB, stesso hash)
    rep = gs.routes["dup-files"]()
    assert len(rep["groups"]) == 1, rep
    g = rep["groups"][0]
    paths = sorted(f["path"] for f in g["files"])
    assert paths == sorted([str(roms / "snes" / "Mario (USA).sfc"), str(roms / "n64" / "Mario (Europe).z64")]), paths
    assert g["size"] == 2 << 20
    assert rep["freeable"] == 2 << 20
    keep = g["files"][g["keep"]]
    assert keep["path"].endswith("Mario (Europe).z64"), keep  # cfg.regions di default: eu prima di us
    assert all(f["same_volume_as_first"] for f in g["files"])
    assert not any(f["is_hardlink"] for f in g["files"])

    # hardlink: il file bersaglio diventa lo stesso inode del file da tenere
    target = next(f["path"] for f in g["files"] if f["path"] != keep["path"])
    res = gs.routes["dup-apply"](body={"hash": g["hash"], "keep": keep["path"], "action": "hardlink"})
    assert res["results"][0]["ok"] and res["freed"] == 2 << 20, res
    assert os.path.samefile(keep["path"], target)
    assert gs.routes["dup-files"]()["freeable"] == 0  # ora sono gia' collegati

    # percorso fuori dalle cartelle della libreria: rifiutato
    with pytest.raises(HTTPException) as e:
        gs.routes["dup-apply"](body={"hash": g["hash"], "keep": str(outside / "copia.sfc"), "action": "delete"})
    assert e.value.status_code == 400
    assert (outside / "copia.sfc").exists()
    print("ok  pulizia dup-files: gruppi per hash, hardlink reale, fuori dalle cartelle rifiutato")


def test_pulizia_delete_keeps_last_copy(tmp_path):
    """delete: se il file da tenere sparisce durante l'operazione, la copia bersaglio NON viene eliminata."""
    cfg, roms, _ = _env(Path(tmp_path))
    mod = _load_backend()
    gs = FakeGS(cfg)
    mod.register(gs)
    g = gs.routes["dup-files"]()["groups"][0]
    keep = g["files"][g["keep"]]["path"]
    target = next(f["path"] for f in g["files"] if f["path"] != keep)
    real_digest = mod._digest

    def digest_then_lose_keep(path):
        h = real_digest(path)
        if os.path.normcase(os.path.realpath(path)) == os.path.normcase(os.path.realpath(target)):
            os.remove(keep)  # il file da tenere sparisce subito prima dell'eliminazione
        return h

    mod._digest = digest_then_lose_keep
    res = gs.routes["dup-apply"](body={"hash": g["hash"], "keep": keep, "action": "delete"})
    assert not res["results"][0]["ok"] and "cambiato" in res["results"][0]["error"] and res["freed"] == 0, res
    assert Path(target).exists(), "eliminata l'ultima copia"
    assert all("dev" in f for f in g["files"])


def test_pulizia_symlink_escaping_roots(tmp_path):
    """Un symlink dentro le cartelle ROM che punta fuori non entra nei gruppi e non e' accettato come keep."""
    cfg, roms, outside = _env(Path(tmp_path))
    link = roms / "snes" / "Mario link.sfc"
    try:
        os.symlink(outside / "copia.sfc", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink non disponibili (Windows senza modalita' sviluppatore)")
    db = sqlite3.connect(cfg.cache / "library.db")
    db.execute("INSERT INTO games VALUES(99,'Link',?,NULL)", (json.dumps([str(link)]),))
    db.commit()
    db.close()
    mod = _load_backend()
    gs = FakeGS(cfg)
    mod.register(gs)
    g = gs.routes["dup-files"]()["groups"][0]
    assert str(link) not in [f["path"] for f in g["files"]]
    with pytest.raises(HTTPException) as e:
        gs.routes["dup-apply"](body={"hash": g["hash"], "keep": str(link), "action": "delete"})
    assert e.value.status_code == 400
    assert (outside / "copia.sfc").exists()


if __name__ == "__main__":
    test_pulizia_dupfiles()
