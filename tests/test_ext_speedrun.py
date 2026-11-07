"""extensions/speedrun: tempo formattato, record con rete finta (httpx.MockTransport), cache, backoff e titolo dalla libreria.
Nessuna chiamata vera a speedrun.com.

Esegui: python -m pytest tests/test_ext_speedrun.py
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load():
    spec = importlib.util.spec_from_file_location("ext_speedrun", ROOT / "extensions" / "speedrun" / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.MIN_GAP = 0  # niente attese nei test
    return mod


GIOCO = {"data": [{"id": "g1", "names": {"international": "Hollow Knight"}, "weblink": "https://www.speedrun.com/hollowknight"}]}
CATEGORIE = {"data": {"categories": {"data": [
    {"id": "c1", "name": "Any%", "type": "per-game"},
    {"id": "c2", "name": "Level", "type": "per-level"},
    {"id": "c3", "name": "All Skills", "type": "per-game"},
]}}}
LB_ANY = {"data": {
    "runs": [{"place": 1, "run": {"weblink": "https://www.speedrun.com/hollowknight/run/x1", "times": {"primary_t": 269.34},
                                  "players": [{"rel": "user", "id": "u1"}]}}],
    "players": {"data": [{"id": "u1", "names": {"international": "Staxis"}}]},
}}
LB_VUOTA = {"data": {"runs": [], "players": {"data": []}}}


def fake_api(conteggio: list):
    def handler(req: httpx.Request) -> httpx.Response:
        conteggio.append(req.url.path)
        p = req.url.path
        if p == "/api/v1/games":
            return httpx.Response(200, json=GIOCO)
        if p == "/api/v1/games/g1":
            return httpx.Response(200, json=CATEGORIE)
        if p == "/api/v1/leaderboards/g1/category/c1":
            return httpx.Response(200, json=LB_ANY)
        if p == "/api/v1/leaderboards/g1/category/c3":
            return httpx.Response(200, json=LB_VUOTA)
        return httpx.Response(404)
    return handler


def client_per(conteggio: list) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake_api(conteggio)))


def test_tempo_formato():
    mod = load()
    assert mod._tempo(269.34) == "4:29"
    assert mod._tempo(3725) == "1:02:05"


def test_wr_solo_categorie_per_gioco_con_run():
    mod = load()
    conteggio = []
    r = mod.wr(client_per(conteggio), "Hollow Knight")
    assert r["nome"] == "Hollow Knight" and r["link"] == "https://www.speedrun.com/hollowknight"
    # una sola categoria ha una run: «Level» (per livello) e «All Skills» (senza run) non compaiono
    assert r["categorie"] == [{"nome": "Any%", "giocatore": "Staxis", "tempo": "4:29",
                               "link": "https://www.speedrun.com/hollowknight/run/x1"}]


def test_record_usa_la_cache_e_non_richiama_la_rete(tmp_path):
    mod = load()
    conteggio = []
    c = client_per(conteggio)
    r1 = mod.record(c, tmp_path, 7, "Hollow Knight", now=1_000_000.0)
    chiamate = len(conteggio)
    r2 = mod.record(c, tmp_path, 7, "Hollow Knight", now=1_000_000.0 + 3600)
    assert r1 == r2 and r1["errore"] == "" and len(conteggio) == chiamate
    mod.record(c, tmp_path, 7, "Hollow Knight", now=1_000_000.0 + 25 * 3600)  # scaduta: si riscarica
    assert len(conteggio) > chiamate


def test_errore_tiene_il_backoff_e_non_rompe_la_route(tmp_path):
    mod = load()
    conteggio = []

    def fuori(req):
        conteggio.append(req.url.path)
        return httpx.Response(503)
    c = httpx.Client(transport=httpx.MockTransport(fuori))
    log = []
    r = mod.record(c, tmp_path, 7, "Hollow Knight", now=1000.0, log=log.append)
    assert r["errore"] == "HTTP 503" and r["categorie"] == [] and log
    n = len(conteggio)
    mod.record(c, tmp_path, 7, "Hollow Knight", now=1000.0 + 60)  # dentro il backoff: nessuna richiesta
    assert len(conteggio) == n
    mod.record(c, tmp_path, 7, "Hollow Knight", now=1000.0 + mod.BACKOFF_BASE + 1)  # dopo il backoff: riprova
    assert len(conteggio) > n


def test_titolo_dalla_libreria(tmp_path):
    mod = load()
    cfg = type("Cfg", (), {"cache": tmp_path})()
    assert mod._titolo(cfg, 7) == ""  # niente libreria ancora
    db = sqlite3.connect(tmp_path / "library.db")
    db.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, title TEXT)")
    db.execute("INSERT INTO games VALUES (7, 'Hollow Knight')")
    db.commit()
    db.close()
    assert mod._titolo(cfg, 7) == "Hollow Knight" and mod._titolo(cfg, 99) == ""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
