"""Risolutori di link: da un indirizzo (accorciatore, pagina di un host) a quello diretto. Si registrano con `register`.

Un risolutore restituisce il nuovo link (o "" se non sa che farne), oppure (link, nome) per dire chi l'ha risolto
(i servizi debrid: il nome finisce nella vista del task).

Ogni risolutore ha anche un'etichetta: è il passaggio che il download manager mostra mentre aspetta («Salto la
pubblicità (ouo.io)», «Cerco il file su datanodes.to»). Così si vede a che punto è, e dove si è fermato se va storto.
"""
from __future__ import annotations

import threading
import time
from typing import Callable
from urllib.parse import urlsplit

# (funzione, etichetta del passaggio: testo fisso oppure funzione url -> testo, "" per non mostrarlo)
_tl = threading.local()  # note e callback del resolve() in corso su questo thread (i risolutori girano in thread)
_FNS: list[tuple[Callable[[str], str | tuple[str, str]], object]] = []


def register(fn: Callable[[str], str | tuple[str, str]], label: object = "") -> None:
    _FNS.append((fn, label))


def note(text: str) -> None:
    """Un risolutore che non ha risolto dice perche' («Debrid-Link: host non supportato»): resta visibile nelle fasi
    successive e nell'errore finale. Fuori da resolve() non fa nulla."""
    notes = getattr(_tl, "notes", None)
    if notes is not None and text and text not in notes:
        notes.append(text)
        _log(text, "warn")
        if _tl.on_phase:
            _tl.on_phase("; ".join(notes))


def phase(name: str) -> None:
    """Passaggio lungo dentro un risolutore (es. browser nascosto); fuori da resolve() non fa nulla."""
    if getattr(_tl, "on_phase", None):
        _tl.on_phase(_show(name))
    _log(name)


def log(msg: str, level: str = "info") -> None:
    """Riga nel registro del download senza cambiare la fase mostrata (dettagli del browser nascosto)."""
    _log(msg, level)


def _log(msg: str, level: str = "info") -> None:
    if getattr(_tl, "on_log", None):
        _tl.on_log(msg, level)


def _show(name: str) -> str:
    notes = getattr(_tl, "notes", None)
    return f"{name} — {'; '.join(notes)}" if notes else name


def resolve(url: str, on_phase: Callable[[str], None] | None = None, notes: list | None = None,
            on_log: Callable[[str, str], None] | None = None) -> tuple[str, str]:
    """(link, chi l'ha risolto). Bloccante (puo' fare rete): da chiamare in un thread. Un risolutore che fallisce
    non ferma gli altri. `on_phase` riceve il nome di ogni passaggio prima che inizi; `notes` raccoglie i motivi
    dei risolutori che non hanno risolto (vedi `note`); `on_log(testo, livello)` riceve passaggi, note ed errori
    dei risolutori per il registro del download."""
    _tl.notes, _tl.on_phase, _tl.on_log = [] if notes is None else notes, on_phase, on_log
    try:
        return _run(url, on_phase)
    finally:
        _tl.notes = _tl.on_phase = _tl.on_log = None


def _run(url: str, on_phase) -> tuple[str, str]:
    by = ""
    for fn, label in _FNS:
        name = ""
        if on_phase and label:
            try:
                name = label(url) if callable(label) else str(label)
            except Exception:  # noqa: BLE001 - un'etichetta rotta non ferma la risoluzione
                name = ""
            if name:
                on_phase(_show(name))
                _log(name)
        t0 = time.time()
        try:
            r = fn(url)
        except Exception as e:  # noqa: BLE001 - il link originale resta valido
            _log(f"{label if isinstance(label, str) and label else getattr(fn, '__name__', 'risolutore')}: {type(e).__name__}: {e}", "warn")
            continue
        r, who = r if isinstance(r, tuple) else (r, "")
        took = time.time() - t0
        if r and r != url:
            _log(f"  → {urlsplit(r).hostname or r} ({took:.1f} s)" + (f", sbloccato da {who}" if who else ""))
        elif took >= 1:
            _log(f"  → nessun cambiamento ({took:.1f} s)")
        if r:
            url, by = r, who or by
    return url, by
