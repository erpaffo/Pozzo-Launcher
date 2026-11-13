"""Confronto titoli per le sorgenti basate su ricerca per nome (IGDB, TheGamesDB, ScreenScraper fallback).

Rimpiazza la distanza di Levenshtein "a mano" di scraperworker.cpp con rapidfuzz (C++),
dopo una normalizzazione che gestisce articoli, numeri romani, punteggiatura e sottotitoli.
"""

from __future__ import annotations

from functools import lru_cache
import re
import unicodedata

try:
    from rapidfuzz import fuzz
except ImportError:  # fallback senza dipendenze
    from difflib import SequenceMatcher

    class fuzz:  # type: ignore
        @staticmethod
        def ratio(a, b):
            return 100 * SequenceMatcher(None, a, b).ratio()

        token_sort_ratio = ratio

ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
         "xi": "11", "xii": "12", "xiii": "13", "xiv": "14", "xv": "15", "xvi": "16", "xvii": "17", "xviii": "18", "xix": "19", "xx": "20"}
_TAGS = re.compile(r"[\(\[][^\)\]]*[\)\]]")


@lru_cache(maxsize=500_000)  # chiamata milioni di volte sugli stessi titoli (libreria + store online)
def normalize(title: str) -> str:
    # ™ ® © prima di NFKD: altrimenti diventano "TM"/"(R)" attaccati alla parola ("Pokemontm Scarlet")
    t = unicodedata.normalize("NFKD", title.replace("™", " ").replace("®", " ").replace("©", " ")).encode("ascii", "ignore").decode().lower()
    t = _TAGS.sub(" ", t)
    t = t.replace("&", " and ").replace("'", "")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    words = [ROMAN.get(w, w) for w in t.split() if w not in ("the", "a", "an")]
    return " ".join(words)


def score(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        # uguali solo grazie ai numeri romani (es. «Mega Man X» / «Mega Man 10»): buono, ma un titolo identico vince
        if re.findall(r"\b\d+\b", _TAGS.sub(" ", a.lower())) != re.findall(r"\b\d+\b", _TAGS.sub(" ", b.lower())):
            return 85.0
        return 100.0
    s = max(fuzz.ratio(na, nb), fuzz.token_sort_ratio(na, nb))
    # "Sonic" vs "Sonic the Hedgehog": se uno e' prefisso dell'altro con sottotitolo, buono ma non perfetto
    main_a, main_b = re.split(r" - |: ", a)[0], re.split(r" - |: ", b)[0]
    if normalize(main_a) == normalize(main_b):
        s = max(s, 85.0)
    # numeri di sequel diversi = gioco diverso
    nums_a, nums_b = re.findall(r"\b\d+\b", na), re.findall(r"\b\d+\b", nb)
    if nums_a != nums_b:
        s -= 25
    return s


def best(query: str, candidates: list, key=lambda c: c, min_score: float = 70):
    """Ritorna (candidato, punteggio) migliore oppure (None, punteggio)."""
    top, top_s = None, 0.0
    for c in candidates:
        names = key(c)
        if isinstance(names, str):
            names = [names]
        s = max((score(query, n) for n in names if n), default=0)
        if s > top_s:
            top, top_s = c, s
    return (top, top_s) if top_s >= min_score else (None, top_s)


# ---------------------------------------------------------------- correzione manuale del match
# campi che una correzione dell'utente porta con se' (dal risultato scelto di una sorgente)
OVERRIDE_FIELDS = ("title", "description", "developer", "publisher", "genres", "release_date", "players",
                   "rating", "rating_count", "rating_critics", "ages", "igdb_id", "igdb_url", "ss_id")


def make_override(title: str, source: str = "", fields: dict | None = None, cover: str = "") -> dict:
    """Correzione salvata in userdata: il titolo scelto (con cui tutte le sorgenti cercano il resto) e i campi
    del risultato scelto. Solo valori semplici, cosi' resta serializzabile in JSON."""
    title = " ".join(str(title or "").split())[:200]
    if not title:
        raise ValueError("titolo vuoto")
    f = {k: v for k, v in (fields or {}).items()
         if k in OVERRIDE_FIELDS and isinstance(v, (str, int, float, list)) and v not in ("", [])}
    f["title"] = title
    return {"title": title, "source": str(source or "")[:40], "fields": f, "cover": str(cover or "")}
