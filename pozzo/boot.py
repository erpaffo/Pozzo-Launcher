"""Registro delle fasi di avvio, letto da GET /api/boot per la schermata di caricamento.

Il registro di avvio è BOOT (fasi fisse, in quest'ordine). Un lavoro a più passi (per esempio
l'installazione di un emulatore) usa un registro suo con `registro("install-<id>")`.
Thread-safe: le fasi si aggiornano da thread diversi.

    with BOOT.phase("library", "Libreria"):   # done a fine blocco, fail se solleva un'eccezione
        ...
    BOOT.start("x", "Etichetta"); BOOT.done("x"); BOOT.fail("x", "motivo")
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

from . import applog

PHASES = [("server", "Avvio del server"), ("config", "Lettura impostazioni"), ("library", "Libreria"),
          ("stores", "Store"), ("extensions", "Estensioni")]


class Registro:
    def __init__(self, fasi=()):
        self._lock = threading.Lock()
        self._iniziali = list(fasi)
        self._fasi: dict[str, dict] = {}
        self.reset()

    def reset(self):
        """Torna allo stato iniziale: tutte le fasi in attesa."""
        with self._lock:
            self._fasi = {i: {"id": i, "label": l, "state": "pending", "msg": ""} for i, l in self._iniziali}

    def _set(self, id: str, state: str, label: str | None = None, msg: str = ""):
        with self._lock:
            f = self._fasi.setdefault(id, {"id": id, "label": id, "state": "pending", "msg": ""})
            if label:
                f["label"] = label
            f["state"], f["msg"] = state, msg

    def start(self, id: str, label: str | None = None):
        self._set(id, "running", label)

    def done(self, id: str):
        self._set(id, "done")

    def fail(self, id: str, msg: str = ""):
        self._set(id, "error", msg=msg)
        applog.write("avvio", f"{id}: {msg}")

    @contextmanager
    def phase(self, id: str, label: str | None = None):
        self.start(id, label)
        try:
            yield
        except Exception as e:
            self.fail(id, str(e) or type(e).__name__)
            raise
        else:
            self.done(id)

    def snapshot(self) -> dict:
        """{"ready", "progress" (0..1), "steps"}: ready quando ogni fase è done o error."""
        with self._lock:
            steps = [{"id": f["id"], "label": f["label"], "state": f["state"]} for f in self._fasi.values()]
        fatte = sum(1 for s in steps if s["state"] in ("done", "error"))
        n = len(steps)
        return {"ready": fatte == n, "progress": round(fatte / n, 3) if n else 1.0, "steps": steps}


BOOT = Registro(PHASES)

_registri: dict[str, Registro] = {}
_registri_lock = threading.Lock()


def registro(nome: str) -> Registro:
    """Registro di un lavoro a più passi, creato alla prima richiesta (per esempio "install-duckstation")."""
    with _registri_lock:
        return _registri.setdefault(nome, Registro())
