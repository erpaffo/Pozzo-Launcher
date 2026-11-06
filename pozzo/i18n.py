"""Cataloghi di traduzione (pozzo/data/locales/<lingua>.json). it.json e' la sorgente: ogni chiave manca -> si ricade su it."""

from __future__ import annotations

import json
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).parent / "data" / "locales"
SOURCE = "it"
current: ContextVar[str] = ContextVar("lang", default=SOURCE)  # lingua della richiesta in corso (cookie gs_lang)
RTL = frozenset(("ar", "he", "fa", "ur"))


def languages() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.json"))


@lru_cache(maxsize=None)
def _load(lang: str) -> dict[str, str]:
    p = DIR / f"{lang}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def catalog(lang: str) -> dict[str, str]:
    """Catalogo completo: la lingua sopra, l'italiano sotto per le chiavi non ancora tradotte."""
    return {**_load(SOURCE), **_load(lang if lang in languages() else SOURCE)}


def tr(key: str, lang: str | None = None, **params) -> str:
    lang = lang or current.get()
    text = catalog(lang).get(key, key)
    try:
        return text.format(**params) if params else text
    except (KeyError, IndexError):
        return text


def from_request(cookie: str | None, accept: str | None) -> str:
    """Lingua per la richiesta: cookie gs_lang, poi Accept-Language, poi italiano."""
    have = languages()
    for cand in [cookie or ""] + [part.split(";")[0].strip() for part in (accept or "").split(",")]:
        for c in (cand, cand.split("-")[0]):
            if c in have:
                return c
    return SOURCE
