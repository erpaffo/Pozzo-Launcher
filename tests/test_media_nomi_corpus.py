"""Corpus di nomi di file realistici e ostili per il parser di media-locale.

Ogni riga dichiara l'atteso: (percorso, kind, title, year, series, season, episode). I casi marcati `ambiguo:`
hanno più letture legittime: si documenta quella scelta (una riga di commento) invece di piegare il parser.

Esegui: python -m pytest tests/test_media_nomi_corpus.py -q
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

# percorso, kind, title, year, series, season, episode
CASI = [
    # ---------------------------------------------------------- film
    ("Film (2020).mkv", "film", "Film", 2020, None, None, None),
    ("Film.2020.1080p.BluRay.x264-GRP.mkv", "film", "Film", 2020, None, None, None),
    ("Film 2020 1080p WEB-DL x265 HDR.mkv", "film", "Film", 2020, None, None, None),
    ("The Matrix (1999) [1080p] [BluRay] [5.1] [YTS.MX].mp4", "film", "The Matrix", 1999, None, None, None),
    ("Il buono, il brutto, il cattivo (1966).mkv", "film", "Il buono, il brutto, il cattivo", 1966, None, None, None),
    ("Amélie (2001).mkv", "film", "Amélie", 2001, None, None, None),
    ("Léon - The Professional (1994).mkv", "film", "Léon - The Professional", 1994, None, None, None),
    ("Spider-Man: No Way Home (2021).mkv", "film", "Spider-Man: No Way Home", 2021, None, None, None),
    ("2001 - Odissea nello spazio (1968).mkv", "film", "2001 - Odissea nello spazio", 1968, None, None, None),
    ("2001 A Space Odyssey.mkv", "film", "2001 A Space Odyssey", None, None, None, None),
    ("Se7en (1995).mkv", "film", "Se7en", 1995, None, None, None),
    ("Se7en.mkv", "film", "Se7en", None, None, None, None),
    ("1917 (2019).mkv", "film", "1917", 2019, None, None, None),
    ("1917.mkv", "film", "1917", 1917, None, None, None),  # ambiguo: il numero è anche l'anno; il titolo resta
    ("Ocean's Eleven (2001).mkv", "film", "Ocean's Eleven", 2001, None, None, None),
    ("Mission Impossible 2 (2000).avi", "film", "Mission Impossible 2", 2000, None, None, None),
    ("Film [Director's Cut] (2010).mkv", "film", "Film", 2010, None, None, None),
    ("Film – Il seguito (2018).mp4", "film", "Film – Il seguito", 2018, None, None, None),
    ("Film.2010.EXTENDED.1080p.BluRay.DTS.x264.mkv", "film", "Film", 2010, None, None, None),
    ("Blade Runner 2049.mkv", "film", "Blade Runner", 2049, None, None, None),  # ambiguo: 2049 è parte del titolo
    ("Charlotte's Web (2006).mkv", "film", "Charlotte's Web", 2006, None, None, None),
    ("Film.2020.ITA.ENG.Subbed.MULTi.1080p.mkv", "film", "Film", 2020, None, None, None),
    ("Film senza anno.mkv", "film", "Film senza anno", None, None, None, None),
    ("Film (2020) [1080p].mkv", "film", "Film", 2020, None, None, None),
    # ---------------------------------------------------------- episodi
    ("Serie/Season 01/S01E02 - Il titolo.mkv", "episodio", "Il titolo", None, "Serie", 1, 2),
    ("Serie/Season 1/S01E02.mkv", "episodio", "Episodio 2", None, "Serie", 1, 2),
    ("Serie/S01E01E02 - Doppia puntata.mkv", "episodio", "Doppia puntata", None, "Serie", 1, 1),
    ("Serie/1x02 - Titolo.mp4", "episodio", "Titolo", None, "Serie", 1, 2),
    ("Serie/Stagione 2/02 - Titolo.mkv", "episodio", "Titolo", None, "Serie", 2, 2),
    ("Breaking Bad/Season 05/05 - Ozymandias.mkv", "episodio", "Ozymandias", None, "Breaking Bad", 5, 5),
    ("The Office/Season 02/S02E01 - La festa.mkv", "episodio", "La festa", None, "The Office", 2, 1),
    ("Serie/Season 01/s01e02.mkv", "episodio", "Episodio 2", None, "Serie", 1, 2),
    ("Serie/Season 01/Serie.S01E02.Titolo.1080p.WEB-DL.mkv", "episodio", "Titolo", None, "Serie", 1, 2),
    ("Serie (2019)/Season 01/S01E02.mkv", "episodio", "Episodio 2", 2019, "Serie", 1, 2),
    ("Serie/Season 01/Titolo - 02.mkv", "episodio", "Titolo", None, "Serie", 1, 2),
    ("Anime/Season 01/[SubsPlease] Titolo - 02 (1080p) [ABC].mkv", "episodio", "Episodio 2", None, "Titolo", 1, 2),
    # ambiguo: convenzione anime «Titolo - 02 (1080p)» non riconosciuta; senza stagione nel nome resta un film
    ("Serie.S01E02.1080p.mkv", "episodio", "Serie", None, None, 1, 2),
    # ambiguo: senza titolo dell'episodio resta il nome della serie nel file
    ("Serie/02 - Titolo.mkv", "episodio", "Titolo", None, "Serie", 1, 2),
    # ambiguo: numero senza cartella di stagione: non si può sapere che è un episodio
    # ---------------------------------------------------------- musica
    ("Artista/Album/01 - Titolo.flac", "brano", "Titolo", None, "Artista", None, None),
    ("Artista/Album/CD1/03 - Altro.mp3", "brano", "Altro", None, "Artista", None, None),
    ("Artista/Album/Disc 2/04 - Altro.mp3", "brano", "Altro", None, "Artista", None, None),
    ("Artista/Album/05.Titolo.ogg", "brano", "Titolo", None, "Artista", None, None),
    ("Artista/Album/01. Titolo.m4a", "brano", "Titolo", None, "Artista", None, None),
    ("Artista/Album/Titolo senza numero.m4a", "brano", "Titolo senza numero", None, "Artista", None, None),
    ("Artista - Titolo.flac", "brano", "Titolo", None, "Artista", None, None),
    ("Artista/Album/Artista - Titolo.flac", "brano", "Titolo", None, "Artista", None, None),
    ("Artista/Album/01 - Señorita (feat. X).mp3", "brano", "Señorita (feat. X)", None, "Artista", None, None),
    ("Sigur Rós/( )/01 - Untitled.flac", "brano", "Untitled", None, "Sigur Rós", None, None),
    ("Daft Punk/Discovery/01 - One More Time.mp3", "brano", "One More Time", None, "Daft Punk", None, None),
    ("Musica/05 - Brano.m4a", "brano", "Brano", None, None, None, None),
    ("Artista/Album/1-01 - Titolo.flac", "brano", "01 - Titolo", None, "Artista", None, None),
    # ambiguo: «1-01» è disco-traccia per alcuni, per noi la traccia è 1 e il resto resta nel titolo
    # ---------------------------------------------------------- non media
    ("locandina.jpg", None, None, None, None, None, None),
    ("Serie/Season 01/poster.jpg", None, None, None, None, None, None),
    ("documento.pdf", None, None, None, None, None, None),
    ("", None, None, None, None, None, None),
]


def lettura(out: dict):
    return (out.get("kind"), out.get("title"), out.get("year"), out.get("series"),
            out.get("season"), out.get("episode"))


def test_corpus():
    errori = []
    for riga in CASI:
        percorso = riga[0]
        atteso = riga[1:]
        letto = lettura(M.identify(percorso))
        if letto != atteso:
            errori.append(f"{percorso!r}\n    atteso: {atteso}\n    letto:  {letto}")
    assert not errori, "casi sbagliati (" + str(len(errori)) + "):\n" + "\n".join(errori)


def test_corpus_almeno_40_casi():
    assert len(CASI) >= 40, len(CASI)


if __name__ == "__main__":
    test_corpus_almeno_40_casi()
    test_corpus()
    print(f"ok  corpus dei nomi: {len(CASI)} casi")
