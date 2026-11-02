"""Suggerimenti (pozzo/similar.py): motivi sempre presenti, esclusioni, serie, sviluppatore, gusto, ordine.

Esegui: PYTHONUTF8=1 python tests/test_similar.py   (o pytest tests/test_similar.py)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import similar  # noqa: E402

GUSTO = {"genres": [("JRPG", 10.0), ("Puzzle", 2.0)], "decades": [("1990", 6.0)],
         "developers": [], "total_hours": 120.0, "samples": 8}
AMATI = [{"id": 100, "title": "Chrono Trigger", "genres": ["JRPG"], "developer": "Square", "year": 1995,
          "playtime": 42 * 3600},
         {"id": 101, "title": "Final Fantasy VI", "genres": ["JRPG"], "developer": "Square", "year": 1994,
          "playtime": 30 * 3600}]
SERIE = {"final-fantasy": {"name": "Final Fantasy",
                           "entries": [{"id": 101, "title": "Final Fantasy VI"}, {"id": 200, "title": "Final Fantasy IX"}]}}


def _c(cid, title, **extra):
    return {"id": cid, "title": title, "genres": [], "store": "local", **extra}


def test_motivo_genere_con_ore(tmp: Path):
    out = similar.recommend([_c(200, "Xenogears", genres=["JRPG"], year=1998)], GUSTO, AMATI)
    assert len(out) == 1 and out[0]["id"] == 200
    testi = [r["text"] for r in out[0]["reasons"]]
    assert any(t.startswith("Ami i JRPG: ") and t.endswith(" ore") for t in testi), testi
    assert any(r["kind"] == "decennio" and "anni '90" in r["text"] for r in out[0]["reasons"]), out[0]
    print("ok  motivo del genere con le ore spese, e del decennio")


def test_mai_senza_motivo(tmp: Path):
    """Un gioco senza generi nel gusto, senza sviluppatore/serie e senza voto non viene proposto."""
    out = similar.recommend([_c(1, "Gioco Qualunque", genres=["Sport"])], GUSTO, AMATI)
    assert out == [], out
    print("ok  niente motivi, niente suggerimento")


def test_sviluppatore_e_serie(tmp: Path):
    out = similar.recommend([_c(200, "Final Fantasy IX", genres=["JRPG"], developer="Square")], GUSTO, AMATI, SERIE)
    kinds = {r["kind"]: r["text"] for r in out[0]["reasons"]}
    assert kinds["sviluppatore"] == "Stesso sviluppatore di Chrono Trigger", kinds
    assert kinds["serie"].startswith("Fa parte di Final Fantasy, come "), kinds
    print("ok  stesso sviluppatore e stessa serie, detti con il nome del gioco")


def test_esclusioni(tmp: Path):
    cand = [_c(1, "Nascosto", genres=["JRPG"], hidden=1), _c(2, "Finito", genres=["JRPG"], status="done"),
            _c(3, "Abbandonato", genres=["JRPG"], status="dropped"), _c(4, "In corso", genres=["JRPG"], status="playing"),
            _c(5, "Nel catalogo", genres=["JRPG"], store="online"), AMATI[0]]
    out = similar.recommend(cand, GUSTO, AMATI, include_unowned=False)
    assert [r["id"] for r in out] == [4], out
    out2 = similar.recommend(cand, GUSTO, AMATI, include_played=True)
    assert {r["id"] for r in out2} == {2, 3, 4, 5}, out2  # giocati e del catalogo solo se richiesti
    print("ok  esclusioni: nascosti, finiti, abbandonati e catalogo (con i parametri giusti)")


def test_ordine_e_limite(tmp: Path):
    cand = [_c(1, "Solo genere", genres=["JRPG"]),
            _c(2, "Genere e sviluppatore", genres=["JRPG"], developer="Square"),
            _c(3, "Genere e voto", genres=["JRPG"], rating=0.9)]
    out = similar.recommend(cand, GUSTO, AMATI)
    assert [r["id"] for r in out] == [2, 3, 1], out
    assert similar.recommend(cand, GUSTO, AMATI, limit=2) == out[:2]
    print("ok  ordine per punteggio e limite rispettato")


def test_somiglianza_testuale(tmp: Path):
    out = similar.recommend([_c(9, "Chrono Trigger 2", genres=["Sport"])], GUSTO, AMATI)
    kinds = [r["kind"] for r in out[0]["reasons"]]
    assert "simile_a" in kinds, out
    print("ok  titolo simile a un gioco amato: motivo «simile a»")


def test_punteggio_del_candidato(tmp: Path):
    out = similar.recommend([_c(1, "Votato bene", rating=0.95)], GUSTO, AMATI)
    assert out[0]["reasons"][0]["kind"] == "punteggio" and "/10" in out[0]["reasons"][0]["text"], out
    print("ok  voto del candidato usato come motivo")


def test_senza_amati(tmp: Path):
    """Senza giochi amati restano i motivi che non dipendono da loro; nessun crash."""
    out = similar.recommend([_c(1, "Xenogears", genres=["JRPG"], developer="Square")], GUSTO, [])
    assert out and all(r["reasons"] for r in out), out
    assert similar.recommend([_c(2, "Senza segnali")], GUSTO, []) == []
    print("ok  nessun gioco amato: si usano solo gusto e voto, senza errori")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        for fn in (test_motivo_genere_con_ore, test_mai_senza_motivo, test_sviluppatore_e_serie, test_esclusioni,
                   test_ordine_e_limite, test_somiglianza_testuale, test_punteggio_del_candidato, test_senza_amati):
            fn(Path(t))
    print("TUTTI I TEST OK")
