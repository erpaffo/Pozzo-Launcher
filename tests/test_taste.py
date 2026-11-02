"""Gusto personale (pozzo/taste.py): ore con rendimenti decrescenti, voto, stato, pochi dati.

Esegui: PYTHONUTF8=1 python tests/test_taste.py   (o pytest tests/test_taste.py)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import taste  # noqa: E402


def _game(genres=(), year=None, developer=None):
    return {"genres": list(genres), "year": year, "developer": developer}


def test_ore_con_rendimenti_decrescenti(tmp: Path):
    """Un gioco da 500 ore non deve schiacciare tre giochi da 20 ore nello stesso genere."""
    games = {1: _game(["RPG"]), 2: _game(["Sparatutto"]), 3: _game(["Sparatutto"]), 4: _game(["Sparatutto"])}
    rows = {1: {"playtime": 500 * 3600},
            2: {"playtime": 20 * 3600}, 3: {"playtime": 20 * 3600}, 4: {"playtime": 20 * 3600}}
    prof = taste.profile(games, rows)
    punteggi = dict(prof["genres"])
    assert punteggi["Sparatutto"] > punteggi["RPG"], prof["genres"]
    assert prof["total_hours"] == 560.0 and prof["samples"] == 4
    print("ok  ore: il logaritmo evita che un solo gioco lunghissimo domini il gusto")


def test_voto_estremo_pesa_di_piu(tmp: Path):
    games = {1: _game(["RPG"]), 2: _game(["Puzzle"]), 3: _game(["Corse"])}
    rows = {1: {"playtime": 10 * 3600, "my_rating": 5},
            2: {"playtime": 10 * 3600, "my_rating": 3},
            3: {"playtime": 10 * 3600, "my_rating": 1}}
    punteggi = dict(taste.profile(games, rows)["genres"])
    assert punteggi["RPG"] > punteggi["Puzzle"] > punteggi["Corse"], punteggi
    assert punteggi["Corse"] < punteggi["Puzzle"], "un voto basso toglie"
    print("ok  voto: 5 stelle sopra 3 stelle, 1 stella sotto (toglie)")


def test_stato_e_preferito(tmp: Path):
    games = {1: _game(["RPG"]), 2: _game(["RPG"]), 3: _game(["RPG"]), 4: _game(["RPG"])}
    rows = {1: {"playtime": 5 * 3600, "status": "done"},
            2: {"playtime": 5 * 3600, "status": "dropped"},
            3: {"playtime": 5 * 3600, "status": "backlog"},
            4: {"playtime": 5 * 3600, "favorite": 1}}
    ordine = [k for k, _ in taste.profile(games, rows)["genres"]]
    assert ordine == ["RPG"]
    singoli = {gid: taste._peso(row) for gid, row in rows.items()}
    assert singoli[4] > singoli[1] > singoli[3] > singoli[2], singoli  # preferito > finito > backlog > abbandonato
    print("ok  stato: preferito > finito > backlog > abbandonato")


def test_decenni_e_sviluppatori(tmp: Path):
    games = {1: _game(["RPG"], 1995, "Square"), 2: _game(["RPG"], 1999, "Square"), 3: _game(["Corse"], 2010, "Codemasters")}
    rows = {1: {"playtime": 20 * 3600}, 2: {"playtime": 20 * 3600}, 3: {"playtime": 1 * 3600}}
    prof = taste.profile(games, rows)
    assert prof["decades"][0][0] == "1990" and prof["decades"][0][1] > dict(prof["decades"])["2010"]
    assert prof["developers"][0] == ("Square", prof["developers"][0][1]), prof["developers"]
    print("ok  decenni e sviluppatori sommati per gioco")


def test_dati_mancanti(tmp: Path):
    games = {1: {"title": "Senza niente"}, 2: _game(["RPG"], None, None)}
    rows = {1: {"playtime": 3 * 3600}, 2: {"playtime": 3 * 3600}}
    prof = taste.profile(games, rows)
    assert prof["genres"] == [("RPG", prof["genres"][0][1])], prof
    assert prof["decades"] == [] and prof["developers"] == [], prof
    assert prof["samples"] == 2 and prof["total_hours"] == 6.0
    print("ok  generi/anni/sviluppatori mancanti: nessun crash, niente voci vuote")


def test_pochi_dati_poco_affidabili(tmp: Path):
    games = {i: _game(["RPG"]) for i in range(1, 10)}
    poche = taste.profile(games, {1: {"playtime": 3600}, 2: {"playtime": 3600}})
    assert poche["samples"] == 2 and poche["reliable"] is False and poche["confidence"] < 1, poche
    molte = taste.profile(games, {i: {"playtime": 3600} for i in range(1, 9)})
    assert molte["reliable"] is True and molte["confidence"] == 1.0, molte
    print("ok  pochi giochi: punteggi segnati come poco affidabili (confidence)")


def test_righe_senza_segnali(tmp: Path):
    games = {1: _game(["RPG"])}
    assert taste.profile(games, {1: {}})["samples"] == 0, "una riga vuota non conta"
    assert taste.profile(games, {})["genres"] == []
    assert taste.profile({}, {1: {"playtime": 3600}})["samples"] == 0, "gioco non in libreria: si salta"
    print("ok  righe vuote o giochi non in libreria: ignorati")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        for fn in (test_ore_con_rendimenti_decrescenti, test_voto_estremo_pesa_di_piu, test_stato_e_preferito,
                   test_decenni_e_sviluppatori, test_dati_mancanti, test_pochi_dati_poco_affidabili,
                   test_righe_senza_segnali):
            fn(Path(t))
    print("TUTTI I TEST OK")
