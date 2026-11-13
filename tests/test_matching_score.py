"""Punteggio titoli: numeri romani vs arabi, sequel diversi, best() sopra soglia.

Esegui: python tests/test_matching_score.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo.matching import best, score  # noqa: E402


def test_identico_100():
    assert score("Mega Man X", "Mega Man X") == 100


def test_romano_uguale_a_arabo_85():
    # uguali solo grazie alla conversione dei romani: buono, ma sotto il 100
    s = score("Mega Man X", "Mega Man 10")
    assert 70 <= s < 100, s


def test_best_preferisce_titolo_identico():
    assert best("Mega Man X", ["Mega Man 10", "Mega Man X"])[0] == "Mega Man X"
    assert best("Mega Man 10", ["Mega Man X", "Mega Man 10"])[0] == "Mega Man 10"


def test_final_fantasy_romano_e_arabo():
    assert score("Final Fantasy XII", "Final Fantasy 12") >= 70
    assert score("Final Fantasy X", "Final Fantasy 10") >= 70


def test_sequel_diversi_sotto_soglia():
    assert score("Halo 2", "Halo 3") < 70
    assert score("Street Fighter II", "Street Fighter III") < 70


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
