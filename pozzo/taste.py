"""Gusto personale di un profilo: generi, decenni e sviluppatori preferiti, dalle sole righe del profilo.

Funzioni pure: ricevono i giochi della libreria condivisa (`games`: id -> record con title, genres, year, developer)
e le righe personali (`rows`: id -> riga di user_games con playtime in secondi, my_rating 1-5, status, favorite) e
restituiscono solo dict. Non leggono database, non conoscono i profili, non copiano metadati.

La formula, per ogni gioco che ha almeno un segnale (ore, voto, stato o preferito):

    ore   = playtime / 3600
    tempo = 3 * log(1 + ore)            # rendimenti decrescenti: 500 ore valgono 18,7; 20 ore valgono 9,1
    voto  = (my_rating - 3) / 2         # -1 … +1 (0 se non votato): 5 stelle pesano, 1 stella toglie
    stato = done 1.4 · playing 1.0 · backlog 0.5 · dropped 0.2 · altro 0.8
    peso  = tempo * (1 + 0.3 * voto) + 2 * voto + stato + (1.0 se preferito)

Il peso va a ogni genere del gioco, al suo decennio (anno // 10 * 10) e al suo sviluppatore; i punteggi sono la
somma dei pesi, dal più alto. Un gioco abbandonato e votato male puo' pesare sotto zero: toglie invece di
aggiungere. Con pochi giochi (samples < MIN_SAMPLES) la classifica e' solo indicativa: `reliable` lo dice.
"""

from __future__ import annotations

from math import log1p

MIN_SAMPLES = 5  # sotto questa soglia la classifica si mostra, ma marcata come poco affidabile
STATO = {"done": 1.4, "playing": 1.0, "backlog": 0.5, "dropped": 0.2}
STATO_DEFAULT = 0.8


def _peso(row: dict) -> float | None:
    """Quanto conta un gioco per il gusto: None se la riga non dice niente (mai aperto, mai votato)."""
    ore = max(0.0, float(row.get("playtime") or 0)) / 3600
    voto_5 = row.get("my_rating")
    try:
        voto = (float(voto_5) - 3) / 2 if voto_5 else 0.0
    except (TypeError, ValueError):
        voto = 0.0
    voto = max(-1.0, min(1.0, voto))
    stato = row.get("status") or ""
    preferito = bool(row.get("favorite"))
    if not ore and not voto_5 and not stato and not preferito:
        return None
    peso = 3 * log1p(ore) * (1 + 0.3 * voto) + 2 * voto + STATO.get(stato, STATO_DEFAULT) + (1.0 if preferito else 0)
    return round(peso, 3)


def _classifica(punteggi: dict) -> list[tuple]:
    return [(k, round(v, 2)) for k, v in sorted(punteggi.items(), key=lambda kv: (-kv[1], str(kv[0])))]


def profile(games: dict, rows: dict) -> dict:
    """{"genres", "decades", "developers", "total_hours", "samples", "reliable", "confidence"}.

    `genres`/`decades`/`developers` sono [(nome, punteggio)] dal punteggio più alto; `confidence` va da 0 a 1 e
    cresce con il numero di giochi che hanno lasciato un segnale.
    """
    generi: dict[str, float] = {}
    decenni: dict[str, float] = {}
    sviluppatori: dict[str, float] = {}
    ore_totali = 0.0
    campioni = 0
    for gid, row in rows.items():
        game = games.get(gid) or games.get(str(gid))
        if not game:
            continue
        ore_totali += max(0.0, float(row.get("playtime") or 0)) / 3600
        peso = _peso(row)
        if peso is None:
            continue
        campioni += 1
        for genere in game.get("genres") or []:
            nome = str(genere or "").strip()
            if nome:
                generi[nome] = generi.get(nome, 0.0) + peso
        anno = game.get("year")
        if isinstance(anno, int) and anno > 0:
            decennio = str(anno // 10 * 10)
            decenni[decennio] = decenni.get(decennio, 0.0) + peso
        sviluppo = str(game.get("developer") or "").strip()
        if sviluppo:
            sviluppatori[sviluppo] = sviluppatori.get(sviluppo, 0.0) + peso
    return {"genres": _classifica(generi), "decades": _classifica(decenni), "developers": _classifica(sviluppatori),
            "total_hours": round(ore_totali, 1), "samples": campioni,
            "reliable": campioni >= MIN_SAMPLES, "confidence": round(min(1.0, campioni / MIN_SAMPLES), 2)}
