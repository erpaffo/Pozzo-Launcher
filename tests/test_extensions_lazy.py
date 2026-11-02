"""Plugin load = "lazy": montati senza importare il backend, avviati al primo accesso (una sola volta).

Esegui: python -m pytest tests/test_extensions_lazy.py
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

COUNTER = "import builtins\nbuiltins.__dict__.setdefault('LAZY_HITS', [])\nbuiltins.LAZY_HITS.append('{id}')\n"
OK = COUNTER + "def register(gs):\n    @gs.route('ciao')\n    def ciao():\n        return {'ok': '{id}'}\n    @gs.route('eco', methods=('POST',))\n    def eco(body: dict):\n        return body\n"


def make(tmp_path, plugins: dict[str, tuple[str, str]]):
    """plugins: {id: (riga load del manifest, sorgente backend)}; ritorna (app, cfg, errori, log)."""
    for pid, (load, src) in plugins.items():
        d = tmp_path / "plugins" / pid
        d.mkdir(parents=True)
        (d / "plugin.toml").write_text(f'[plugin]\nname = "{pid}"\napi = 1\n{load}\n', encoding="utf-8")
        (d / "backend.py").write_text(src.replace("{id}", pid), encoding="utf-8")
    cfg = SimpleNamespace(config_path=tmp_path / "config.toml", app={})
    app, log = FastAPI(), []
    errors = X.load_backends(app, cfg, X.Events(), log.append)
    return app, cfg, errors, log


@pytest.fixture(autouse=True)
def _clean():
    import builtins
    builtins.LAZY_HITS = []
    yield
    X.stop_jobs()
    for d in (X.LOAD_MS, X.FIRST_USE_MS, X.EAGER_NEEDED):
        d.clear()


def plug(cfg, pid, errors=None):
    return next(p for p in X.list_plugins(cfg, errors) if p["id"] == pid)


def hits():
    import builtins
    return list(builtins.LAZY_HITS)


def test_lazy_not_imported_at_startup_and_once_at_first_access(tmp_path):
    app, cfg, errors, _ = make(tmp_path, {"pigro": ('load = "lazy"', OK)})
    assert errors == {} and hits() == []  # niente import all'avvio
    p = plug(cfg, "pigro")
    assert p["load"] == "lazy" and p["load_ms"] is not None and p["first_use_ms"] is None
    c = TestClient(app)
    assert c.post("/plugin-api/pigro/eco", json={"a": 1}).json() == {"a": 1}  # la prima richiesta e' inoltrata
    assert c.get("/plugin-api/pigro/ciao").json() == {"ok": "pigro"}
    assert c.get("/plugin-api/pigro/ciao").json() == {"ok": "pigro"}
    assert hits() == ["pigro"]  # importato una sola volta
    p = plug(cfg, "pigro")
    assert p["first_use_ms"] is not None and p["eager_needed"] == []
    assert c.get("/plugin-api/pigro/non-esiste").status_code == 404
    assert X.LOAD_TOTAL_MS >= 0


def test_eager_unchanged(tmp_path):
    app, cfg, errors, _ = make(tmp_path, {"subito": ("", OK), "x": ('load = "boh"', OK)})
    assert hits() == ["subito", "x"]  # eager: importati all'avvio (anche con un valore sconosciuto)
    assert plug(cfg, "subito")["load"] == plug(cfg, "x")["load"] == "eager"
    assert TestClient(app).get("/plugin-api/subito/ciao").json() == {"ok": "subito"}
    assert X.FIRST_USE_MS == {}


def test_register_error_gives_500_only_on_that_plugin(tmp_path):
    bad = "def register(gs):\n    raise RuntimeError('rotto')\n"
    app, cfg, errors, log = make(tmp_path, {"guasto": ('load = "lazy"', bad), "sano": ('load = "lazy"', OK)})
    assert errors == {}  # all'avvio nessun errore: il backend non e' ancora stato avviato
    c = TestClient(app)
    r = c.get("/plugin-api/guasto/ciao")
    assert r.status_code == 500 and "rotto" in r.json()["detail"] and "guasto" in r.json()["detail"]
    assert c.get("/plugin-api/guasto/ciao").status_code == 500
    assert c.get("/plugin-api/sano/ciao").json() == {"ok": "sano"}  # l'app e gli altri plugin funzionano
    assert "RuntimeError" in errors["guasto"] and any("guasto" in m for m in log)
    assert plug(cfg, "guasto", errors)["error"]


def test_lazy_plugin_using_gs_on_is_flagged_but_works(tmp_path):
    src = ("def register(gs):\n    gs.on('game_started', lambda d: None)\n"
           "    @gs.route('ciao')\n    def ciao():\n        return {'ok': 1}\n")
    app, cfg, errors, log = make(tmp_path, {"evento": ('load = "lazy"', src)})
    assert X.EAGER_NEEDED == {}  # prima dell'uso non si sa
    assert TestClient(app).get("/plugin-api/evento/ciao").json() == {"ok": 1}
    assert X.EAGER_NEEDED == {"evento": {"gs.on"}}
    assert plug(cfg, "evento")["eager_needed"] == ["gs.on"]
    assert any("gs.on" in m and "eager" in m for m in log)
