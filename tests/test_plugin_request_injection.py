"""Con un FastAPI vero (non il FakeGS dei test) le rotte dei backend media ricevono davvero `request`.

I backend usano `from __future__ import annotations` e `request: Request = None`: se FastAPI non lo riconoscesse,
il profilo sarebbe sempre quello di riserva e la watchlist/ripresa per profilo non funzionerebbe nel launcher.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

EXT = Path(__file__).resolve().parent.parent / "extensions"


def _load(name: str, folder: str):
    import sys
    d = str(EXT / folder)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(name, EXT / folder / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class RealGS:
    """Come PluginAPI: le rotte finiscono su un'app FastAPI reale."""

    def __init__(self, app, cfg, pid):
        self.app, self.cfg, self.id, self.settings = app, cfg, pid, {}

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.app.add_api_route(f"/plugin-api/{self.id}/{path.lstrip('/')}", fn, methods=list(methods))
            return fn
        return deco

    def log(self, *a, **k):
        pass

    def job(self, *a, **k):
        return None

    def on(self, *a, **k):
        pass

    def add_library_kind(self, *a, **k):
        pass

    def add_player(self, *a, **k):
        pass

    def add_scraper(self, *a, **k):
        pass

    def add_store(self, *a, **k):
        pass

    def add_source(self, *a, **k):
        pass

    def save_settings(self, *a, **k):
        pass


def test_media_locale_riceve_request(tmp_path):
    ml = _load("ml_inj", "media-locale")
    seen = []
    orig = ml.profile_id
    ml.profile_id = lambda request=None, cfg=None: (seen.append(request is not None), orig(request, cfg))[1]
    app = FastAPI()
    cfg = SimpleNamespace(config_path=tmp_path / "config.toml", app={"profile": "default"})
    ml.register(RealGS(app, cfg, "media-locale"))
    c = TestClient(app, cookies={"gs_profile": "profilo-inesistente"})  # id non valido: ricade su cfg.app
    seen.clear()
    r = c.post("/plugin-api/media-locale/watchlist", json={"item_key": "a:1", "title": "Dune", "kind": "film"})
    assert r.status_code == 200, r.text
    r = c.get("/plugin-api/media-locale/watchlist")
    assert r.status_code == 200 and [x["title"] for x in r.json()["items"]] == ["Dune"]
    r = c.get("/plugin-api/media-locale/list")
    assert r.status_code == 200
    assert seen and all(seen), "FastAPI deve passare `request` alle rotte (altrimenti il profilo non si legge mai dal cookie)"


def test_ricette_web_riceve_request(tmp_path, monkeypatch):
    """Se `request` non arrivasse, i due profili vedrebbero lo stesso avanzamento."""
    import sqlite3
    rw = _load("rw_inj", "ricette-web")
    monkeypatch.setattr(rw, "load_recipes", lambda ext_dir=None: [])
    monkeypatch.setattr(rw, "kodi_bridge_module", lambda: None)
    app = FastAPI()
    cfg = SimpleNamespace(config_path=tmp_path / "config.toml", app={"profile": "a", "profiles": [{"id": "a"}, {"id": "b"}]})
    rw.register(RealGS(app, cfg, "ricette-web"))
    conn = sqlite3.connect(tmp_path / "ricette-web-cache" / "ricette.db")
    conn.execute("INSERT INTO items (id, recipe_id, kind, title, source, duration, updated) VALUES ('x1','r','film','Film','ricette-web', 3000, 0)")
    conn.commit(); conn.close()
    a, b = TestClient(app), TestClient(app, cookies={"gs_profile": "b"})
    assert a.get("/plugin-api/ricette-web/list").status_code == 200
    r = b.post("/plugin-api/ricette-web/set_progress", json={"id": "x1", "pos": 120})
    assert r.status_code == 200, r.text
    pos = lambda cl: next(i for i in cl.get("/plugin-api/ricette-web/list").json() if i["id"] == "x1")["resume_pos"]
    assert pos(b) == 120.0, "il profilo del cookie vede il suo avanzamento"
    assert pos(a) == 0.0, "l'altro profilo no: `request` e' arrivato e il cookie e' stato letto"
    r = a.post("/plugin-api/ricette-web/prefetch", json={"id": "inesistente"})
    assert r.status_code == 200 and r.json() == {"ok": False, "warming": False}
