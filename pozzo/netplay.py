"""Gioco con un amico (netplay): codice invito e argomenti per l'emulatore.

Il codice è "POZZO-" seguito da base64url di un JSON compatto con host, porta, gioco e scadenza.
Nessun server: chi ospita incolla il codice nella chat e l'amico lo incolla in Pozzo.
Il codice non è firmato: la sicurezza sta nella validazione rigida e nella conferma prima dell'avvio.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import re
import time

PORT = 55435
TTL = 3600  # secondi di validità del codice
PREFIX = "POZZO-"
MAX_PAYLOAD = 512  # tetto della parte dopo il prefisso; il codice si incolla a mano (i secrets di Discord ne vorrebbero 128)

_B64_RE = re.compile(r"[A-Za-z0-9_-]+")


def supported(emulator: str) -> bool:
    """Oggi solo RetroArch ha il netplay da riga di comando."""
    return emulator == "retroarch"


def _pack(info: dict) -> str:
    body = json.dumps(info, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")


def encode(info: dict) -> str:
    """Crea il codice invito; accorcia nick e core se il codice supera MAX_PAYLOAD caratteri."""
    d = dict(info)
    d.setdefault("v", 1)
    if "x" not in d:
        d["x"] = int(time.time() + TTL)  # secondi interi: il float occuperebbe ~8 caratteri in più
    part = _pack(d)
    if len(part) > MAX_PAYLOAD:
        # il nick più lungo che ci sta (la lunghezza cresce con il nick: si cerca con la bisezione)
        nick, lo, hi = d.get("n", ""), 0, len(d.get("n", ""))
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(_pack(dict(d, n=nick[:mid]))) <= MAX_PAYLOAD:
                lo = mid
            else:
                hi = mid - 1
        d["n"] = nick[:lo]
        part = _pack(d)
    if len(part) > MAX_PAYLOAD and d.get("c"):
        d["c"] = ""
        part = _pack(d)
    if len(part) > MAX_PAYLOAD:
        raise ValueError("Codice troppo lungo: gioco o cartella non compatibili con l'invito")
    return PREFIX + part


def decode(code: str, now: float | None = None) -> dict:
    """Legge un codice invito; ValueError con messaggio in italiano se non è valido o è scaduto."""
    if not isinstance(code, str):
        raise ValueError("Codice non valido")
    s = "".join(code.split())  # toglie spazi e a capo incollati
    if not s.startswith(PREFIX):
        raise ValueError("Codice non valido: manca il prefisso POZZO-")
    part = s[len(PREFIX):]
    if not part or not _B64_RE.fullmatch(part):
        raise ValueError("Codice non valido: caratteri non ammessi")
    try:
        raw = base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
        d = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError):
        raise ValueError("Codice non valido: dati corrotti") from None
    if not isinstance(d, dict):
        raise ValueError("Codice non valido: dati corrotti")

    v = d.get("v")
    if v != 1 or isinstance(v, bool):
        raise ValueError("Codice non valido: versione non supportata")
    x = d.get("x")
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        raise ValueError("Codice non valido: scadenza mancante")
    if x < (time.time() if now is None else now):
        raise ValueError("Codice scaduto: chiedi un nuovo invito")
    h = d.get("h")
    try:
        if not isinstance(h, str):
            raise ValueError
        ipaddress.ip_address(h)
    except ValueError:
        raise ValueError("Codice non valido: indirizzo IP non valido") from None
    p = d.get("p")
    if not isinstance(p, int) or isinstance(p, bool) or not 1 <= p <= 65535:
        raise ValueError("Codice non valido: porta non valida")
    k = d.get("k")
    if not isinstance(k, str) or not k:
        raise ValueError("Codice non valido: gioco mancante")
    if not isinstance(d.get("n"), str):
        raise ValueError("Codice non valido: nick non valido")
    return d


def args(mode: str, host: str = "", port: int = PORT, nick: str = "") -> list[str]:
    """Argomenti RetroArch per ospitare ("host") o unirsi ("join") a una partita."""
    if mode == "host":
        out = ["--host", "--port", str(port)]
    elif mode == "join":
        out = ["--connect", host, "--port", str(port)]
    else:
        raise ValueError(f"Modalità netplay sconosciuta: {mode}")
    if nick:
        out += ["--nick", nick]
    return out
