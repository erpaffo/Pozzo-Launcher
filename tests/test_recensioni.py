"""extensions/recensioni: parsing delle risposte, cache con scadenza, route con una richiesta HTTP vera (TestClient).
Le chiamate di rete verso Steam/OpenCritic sono sostituite; Metacritic viene dal database della libreria.

Esegui: python -m pytest tests/test_recensioni.py
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pozzo import config as C  # noqa: E402
from pozzo.library import build  # noqa: E402


def load():
    spec = importlib.util.spec_from_file_location("ext_recensioni", ROOT / "extensions" / "recensioni" / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parsing():
    m = load()
    steam = {"query_summary": {"review_score_desc": "Very Positive", "total_positive": 900, "total_reviews": 1200}}
    assert m.parse_steam(steam) == {"desc": "Very Positive", "positive": 900, "total": 1200, "percent": 75}
    assert m.parse_steam({"query_summary": {"total_reviews": 0}}) is None
    og = {"id": 42, "topCriticScore": 86.4, "percentRecommended": 91.2, "tier": "Mighty", "url": "https://opencritic.com/game/42/x"}
    assert m.parse_oc_game(og) == {"score": 86, "recommended": 91, "tier": "Mighty", "url": "https://opencritic.com/game/42/x"}
    assert m.parse_oc_game({"id": 1, "topCriticScore": -1}) is None
    assert m.pick_oc([{"id": 5, "name": "Hollow Knight: Silksong"}, {"id": 7, "name": "Hollow Knight"}], "hollow knight") == 7
    assert m.pick_oc([{"id": 5, "name": "Hollow Knight: Silksong"}], "Hollow Knight") is None
    assert m.steam_appid({"key": "windows/steam:367520", "page": "", "store_pages": None}) == "367520"
    assert m.steam_appid({"key": "x", "page": "", "store_pages": '[{"url": "https://store.steampowered.com/app/57300/"}]'}) == "57300"
    assert m.steam_appid({"key": "x", "page": "", "store_pages": None}) is None


def test_cache_scadenza():
    m = load()
    store, chiamate = {}, []

    def ok():
        chiamate.append(1)
        return {"score": 80}

    def boom():
        raise RuntimeError("rete")

    assert m.cached(store, "oc", ok, now=1000.0, ident="k") == {"score": 80}
    m.cached(store, "oc", ok, now=1000.0 + 6 * 86400, ident="k")
    assert len(chiamate) == 1                                   # 6 giorni: ancora in cache
    m.cached(store, "oc", ok, now=1000.0 + 8 * 86400, ident="k")
    assert len(chiamate) == 2                                   # oltre 7 giorni: di nuovo
    m.cached(store, "oc", ok, now=1000.0 + 8 * 86400, ident="altra")
    assert len(chiamate) == 3                                   # cambia la chiave: di nuovo
    assert m.cached(store, "st", boom, now=0.0, log=lambda _: None) is None
    m.cached(store, "st", ok, now=86399.0)
    assert len(chiamate) == 3                                   # errore ricordato per un giorno
    m.cached(store, "st", ok, now=86401.0)
    assert len(chiamate) == 4


def test_route_scores(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    cfg = C.Config(cache=tmp_path / "cache")
    cfg.config_path = tmp_path / "config.toml"
    cfg.app = {}
    cfg.cache.mkdir(parents=True, exist_ok=True)
    lib = sqlite3.connect(cfg.cache / "library.db")
    lib.executescript(build.SCHEMA)
    lib.execute("INSERT INTO games(id, key, platform, title, sort_title, grp, is_primary, store, found, rating_critics, page) "
                "VALUES(3, 'windows/steam:367520', 'windows', 'Hollow Knight', 'hollow knight', 'hk', 1, 'steam', 1, 0.87, "
                "'https://store.steampowered.com/app/367520')")
    lib.commit()
    lib.close()

    app = FastAPI()

    class GS:  # come PluginAPI: le route finiscono sull'app, le impostazioni restano in memoria
        def __init__(self):
            self.cfg, self.settings, self.log = cfg, {}, (lambda _: None)

        def route(self, path, methods=("GET",)):
            def deco(fn):
                app.add_api_route(f"/plugin-api/recensioni/{path}", fn, methods=list(methods))
                return fn
            return deco

        def save_settings(self, values):
            self.settings.update(values)

    m = load()
    m.register(GS())
    monkeypatch.setattr(m, "fetch_steam", lambda appid: {"desc": "Very Positive", "positive": 9, "total": 10, "percent": 90,
                                                         "url": "https://store.steampowered.com/app/367520/"} if appid == "367520" else None)
    cl = TestClient(app)
    r = cl.get("/plugin-api/recensioni/scores/3")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["metacritic"] == {"score": 87, "url": "https://www.metacritic.com/search/Hollow%20Knight/"}
    assert j["opencritic"] is None                              # nessuna chiave: nessuna richiesta
    assert j["steam"]["percent"] == 90
    assert cl.get("/plugin-api/recensioni/scores/99").status_code == 404
    assert cl.get("/plugin-api/recensioni/stato").json() == {"opencritic": False}
    assert cl.post("/plugin-api/recensioni/chiave", json={"opencritic_key": " abc "}).json() == {"opencritic": True}
