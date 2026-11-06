"""hot_load / hot_unload: montaggio e rimozione di un plugin a runtime, senza riavvio.

Esegui: python -m pytest tests/test_extensions_hot.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pozzo.app import extensions as X  # noqa: E402

SRC = "def register(gs):\n    @gs.route('v')\n    def v():\n        return {{'v': {n}}}\n"


def write(tmp_path, pid, load="", src=SRC.format(n=1)):
    d = tmp_path / "plugins" / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.toml").write_text(f'[plugin]\nname = "{pid}"\napi = 1\n{load}\n', encoding="utf-8")
    (d / "backend.py").write_text(src, encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    yield tmp_path, SimpleNamespace(config_path=tmp_path / "config.toml", app={}), FastAPI(), X.Events(), {}
    X.stop_jobs()
    X.LAZY.clear()


@pytest.mark.parametrize("load", ["", 'load = "lazy"'])
def test_load_update_unload(env, load):
    tmp, cfg, app, ev, errors = env
    c = TestClient(app)
    write(tmp, "nuovo", load)
    assert X.hot_load(app, cfg, ev, "nuovo", lambda *_: None, errors) is True
    assert c.get("/plugin-api/nuovo/v").json() == {"v": 1}
    write(tmp, "nuovo", load, SRC.format(n=2) + "# piu lungo\n")  # cache pyc: mtime+dimensione
    assert X.hot_load(app, cfg, ev, "nuovo", lambda *_: None, errors) is True
    assert c.get("/plugin-api/nuovo/v").json() == {"v": 2}
    assert sum(str(getattr(r, "path", "")).startswith("/plugin-api/nuovo/") for r in app.router.routes) == 1
    X.hot_unload(app, "nuovo")
    assert c.get("/plugin-api/nuovo/v").status_code == 404


def test_broken_backend_returns_false_and_leaves_no_routes(env):
    tmp, cfg, app, ev, errors = env
    write(tmp, "rotto", src="def register(gs):\n    gs.route('x')(lambda: 1)\n    raise RuntimeError('boom')\n")
    assert X.hot_load(app, cfg, ev, "rotto", lambda *_: None, errors) is False
    assert "boom" in errors["rotto"]
    assert not any(str(getattr(r, "path", "")).startswith("/plugin-api/rotto/") for r in app.router.routes)


def test_unload_stops_jobs_and_lazy_events(env):
    tmp, cfg, app, ev, errors = env
    write(tmp, "lav", src="def register(gs):\n    gs.job('j', lambda: None, 3600)\n")
    X.hot_load(app, cfg, ev, "lav", lambda *_: None, errors)
    assert any(j.pid == "lav" for j in X.JOBS)
    X.hot_unload(app, "lav")
    assert not any(j.pid == "lav" for j in X.JOBS)
    assert X.hot_load(app, cfg, ev, "assente", lambda *_: None, errors) is False
