"""Contratto «fonte di media»: lo stesso test su media-locale, Jellyfin e Plex (client HTTP finto).

    list(kind, query) -> [MediaItem] / detail(id) / play_target(id) / set_progress(id, pos, seen)
    MediaItem = {id, kind, title, series?, season?, episode?, year?, duration?, poster?, backdrop?, overview?,
                 source, resume_pos?, seen?}   (+ album per i brani locali)

Esegui: python -m pytest tests/test_media_contratto.py
"""

from __future__ import annotations

import importlib.util
import re
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXT = ROOT / "extensions"
ITEM_KEYS = {"id", "kind", "title", "series", "season", "episode", "year", "duration", "poster", "backdrop",
             "overview", "source", "resume_pos", "seen", "album"}
KINDS = {"film", "episodio", "brano"}


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"ext_{name.replace('-', '_')}", EXT / name / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeGS:
    """Sostituto di PluginAPI: raccoglie rotte, kind, player e impostazioni invece di toccare FastAPI."""

    def __init__(self, cfg, pid):
        self.cfg, self.id, self.routes, self.settings = cfg, pid, {}, {}
        self.kinds, self.players, self.logs, self.jobs = [], [], [], []
        self.log = self.logs.append

    def route(self, path, methods=("GET",)):
        def deco(fn):
            self.routes[(path.lstrip("/"), methods[0])] = fn
            return fn
        return deco

    def get(self, path, **kw):
        return self.routes[(path, "GET")](**kw)

    def post(self, path, body=None, **kw):
        if body is None:
            return self.routes[(path, "POST")](**kw)
        return self.routes[(path, "POST")](body=body, **kw)

    def add_library_kind(self, kind):
        self.kinds.append(kind)

    def add_player(self, player):
        self.players.append(player)

    def save_settings(self, values):
        self.settings.update(values)

    def job(self, name, fn, every, run_at_start=False):
        self.jobs.append(name)


class Resp:
    def __init__(self, data, status_code=200, content=b"", ctype="application/json"):
        self.data, self.status_code, self.content = data, status_code, content
        self.headers = {"content-type": ctype}

    def json(self):
        return self.data


class MockHttp:
    """Client HTTP finto: [ (pattern sull'URL, risposta), ... ] e registro delle chiamate."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def request(self, method, url, params=None, json=None, headers=None, **kw):
        self.calls.append({"method": method, "url": url, "params": params or {}, "json": json or {},
                           "headers": headers or {}})
        for pattern, data in self.routes:
            if re.search(pattern, url):
                return data if isinstance(data, Resp) else Resp(data)
        return Resp({}, status_code=404)

    def close(self):
        pass

    def calls_to(self, needle: str) -> list[dict]:
        return [c for c in self.calls if needle in c["url"]]


def cfg_for(tmp: Path):
    return SimpleNamespace(config_path=tmp / "config.toml", app={})


def contract(src, kinds=KINDS):
    """Asserzioni comuni alle tre fonti. `src` espone list/detail/play_target/set_progress e `source`."""
    items = src.list()
    assert items and {i["kind"] for i in items} == kinds
    for item in items:
        assert item["source"] == src.source
        assert item["id"] and isinstance(item["title"], str) and item["title"]
        assert item["kind"] in KINDS and set(item) <= ITEM_KEYS, item

    first = items[0]
    assert src.detail(first["id"])["title"] == first["title"]
    with pytest.raises(HTTPException) as err:
        src.detail("non-esiste")
    assert err.value.status_code == 404

    target = src.play_target(first["id"])
    assert isinstance(target["resume_pos"], (int, float))
    assert target.get("url") or target.get("path")

    assert src.set_progress(first["id"], 42.5, False)["ok"] is True
    assert src.set_progress(first["id"], 0.0, True)["ok"] is True
    return items


# ---------------------------------------------------------------- media-locale
class Locale:
    source = "media-locale"

    def __init__(self, gs):
        self.gs = gs

    def list(self, kind="", query=""):
        return self.gs.get("list", kind=kind, query=query)

    def detail(self, item_id):
        return self.gs.get("detail", id=item_id)

    def play_target(self, item_id):
        return self.gs.get("play_target", id=item_id)

    def set_progress(self, item_id, pos, seen):
        return self.gs.post("set_progress", {"id": item_id, "pos": pos, "seen": seen})


def make_locale(tmp: Path):
    M = load("media-locale")
    lib = tmp / "media"
    (lib / "Serie (2019)" / "Season 01").mkdir(parents=True)
    (lib / "Artista" / "Album").mkdir(parents=True)
    (lib / "Film (2020).mkv").write_bytes(b"x")
    (lib / "Corto.mp4").write_bytes(b"x")
    (lib / "poster.jpg").write_bytes(b"jpg")
    (lib / "Serie (2019)" / "Season 01" / "S01E02 - Il titolo.mkv").write_bytes(b"x")
    (lib / "Artista" / "Album" / "01 - Titolo.flac").write_bytes(b"x")
    gs = FakeGS(cfg_for(tmp), "media-locale")
    M.register(gs)
    gs.post("roots", {"add": str(lib)})
    gs.post("scan")
    return M, gs, lib


def test_contratto_media_locale(tmp):
    M, gs, lib = make_locale(tmp)
    src = Locale(gs)
    items = contract(src)

    kinds = {i["kind"]: i for i in items}
    assert kinds["episodio"]["series"] == "Serie" and kinds["episodio"]["year"] == 2019
    assert kinds["episodio"]["season"] == 1 and kinds["episodio"]["episode"] == 2
    assert kinds["brano"]["series"] == "Artista" and kinds["brano"]["album"] == "Album"
    assert kinds["film"]["year"] == 2020
    assert gs.jobs == ["scansione-media"]  # riscansione periodica in background, non all'avvio

    # il poster locale compare come URL della rotta artwork, che restituisce il file vero
    film = next(i for i in items if i["title"] == "Film")
    assert film["poster"] == f"/plugin-api/media-locale/artwork?id={film['id']}"
    art = gs.get("artwork", id=film["id"])
    assert isinstance(art, FileResponse) and Path(art.path).name == "poster.jpg"

    # mkv: player integrato no, lettore esterno sì (niente transcodifica)
    mkv = gs.get("play_target", id=film["id"])
    assert mkv["external"] is True and "url" not in mkv and Path(mkv["path"]).name == "Film (2020).mkv"
    mp4 = next(i for i in items if i["title"] == "Corto")
    inapp = gs.get("play_target", id=mp4["id"])
    assert inapp["external"] is False and inapp["url"] == f"/plugin-api/media-locale/stream?id={mp4['id']}"
    assert Path(gs.get("stream", id=mp4["id"]).path).name == "Corto.mp4"


def test_media_locale_progressi(tmp):
    M, gs, _ = make_locale(tmp)
    item = next(i for i in gs.get("list") if i["title"] == "Film")
    out = gs.post("set_progress", {"id": item["id"], "pos": 120, "seen": False})
    assert out["item"]["resume_pos"] == 120.0 and out["item"]["seen"] is False
    assert gs.get("play_target", id=item["id"])["resume_pos"] == 120.0

    # oltre il 90% della durata -> «visto» e posizione azzerata
    out = gs.post("set_progress", {"id": item["id"], "pos": 95, "duration": 100})
    assert out["item"]["seen"] is True and "resume_pos" not in out["item"]
    assert gs.get("play_target", id=item["id"])["resume_pos"] == 0.0

    # i parametri in query funzionano quanto il corpo JSON
    out = gs.post("set_progress", None, id=item["id"], pos=10, seen=False)
    assert out["item"]["resume_pos"] == 10.0


def test_media_locale_ricerca_e_filtri(tmp):
    M, gs, _ = make_locale(tmp)
    assert [i["title"] for i in gs.get("list", kind="film")] == ["Corto", "Film"]
    assert {i["title"] for i in gs.get("list", query="Titolo")} == {"Il titolo", "Titolo"}
    assert gs.get("list", kind="boh") == gs.get("list")  # kind sconosciuto: nessun filtro
    assert gs.get("list", query="%") == []  # il carattere jolly non è interpretato
    assert len(gs.get("list", limit=1)) == 1


def test_media_locale_cartelle_valide(tmp):
    M, gs, lib = make_locale(tmp)
    with pytest.raises(HTTPException) as err:
        gs.post("roots", {"add": "cartella/relativa"})
    assert err.value.status_code == 400
    with pytest.raises(HTTPException):
        gs.post("roots", {"add": str(lib / "poster.jpg")})
    with pytest.raises(HTTPException):
        gs.post("roots", {"add": str(tmp / "non-esiste")})
    assert gs.get("roots")["roots"][0]["items"] == 4

    out = gs.post("roots", {"remove": str(lib)})
    assert out["roots"] == [] and gs.get("list") == []


def test_media_locale_percorsi_fuori_dalle_cartelle(tmp):
    """Un item che punta fuori dalle cartelle scelte non si serve: nessun percorso arbitrario dalle rotte."""
    M, gs, lib = make_locale(tmp)
    outside = tmp / "segreto.mp4"
    outside.write_bytes(b"x")
    db_file = next((tmp / "media-locale-cache").glob("media.db"))
    conn = sqlite3.connect(db_file)
    conn.execute("INSERT INTO items(id, kind, title, path, poster, root) VALUES('x1','film','Furbo',?,'',?)",
                 (str(outside), str(lib)))
    conn.commit()
    conn.close()
    assert gs.get("detail", id="x1")["title"] == "Furbo"
    for route in ("stream", "play_target", "artwork"):
        with pytest.raises(HTTPException) as err:
            gs.get(route, id="x1")
        assert err.value.status_code == 404
    with pytest.raises(HTTPException):  # il lettore esterno non riceve un percorso fuori dalle cartelle
        gs.post("external", {"id": "x1"})


# ---------------------------------------------------------------- Jellyfin
JF_ITEMS = [
    {"Id": "jf1", "Type": "Movie", "Name": "Film", "ProductionYear": 2020, "RunTimeTicks": 54_000_000_000,
     "Overview": "Trama", "ImageTags": {"Primary": "a"}, "Container": "mkv",
     "UserData": {"PlaybackPositionTicks": 12_000_000_000, "Played": False}},
    {"Id": "jf2", "Type": "Episode", "Name": "Pilota", "SeriesName": "Serie", "ParentIndexNumber": 1,
     "IndexNumber": 2, "RunTimeTicks": 24_000_000_000, "Container": "mp4", "UserData": {}},
    {"Id": "jf3", "Type": "Audio", "Name": "Brano", "SeriesName": "Artista", "Container": "flac",
     "UserData": {"Played": True}},
]


def jellyfin_http():
    return MockHttp([
        (r"/Users/AuthenticateByName", {"AccessToken": "T1", "User": {"Id": "U1"}}),
        (r"/Users/U1/Items/jf1", JF_ITEMS[0]),
        (r"/Users/U1/Items/jf2", JF_ITEMS[1]),
        (r"/Users/U1/Items/jf3", JF_ITEMS[2]),
        (r"/Items", {"Items": JF_ITEMS}),
        (r"/Sessions/", {"Ok": True}),
        (r"/Users/U1/PlayedItems/", {"Ok": True}),
    ])


class ServerSource:
    """Le rotte di media-server, con il client HTTP finto al posto di httpx."""

    def __init__(self, gs, source):
        self.gs, self.source = gs, source

    def list(self, kind="", query=""):
        return self.gs.get("list", kind=kind, query=query, source=self.source)

    def detail(self, item_id):
        return self.gs.get("detail", id=item_id, source=self.source)

    def play_target(self, item_id):
        return self.gs.get("play_target", id=item_id, source=self.source)

    def set_progress(self, item_id, pos, seen):
        return self.gs.post("set_progress", {"id": item_id, "pos": pos, "seen": seen}, source=self.source)


def test_contratto_jellyfin(tmp, monkeypatch):
    M = load("media-server")
    http = jellyfin_http()
    monkeypatch.setattr(M, "Http", lambda *a, **k: http)
    gs = FakeGS(cfg_for(tmp), "media-server")
    M.register(gs)
    saved = gs.post("config", {"source": "jellyfin", "base_url": "http://jf.local", "username": "u", "password": "p"})
    assert saved["ok"] and saved["servers"]["jellyfin"]["configured"] is True
    assert "token" not in saved["servers"]["jellyfin"]  # niente segreti in uscita
    assert "password" not in gs.settings["servers"]["jellyfin"]  # la password serve solo al primo accesso
    assert gs.settings["servers"]["jellyfin"]["user_id"] == "U1"

    src = ServerSource(gs, "jellyfin")
    items = contract(src)
    kinds = {i["kind"]: i for i in items}
    assert kinds["film"]["year"] == 2020 and kinds["film"]["duration"] == 5400.0
    assert kinds["episodio"]["series"] == "Serie" and kinds["episodio"]["episode"] == 2
    assert kinds["brano"]["seen"] is True
    assert kinds["film"]["poster"].startswith("/plugin-api/media-server/artwork?source=jellyfin")

    # stream diretto, non transcodifica; mkv -> lettore esterno, mp4 -> integrato
    target = gs.get("play_target", id="jf1", source="jellyfin")
    assert target["url"].startswith("http://jf.local/Videos/jf1/stream?") and "static=true" in target["url"]
    assert target["external"] is True
    assert gs.get("play_target", id="jf2", source="jellyfin")["external"] is False
    assert gs.get("play_target", id="jf3", source="jellyfin")["url"].startswith("http://jf.local/Audio/jf3/stream?")

    # progresso e «visto» vanno al server
    http.calls.clear()
    src.set_progress("jf1", 42.0, False)
    progress = http.calls_to("/Sessions/Playing/Progress")
    assert progress and progress[0]["json"]["PositionTicks"] == 420_000_000
    src.set_progress("jf1", 0.0, True)
    assert http.calls_to("/Users/U1/PlayedItems/jf1") and http.calls_to("/Sessions/Playing/Stopped")

    assert gs.get("test", source="jellyfin")["ok"] is True


def test_jellyfin_login_richiesto_per_visto():
    """Con la sola chiave API non si segna «visto»: lo stato è del server e serve l'utente."""
    M = load("media-server")
    adapter = M.Jellyfin("http://jf.local", jellyfin_http(), token="T1")
    with pytest.raises(HTTPException) as err:
        adapter.set_progress("jf1", 0, True)
    assert err.value.status_code == 400


# ---------------------------------------------------------------- Plex
PLEX_MOVIE = {"ratingKey": "101", "type": "movie", "title": "Film Plex", "year": 2019, "duration": 5_400_000,
              "summary": "Trama", "thumb": "/library/metadata/101/thumb/1", "viewOffset": 60_000,
              "Media": [{"Part": [{"key": "/library/parts/9/file.mkv", "container": "mkv"}]}]}
PLEX_EPISODE = {"ratingKey": "102", "type": "episode", "title": "Pilota", "grandparentTitle": "Serie",
                "parentIndex": 2, "index": 3, "duration": 2_400_000, "viewCount": 1,
                "Media": [{"Part": [{"key": "/library/parts/10/file.mp4", "container": "mp4"}]}]}
PLEX_TRACK = {"ratingKey": "103", "type": "track", "title": "Brano", "grandparentTitle": "Artista",
              "parentTitle": "Album", "duration": 200_000,
              "Media": [{"Part": [{"key": "/library/parts/11/file.flac", "container": "flac"}]}]}


def plex_http():
    return MockHttp([
        (r"/library/sections$", {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"},
                                                                 {"key": "2", "type": "show"},
                                                                 {"key": "3", "type": "artist"}]}}),
        (r"/library/sections/1/all", {"MediaContainer": {"Metadata": [PLEX_MOVIE]}}),
        (r"/library/sections/2/all", {"MediaContainer": {"Metadata": [PLEX_EPISODE]}}),
        (r"/library/sections/3/all", {"MediaContainer": {"Metadata": [PLEX_TRACK]}}),
        (r"/library/metadata/101", {"MediaContainer": {"Metadata": [PLEX_MOVIE]}}),
        (r"/library/metadata/102", {"MediaContainer": {"Metadata": [PLEX_EPISODE]}}),
        (r"/library/metadata/103", {"MediaContainer": {"Metadata": [PLEX_TRACK]}}),
        (r"/search", {"MediaContainer": {"Hub": [{"Metadata": [PLEX_MOVIE]}]}}),
        (r"/:/progress", {}),
        (r"/:/scrobble", {}),
        (r"/:/unscrobble", {}),
    ])


def test_contratto_plex(tmp, monkeypatch):
    M = load("media-server")
    http = plex_http()
    monkeypatch.setattr(M, "Http", lambda *a, **k: http)
    gs = FakeGS(cfg_for(tmp), "media-server")
    M.register(gs)
    saved = gs.post("config", {"source": "plex", "base_url": "http://plex.local:32400", "token": "tok"})
    assert saved["ok"] and "tok" not in str(saved)

    src = ServerSource(gs, "plex")
    items = contract(src)
    kinds = {i["kind"]: i for i in items}
    assert kinds["film"]["year"] == 2019 and kinds["film"]["resume_pos"] == 60.0
    assert kinds["episodio"]["series"] == "Serie" and kinds["episodio"]["season"] == 2
    assert kinds["episodio"]["episode"] == 3 and kinds["episodio"]["seen"] is True
    assert kinds["film"]["poster"].startswith("/plugin-api/media-server/artwork?source=plex")

    target = gs.get("play_target", id="101", source="plex")
    assert target["url"].startswith("http://plex.local:32400/library/parts/9/file.mkv?") and target["external"] is True
    assert gs.get("play_target", id="102", source="plex")["external"] is False

    http.calls.clear()
    src.set_progress("101", 42.0, False)
    progress = http.calls_to("/:/progress")
    assert progress and progress[0]["params"]["time"] == "42000" and progress[0]["params"]["state"] == "playing"
    src.set_progress("101", 0.0, True)
    assert http.calls_to("/:/scrobble")

    assert [i["title"] for i in gs.get("list", query="film", source="plex")] == ["Film Plex"]


def test_media_server_senza_configurazione(tmp):
    M = load("media-server")
    gs = FakeGS(cfg_for(tmp), "media-server")
    M.register(gs)
    with pytest.raises(HTTPException) as err:
        gs.get("list")
    assert err.value.status_code == 400
    assert gs.get("config") == {"servers": {}, "sources": []}
    assert gs.get("test")["ok"] is False
    # indirizzo non http/https: rifiutato (niente file:// o altri schemi)
    with pytest.raises(HTTPException):
        gs.post("config", {"source": "plex", "base_url": "file:///c:/x", "token": "t"})
    with pytest.raises(HTTPException):
        gs.post("config", {"source": "plex", "base_url": "http://plex.local", "token": ""})


def test_media_server_immagine_passata_dal_server(tmp, monkeypatch):
    """Il frontend riceve l'immagine da Pozzo: il token non compare negli URL della UI."""
    M = load("media-server")
    http = MockHttp([(r"/library/metadata/101/thumb", Resp({}, content=b"img", ctype="image/jpeg"))])
    monkeypatch.setattr(M, "Http", lambda *a, **k: http)
    gs = FakeGS(cfg_for(tmp), "media-server")
    M.register(gs)
    gs.post("config", {"source": "plex", "base_url": "http://plex.local:32400", "token": "tok"})
    out = gs.get("artwork", src="/library/metadata/101/thumb/1", source="plex")
    assert out.body == b"img" and out.media_type == "image/jpeg"
    call = http.calls_to("/library/metadata/101/thumb")[0]
    assert call["params"]["X-Plex-Token"] == "tok"  # il token resta lato server
    with pytest.raises(HTTPException):  # immagine fuori dal server: rifiutata
        gs.get("artwork", src="http://evil.local/x.jpg", source="plex")


def test_media_server_espone_player(tmp):
    M = load("media-server")
    gs = FakeGS(cfg_for(tmp), "media-server")
    M.register(gs)
    assert {p["mode"] for p in gs.players} == {"integrato", "esterno"}


def test_rotte_reali_delle_due_estensioni(tmp):
    """Le estensioni vere, caricate dal loader vero in un'app FastAPI: api = 2 e rotte firmate correttamente."""
    import shutil

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from pozzo.app import extensions as X

    for name in ("media-locale", "media-server"):
        shutil.copytree(EXT / name, tmp / "plugins" / name)
    cfg = SimpleNamespace(config_path=tmp / "config.toml", app={})
    app = FastAPI()
    try:
        errors = X.load_backends(app, cfg, X.Events(), lambda m: None)
        assert errors == {}
        c = TestClient(app)
        assert c.get("/plugin-api/media-locale/list").json() == []
        assert c.get("/plugin-api/media-locale/roots").json() == {"roots": []}
        assert c.get("/plugin-api/media-locale/detail?id=boh").status_code == 404
        assert c.post("/plugin-api/media-locale/set_progress", json={"id": "boh", "pos": 1}).status_code == 404
        assert c.get("/plugin-api/media-server/config").json() == {"servers": {}, "sources": []}
        assert c.get("/plugin-api/media-server/list").status_code == 400  # nessun server configurato

        # percorso completo: cartella scelta -> scansione -> file servito con Range (il player può cercare)
        lib = tmp / "video"
        lib.mkdir()
        (lib / "Film (2020).mp4").write_bytes(b"0123456789")
        assert c.post("/plugin-api/media-locale/roots", json={"add": str(lib)}).json()["roots"][0]["items"] == 0
        assert c.post("/plugin-api/media-locale/scan").json()["items"] == 1
        item = c.get("/plugin-api/media-locale/list").json()[0]
        assert (item["title"], item["year"]) == ("Film", 2020)
        part = c.get(f"/plugin-api/media-locale/stream?id={item['id']}", headers={"Range": "bytes=2-5"})
        assert part.status_code == 206 and part.content == b"2345"
    finally:
        X.stop_jobs()
        for reg in (X.LIBRARY_KINDS, X.PLAYERS, X.SCRAPERS):
            reg.clear()
        X.LOAD_MS.clear()
