"""Siti di mod per i titoli più famosi.

Una tabella curata (pozzo/data/mod_sites.json): titolo + console -> siti che hanno le mod di quel gioco. Nessuna
ricerca per ogni gioco della libreria: solo i titoli in tabella, e il link porta alla ricerca del sito. I modelli di ricerca
dei siti stanno tutti nel file dati, quindi se un sito cambia indirizzo si corregge in un punto solo.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from .matching import normalize

DATA = Path(__file__).parent / "data" / "mod_sites.json"


@lru_cache(maxsize=1)
def _table() -> dict:
    table = json.loads(DATA.read_text(encoding="utf-8"))
    for game in table["games"]:
        game["_alias"] = [normalize(alias) for alias in game["aliases"]]
    return table


def sites_for(*titles: str, platform: str) -> list[dict]:
    """Siti di mod del primo gioco in tabella che corrisponde a uno dei titoli (nome, nome del DAT...) su quella console.
    Corrisponde se il titolo normalizzato è l'alias o comincia con l'alias (es. «... Special Edition», «... (USA)»)."""
    table = _table()
    names = [n for n in (normalize(t) for t in titles if t) if n]
    for game in table["games"]:
        if platform not in game["platforms"]:
            continue
        if any(n == a or n.startswith(a + " ") for n in names for a in game["_alias"]):
            return [_link(table["sites"], game, site) for site in game["sites"]]
    return []


def _link(sites: dict, game: dict, site) -> dict:
    sid, url = (site, None) if isinstance(site, str) else (site["site"], site.get("url"))
    return {"site": sid, "name": sites[sid]["name"],
            "url": url or sites[sid]["search"].replace("{q}", quote_plus(game["name"]))}
