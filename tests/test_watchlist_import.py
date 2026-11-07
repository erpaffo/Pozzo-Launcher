"""Importazione watchlist di media-locale: parser, AniList (httpx mockato), bulk, migrazione.

Esegui: python -m pytest tests/test_watchlist_import.py -q
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
EXT = ROOT / "extensions" / "media-locale"


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, EXT / fname)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ML = _load("media_locale_backend_wl", "backend.py")
W = ML.wli
from test_media_scansione import FakeGS  # noqa: E402


def impianto(tmp):
    gs = FakeGS(SimpleNamespace(config_path=tmp / "config.toml", app={}))
    ML.register(gs)
    return gs


ANILIST = {"data": {"MediaListCollection": {"lists": [
    {"entries": [
        {"status": "CURRENT", "progress": 3, "score": 8.5, "media": {
            "id": 1, "idMal": 10, "title": {"romaji": "Shingeki", "english": "Attack on Titan", "native": "x"},
            "episodes": 25, "startDate": {"year": 2013}, "coverImage": {"large": "http://c/1.jpg"},
            "description": "<b>Bold</b> text"}},
        {"status": "PLANNING", "progress": 0, "score": 0, "media": {
            "id": 2, "idMal": None, "title": {"romaji": "Only Romaji", "english": None}, "episodes": None}},
        {"status": "REPEATING", "progress": 1, "score": 90, "media": {"id": 3, "title": {"romaji": "R"}}},
    ]},
    {"entries": [{"status": "CURRENT", "progress": 3, "score": 8.5, "media": {"id": 1, "title": {"romaji": "Shingeki"}}}]},
]}}}


def test_parse_anilist():
    e = W.parse_anilist(ANILIST)
    assert len(e) == 3  # duplicato nelle liste custom eliminato
    a = e[0]
    assert a["title"] == "Attack on Titan" and a["original_title"] == "Shingeki"
    assert a["category"] == "anime" and a["kind"] == "episodio" and a["status"] == "watching"
    assert (a["progress"], a["total"], a["year"], a["rating"]) == (3, 25, 2013, 8.5)
    assert a["ext_ids"] == {"anilist": 1, "mal": 10} and a["import_source"] == "anilist"
    assert a["overview"] == "Bold text" and a["poster"] == "http://c/1.jpg"
    assert e[1]["title"] == "Only Romaji" and e[1]["status"] == "plan_to_watch" and e[1]["ext_ids"] == {"anilist": 2}
    assert e[2]["status"] == "watching" and e[2]["rating"] == 9.0  # scala 0-100 normalizzata


@pytest.mark.parametrize("anilist,expected", [("COMPLETED", "completed"), ("PAUSED", "on_hold"), ("DROPPED", "dropped")])
def test_anilist_status_map(anilist, expected):
    d = {"lists": [{"entries": [{"status": anilist, "media": {"id": 1, "title": {"romaji": "T"}}}]}]}
    assert W.parse_anilist(d)[0]["status"] == expected


class FakeResp:
    def __init__(self, body, code=200):
        self.body, self.status_code = body, code

    def json(self):
        return self.body


class FakeClient:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.resp


def test_fetch_anilist_ok_e_errori():
    c = FakeClient(FakeResp(ANILIST))
    assert len(W.fetch_anilist("pippo", c)) == 3
    assert c.calls[0][0] == "https://graphql.anilist.co" and c.calls[0][1]["timeout"] == 10
    nf = FakeClient(FakeResp({"errors": [{"message": "User not found", "status": 404}]}, 404))
    with pytest.raises(ValueError, match="non trovato"):
        W.fetch_anilist("nessuno", nf)
    pr = FakeClient(FakeResp({"errors": [{"message": "Private User", "status": 403}]}, 403))
    with pytest.raises(ValueError, match="privata"):
        W.fetch_anilist("segreto", pr)
    with pytest.raises(ValueError):
        W.fetch_anilist("  ", c)


MAL = """<?xml version="1.0"?><myanimelist><myinfo/>
<anime><series_animedb_id>20</series_animedb_id><series_title><![CDATA[Naruto]]></series_title>
<series_episodes>220</series_episodes><my_watched_episodes>50</my_watched_episodes><my_score>7</my_score>
<my_status>Watching</my_status></anime>
<anime><series_animedb_id>21</series_animedb_id><series_title>One Piece</series_title><series_episodes>0</series_episodes>
<my_watched_episodes>0</my_watched_episodes><my_score>0</my_score><my_status>6</my_status></anime>
<anime><series_animedb_id>22</series_animedb_id><series_title></series_title></anime>
</myanimelist>"""


def test_parse_mal_xml():
    rep = {}
    e = W.parse_mal_xml(MAL, rep)
    assert [x["title"] for x in e] == ["Naruto", "One Piece"] and rep["skipped"] == 1
    assert e[0]["status"] == "watching" and e[0]["progress"] == 50 and e[0]["total"] == 220 and e[0]["rating"] == 7
    assert e[0]["ext_ids"] == {"mal": 20} and e[0]["category"] == "anime"
    assert e[1]["status"] == "plan_to_watch"


@pytest.mark.parametrize("bad", ['<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x/>', "<!doctype x><x/>", "<!ENTITY a 'b'><x/>"])
def test_mal_rifiuta_doctype(bad):
    with pytest.raises(ValueError):
        W.parse_mal_xml(bad)
    with pytest.raises(ValueError):
        W.parse_mal_xml("<broken")


def test_parse_csv_letterboxd():
    e = W.parse_csv("Date,Name,Year,Letterboxd URI,Rating\n2020-01-01,Heat,1995,http://x,4.5\n2020-01-02,Alien,1979,http://y,\n")
    assert e[0]["title"] == "Heat" and e[0]["year"] == 1995 and e[0]["category"] == "film" and e[0]["kind"] == "film"
    assert e[0]["status"] == "completed" and e[0]["rating"] == 9.0 and e[0]["import_source"] == "letterboxd"
    assert e[1]["rating"] == 0 and e[1]["status"] == "completed"  # ha la colonna rating: file ratings/watched
    wl = W.parse_csv("Date,Name,Year,Letterboxd URI\n2020-01-01,Heat,1995,http://x\n")
    assert wl[0]["status"] == "plan_to_watch"


def test_parse_csv_generico():
    e = W.parse_csv("title;year;type;status;progress;rating;imdb;tmdb\nDark;2017;show;watching;5;8;tt1;99\nX;;;;;;;\n,,\n")
    d = e[0]
    assert d["category"] == "serie" and d["kind"] == "episodio" and d["status"] == "watching" and d["progress"] == 5
    assert d["rating"] == 8 and d["ext_ids"] == {"imdb": "tt1", "tmdb": 99} and d["year"] == 2017
    assert e[1]["category"] == "" and e[1]["year"] is None


def test_parse_json_trakt_e_generico():
    trakt = '[{"type":"movie","movie":{"title":"Heat","year":1995,"ids":{"imdb":"tt0113277","tmdb":949}}},' \
            '{"show":{"title":"Dark","year":2017,"ids":{"tmdb":70523}},"rating":9,"last_watched_at":"2020"},' \
            '{"title":"Generico","year":2001,"category":"anime"}, 5]'
    rep = {}
    e = W.parse_json(trakt, rep)
    assert len(e) == 3 and rep["skipped"] == 1
    assert e[0]["category"] == "film" and e[0]["ext_ids"] == {"imdb": "tt0113277", "tmdb": 949}
    assert e[1]["category"] == "serie" and e[1]["status"] == "completed" and e[1]["rating"] == 9
    assert e[2]["category"] == "anime" and e[2]["year"] == 2001
    with pytest.raises(ValueError):
        W.parse_json("{no")


def test_parse_text_e_limiti():
    e = W.parse_text("# commento\n\nHeat (1995)\n  Alien \n" + "x" * 400 + "\n")
    assert [x["title"] for x in e[:2]] == ["Heat", "Alien"] and e[0]["year"] == 1995 and e[0]["category"] == ""
    assert len(e[2]["title"]) == 300
    rep = {}
    assert len(W.parse_text("\n".join(f"t{i}" for i in range(5100)), rep)) == 5000
    assert rep["skipped"] == 100 and rep["warnings"]


def entry(**kw):
    base = {"title": "Attack on Titan", "category": "anime", "status": "watching", "progress": 5, "total": 25,
            "ext_ids": {"anilist": 1}, "import_source": "anilist", "year": 2013}
    return {**base, **kw}


def test_bulk_dedup_e_unione_non_distruttiva(tmp):
    gs = impianto(tmp)
    r = gs.post("watchlist/bulk", {"entries": [entry(), entry(), "male", {"title": ""}]})
    assert r == {"added": 1, "updated": 0, "skipped": 3}  # duplicato nel batch non cambia nulla
    item = gs.get("watchlist")["items"][0]
    assert item["item_key"] == "wl:anilist:1" and item["ext_ids"] == {"anilist": 1} and item["priority"] == "medium"

    # l'utente personalizza, poi reimporta con dati "peggiori" e stato diverso
    gs.post("watchlist", {"item_key": "wl:anilist:1", "notes": "mio", "priority": "high", "rating": 9, "progress": 10})
    r = gs.post("watchlist/bulk", {"entries": [entry(progress=2, status="dropped", rating=3, notes="x",
                                                   ext_ids={"mal": 7}, total=26)]})
    assert r == {"added": 0, "updated": 1, "skipped": 0}
    it = gs.get("watchlist")["items"][0]
    assert (it["progress"], it["notes"], it["priority"], it["rating"]) == (10, "mio", "high", 9)
    assert it["status"] == "watching"  # esistente non plan_to_watch: non sostituito
    assert it["total"] == 26 and it["ext_ids"] == {"anilist": 1, "mal": 7}

    # dedup per titolo normalizzato + anno + categoria (nessun id esterno)
    gs.post("watchlist/bulk", {"entries": [{"title": "Heat", "year": 1995, "category": "film"}]})
    r = gs.post("watchlist/bulk", {"entries": [{"title": "HEAT!", "year": 1995, "category": "film", "status": "completed"}]})
    assert r["updated"] == 1 and r["added"] == 0
    heat = [i for i in gs.get("watchlist")["items"] if i["title"] == "Heat"][0]
    assert heat["status"] == "completed" and heat["item_key"] == "wl:heat-1995"
    # categoria diversa, stesso titolo: voce nuova
    assert gs.post("watchlist/bulk", {"entries": [{"title": "Heat", "year": 1995, "category": "serie"}]})["added"] == 1
    # linked_key diventa item_key
    r = gs.post("watchlist/bulk", {"entries": [{"title": "Mio", "linked_key": "media-locale:abc"}]})
    assert r["added"] == 1 and gs.get("watchlist", category="") ["items"]
    assert any(i["item_key"] == "media-locale:abc" for i in gs.get("watchlist")["items"])
    with pytest.raises(Exception):
        gs.post("watchlist/bulk", {"entries": "no"})


def test_route_import_anteprima_non_salva(tmp):
    gs = impianto(tmp)
    r = gs.post("watchlist/import", {"provider": "text", "content": "Heat (1995)\nAlien"})
    assert len(r["entries"]) == 2 and r["skipped"] == 0 and r["warnings"] == []
    assert gs.get("watchlist")["items"] == []
    with pytest.raises(Exception):
        gs.post("watchlist/import", {"provider": "mal", "content": "<!DOCTYPE x><x/>"})
    with pytest.raises(Exception):
        gs.post("watchlist/import", {"provider": "boh"})


def test_get_category_e_save_nuovi_campi(tmp):
    gs = impianto(tmp)
    gs.post("watchlist", {"id": "a", "title": "A", "category": "anime", "progress": 3, "total": 12, "ext_ids": {"mal": 1},
                          "linked_key": "k", "import_source": "mal"})
    gs.post("watchlist", {"id": "b", "title": "B", "category": "boh", "progress": -4})
    gs.post("watchlist", {"id": "a", "ext_ids": {"tmdb": 5}, "progress": "x"})
    a = gs.get("watchlist", category="anime")["items"]
    assert len(a) == 1 and a[0]["ext_ids"] == {"mal": 1, "tmdb": 5} and a[0]["progress"] == 3 and a[0]["total"] == 12
    assert a[0]["linked_key"] == "k" and a[0]["import_source"] == "mal"
    b = [i for i in gs.get("watchlist")["items"] if i["title"] == "B"][0]
    assert b["category"] == "" and b["progress"] == 0
    assert len(gs.get("watchlist", category="serie")["items"]) == 0


def test_migrazione_db_vecchio(tmp):
    gs = impianto(tmp)
    p = ML.db_path(gs.cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p)
    c.executescript("""DROP TABLE IF EXISTS watchlist; CREATE TABLE watchlist (item_key TEXT PRIMARY KEY, item_id TEXT, source TEXT DEFAULT 'media-locale',
        title TEXT NOT NULL, kind TEXT DEFAULT 'film', series TEXT, poster TEXT, backdrop TEXT, year INTEGER, genre TEXT,
        overview TEXT, url TEXT, status TEXT DEFAULT 'plan_to_watch', priority TEXT DEFAULT 'medium',
        rating INTEGER DEFAULT 0, notes TEXT DEFAULT '', added_at REAL, updated_at REAL);
        INSERT INTO watchlist(item_key,title,kind,genre) VALUES('1','F','film','Dramma'),('2','S','episodio','Dramma'),
        ('3','A','episodio','Animazione, Azione');""")
    c.commit()
    c.close()
    ML._MIGRATI.discard(str(p))
    items = {i["item_key"]: i for i in gs.get("watchlist")["items"]}
    assert [items[k]["category"] for k in "123"] == ["film", "serie", "anime"]
    assert items["1"]["ext_ids"] == {} and items["1"]["progress"] == 0
    gs.get("watchlist")  # idempotente


def test_bulk_associa_voce_esistente_senza_duplicarla(tmp):
    # «Associa ai titoli trovati» rimanda voci già salvate con il nuovo linked_key: devono aggiornarsi, non raddoppiare
    gs = impianto(tmp)
    gs.post("watchlist", {"item_key": "media-locale:abc", "title": "Cowboy Bebop", "kind": "episodio",
                          "category": "anime", "year": 1998, "notes": "da rivedere", "priority": "high"})
    out = gs.post("watchlist/bulk", {"entries": [{"item_key": "media-locale:abc", "title": "Cowboy Bebop", "year": 1998,
                                                   "category": "anime", "kind": "episodio", "linked_key": "media-locale:ep1"}]})
    assert out["added"] == 0
    rows = gs.get("watchlist")["items"]
    assert len(rows) == 1 and rows[0]["linked_key"] == "media-locale:ep1"
    assert rows[0]["notes"] == "da rivedere" and rows[0]["priority"] == "high"


def test_salvataggio_forma_annidata_e_rimozione(tmp):
    gs = impianto(tmp)
    voce = {"item_key": "media-locale:k1", "title": "Dune", "kind": "film", "year": 2021, "status": "watching"}
    # forma usata dall'interfaccia: {action, entry, entries}; prima dava 400 e la voce restava solo nel browser
    out = gs.post("watchlist", {"action": "upsert", "entry": voce, "entries": [voce]})
    assert out["ok"] and out["item"]["title"] == "Dune"
    assert [r["item_key"] for r in gs.get("watchlist")["items"]] == ["media-locale:k1"]
    # «remove» non deve più comparire come nuova voce con la chiave per titolo
    gs.post("watchlist", {"action": "remove", "item_key": "media-locale:k1", "entries": []})
    assert gs.get("watchlist")["items"] == []


def test_migrazione_toglie_le_voci_fantasma(tmp):
    gs = impianto(tmp)
    ML._MIGRATI.clear()
    conn = sqlite3.connect(ML.db_path(gs.cfg))
    conn.executescript(ML.SCHEMA)
    conn.execute("INSERT INTO watchlist (item_key, item_id, title, added_at, updated_at) VALUES ('media-locale:ab12', 'ab12', 'ab12', 1, 1)")
    conn.execute("INSERT INTO watchlist (item_key, item_id, title, added_at, updated_at) VALUES ('media-locale:ok', 'ok', 'Blade Runner', 1, 1)")
    conn.commit(); conn.close()
    titoli = [r["title"] for r in gs.get("watchlist")["items"]]
    assert titoli == ["Blade Runner"]
