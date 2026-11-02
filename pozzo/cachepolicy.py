"""Scadenze della cache delle risposte delle fonti: una sola tabella, (TTL positivo, TTL negativo) in secondi.

La chiave di cache e' l'URL con i parametri (o il titolo normalizzato), mai il profilo: piu' profili
condividono la stessa copia. "Negativo" = 404 o risposta senza risultati: dura meno, perche' un gioco
mancante oggi puo' comparire nella fonte domani, ma non va richiesto a ogni scansione.
"""

DAY = 86400

TTL = {
    "rawg": (30 * DAY, 7 * DAY),          # metadati di un gioco: cambiano di rado
    "igdb": (30 * DAY, 7 * DAY),
    "screenscraper": (30 * DAY, 7 * DAY),  # la quota giornaliera e' scarsa: meglio non rifare mai la stessa domanda
    "thegamesdb": (30 * DAY, 7 * DAY),
    "arcadedb": (30 * DAY, 7 * DAY),
    "wikipedia": (90 * DAY, 7 * DAY),     # voci quasi statiche
    "hltb": (180 * DAY, 30 * DAY),        # durate: stabili; HowLongToBeat limita a ~50 ricerche al minuto
}
DEFAULT = (30 * DAY, 7 * DAY)
KV_SOURCES = {"hltb": "hltb:"}  # fonti salvate nella tabella kv di cache.db (non in http_cache): prefisso delle chiavi


def ttls(source: str) -> tuple[float, float]:
    return TTL.get(source, DEFAULT)
