"""Impostazioni della copia veloce: cartella, cancellazione a fine partita, validazione."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402


@pytest.fixture
def env(tmp_path):
    cfg = config.Config(cache=tmp_path / "cache", output=tmp_path / "out")
    cfg.cache.mkdir()
    cfg.config_path = tmp_path / "config.toml"
    with TestClient(create_app(cfg)) as client:
        yield cfg, client


def test_default(env):
    cfg, client = env
    r = client.get("/api/app/fastcopy").json()
    assert r["dir"] == ""
    assert r["delete_after"] is True
    assert r["default_dir"] == str(cfg.cache / "fastcopy")
    assert r["free_gb"] is None or r["free_gb"] > 0


def test_salvataggio_e_rilettura(env, tmp_path):
    _, client = env
    dest = tmp_path / "veloce" / "fc"
    r = client.post("/api/app/fastcopy", json={"dir": str(dest), "delete_after": False})
    assert r.status_code == 200
    assert r.json()["dir"] == str(dest)
    assert r.json()["delete_after"] is False
    again = client.get("/api/app/fastcopy").json()
    assert again["dir"] == str(dest) and again["delete_after"] is False


def test_delete_after_non_bool_400(env):
    _, client = env
    assert client.post("/api/app/fastcopy", json={"delete_after": "no"}).status_code == 400
    assert client.post("/api/app/fastcopy", json={"delete_after": 0}).status_code == 400


def test_radice_disco_400(env, tmp_path):
    _, client = env
    r = client.post("/api/app/fastcopy", json={"dir": tmp_path.anchor})
    assert r.status_code == 400
    assert "Scegli una cartella dedicata" in r.json()["detail"]


def test_cartella_non_vuota_400(env, tmp_path):
    _, client = env
    altra = tmp_path / "musica"
    altra.mkdir()
    (altra / "brano.mp3").write_bytes(b"x")
    r = client.post("/api/app/fastcopy", json={"dir": str(altra)})
    assert r.status_code == 400
    assert "non è vuota" in r.json()["detail"]
    assert (altra / "brano.mp3").exists()


def test_cartella_nuova_creata(env, tmp_path):
    _, client = env
    nuova = tmp_path / "nuova" / "dentro"
    r = client.post("/api/app/fastcopy", json={"dir": str(nuova)})
    assert r.status_code == 200
    assert nuova.is_dir()


def test_aggiornamento_parziale(env, tmp_path):
    _, client = env
    dest = tmp_path / "veloce"
    client.post("/api/app/fastcopy", json={"dir": str(dest)})
    r = client.post("/api/app/fastcopy", json={"delete_after": False})
    assert r.status_code == 200
    assert r.json()["dir"] == str(dest)
    assert r.json()["delete_after"] is False


def test_cartella_marcata_e_mai_nella_libreria(env, tmp_path):
    cfg, client = env
    nuova = tmp_path / "ssd" / "temp"  # nome qualsiasi: il marcatore la rende svuotabile da purge_stale
    assert client.post("/api/app/fastcopy", json={"dir": str(nuova)}).status_code == 200
    assert (nuova / ".pozzo-fastcopy").is_file()
    cfg.roms = tmp_path / "roms"
    for d in (cfg.roms, cfg.roms / "snes", tmp_path):  # la libreria, dentro, sopra
        r = client.post("/api/app/fastcopy", json={"dir": str(d)})
        assert r.status_code == 400 and "libreria" in r.json()["detail"]
