"""Suggerimenti di giochi da giocare, con il motivo scritto in chiaro, dalle sole informazioni della libreria.

Funzioni pure: non toccano database, rete o profili.

    similar.recommend(candidates, taste, loved, franchise_info, limit=20, include_unowned=True, include_played=False)

`candidates` sono i giochi della libreria condivisa (posseduti e non: ROM senza store, cataloghi esterni, DAT); se
portano anche i campi personali del profilo (`hidden`, `status`, `playtime`, `my_rating`, `favorite`) servono per
escludere e per pesare, altrimenti si usano solo i metadati. `taste` è il risultato di taste.profile(); `loved` sono
i giochi che la persona ha amato; `franchise_info` è il risultato di franchise.group() (o None).

Il punteggio (0…10 circa) somma:

    generi 2,0 · gusto per i suoi generi      decennio 0,8 · gusto per il suo decennio
    sviluppatore 2,0 · stesso sviluppatore di un gioco amato
    serie 2,5 · stessa serie di un gioco amato
    voto 1,5 · voto del candidato (0…1)       simile 1,5 · somiglianza del titolo con un gioco amato (0…1)

Ogni suggerimento esce con almeno un motivo (`reasons`, kind in sviluppatore/serie/genere/simile_a/punteggio/decennio):
senza motivi il gioco non viene proposto, così non ci sono consigli «a caso».
"""

from __future__ import annotations

from rapidfuzz import fuzz

from .matching import normalize

SIMILE = 70  # sotto questa somiglianza due titoli non si somigliano abbastanza per dirlo
ANNI = {"1970": "anni '70", "1980": "anni '80", "1990": "anni '90", "2000": "anni 2000", "2010": "anni 2010",
        "2020": "anni 2020"}


def _ore(game: dict) -> float:
    try:
        return max(0.0, float(game.get("playtime") or 0)) / 3600
    except (TypeError, ValueError):
        return 0.0


def _gusto(taste: dict, chiave: str) -> dict[str, float]:
    """{nome: punteggio} normalizzato 0…1 (il gusto più forte vale 1)."""
    voci = taste.get(chiave) or []
    massimo = max([v for _k, v in voci if v > 0], default=0) or 1
    return {k: max(0.0, v) / massimo for k, v in voci}


def _testo(game: dict) -> str:
    return normalize(f"{game.get('title') or ''} {' '.join(game.get('genres') or [])}")


def _vietato(game: dict, include_played: bool) -> bool:
    """Nascosto, gia' finito o abbandonato: non si suggerisce (a meno di chiederlo)."""
    if game.get("hidden"):
        return True
    return not include_played and (game.get("status") or "") in ("done", "dropped")


def _serie_di(franchise_info: dict | None) -> tuple[dict, dict]:
    """(id gioco -> id serie, id serie -> nome) dal risultato di franchise.group()."""
    per_gioco, nomi = {}, {}
    for sid, info in (franchise_info or {}).items():
        nomi[sid] = info.get("name") or sid
        for e in info.get("entries") or []:
            per_gioco[e.get("id")] = sid
    return per_gioco, nomi


def recommend(candidates: list[dict], taste: dict, loved: list[dict], franchise_info: dict | None = None,
              limit: int = 20, include_unowned: bool = True, include_played: bool = False) -> list[dict]:
    """I giochi più adatti, dal punteggio più alto, ognuno con i suoi motivi."""
    amati = {g.get("id"): g for g in loved if g.get("id") is not None}
    generi, decenni = _gusto(taste, "genres"), _gusto(taste, "decades")
    sviluppatori_amati: dict[str, dict] = {}
    for g in loved:
        nome = str(g.get("developer") or "").strip()
        if nome:
            sviluppatori_amati.setdefault(nome.lower(), g)  # il primo amato con quello sviluppatore, non l'ultimo
    serie_di, nomi_serie = _serie_di(franchise_info)
    serie_amate: dict[str, dict] = {}
    for i, g in amati.items():
        if i in serie_di:
            serie_amate.setdefault(serie_di[i], g)
    # ore spese nei giochi amati, per genere (per il motivo «Ami i JRPG: 42 ore»)
    ore_genere: dict[str, float] = {}
    for g in loved:
        for genere in g.get("genres") or []:
            ore_genere[genere] = ore_genere.get(genere, 0.0) + _ore(g)

    out = []
    for c in candidates:
        cid = c.get("id")
        if cid is None or cid in amati or _vietato(c, include_played):
            continue
        if not include_unowned and c.get("store") == "online":
            continue
        punti, motivi = 0.0, []

        suoi_generi = [g for g in (c.get("genres") or []) if generi.get(g)]
        if suoi_generi:
            punti += 2.0 * min(1.0, sum(generi[g] for g in suoi_generi))
            genere = max(suoi_generi, key=lambda g: generi[g])
            ore = ore_genere.get(genere, 0.0)
            motivi.append({"kind": "genere", "text": f"Ami i {genere}" + (f": {ore:.0f} ore" if ore >= 1 else "")})

        anno = c.get("year")
        if isinstance(anno, int) and anno > 0:
            decennio = str(anno // 10 * 10)
            if decenni.get(decennio):
                punti += 0.8 * decenni[decennio]
                motivi.append({"kind": "decennio", "text": f"Ti piacciono i giochi degli {ANNI.get(decennio, decennio)}"})

        sviluppatore = str(c.get("developer") or "").strip()
        if sviluppatore and sviluppatore.lower() in sviluppatori_amati:
            punti += 2.0
            gemello = sviluppatori_amati[sviluppatore.lower()]
            motivi.append({"kind": "sviluppatore", "text": f"Stesso sviluppatore di {gemello.get('title')}"})

        sid = serie_di.get(cid)
        if sid and sid in serie_amate:
            punti += 2.5
            motivi.append({"kind": "serie", "text": f"Fa parte di {nomi_serie[sid]}, come {serie_amate[sid].get('title')}"})

        try:
            voto = float(c.get("rating") or 0)
        except (TypeError, ValueError):
            voto = 0.0
        if voto > 0:
            punti += 1.5 * min(1.0, voto)
            motivi.append({"kind": "punteggio", "text": f"Voto {voto * 10:.1f}/10"})

        testo = _testo(c)
        vicino = max(loved, key=lambda g: fuzz.token_set_ratio(testo, _testo(g)), default=None)
        if vicino is not None:
            somiglianza = fuzz.token_set_ratio(testo, _testo(vicino)) / 100
            if somiglianza * 100 >= SIMILE:
                punti += 1.5 * somiglianza
                motivi.append({"kind": "simile_a", "text": f"Simile a {vicino.get('title')}"})

        if motivi:  # mai un consiglio senza motivo
            out.append({"id": cid, "title": c.get("title") or "", "score": round(punti, 2), "reasons": motivi})
    out.sort(key=lambda r: (-r["score"], r["title"]))
    return out[:max(0, limit)]
