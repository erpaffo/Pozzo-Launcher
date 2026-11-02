"""Classifiche collegate alle ROM (pozzo/rankings.py): scale diverse, peso dei voti, fonte, esclusioni.

Esegui: PYTHONUTF8=1 python tests/test_rankings.py   (o pytest tests/test_rankings.py)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import rankings  # noqa: E402


def _g(gid, title, platform="snes", ratings=None, **extra):
    base = {"id": gid, "title": title, "platform": platform, "store": "local", "rating": 0.8,
            "rating_count": 500, "rating_critics": None, "ratings": ratings}
    base.update(extra)
    return base


def test_scale_diverse(tmp: Path):
    assert rankings._norm(0.85) == 85.0        # 0…1 (IGDB, RAWG)
    assert rankings._norm(4.5) == 90.0         # 0…5 (stelle)
    assert rankings._norm(88) == 88.0          # 0…100 (critica)
    assert rankings._norm("9.2") == 92.0       # 0…10 come testo
    assert rankings._norm(None) is None and rankings._norm("boh") is None
    print("ok  scale 0…1, 0…5, 0…10 e 0…100 portate a 0…100")


def test_peso_dei_voti_fonti_e_fonte_dichiarata(tmp: Path):
    ratings = [{"source": "igdb", "name": "IGDB", "rating": 0.9, "count": 1000},
               {"source": "steam", "name": "Recensioni Steam", "rating": 0.5, "count": 5}]
    punto, fonte = rankings.punteggio(_g(1, "Gioco", ratings=ratings))
    assert 88 < punto < 90, punto  # il voto con 1000 persone pesa quasi tutto
    assert fonte.startswith("IGDB") and "Recensioni Steam" in fonte, fonte
    print(f"ok  media pesata sui voti ({punto}/100) e fonti dichiarate ({fonte})")


def test_senza_voti_affidabili(tmp: Path):
    solo_uno = _g(1, "Poco votato", ratings=[{"source": "igdb", "rating": 0.9, "count": 3}],
                  rating=0.9, rating_count=3, rating_critics=None)
    assert rankings.punteggio(solo_uno) is None, "una fonte con 3 voti non basta"
    assert rankings.top("snes", [solo_uno]) == []
    print("ok  pochi voti: il gioco non entra in classifica")


def test_top_per_console_e_ordine(tmp: Path):
    games = [_g(1, "Bravo", ratings=[{"source": "igdb", "rating": 0.7, "count": 900}]),
             _g(2, "Ottimo", ratings=[{"source": "igdb", "rating": 0.95, "count": 900}]),
             _g(3, "Altrove", platform="nes", ratings=[{"source": "igdb", "rating": 0.99, "count": 900}])]
    out = rankings.top("snes", games)
    assert [r["id"] for r in out] == [2, 1], out
    assert all(set(r) == {"id", "title", "score", "source"} for r in out), out
    assert rankings.top("snes", games, limit=1) == out[:1]
    print("ok  top della console, ordine per punteggio, limite")


def test_tutte_le_console_senza_doppioni(tmp: Path):
    games = [_g(1, "Stesso Gioco", platform="snes", ratings=[{"source": "igdb", "rating": 0.7, "count": 900}]),
             _g(2, "Stesso Gioco", platform="gba", store="online",
                ratings=[{"source": "igdb", "rating": 0.95, "count": 900}])]
    out = rankings.top("all", games)
    assert len(out) == 1 and out[0]["id"] == 2 and out[0]["score"] > 90, out
    pari = [_g(3, "Pareggio", platform="snes", ratings=[{"source": "igdb", "rating": 0.8, "count": 900}]),
            _g(4, "Pareggio", platform="gba", store="online",
               ratings=[{"source": "igdb", "rating": 0.8, "count": 900}])]
    assert rankings.top("all", pari)[0]["id"] == 3, "a pari voto vince la versione posseduta"
    print("ok  «tutte»: un gioco su più console resta una voce sola")


def test_campi_combinati_senza_elenco(tmp: Path):
    """Voci vecchie, senza `ratings` per fonte: si usano rating e critica combinati della libreria."""
    g = _g(1, "Vecchio", ratings=None, rating=0.82, rating_count=300, rating_critics=0.9)
    punto, fonte = rankings.punteggio(g)
    assert 80 < punto < 95 and "RAWG" in fonte, (punto, fonte)
    print("ok  voci senza elenco per fonte: si usano i voti combinati della libreria")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        for fn in (test_scale_diverse, test_peso_dei_voti_fonti_e_fonte_dichiarata, test_senza_voti_affidabili,
                   test_top_per_console_e_ordine, test_tutte_le_console_senza_doppioni,
                   test_campi_combinati_senza_elenco):
            fn(Path(t))
    print("TUTTI I TEST OK")
