"""Errori non previsti: dire subito che cosa e' successo invece di «Internal Server Error».

Un'eccezione che nessuno ha gestito diventa una risposta JSON con la stessa forma degli altri errori
({"detail", "code"}) piu' `error` (il tipo) e `where` (il punto del codice): `detail` e' il testo per la persona, con la
causa probabile quando la si riconosce, `error` e `where` servono per segnalare o correggere il problema.
"""

from __future__ import annotations

import errno
import sqlite3
import traceback
from pathlib import Path

import httpx

MAX = 300  # caratteri della causa tecnica: un messaggio di rete o di SQL puo' essere lunghissimo


def where(exc: BaseException) -> str:
    """Ultimo punto del codice di Pozzo (o di un'estensione) nella traccia, es. «pozzo/app/routes/manual.py:81 (apply)»."""
    frames = traceback.extract_tb(exc.__traceback__)
    for fr in reversed(frames):
        parts = Path(fr.filename).parts
        at = max((i for i, p in enumerate(parts[:-1]) if p in ("pozzo", "extensions")), default=None)
        if at is not None:
            return f"{'/'.join(parts[at:])}:{fr.lineno} ({fr.name})"
    # nessun punto riconoscibile (libreria esterna): almeno l'ultimo della traccia
    return f"{Path(frames[-1].filename).name}:{frames[-1].lineno} ({frames[-1].name})" if frames else ""


def explain(exc: BaseException) -> tuple[int, str]:
    """(codice HTTP, testo per la persona). La causa tecnica e' sempre in coda, tra parentesi."""
    tech = f"{type(exc).__name__}: {exc}"[:MAX]
    low = str(exc).lower()
    if isinstance(exc, sqlite3.OperationalError):
        if "locked" in low or "busy" in low:
            return 503, f"Il database e' occupato da un altro processo: riprova tra poco ({tech})"
        if "no such column" in low or "no column named" in low or "no such table" in low:
            return 500, f"Il database e' di una versione diversa dall'app: ricostruisci la libreria ({tech})"
        return 500, f"Errore del database ({tech})"
    if isinstance(exc, sqlite3.DatabaseError):
        return 500, f"Database danneggiato o illeggibile ({tech})"
    if isinstance(exc, PermissionError):
        return 500, f"Permesso negato su «{exc.filename or '?'}»: chiudi il programma che lo usa o controlla i permessi ({tech})"
    if isinstance(exc, FileNotFoundError):
        return 500, f"File o cartella non trovati: «{exc.filename or '?'}» (disco scollegato o file spostato?) ({tech})"
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return 500, f"Spazio su disco esaurito ({tech})"
    if isinstance(exc, httpx.TimeoutException):
        return 504, f"Il server non ha risposto in tempo ({tech})"
    if isinstance(exc, httpx.HTTPError):  # connessione rifiutata, DNS, TLS, risposta interrotta
        return 502, f"Rete non raggiungibile o server che non risponde ({tech})"
    return 500, f"Errore imprevisto ({tech})"
