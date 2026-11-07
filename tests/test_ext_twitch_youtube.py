"""extensions/twitch-youtube: parsing delle risposte, token Twitch in cache, errori con chiavi mancanti, cache delle route.
Rete finta (httpx.MockTransport): nessuna chiamata vera.

Esegui: python -m pytest tests/test_ext_twitch_youtube.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load():
    spec = importlib.util.spec_from_file_location("ext_twitch_youtube", ROOT / "extensions" / "twitch-youtube" / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._cache.clear()
    mod._token.clear()
    return mod


STREAMS = {"data": [{"user_name": "Shroud", "user_login": "shroud", "title": "Ranked!", "viewer_count": 12345,
                     "thumbnail_url": "https://static-cdn.jtvnw.net/previews-ttv/live_user_shroud-{width}x{height}.jpg"}]}
VIDEOS = {"items": [
    {"id": {"kind": "youtube#video", "videoId": "abc123XYZ_-"},
     "snippet": {"title": "Elden Ring &amp; DLC &#39;Trailer&#39;", "channelTitle": "Bandai &amp; Co",
                 "thumbnails": {"medium": {"url": "https://i.ytimg.com/vi/abc123XYZ_-/mqdefault.jpg"}}}},
    {"id": {"kind": "youtube#video", "videoId": "second111AA"},
     "snippet": {"title": "Guida", "channelTitle": "Canale", "thumbnails": {"default": {"url": "https://i.ytimg.com/d.jpg"}}}},
]}


def mock_client(m, monkeypatch, handler):
    monkeypatch.setattr(m, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))


def test_parse_streams_e_videos():
    m = load()
    assert m.parse_streams(STREAMS) == [{
        "user": "Shroud", "title": "Ranked!", "viewers": 12345,
        "thumbnail": "https://static-cdn.jtvnw.net/previews-ttv/live_user_shroud-440x248.jpg",
        "url": "https://www.twitch.tv/shroud"}]
    assert m.parse_streams({"data": []}) == []
    video = m.parse_videos(VIDEOS)
    assert video[0] == {"title": "Elden Ring & DLC 'Trailer'", "channel": "Bandai & Co",
                        "thumb": "https://i.ytimg.com/vi/abc123XYZ_-/mqdefault.jpg", "videoId": "abc123XYZ_-"}
    assert video[1]["thumb"] == "https://i.ytimg.com/d.jpg"                # ripiego su «default»
    assert m.parse_videos({"items": [{"id": {"kind": "youtube#channel"}, "snippet": {}}]}) == []


def test_live_token_in_cache_e_richieste(monkeypatch):
    m = load()
    chiamate = []

    def handler(req: httpx.Request):
        chiamate.append((req.url.host, req.url.path, dict(req.url.params)))
        if req.url.host == "id.twitch.tv":
            assert b"client_credentials" in req.content
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if req.url.path == "/helix/games":
            assert req.headers["Client-Id"] == "cid" and req.headers["Authorization"] == "Bearer tok"
            return httpx.Response(200, json={"data": [{"id": "1245620", "name": "Elden Ring"}]})
        return httpx.Response(200, json=STREAMS)

    mock_client(m, monkeypatch, handler)
    assert m.twitch_live("Elden Ring", "cid", "sec")[0]["user"] == "Shroud"
    m.twitch_live("Elden Ring", "cid", "sec")
    assert sum(1 for c in chiamate if c[0] == "id.twitch.tv") == 1       # token riusato fino alla scadenza
    assert ("api.twitch.tv", "/helix/streams", {"game_id": "1245620", "first": "6"}) in chiamate

    m._token["exp"] = 0                                                   # scaduto: se ne chiede uno nuovo
    m.twitch_live("Elden Ring", "cid", "sec")
    assert sum(1 for c in chiamate if c[0] == "id.twitch.tv") == 2


def test_gioco_sconosciuto_non_chiede_le_dirette(monkeypatch):
    m = load()
    chiamate = []

    def handler(req: httpx.Request):
        chiamate.append(req.url.path)
        if req.url.host == "id.twitch.tv":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx.Response(200, json={"data": []})

    mock_client(m, monkeypatch, handler)
    assert m.twitch_live("Gioco Inesistente", "cid", "sec") == []
    assert "/helix/streams" not in chiamate


def test_credenziali_sbagliate_e_rete(monkeypatch):
    m = load()
    mock_client(m, monkeypatch, lambda req: httpx.Response(401, json={"message": "invalid client"}))
    with pytest.raises(HTTPException) as e:
        m.twitch_live("Elden Ring", "cid", "sec")
    assert e.value.status_code == 502 and "credenziali" in e.value.detail

    def guasta(req):
        raise httpx.ConnectError("no network")

    m._token.clear()
    mock_client(m, monkeypatch, guasta)
    with pytest.raises(HTTPException) as e:
        m.youtube_videos("Elden Ring", "KEY")
    assert e.value.status_code == 502 and "rete" in e.value.detail


def test_youtube_query_e_deduplica(monkeypatch):
    m = load()
    query = []

    def handler(req: httpx.Request):
        query.append(dict(req.url.params))
        return httpx.Response(200, json=VIDEOS)                          # stessi video per trailer e guida

    mock_client(m, monkeypatch, handler)
    out = m.youtube_videos("Elden Ring", "KEY")
    assert [q["q"] for q in query] == ["Elden Ring trailer", "Elden Ring guida"]
    assert all(q["part"] == "snippet" and q["type"] == "video" and q["maxResults"] == "6" and q["key"] == "KEY" for q in query)
    assert [v["videoId"] for v in out] == ["abc123XYZ_-", "second111AA"]  # niente doppioni


class FakeGS:
    """Come PluginAPI: le route finiscono sull'app, le impostazioni restano in memoria."""

    def __init__(self, app):
        self.app, self.settings, self.log = app, {}, (lambda _: None)

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.app.add_api_route(f"/plugin-api/twitch-youtube/{path}", fn, methods=list(methods))
            return fn
        return deco

    def save_settings(self, values):
        self.settings.update(values)


def test_route_chiavi_mancanti_salvataggio_e_cache(monkeypatch):
    m = load()
    app = FastAPI()
    gs = FakeGS(app)
    m.register(gs)
    cl = TestClient(app)

    r = cl.get("/plugin-api/twitch-youtube/live/Elden%20Ring")
    assert r.status_code == 400 and "Client ID" in r.json()["detail"]
    r = cl.get("/plugin-api/twitch-youtube/videos/Elden%20Ring")
    assert r.status_code == 400 and "YouTube" in r.json()["detail"]
    assert cl.get("/plugin-api/twitch-youtube/stato").json() == {"twitch": False, "youtube": False}

    j = cl.post("/plugin-api/twitch-youtube/impostazioni",
                json={"twitch_client_id": " cid ", "twitch_client_secret": "sec", "youtube_key": ""}).json()
    assert j == {"twitch": True, "youtube": False}
    assert gs.settings == {"twitch_client_id": "cid", "twitch_client_secret": "sec"}   # chiave vuota: non tocca nulla

    chiamate = []
    monkeypatch.setattr(m, "twitch_live", lambda t, c, s: chiamate.append(t) or [{"user": "x"}])
    assert cl.get("/plugin-api/twitch-youtube/live/Elden%20Ring").json() == {"streams": [{"user": "x"}]}
    cl.get("/plugin-api/twitch-youtube/live/Elden%20Ring")
    assert chiamate == ["Elden Ring"]                                      # seconda risposta dalla cache
