"""Serie, franchise e ordine di gioco, dalle sole informazioni della libreria condivisa.

Funzioni pure: ricevono i dict dei giochi (record di library.db: id, title, year e, se c'e', un campo dichiarato
`series`/`franchise`/`franchises`) e non toccano database, rete o profili.

La serie, in ordine di fiducia:
1. il campo dichiarato dal gioco (`series`, `franchise` o il primo di `franchises`);
2. il titolo: si toglie il sottotitolo (dopo «:» o « - »), il numero del capitolo (arabo o romano) e la dicitura di
   riedizione (remake, remaster, edizione definitiva...). I titoli che restano uguali — o quasi uguali, con
   rapidfuzz — sono la stessa serie;
3. niente: un gioco solo non e' una serie.

Una riedizione non e' un capitolo nuovo: resta sulla posizione dell'originale, quindi non risulta «mancante» se quel
capitolo e' gia' in libreria. Per «cosa manca» si guardano solo i titoli gia' presenti nella libreria condivisa
(posseduti, cataloghi degli store, DAT): nessuna rete e nessun elenco scritto a mano.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from .matching import normalize

# Un capitolo indicato in lettere, oltre a quelli che normalize() gia' converte (fino a «x»).
ROMANI = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
          "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19,
          "xx": 20}
# riedizioni e raccolte: stesso gioco, non un capitolo nuovo
RIEDIZIONE = re.compile(r"\b(remake|remastered|remaster|hd|definitive|ultimate|deluxe|complete|goty|"
                        r"game of the year|anniversary|director s cut|directors cut|collection|trilogy|edition)\b")
SOTTOTITOLO = re.compile(r"\s*:|\s+-\s+|\s+\u2013\s+|\s+\u2014\s+")
# nomi diversi per la stessa saga (stessa idea di DEFAULT_ALIASES in library/build.py, ma senza dipendere da lui)
ALIASES = {"zelda": "The Legend of Zelda", "mario bros": "Super Mario", "pokemon": "Pokémon",
           "final fantasy series": "Final Fantasy"}
SIMILI = 92  # due basi di titolo piu' vicine di cosi' sono la stessa serie
SENZA_NUMERO = 999


def _slug(name: str) -> str:
    """Stesso slug di library/build.py: «The Legend of Zelda» -> «legend-of-zelda»."""
    return normalize(name).replace(" ", "-")


def _analizza(title: str) -> tuple[str, int | None, bool]:
    """(base del titolo, numero del capitolo, e' una riedizione)."""
    riedizione = bool(RIEDIZIONE.search(normalize(title)))
    testa = SOTTOTITOLO.split(title, maxsplit=1)[0]
    parole = RIEDIZIONE.sub(" ", normalize(testa)).split()
    numero = None
    if parole and parole[-1].isdigit():
        numero, parole = int(parole[-1]), parole[:-1]
    elif parole and parole[-1] in ROMANI:
        numero, parole = ROMANI[parole[-1]], parole[:-1]
    return " ".join(parole), numero, riedizione


def _nome_mostrato(title: str) -> str:
    """Il titolo senza sottotitolo, numero e dicitura di riedizione, con le maiuscole originali."""
    parole = SOTTOTITOLO.split(title, maxsplit=1)[0].split()
    while parole and (parole[-1].isdigit() or parole[-1].lower().strip(".") in ROMANI):
        parole.pop()
    while parole and RIEDIZIONE.search(normalize(parole[-1])):
        parole.pop()
    return " ".join(parole).strip() or title


def _dichiarata(game: dict) -> str:
    """Serie scritta nei dati del gioco (se c'e')."""
    for chiave in ("series", "franchise"):
        v = game.get(chiave)
        if isinstance(v, str) and v.strip():
            return v.strip()
    v = game.get("franchises")
    if isinstance(v, list) and v and isinstance(v[0], str) and v[0].strip():
        return v[0].strip()
    return ""


def _serie(game: dict, aliases: dict[str, str]) -> tuple[str, str] | None:
    """(id della serie, nome da mostrare) oppure None se dal gioco non si capisce nessuna serie."""
    nome = _dichiarata(game)
    if nome:
        return _slug(nome), nome
    base, _numero, _ried = _analizza(game.get("title") or "")
    if not base:
        return None
    nome = aliases.get(base) or _nome_mostrato(game["title"])
    return _slug(nome), nome


def _ordine(entry: dict) -> tuple:
    _base, numero, _ried = _analizza(entry["title"])
    return (numero if numero is not None else SENZA_NUMERO, entry.get("year") or SENZA_NUMERO, entry["title"])


def group(games: list[dict], aliases: dict[str, str] | None = None) -> dict[str, dict]:
    """{id_serie: {"name", "entries": [{"id", "title", "year"}]}}, capitoli in ordine di gioco.

    Una serie esiste se e' dichiarata nei dati, oppure se almeno due titoli finiscono nella stessa base.
    """
    alias = {**ALIASES, **(aliases or {})}
    gruppi: dict[str, dict] = {}
    for g in games:
        if g.get("id") is None or not (g.get("title") or ""):
            continue
        serie = _serie(g, alias)
        if serie:
            sid, nome = serie
            gruppi.setdefault(sid, {"name": nome, "entries": [], "_dichiarata": False})
            gruppi[sid]["_dichiarata"] |= bool(_dichiarata(g))
            gruppi[sid]["entries"].append({"id": g["id"], "title": g["title"], "year": g.get("year")})
    _unisci_simili(gruppi)
    out = {}
    for sid, info in gruppi.items():
        if len(info["entries"]) > 1 or info["_dichiarata"]:
            out[sid] = {"name": info["name"], "entries": sorted(info["entries"], key=_ordine)}
    return out


def _unisci_simili(gruppi: dict[str, dict]) -> None:
    """«Final Fantasy 7» e «Final Fantasy VII» sono la stessa serie: basi quasi uguali, gruppi uniti."""
    tenuti: list[str] = []  # id gia' consolidati, dai piu' capitoli ai meno
    for sid in sorted(gruppi, key=lambda s: -len(gruppi[s]["entries"])):
        base = _analizza(gruppi[sid]["entries"][0]["title"])[0]
        gemello = next((t for t in tenuti
                        if fuzz.ratio(base, _analizza(gruppi[t]["entries"][0]["title"])[0]) >= SIMILI), None)
        if gemello is None:
            tenuti.append(sid)
            continue
        gruppi[gemello]["entries"] += gruppi.pop(sid)["entries"]


def _possesso(game: dict) -> bool:
    """Posseduto: tutto tranne i giochi che esistono solo nel catalogo online di uno store."""
    return game.get("store") != "online"


def of(game_id, games: list[dict], aliases: dict[str, str] | None = None) -> dict:
    """Dove sta un gioco nella sua serie: {"series", "order", "owned", "missing"}.

    `missing` sono i titoli della serie che la libreria condivide ma il profilo non possiede, senza contare le
    riedizioni di un capitolo gia' posseduto. Un gioco che non e' in nessuna serie: "series" None e l'ordine e' solo lui.
    """
    target = next((g for g in games if g.get("id") == game_id), None)
    if target is None:
        raise ValueError(f"gioco sconosciuto: {game_id}")
    vuoto = {"series": None, "order": [game_id], "owned": [game_id], "missing": []}
    serie = _serie(target, {**ALIASES, **(aliases or {})})
    if not serie:
        return vuoto
    info = group(games, aliases).get(serie[0])
    if not info:
        return vuoto
    by_id = {g["id"]: g for g in games}
    posseduti = {e["id"] for e in info["entries"] if _possesso(by_id[e["id"]])}
    capitoli_posseduti = {_analizza(by_id[i]["title"])[1] for i in posseduti} - {None}
    missing = []
    for e in info["entries"]:
        if e["id"] in posseduti:
            continue
        _base, numero, _ried = _analizza(e["title"])
        if numero is not None and numero in capitoli_posseduti:
            continue  # riedizione (o versione) di un capitolo che c'e' gia'
        missing.append(e["title"])
    return {"series": info["name"], "order": [e["id"] for e in info["entries"]],
            "owned": [e["id"] for e in info["entries"] if e["id"] in posseduti], "missing": missing}
