"""Scansione incrementale di media-locale: i file invariati non vengono rianalizzati.

Si contano le chiamate al parser (`identify`), non i secondi: una misura a orologio sarebbe inaffidabile.

Esegui: python -m pytest tests/test_media_scansione.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load():
    spec = importlib.util.spec_from_file_location("media_locale_backend",
                                                 ROOT / "extensions" / "media-locale" / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ML = load()


class FakeGS:
    def __init__(self, cfg, pid="media-locale"):
        self.cfg, self.id, self.routes, self.settings, self.logs = cfg, pid, {}, {}, []
        self.log = self.logs.append

    def route(self, path, methods=("GET",)):
        def deco(fn):
            key = path.lstrip("/")
            self.routes[key] = fn
            self.routes[(key, methods[0])] = fn
            return fn
        return deco

    def get(self, path, **kw):
        key = path.lstrip("/")
        fn = self.routes.get((key, "GET")) or self.routes[key]
        return fn(**kw)

    def post(self, path, body=None, **kw):
        key = path.lstrip("/")
        fn = self.routes.get((key, "POST")) or self.routes[key]
        if body is None:
            return fn(**kw)
        return fn(body=body, **kw)

    def add_library_kind(self, kind):
        pass

    def add_player(self, player):
        pass

    def job(self, *a, **k):
        pass

    def save_settings(self, values):
        self.settings.update(values)


def impianto(tmp: Path, files=None):
    """Cartella con N file media + estensione registrata; ritorna (gs, cartella, contatore del parser)."""
    cfg = SimpleNamespace(config_path=tmp / "config.toml", app={})
    lib = tmp / "media"
    lib.mkdir(parents=True, exist_ok=True)
    for nome in files or ["Film A (2001).mp4", "Film B (2002).mp4", "Serie/Season 01/S01E01.mkv",
                          "Artista/Album/01 - Uno.flac", "Artista/Album/02 - Due.mp3"]:
        p = lib / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * 10)
    gs = FakeGS(cfg)
    ML.register(gs)
    gs.routes["roots"](body={"add": str(lib)})

    chiamate = {"n": 0}
    vero = ML.identify

    def contatore(percorso):
        chiamate["n"] += 1
        return vero(percorso)

    ML.identify = contatore
    return gs, lib, chiamate


def test_prima_scansione_analizza_tutto(tmp):
    gs, lib, chiamate = impianto(tmp)
    assert gs.routes["scan"]()["items"] == 5
    assert chiamate["n"] == 5
    assert len(gs.routes["list"]()) == 5


def test_seconda_scansione_non_rianalizza(tmp):
    gs, lib, chiamate = impianto(tmp)
    gs.routes["scan"]()
    chiamate["n"] = 0
    assert gs.routes["scan"]()["items"] == 5  # li vede tutti...
    assert chiamate["n"] == 0  # ...ma non ne rilegge nessuno
    assert len(gs.routes["list"]()) == 5


def test_file_cambiato_viene_rianalizzato(tmp):
    gs, lib, chiamate = impianto(tmp)
    gs.routes["scan"]()
    chiamate["n"] = 0
    (lib / "Film A (2001).mp4").write_bytes(b"y" * 99)  # dimensione diversa
    gs.routes["scan"]()
    assert chiamate["n"] == 1
    (lib / "Film B (2002).mp4").touch()  # solo la data
    chiamate["n"] = 0
    gs.routes["scan"]()
    assert chiamate["n"] == 1, "una data nuova basta a rileggere il file"


def test_file_cancellato_sparisce(tmp):
    gs, lib, chiamate = impianto(tmp)
    gs.routes["scan"]()
    (lib / "Artista" / "Album" / "01 - Uno.flac").unlink()
    chiamate["n"] = 0
    assert gs.routes["scan"]()["items"] == 4
    assert chiamate["n"] == 0
    assert {i["title"] for i in gs.routes["list"]()} >= {"Film A", "Due"}
    assert "Uno" not in {i["title"] for i in gs.routes["list"]()}


def test_file_nuovo_viene_analizzato(tmp):
    gs, lib, chiamate = impianto(tmp)
    gs.routes["scan"]()
    (lib / "Film C (2003).mp4").write_bytes(b"x" * 10)
    chiamate["n"] = 0
    assert gs.routes["scan"]()["items"] == 6
    assert chiamate["n"] == 1
    assert "Film C" in {i["title"] for i in gs.routes["list"]() if i["kind"] == "film"}


def test_poster_nuovo_viene_raccolto(tmp):
    """Aggiungere poster.jpg non cambia i file: la cartella va riletta per agganciare la copertina."""
    gs, lib, chiamate = impianto(tmp)
    gs.routes["scan"]()
    assert "poster" not in gs.routes["list"](kind="film")[0]
    (lib / "poster.jpg").write_bytes(b"jpg")
    chiamate["n"] = 0
    gs.routes["scan"]()
    assert chiamate["n"] == 2  # i due film della cartella
    assert gs.routes["list"](kind="film")[0]["poster"].startswith("/plugin-api/media-locale/artwork?id=")


def test_progressi_sopravvivono_alla_riscansione(tmp):
    gs, lib, chiamate = impianto(tmp)
    gs.routes["scan"]()
    film = next(i for i in gs.routes["list"](kind="film") if i["title"] == "Film A")
    gs.routes["set_progress"](body={"id": film["id"], "pos": 120, "seen": False})
    gs.routes["scan"]()
    (lib / "poster.jpg").write_bytes(b"jpg")  # forza un giro che riscrive la cartella
    gs.routes["scan"]()
    assert gs.routes["play_target"](id=film["id"])["resume_pos"] == 120.0


def test_database_vecchio_senza_colonne_nuove(tmp):
    """Un media.db creato prima della scansione incrementale si aggiorna da solo, senza perdere contenuti."""
    import sqlite3

    cfg = SimpleNamespace(config_path=tmp / "config.toml", app={})
    percorso = ML.db_path(cfg)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    vecchio = sqlite3.connect(percorso)
    vecchio.executescript(
        "CREATE TABLE roots(path TEXT PRIMARY KEY, added REAL);"
        "CREATE TABLE items(id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, series TEXT DEFAULT '',"
        " album TEXT DEFAULT '', season INTEGER, episode INTEGER, track INTEGER, year INTEGER, duration REAL,"
        " path TEXT NOT NULL, poster TEXT DEFAULT '', root TEXT NOT NULL, pos REAL DEFAULT 0, seen INTEGER DEFAULT 0,"
        " updated REAL);"
        "INSERT INTO roots VALUES('/vecchia', 0);"
        "INSERT INTO items(id, kind, title, path, root) VALUES('v1', 'film', 'Vecchio', '/vecchia/f.mp4', '/vecchia');")
    vecchio.commit()
    vecchio.close()

    conn = ML.connect(percorso)
    colonne = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
    assert {"size", "mtime", "backdrop", "overview", "genres"} <= colonne
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    conn.close()


def test_scansione_anime_e_colonne_metadati(tmp):
    """Scansione di anime senza cartella stagione e verifica colonne metadati."""
    gs, lib, _ = impianto(tmp, files=["Anime/One Piece/One Piece - 1050.mkv", "Film/Matrix (1999).mkv"])
    res = gs.routes["scan"]()
    assert res["items"] == 2
    items = gs.routes["list"]()
    op = next(i for i in items if "One Piece" in i.get("series", ""))
    assert op["kind"] == "episodio"
    assert op["episode"] == 1050
    assert op["season"] == 1
    assert op["series"] == "One Piece"
    film = next(i for i in items if i["kind"] == "film")
    assert film["title"] == "Matrix" and film["year"] == 1999


def test_watchlist_crud_e_filtri(tmp):
    """Test delle rotte GET/POST /watchlist e POST /watchlist/remove con aggiornamenti parziali."""
    gs, lib, _ = impianto(tmp)

    # Inizialmente vuota
    assert gs.get("watchlist") == {"items": []}

    # 1. Creazione primo elemento (con source + id -> item_key automatica)
    res1 = gs.post("watchlist", {
        "id": "m1",
        "source": "media-locale",
        "title": "Inception",
        "kind": "film",
        "year": 2010,
        "genre": "Sci-Fi",
        "overview": "Sogni",
        "poster": "/poster1.jpg",
        "status": "plan_to_watch",
        "priority": "medium",
        "rating": 8,
        "notes": "Da rivedere",
    })
    assert res1["ok"] is True
    item1 = res1["item"]
    assert item1["item_key"] == "media-locale:m1"
    assert item1["item_id"] == "m1"
    assert item1["title"] == "Inception"
    assert item1["status"] == "plan_to_watch"
    assert item1["priority"] == "medium"
    assert item1["rating"] == 8
    assert item1["notes"] == "Da rivedere"
    assert item1["added_at"] > 0

    # 2. Aggiornamento parziale sullo stesso item_key: preserva metadati e added_at
    added_orig = item1["added_at"]
    res_upd = gs.post("watchlist", {
        "item_key": "media-locale:m1",
        "status": "watching",
        "priority": "high",
        "rating": 15,  # clamped a 10
        "notes": "Iniziato ieri",
    })
    assert res_upd["ok"] is True
    upd = res_upd["item"]
    assert upd["item_key"] == "media-locale:m1"
    assert upd["title"] == "Inception"
    assert upd["year"] == 2010
    assert upd["genre"] == "Sci-Fi"
    assert upd["poster"] == "/poster1.jpg"
    assert upd["status"] == "watching"
    assert upd["priority"] == "high"
    assert upd["rating"] == 10
    assert upd["notes"] == "Iniziato ieri"
    assert upd["added_at"] == added_orig
    assert upd["updated_at"] >= added_orig

    # 3. Secondo elemento con priorita' bassa
    gs.post("watchlist", {
        "item_key": "jellyfin:jf99",
        "item_id": "jf99",
        "source": "jellyfin",
        "title": "Old Movie",
        "status": "completed",
        "priority": "low",
        "rating": 7,
    })

    # 4. GET /watchlist ordinata per peso priorita' DESC (high prima di low)
    all_items = gs.get("watchlist")["items"]
    assert [i["item_key"] for i in all_items] == ["media-locale:m1", "jellyfin:jf99"]

    # Filtri query su GET /watchlist
    only_watching = gs.get("watchlist", status="watching")["items"]
    assert len(only_watching) == 1 and only_watching[0]["item_key"] == "media-locale:m1"

    only_low = gs.get("watchlist", priority="low")["items"]
    assert len(only_low) == 1 and only_low[0]["item_key"] == "jellyfin:jf99"

    # 5. Rimozione tramite item_key o id
    rem1 = gs.post("watchlist/remove", {"item_key": "media-locale:m1"})
    assert rem1 == {"ok": True, "removed": "media-locale:m1"}
    assert [i["item_key"] for i in gs.get("watchlist")["items"]] == ["jellyfin:jf99"]

    rem2 = gs.post("watchlist/remove", {"id": "jf99"})
    assert rem2 == {"ok": True, "removed": "jf99"}
    assert gs.get("watchlist")["items"] == []
