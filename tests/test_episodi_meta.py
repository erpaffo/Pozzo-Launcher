"""Nome e trama degli episodi: props StreamingCommunity (ricette-web) e TMDB (media-locale)."""
import html
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


kb = _load("kb_episodi", "extensions/ricette-web/kodi_bridge.py")
meta = _load("metadata", "extensions/media-locale/metadata.py")


def test_sc_props_name_e_plot():
    props = {"title": {"id": 7, "slug": "x"}, "loadedSeason": {"number": 2, "episodes": [
        {"id": 11, "number": 1, "name": "Il primo", "plot": "Trama <b>uno</b>"},
        {"id": 12, "number": 2, "name": "", "description": ""},
    ]}}
    page = '<div data-page="%s"></div>' % html.escape(json.dumps({"props": props}), quote=True)
    eps = kb.scrape_channel_episodes(page, "https://streamingcommunity.example/it/titles/7-x", "Serie", "sc")
    assert (eps[0]["title"], eps[0]["overview"]) == ("Il primo", "Trama uno")
    assert (eps[1]["title"], eps[1]["overview"]) == ("Episodio 2", "")


class R:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def _fake_tmdb(monkeypatch, calls):
    monkeypatch.setenv("TMDB_API_KEY", "k")
    meta._EP_CACHE.clear()

    def get(url, **kw):
        calls.append(url)
        if "/search/tv" in url:
            return R({"results": [{"id": 5}]})
        return R({"episodes": [{"episode_number": 1, "name": "Pilot", "overview": "Trama", "still_path": "/s.jpg"}]})

    monkeypatch.setattr(meta.httpx, "get", get)


def test_tmdb_episodio_con_cache(monkeypatch):
    calls = []
    _fake_tmdb(monkeypatch, calls)
    m = meta.fetch_tmdb_episode_metadata("Serie", 1, 1)
    assert m == {"title": "Pilot", "overview": "Trama", "still": "https://image.tmdb.org/t/p/w500/s.jpg"}
    meta.fetch_tmdb_episode_metadata("Serie", 1, 2)
    assert len(calls) == 2  # una ricerca + una stagione, poi cache


def test_tmdb_senza_chiave_o_errore(monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    assert meta.fetch_tmdb_episode_metadata("Serie", 1, 1) == {}
    monkeypatch.setenv("TMDB_API_KEY", "k")
    meta._EP_CACHE.clear()
    monkeypatch.setattr(meta.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rete")))
    assert meta.fetch_tmdb_episode_metadata("Serie", 1, 1) == {}


def test_enrich_non_sovrascrive(monkeypatch):
    _fake_tmdb(monkeypatch, [])
    base = {"kind": "episodio", "series": "Serie", "season": 1, "episode": 1, "poster": "p", "path": "/a/S01E01.mkv"}
    r = meta.enrich_item({**base, "title": "S01E01.mkv"})
    assert (r["title"], r["overview"]) == ("Pilot", "Trama")
    r = meta.enrich_item({**base, "title": "Titolo mio", "overview": "Mia trama"})
    assert (r["title"], r["overview"]) == ("Titolo mio", "Mia trama")
