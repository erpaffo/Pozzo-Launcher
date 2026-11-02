"""Classifiche collegate alle ROM: i giochi meglio votati di una console, con la fonte dichiarata.

Funzioni pure: ricevono i giochi della libreria condivisa (record di library.db: id, title, platform, rating,
rating_critics, rating_count e, quando c'e', l'elenco `ratings` per fonte) e restituiscono dict.

Non e' una seconda classifica: l'affidabilità dei voti e' la stessa regola della Top gia' esistente
(`topgames.score`: almeno due fonti, oppure il voto della critica, oppure 50 voti). Qui si aggiunge il punteggio
0…100 combinato, che tiene conto di quante persone hanno votato, e la fonte in chiaro.

Le fonti non usano tutte la stessa scala: 0…1 (IGDB, RAWG dopo la combinazione in library/ratings.py), 0…5
(stelle degli utenti) e 0…100 (critica). `_norm` le porta tutte a 0…100.
"""

from __future__ import annotations

import json

from . import topgames as T
from .library.ratings import NAMES


def _norm(valore) -> float | None:
    """Voto portato a 0…100, qualunque sia la scala della fonte; None se non e' un numero."""
    try:
        v = float(json.loads(valore)) if isinstance(valore, str) else float(valore)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v <= 1:
        return v * 100
    if v <= 5:
        return v * 20
    if v <= 10:
        return v * 10
    return v if v <= 100 else None


def fonti(game: dict) -> list[dict]:
    """[{"source", "name", "score", "count"}] con score 0…100, dall'elenco per fonte o dai campi combinati."""
    elenco = game.get("ratings")
    if isinstance(elenco, str):
        try:
            elenco = json.loads(elenco)
        except ValueError:
            elenco = []
    out = []
    for r in elenco or []:
        if not isinstance(r, dict):
            continue
        punto = _norm(r.get("rating"))
        if punto is None:
            continue
        fonte = str(r.get("source") or "")
        out.append({"source": fonte, "name": r.get("name") or NAMES.get(fonte, fonte),
                    "score": punto, "count": int(r.get("count") or 0)})
    if out:
        return out
    # libreria senza elenco per fonte (voci vecchie): i campi combinati, che sono gia' 0…1
    for fonte, campo in (("igdb", "rating"), ("rawg", "rating_critics")):
        punto = _norm(game.get(campo))
        if punto is not None:
            out.append({"source": fonte, "name": NAMES.get(fonte, fonte), "score": punto,
                        "count": int(game.get("rating_count") or 0)})
    return out


def punteggio(game: dict) -> tuple[float, str] | None:
    """(punteggio 0…100, fonti) di un gioco: media pesata sui voti, None se non c'e' niente di affidabile."""
    if T.score(game) is None:
        return None
    voci = fonti(game)
    if not voci:
        return None
    peso = sum(min(v["count"], 5000) or 10 for v in voci)  # la fonte senza voti conta poco, non zero
    punteggio = sum(v["score"] * (min(v["count"], 5000) or 10) for v in voci) / peso
    nomi = list(dict.fromkeys(v["name"] for v in sorted(voci, key=lambda v: -v["count"])))
    return round(punteggio, 1), ", ".join(nomi)


def top(console: str, games: list[dict], limit: int = 100) -> list[dict]:
    """[{id, title, score, source}] dal punteggio più alto; console vuota o «all» = tutte.

    Lo stesso gioco su più console e' una voce sola (si tiene il voto migliore, o la versione posseduta a pari voto).
    """
    tutte = console in ("", "all", "*", None)
    scelti: dict[str, dict] = {}
    for g in games:
        if not tutte and g.get("platform") != console:
            continue
        if g.get("id") is None:
            continue
        risultato = punteggio(g)
        if risultato is None:  # senza voto affidabile non entra
            continue
        chiave = " ".join((g.get("title") or "").lower().split()) or str(g["id"])
        posseduto = g.get("store") != "online"
        voce = {"id": g["id"], "title": g.get("title") or "", "score": risultato[0], "source": risultato[1]}
        vecchio = scelti.get(chiave)
        if vecchio is None or (voce["score"], posseduto) > (vecchio["score"], vecchio["_poss"]):
            scelti[chiave] = {**voce, "_poss": posseduto}
    ordinate = sorted(scelti.values(), key=lambda v: (-v["score"], v["title"].lower()))
    return [{k: v for k, v in voce.items() if not k.startswith("_")} for voce in ordinate[:max(0, limit)]]
