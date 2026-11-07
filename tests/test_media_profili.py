"""Media locale per profilo: watchlist e avanzamento separati, migrazione, backup JSON (export/import).

Esegui: python -m pytest tests/test_media_profili.py -q
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_media_scansione import FakeGS, ML  # noqa: E402


def impianto(tmp, profilo="a"):
    gs = FakeGS(SimpleNamespace(config_path=tmp / "config.toml", app={"profile": profilo}))
    ML.register(gs)
    return gs


def come(gs, profilo):
    gs.cfg.app["profile"] = profilo


def aggiungi_item(gs, item_id="x1"):
    c = sqlite3.connect(ML.db_path(gs.cfg))
    c.execute("INSERT INTO items(id, kind, title, path, poster, root) VALUES(?,?,?,?,?,?)",
              (item_id, "film", "Film", str(gs.cfg.config_path), "", "r"))
    c.commit()
    c.close()


def test_watchlist_separata_per_profilo(tmp):
    gs = impianto(tmp)
    gs.post("watchlist", {"item_key": "k", "title": "Heat", "notes": "di A"})
    come(gs, "b")
    assert gs.get("watchlist")["items"] == []
    gs.post("watchlist", {"item_key": "k", "title": "Heat", "notes": "di B", "priority": "high"})
    gs.post("watchlist/bulk", {"entries": [{"title": "Solo B", "year": 2000}]})
    come(gs, "a")
    voci = gs.get("watchlist")["items"]
    assert [(v["item_key"], v["notes"], v["priority"]) for v in voci] == [("k", "di A", "medium")]
    gs.post("watchlist/remove", {"item_key": "k"})
    assert gs.get("watchlist")["items"] == []
    come(gs, "b")
    assert {v["title"] for v in gs.get("watchlist")["items"]} == {"Heat", "Solo B"}
    assert {e["title"] for e in gs.get("watchlist/export")["entries"]} == {"Heat", "Solo B"}


def test_avanzamento_per_profilo(tmp):
    gs = impianto(tmp)
    aggiungi_item(gs)
    gs.post("set_progress", {"id": "x1", "pos": 42, "duration": 1000})
    assert gs.get("detail", id="x1")["resume_pos"] == 42
    come(gs, "b")
    assert "resume_pos" not in gs.get("detail", id="x1") and gs.get("detail", id="x1")["seen"] is False
    gs.post("set_progress", {"id": "x1", "pos": 950, "duration": 1000})  # oltre il 90%: visto
    assert gs.get("detail", id="x1")["seen"] is True
    assert gs.get("list")[0]["seen"] is True
    come(gs, "a")
    assert gs.get("list")[0]["resume_pos"] == 42 and gs.get("list")[0]["seen"] is False


def test_migrazione_db_vecchio_verso_profilo_attivo(tmp):
    gs = impianto(tmp, "a")
    p = ML.db_path(gs.cfg)
    aggiungi_item(gs)
    c = sqlite3.connect(p)
    c.executescript("""DROP TABLE watchlist; DROP TABLE progress;
        CREATE TABLE watchlist (item_key TEXT PRIMARY KEY, item_id TEXT, source TEXT DEFAULT 'media-locale',
        title TEXT NOT NULL, kind TEXT DEFAULT 'film', series TEXT, poster TEXT, backdrop TEXT, year INTEGER, genre TEXT,
        overview TEXT, url TEXT, status TEXT DEFAULT 'plan_to_watch', priority TEXT DEFAULT 'medium',
        rating INTEGER DEFAULT 0, notes TEXT DEFAULT '', added_at REAL, updated_at REAL);
        INSERT INTO watchlist(item_key,title,kind,notes) VALUES('1','Vecchio','film','mia');
        UPDATE items SET pos=77, seen=0 WHERE id='x1';""")
    c.commit()
    c.close()
    ML._MIGRATI.discard(str(p))
    gs = impianto(tmp, "b")  # il profilo attivo alla migrazione e' «b»
    assert [(v["item_key"], v["notes"]) for v in gs.get("watchlist")["items"]] == [("1", "mia")]
    assert gs.get("detail", id="x1")["resume_pos"] == 77
    come(gs, "a")
    assert gs.get("watchlist")["items"] == [] and "resume_pos" not in gs.get("detail", id="x1")
    ML._MIGRATI.discard(str(p))
    come(gs, "b")
    assert len(gs.get("watchlist")["items"]) == 1 and gs.get("detail", id="x1")["resume_pos"] == 77  # idempotente


def test_export_import_ripristina_voci_e_chiavi(tmp):
    gs = impianto(tmp)
    gs.post("watchlist", {"item_key": "media-locale:abc", "title": "Dune", "kind": "film", "category": "film", "year": 2021,
                          "notes": "da rivedere", "priority": "high", "rating": 9, "status": "watching",
                          "progress": 3, "total": 10, "linked_key": "media-locale:l", "ext_ids": {"tmdb": 5}})
    gs.post("watchlist/bulk", {"entries": [{"title": "Bebop", "category": "anime", "ext_ids": {"mal": 1}}]})
    exp = gs.get("watchlist/export")
    assert exp["version"] == 1 and exp["app"] == "pozzo-media" and exp["profile"] == "a" and exp["exported_at"] > 0
    assert len(exp["entries"]) == 2 and "profile" not in exp["entries"][0]
    assert next(e for e in exp["entries"] if e["title"] == "Dune")["ext_ids"] == {"tmdb": 5}

    come(gs, "vuoto")
    prev = gs.post("watchlist/import", {"provider": "pozzo", "content": json.dumps(exp)})
    assert len(prev["entries"]) == 2 and gs.get("watchlist")["items"] == []  # anteprima: non salva
    assert gs.post("watchlist/bulk", {"entries": prev["entries"]}) == {"added": 2, "updated": 0, "skipped": 0}
    dune = next(v for v in gs.get("watchlist")["items"] if v["title"] == "Dune")
    assert (dune["item_key"], dune["notes"], dune["priority"], dune["rating"], dune["status"], dune["progress"],
            dune["linked_key"], dune["kind"], dune["year"]) == (
        "media-locale:abc", "da rivedere", "high", 9, "watching", 3, "media-locale:l", "film", 2021)
    assert {v["item_key"] for v in gs.get("watchlist")["items"]} == {e["item_key"] for e in exp["entries"]}


def test_import_pozzo_non_distruttivo(tmp):
    gs = impianto(tmp)
    gs.post("watchlist", {"item_key": "k1", "title": "Dune", "year": 2021, "notes": "miei", "priority": "low",
                          "progress": 8, "rating": 7})
    backup = {"version": 1, "entries": [
        {"item_key": "k1", "title": "Dune", "year": 2021, "notes": "vecchie", "priority": "high", "progress": 2, "rating": 3},
        {"item_key": "k2", "title": "Altro", "notes": "n", "priority": "high"}]}
    prev = gs.post("watchlist/import", {"provider": "pozzo", "content": json.dumps(backup)})
    assert gs.post("watchlist/bulk", {"entries": prev["entries"]})["added"] == 1
    items = {v["item_key"]: v for v in gs.get("watchlist")["items"]}
    assert (items["k1"]["notes"], items["k1"]["priority"], items["k1"]["progress"], items["k1"]["rating"]) == ("miei", "low", 8, 7)
    assert items["k2"]["notes"] == "n" and items["k2"]["priority"] == "high"
    # note e priorita' di default si riempiono dal backup
    gs.post("watchlist", {"item_key": "k3", "title": "Vuoto"})
    b2 = {"version": 1, "entries": [{"item_key": "k3", "title": "Vuoto", "notes": "dal backup", "priority": "high"}]}
    gs.post("watchlist/bulk", {"entries": gs.post("watchlist/import", {"provider": "pozzo", "content": json.dumps(b2)})["entries"]})
    k3 = next(v for v in gs.get("watchlist")["items"] if v["item_key"] == "k3")
    assert (k3["notes"], k3["priority"]) == ("dal backup", "high")


@pytest.mark.parametrize("bad", ["{no", "[]", '{"version": 2, "entries": []}', '{"version": 1}', '{"version": 1, "entries": 5}'])
def test_formato_non_valido_rifiutato(tmp, bad):
    gs = impianto(tmp)
    with pytest.raises(Exception):
        gs.post("watchlist/import", {"provider": "pozzo", "content": bad})
    with pytest.raises(ValueError):
        ML.wli.parse_pozzo(bad)


def test_limiti_parse_pozzo():
    big = {"version": 1, "entries": [{"title": "t" * 400}] + [{"title": f"x{i}"} for i in range(5100)]}
    rep = {}
    e = ML.wli.parse_pozzo(json.dumps(big), rep)
    assert len(e) == 5000 and len(e[0]["title"]) == 300 and rep["skipped"] == 101
    with pytest.raises(ValueError, match="grande"):
        ML.wli.parse_pozzo(" " * 10_000_001)


def test_profile_id_cookie(tmp):
    cfg = SimpleNamespace(app={"profile": "p1"})
    req = SimpleNamespace(cookies={"gs_profile": "inesistente"})
    assert ML.profile_id(None, cfg) == "p1" and ML.profile_id(req, cfg) == "p1"
    assert ML.profile_id(None, SimpleNamespace(app={})) == "default"


def test_migrazione_interrotta_si_completa_senza_perdere_la_watchlist(tmp):
    # simula l'interruzione tra RENAME e copia: la watchlist vecchia e' in watchlist_old, quella nuova e' vuota
    import sqlite3 as _sq
    gs = impianto(tmp) if "impianto" in globals() else None
    assert gs is not None
    db = ML.db_path(gs.cfg)
    conn = _sq.connect(db)
    conn.executescript(ML.SCHEMA)
    cols = ",".join(ML.WATCHLIST_COLS)
    conn.execute("CREATE TABLE watchlist_old AS SELECT * FROM watchlist WHERE 0")
    conn.execute("INSERT INTO watchlist_old (item_key, item_id, title, added_at, updated_at) VALUES ('a:1','1','Dune',1,1)")
    conn.commit(); conn.close()
    ML._MIGRATI.clear()
    ML.connect(db, "a").close()  # come all'avvio: register() migra col profilo attivo
    titoli = [r["title"] for r in gs.get("watchlist")["items"]]
    assert titoli == ["Dune"], "la voce non deve restare chiusa in watchlist_old"
    c2 = _sq.connect(db)
    assert c2.execute("SELECT 1 FROM sqlite_master WHERE name='watchlist_old'").fetchone() is None
    c2.close()


def test_copia_di_sicurezza_prima_della_migrazione(tmp):
    import sqlite3 as _sq
    gs = impianto(tmp)
    db = ML.db_path(gs.cfg)
    # database con la vecchia watchlist (senza colonna profile)
    old = _sq.connect(db)
    old.execute("DROP TABLE IF EXISTS watchlist")
    old.execute("CREATE TABLE watchlist (item_key TEXT PRIMARY KEY, item_id TEXT, source TEXT, title TEXT NOT NULL, kind TEXT, series TEXT,"
                " poster TEXT, backdrop TEXT, year INTEGER, genre TEXT, overview TEXT, url TEXT, status TEXT, priority TEXT, rating INTEGER,"
                " notes TEXT, added_at REAL, updated_at REAL)")
    old.execute("INSERT INTO watchlist (item_key,item_id,title,added_at,updated_at) VALUES ('k','k','Heat',1,1)")
    old.commit(); old.close()
    ML._MIGRATI.clear()
    ML.connect(db, "a").close()  # come all'avvio: register() migra col profilo attivo
    assert [r["title"] for r in gs.get("watchlist")["items"]] == ["Heat"]
    from pathlib import Path as _P
    assert _P(str(db) + ".bak-profili").exists(), "copia di sicurezza creata"
