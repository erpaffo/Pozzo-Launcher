"""Serie e ordine di gioco (pozzo/franchise.py): numeri romani, sottotitoli, remake, serie uguali per sbaglio.

Esegui: PYTHONUTF8=1 python tests/test_franchise.py   (o pytest tests/test_franchise.py)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import franchise  # noqa: E402


def _g(gid, title, year=None, **extra):
    return {"id": gid, "title": title, "year": year, "store": "local", **extra}


def test_numeri_romani(tmp: Path):
    games = [_g(9, "Final Fantasy IX", 2000), _g(7, "Final Fantasy VII", 1997),
             _g(8, "Final Fantasy VIII", 1999)]
    serie = franchise.group(games)
    assert list(serie) == ["final-fantasy"], serie
    assert [e["id"] for e in serie["final-fantasy"]["entries"]] == [7, 8, 9], "ordine dei capitoli, non alfabetico"
    print("ok  numeri romani: VII, VIII, IX messi in ordine di capitolo")


def test_sottotitoli(tmp: Path):
    games = [_g(2, "The Legend of Zelda: Tears of the Kingdom", 2023),
             _g(1, "The Legend of Zelda: Breath of the Wild", 2017)]
    serie = franchise.group(games)
    assert list(serie) == ["legend-of-zelda"], serie
    assert serie["legend-of-zelda"]["name"] == "The Legend of Zelda"
    assert [e["id"] for e in serie["legend-of-zelda"]["entries"]] == [1, 2], "senza numero: ordine di uscita"
    print("ok  sottotitoli: stessa serie, ordine per anno")


def test_remake_non_e_un_capitolo(tmp: Path):
    games = [_g(7, "Final Fantasy VII", 1997, store="steam"),
             _g(70, "Final Fantasy VII Remake", 2020, store="online")]
    serie = franchise.group(games)
    assert len(serie["final-fantasy"]["entries"]) == 2, serie
    stato = franchise.of(7, games)
    assert stato["series"] == "Final Fantasy" and stato["owned"] == [7], stato
    assert stato["missing"] == [], "il remake non e' un capitolo mancante se ho l'originale"
    print("ok  remake: sta nella serie ma non conta come capitolo mancante")


def test_cosa_manca(tmp: Path):
    games = [_g(7, "Final Fantasy VII", 1997, store="steam"),
             _g(8, "Final Fantasy VIII", 1999, store="online"),
             _g(9, "Final Fantasy IX", 2000, store="online")]
    stato = franchise.of(7, games)
    assert stato["missing"] == ["Final Fantasy VIII", "Final Fantasy IX"], stato
    assert stato["order"] == [7, 8, 9] and stato["owned"] == [7], stato
    print("ok  mancanti: i capitoli che la libreria conosce ma il profilo non ha")


def test_gioco_senza_serie(tmp: Path):
    games = [_g(1, "Tetris"), _g(2, "Final Fantasy VII", 1997), _g(3, "Final Fantasy VIII", 1999)]
    assert "tetris" not in franchise.group(games)
    stato = franchise.of(1, games)
    assert stato == {"series": None, "order": [1], "owned": [1], "missing": []}, stato
    print("ok  gioco solo: nessuna serie, ordine da solo")


def test_serie_simili_ma_diverse(tmp: Path):
    games = [_g(1, "Final Fantasy VII", 1997), _g(2, "Final Fantasy VIII", 1999),
             _g(3, "Final Fantasy Tactics: The War of the Lions", 2007),
             _g(4, "Final Fantasy Tactics: The Zodiac Age", 2007)]
    serie = franchise.group(games)
    assert [e["id"] for e in serie["final-fantasy"]["entries"]] == [1, 2], "Tactics non entra nella serie principale"
    assert [e["id"] for e in serie["final-fantasy-tactics"]["entries"]] == [3, 4], serie
    print("ok  nomi simili: Tactics resta una serie a parte")


def test_serie_dichiarata(tmp: Path):
    games = [_g(1, "Pokémon Rosso", franchise="Pokémon"), _g(2, "Pokémon Blu", franchise="Pokémon")]
    serie = franchise.group(games)
    assert serie["pokemon"]["name"] == "Pokémon" and len(serie["pokemon"]["entries"]) == 2, serie
    # senza il campo dichiarato i due titoli non hanno niente in comune: nessuna serie
    games2 = [{"id": 1, "title": "Pokémon Rosso", "year": 1996}, {"id": 2, "title": "Pokémon Blu", "year": 1996}]
    assert franchise.group(games2) == {}
    print("ok  serie dichiarata nei dati: vince sul titolo")


def test_basi_quasi_uguali(tmp: Path):
    games = [_g(1, "Mega Man 2", 1988), _g(2, "Megaman 3", 1990)]
    serie = franchise.group(games)
    assert len(serie) == 1, serie
    assert [e["id"] for e in next(iter(serie.values()))["entries"]] == [1, 2]
    print("ok  «Mega Man» e «Megaman»: stessa serie (rapidfuzz)")


def test_gioco_sconosciuto(tmp: Path):
    try:
        franchise.of(99, [_g(1, "Tetris")])
    except ValueError as e:
        assert "sconosciuto" in str(e), e
    else:
        raise AssertionError("ci si aspetta ValueError")
    print("ok  gioco sconosciuto: ValueError")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        for fn in (test_numeri_romani, test_sottotitoli, test_remake_non_e_un_capitolo, test_cosa_manca,
                   test_gioco_senza_serie, test_serie_simili_ma_diverse, test_serie_dichiarata,
                   test_basi_quasi_uguali, test_gioco_sconosciuto):
            fn(Path(t))
    print("TUTTI I TEST OK")
