"""media-server contro un server finto (httpx.MockTransport): stesso set di prove per Jellyfin e Plex.

Nessuna rete: le risposte vengono da tests/fixtures_media/*.json. Copre list, detail, play_target,
set_progress, server irraggiungibile, token scaduto (401), contenuto senza poster, episodio senza stagione.

Esegui: python -m pytest tests/test_media_server_mock.py -q
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).parent / "fixtures_media"
TOKEN = "TOKEN-SEGRETO"


def load():
    spec = importlib.util.spec_from_file_location("media_server_backend",
                                                 ROOT / "extensions" / "media-server" / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = load()


def fixture(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- server finto
class Fake:
    """Gestore di httpx.MockTransport: [ (predicato sull'URL, risposta | eccezione), ... ]."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, request):
        self.calls.append(request)
        for match, data in self.table:
            if match(request):
                if isinstance(data, Exception):
                    raise data
                if isinstance(data, tuple):
                    return httpx.Response(data[0], json=data[1])
                return httpx.Response(200, json=data)
        return httpx.Response(404, json={"errore": "non trovata"})

    def paths(self, method: str | None = None) -> list[str]:
        return [r.url.path for r in self.calls if method is None or r.method == method]

    def body(self, path: str) -> dict:
        for r in self.calls:
            if r.url.path == path:
                return json.loads(r.content or b"{}")
        raise AssertionError(f"nessuna chiamata a {path}: {self.paths()}")


def route(path: str, data, status: int = 200):
    return (lambda r, p=path: r.url.path == p, (status, data) if status != 200 else data)


def under(prefix: str, data):
    return (lambda r, p=prefix: r.url.path.startswith(p), data)


JF = [
    route("/Users/U1/Items/jf-movie", fixture("jellyfin_item_movie.json")),
    route("/Users/U1/Items/jf-ep", fixture("jellyfin_item_episode_senza_stagione.json")),
    under("/Users/U1/PlayedItems/", {}),
    under("/Sessions/Playing", {}),
    route("/Items", fixture("jellyfin_items.json")),
]

PLEX = [
    route("/library/sections", fixture("plex_sections.json")),
    route("/library/sections/1/all", fixture("plex_section_movies.json")),
    route("/library/sections/2/all", fixture("plex_section_episodes_senza_stagione.json")),
    route("/library/sections/3/all", {"MediaContainer": {"Metadata": []}}),
    route("/library/metadata/201", fixture("plex_item_movie.json")),
    route("/library/metadata/202", fixture("plex_item_episode_senza_stagione.json")),
    route("/library/metadata/203", fixture("plex_item_movie_senza_poster.json")),
    under("/:/", {}),
]


def server(monkeypatch, table):
    """Instrada il vero httpx.Client su MockTransport: si prova anche la classe Http dell'estensione."""
    handler = Fake(table)
    real = httpx.Client

    def factory(*a, **kw):
        kw["transport"] = httpx.MockTransport(handler)
        return real(*a, **kw)

    monkeypatch.setattr(httpx, "Client", factory)
    return handler


def jellyfin(monkeypatch, table=None):
    handler = server(monkeypatch, table if table is not None else JF)
    return M.Jellyfin("http://jellyfin.local:8096", M.Http(), TOKEN, "U1"), handler


def plex(monkeypatch, table=None):
    handler = server(monkeypatch, table if table is not None else PLEX)
    return M.Plex("http://plex.local:32400", M.Http(), TOKEN), handler


SOURCES = {
    "jellyfin": {
        "make": jellyfin, "film": "jf-movie", "episode": "jf-ep", "senza_poster": "jf-ep",
        "progress": "/Sessions/Playing/Progress", "base": "http://jellyfin.local:8096",
    },
    "plex": {
        "make": plex, "film": "201", "episode": "202", "senza_poster": "203",
        "progress": "/:/progress", "base": "http://plex.local:32400",
    },
}


@pytest.fixture(params=list(SOURCES))
def source(request):
    return request.param


def adapter(source, monkeypatch, table=None):
    return SOURCES[source]["make"](monkeypatch, table)


# ---------------------------------------------------------------- contratto
def test_list_ha_la_forma_media_item(source, monkeypatch):
    ad, _ = adapter(source, monkeypatch)
    items = ad.list()
    assert items, "lista vuota"
    for item in items:
        assert set(item) <= {"id", "kind", "title", "series", "season", "episode", "year", "duration", "poster",
                             "overview", "source", "resume_pos", "seen"}
        assert item["id"] and item["title"] and item["kind"] in ("film", "episodio", "brano")
        assert item["source"] == source
    assert TOKEN not in json.dumps(items), "il token non deve comparire negli item"


def test_list_filtra_per_tipo(source, monkeypatch):
    """Il filtro arriva al server (Jellyfin: IncludeItemTypes; Plex: solo la sezione giusta)."""
    ad, handler = adapter(source, monkeypatch)
    films = ad.list(kind="film")
    if source == "jellyfin":
        call = next(r for r in handler.calls if r.url.path == "/Items")
        assert call.url.params["IncludeItemTypes"] == "Movie"
    else:
        assert "/library/sections/1/all" in handler.paths()
        assert "/library/sections/2/all" not in handler.paths()
        assert films and all(i["kind"] == "film" for i in films)


def test_detail(source, monkeypatch):
    ad, _ = adapter(source, monkeypatch)
    film = next(i for i in ad.list() if i["kind"] == "film")
    assert ad.detail(film["id"]) == film
    with pytest.raises(HTTPException) as err:
        ad.detail("non-esiste")
    assert err.value.status_code == 404
    assert "Traceback" not in str(err.value.detail)


def test_play_target(source, monkeypatch):
    ad, _ = adapter(source, monkeypatch)
    film = SOURCES[source]["film"]
    mkv = ad.play_target(film)
    assert mkv["url"].startswith(SOURCES[source]["base"]) and mkv["external"] is True
    assert mkv["mime"] == "video/x-matroska"
    mp4 = ad.play_target(SOURCES[source]["episode"])
    assert mp4["external"] is False and mp4["mime"] == "video/mp4"
    assert isinstance(mp4["resume_pos"], (int, float))


def test_set_progress_manda_la_posizione_al_server(source, monkeypatch):
    ad, handler = adapter(source, monkeypatch)
    ad.set_progress(SOURCES[source]["film"], 42.0, False)
    if source == "jellyfin":
        assert handler.body("/Sessions/Playing/Progress")["PositionTicks"] == 420_000_000
    else:
        call = next(r for r in handler.calls if r.url.path == "/:/progress")
        assert call.url.params["time"] == "42000" and call.url.params["state"] == "playing"
        assert call.url.params["key"] == "201"


def test_set_progress_seen(source, monkeypatch):
    ad, handler = adapter(source, monkeypatch)
    ad.set_progress(SOURCES[source]["film"], 0.0, True)
    if source == "jellyfin":
        assert any("/Users/U1/PlayedItems/" in p for p in handler.paths("POST"))
        assert "/Sessions/Playing/Stopped" in handler.paths("POST")
    else:
        assert "/:/scrobble" in handler.paths("POST")


# ---------------------------------------------------------------- casi ostili
def test_server_irraggiungibile(source, monkeypatch):
    boom = httpx.ConnectError(f"connessione rifiutata verso {SOURCES[source]['base']}?token={TOKEN}")
    ad, _ = adapter(source, monkeypatch, [(lambda r: True, boom)])
    with pytest.raises(HTTPException) as err:
        ad.list()
    assert err.value.status_code == 502
    assert "non raggiungibile" in err.value.detail
    assert TOKEN not in err.value.detail, "l'URL con il token non deve finire nel messaggio"
    assert "?" not in err.value.detail


def test_token_scaduto_401(source, monkeypatch):
    ad, _ = adapter(source, monkeypatch, [(lambda r: True, (401, {"errore": "unauthorized"}))])
    with pytest.raises(HTTPException) as err:
        ad.list()
    assert err.value.status_code == 401
    assert "credenziali" in err.value.detail.lower()
    assert TOKEN not in err.value.detail


def test_item_senza_poster(source, monkeypatch):
    ad, _ = adapter(source, monkeypatch)
    item = ad.detail(SOURCES[source]["senza_poster"])
    assert "poster" not in item and item["title"]


def test_episodio_senza_stagione(source, monkeypatch):
    ad, _ = adapter(source, monkeypatch)
    episodio = ad.detail(SOURCES[source]["episode"])
    assert episodio["kind"] == "episodio" and "season" not in episodio and "episode" not in episodio
    assert episodio["series"] == "Serie"


def test_risposta_non_leggibile(source, monkeypatch):
    """Server che risponde HTML invece di JSON (pagina di errore di un proxy): errore pulito, non 500."""
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: real(*a, **{**kw, "transport": httpx.MockTransport(
        lambda request: httpx.Response(200, text="<html>manutenzione</html>"))}))
    ad = (M.Jellyfin("http://jellyfin.local:8096", M.Http(), TOKEN, "U1") if source == "jellyfin"
          else M.Plex("http://plex.local:32400", M.Http(), TOKEN))
    with pytest.raises(HTTPException) as err:
        ad.list()
    assert err.value.status_code == 502 and "non leggibile" in err.value.detail
