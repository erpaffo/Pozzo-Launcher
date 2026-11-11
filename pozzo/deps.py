"""Messaggio unico per le dipendenze Python mancanti all'avvio (rich, fastapi, uvicorn...).

Senza, `python -m pozzo app` finiva con un traceback di ModuleNotFoundError: qui si dice quale
modulo manca e quale comando eseguire con l'interprete giusto. Solo ASCII: il messaggio arriva
anche su console con codepage diverse da UTF-8.
"""

from __future__ import annotations

import sys


def hint(e: ModuleNotFoundError) -> str:
    return (f'Manca il modulo Python "{e.name}", serve per avviare Pozzo.\n'
            f"Installa le dipendenze con:\n"
            f"  {sys.executable} -m pip install -r requirements.txt\n"
            f"Pozzo richiede Python 3.12: se l'interprete attuale e' un'altra versione, usa l'ambiente "
            f"del repository (.venv\\Scripts\\python -m pozzo app).")

