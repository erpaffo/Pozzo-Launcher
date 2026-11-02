"""API per preset di esperienza: CRUD, attivazione, fallback e isolamento per profilo."""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config  # noqa: E402
from pozzo import profilecfg as PC  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402


def _client(tmp_path):
    cfg = config.Config(cache=tmp_path / "cache", output=tmp_path / "out")
    cfg.cache.mkdir()
    cfg.config_path = tmp_path / "config.toml"
    return cfg, TestClient(create_app(cfg))


def test_default_presets_crud_and_activation(tmp_path):
    cfg, client = _client(tmp_path)
    with client:
        response = client.get("/api/exp-profiles")
        assert response.status_code == 200
        assert [p["nome"] for p in response.json()["profiles"]] == [
            "Classico", "Cinema serata", "Console TV", "Leggero",
        ]

        created = client.post("/api/exp-profiles", json={
            "nome": "Serata mia",
            "experience": "cinema",
            "theme": "default",
            "animations": "reduced",
        })
        assert created.status_code == 200
        preset = next(p for p in created.json()["profiles"] if p["nome"] == "Serata mia")
        assert preset["id"].startswith("serata-mia-")
        assert preset["experience"] == "cinema"

        applied = client.post("/api/exp-profiles/activate", json={"id": preset["id"]})
        assert applied.status_code == 200
        assert applied.json() == {
            "active": preset["id"], "experience": "cinema", "theme": "default", "animations": "reduced",
        }
        assert PC.get(cfg, "experience") == "cinema"
        assert PC.get(cfg, "theme") == "default"
        assert PC.get(cfg, "exp_animations") == "reduced"

        removed = client.request("DELETE", "/api/exp-profiles", json={"id": preset["id"]})
        assert removed.status_code == 200
        assert all(p["id"] != preset["id"] for p in removed.json()["profiles"])


def test_orphaned_values_fall_back_and_presets_are_profile_scoped(tmp_path):
    cfg, client = _client(tmp_path)
    cfg.app["profiles"] = [{"id": "luca", "name": "Luca"}]
    cfg.app["profile"] = "luca"
    with client:
        PC.set(cfg, "exp_profiles", [{
            "id": "vecchio", "nome": "Vecchio", "experience": "rimossa",
            "theme": "tema-rimosso", "animations": "obsolete",
        }])
        applied = client.post("/api/exp-profiles/activate", json={"id": "vecchio"})
        assert applied.status_code == 200
        assert applied.json() == {
            "active": "vecchio", "experience": "catalog", "theme": "default", "animations": "normal",
        }
        assert PC.get(cfg, "experience") == "catalog"
        assert PC.get(cfg, "theme") == "default"
        assert PC.get(cfg, "exp_animations") == "normal"
        assert PC.path(cfg, "luca").exists()

        cfg.app["profile"] = "default"
        defaults = client.get("/api/exp-profiles").json()
        assert [p["nome"] for p in defaults["profiles"]] == [
            "Classico", "Cinema serata", "Console TV", "Leggero",
        ]


def test_invalid_exp_profile_inputs_are_rejected(tmp_path):
    _, client = _client(tmp_path)
    with client:
        assert client.post("/api/exp-profiles", json={
            "nome": "", "experience": "catalog", "theme": "default", "animations": "normal",
        }).status_code == 400
        assert client.post("/api/exp-profiles", json={
            "nome": "Valido", "experience": "catalog", "theme": "default", "animations": "fast",
        }).status_code == 400
        assert client.post("/api/exp-profiles/activate", json={"id": "inesistente"}).status_code == 404
        assert client.request("DELETE", "/api/exp-profiles", json={"id": "inesistente"}).status_code == 404
