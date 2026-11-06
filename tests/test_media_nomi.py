"""Parser dei nomi dei file di media-locale: casi normali (Jellyfin/Plex), anime e cartelle tematiche.

Esegui: python -m pytest tests/test_media_nomi.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load():
    spec = importlib.util.spec_from_file_location("media_locale_backend",
                                                 ROOT / "extensions" / "media-locale" / "backend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = load()


def test_film_normali():
    assert M.identify("Film (2020).mkv") == {"kind": "film", "title": "Film", "year": 2020}
    assert M.identify("Il Signore degli Anelli - La Compagnia dell'Anello (2001).mkv") == {
        "kind": "film", "title": "Il Signore degli Anelli - La Compagnia dell'Anello", "year": 2001}
    assert M.identify("Film.2020.1080p.BluRay.x264-GRP.mkv") == {"kind": "film", "title": "Film", "year": 2020}
    assert M.identify("The Matrix.1999.WEB-DL.H264.ita.eng.mkv") == {"kind": "film", "title": "The Matrix",
                                                                   "year": 1999}
    assert M.identify("Film [1080p] (2020).mp4") == {"kind": "film", "title": "Film", "year": 2020}


def test_film_anomali():
    # senza anno: titolo intero
    assert M.identify("Film senza anno.mkv") == {"kind": "film", "title": "Film senza anno", "year": None}
    # un numero finale che fa parte del titolo viene letto come anno: il titolo resta (limite noto, come Jellyfin)
    out = M.identify("Blade Runner 2049.mkv")
    assert out["title"] == "Blade Runner" and out["year"] == 2049
    # titolo che è solo un numero: non resta un titolo vuoto
    assert M.identify("1917.mkv") == {"kind": "film", "title": "1917", "year": 1917}
    # parola che sembra un'etichetta di release ma è parte del titolo
    assert M.identify("Charlotte's Web (2006).mkv") == {"kind": "film", "title": "Charlotte's Web", "year": 2006}
    # file non media
    assert M.identify("locandina.jpg") == {}
    assert M.identify("") == {}


def test_episodi():
    assert M.identify("Serie/Season 01/S01E02 - Il titolo.mkv") == {
        "kind": "episodio", "title": "Il titolo", "series": "Serie", "season": 1, "episode": 2}
    assert M.identify("Serie/s01.e02.mkv")["season"] == 1
    assert M.identify("Serie/s01.e02.mkv")["episode"] == 2
    assert M.identify("Serie/1x02 - Titolo.mp4") == {"kind": "episodio", "title": "Titolo", "series": "Serie",
                                                     "season": 1, "episode": 2}
    out = M.identify("Serie/Stagione 2/02 - Titolo.mkv")  # stagione dalla cartella, episodio dal numero
    assert (out["season"], out["episode"], out["title"]) == (2, 2, "Titolo")
    out = M.identify("Serie (2019)/Season 01/S01E02.mkv")  # niente titolo: «Episodio N» e anno dalla serie
    assert (out["series"], out["year"], out["title"]) == ("Serie", 2019, "Episodio 2")
    # S01E02E03: vale il primo episodio
    assert M.identify("Serie/S01E02E03.mkv")["episode"] == 2


def test_episodio_anomalo():
    # in cartella Serie/Serie TV senza sottocartella stagione: riconosciuto come episodio con default season=1
    out = M.identify("Serie/02 - Titolo.mkv")
    assert out == {"kind": "episodio", "title": "Titolo", "series": "Serie", "season": 1, "episode": 2}
    # senza stagione e senza cartella serie/anime: resta un film («02 - Titolo»)
    out = M.identify("Altro/02 - Titolo.mkv")
    assert out == {"kind": "film", "title": "02 - Titolo", "year": None}
    # 1x02 dentro una cartella di stagione: la stagione del nome vince
    out = M.identify("Serie/Season 05/1x02 - Titolo.mkv")
    assert (out["season"], out["episode"]) == (1, 2)


def test_anime_one_piece():
    # One Piece deve essere SEMPRE riconosciuto come serie/episodio e MAI come film
    out = M.identify("One Piece - 1050.mkv")
    assert out == {"kind": "episodio", "title": "Episodio 1050", "series": "One Piece", "season": 1, "episode": 1050}

    out = M.identify("Anime/One Piece/1050.mkv")
    assert out == {"kind": "episodio", "title": "Episodio 1050", "series": "One Piece", "season": 1, "episode": 1050}

    out = M.identify("[Sub-ITA] One Piece 1050.mkv")
    assert out == {"kind": "episodio", "title": "Episodio 1050", "series": "One Piece", "season": 1, "episode": 1050}

    out = M.identify("One Piece 01.mp4")
    assert out == {"kind": "episodio", "title": "Episodio 1", "series": "One Piece", "season": 1, "episode": 1}

    out = M.identify("One Piece E1050.mkv")
    assert out == {"kind": "episodio", "title": "Episodio 1050", "series": "One Piece", "season": 1, "episode": 1050}

    out = M.identify("Anime/One Piece/One Piece - 1050.mkv")
    assert out == {"kind": "episodio", "title": "Episodio 1050", "series": "One Piece", "season": 1, "episode": 1050}

    out = M.identify("One Piece/1050.mkv")
    assert out == {"kind": "episodio", "title": "Episodio 1050", "series": "One Piece", "season": 1, "episode": 1050}

    out = M.identify("One Piece - 1050 - Il risveglio del Gear 5.mkv")
    assert out == {"kind": "episodio", "title": "Il risveglio del Gear 5", "series": "One Piece", "season": 1, "episode": 1050}

    # Verifica tassativa: mai film!
    for f in ("One Piece.mkv", "One Piece 1050.mkv", "One Piece/One Piece - 1050.mkv", "Anime/One Piece/1050.mkv"):
        assert M.identify(f)["kind"] == "episodio", f"{f} non deve essere film"


def test_cartelle_tematiche():
    # Se parts contiene anime/animazione -> sempre episodio
    out = M.identify("Anime/SerieSconosciuta/01.mkv")
    assert out["kind"] == "episodio" and out["episode"] == 1
    out = M.identify("Animazione/Special (2020).mkv")
    assert out["kind"] == "episodio"

    # Se parts contiene film/movies -> prioritariamente film
    out = M.identify("Film/Inception.mkv")
    assert out["kind"] == "film" and out["title"] == "Inception"
    out = M.identify("Movies/The Matrix (1999).mkv")
    assert out["kind"] == "film" and out["title"] == "The Matrix" and out["year"] == 1999

    # Se parts contiene serie/serie tv/tv shows -> episodio
    out = M.identify("Serie TV/Breaking Bad/01 - Pilot.mkv")
    assert out["kind"] == "episodio" and out["episode"] == 1
    out = M.identify("TV Shows/Stranger Things/01.mkv")
    assert out["kind"] == "episodio" and out["episode"] == 1


def test_brani():
    assert M.identify("Artista/Album/01 - Titolo.flac") == {
        "kind": "brano", "title": "Titolo", "album": "Album", "series": "Artista", "track": 1}
    assert M.identify("Artista/Album/CD1/03 - Altro.mp3") == {
        "kind": "brano", "title": "Altro", "album": "Album", "series": "Artista", "track": 3}
    out = M.identify("Musica/05 - Brano.m4a")  # cartella piatta: niente artista né album
    assert out == {"kind": "brano", "title": "Brano", "album": "", "track": 5}
    out = M.identify("Artista/Album/Nessun numero.flac")
    assert "track" not in out and out["title"] == "Nessun numero"
    assert M.identify("Artista/Album/07.Titolo.ogg")["track"] == 7


def test_formati_letti_dal_browser():
    assert ".mp4" in M.BROWSER and ".mp3" in M.BROWSER
    assert ".mkv" not in M.BROWSER  # serve il lettore esterno: niente transcodifica
    assert M.MEDIA == M.VIDEO | M.AUDIO


if __name__ == "__main__":  # anche come script, come gli altri test del repo
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
    print("ok  parser dei nomi dei media")
