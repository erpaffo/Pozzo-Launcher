"""Webhook in uscita: POST JSON agli URL configurati in cfg.app["webhooks"] quando succede qualcosa in pozzo.

Config: lista di {"url": str, "events": [nome pubblico], "secret": str (opz.), "enabled": bool (default True)}.
Con un secret ogni richiesta porta X-Pozzo-Signature: sha256=<hmac del corpo>.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("pozzo.webhooks")

# nome sul bus interno -> nome pubblico mandato agli hook
EVENTS = {"game_started": "gioco_avviato", "game_stopped": "gioco_chiuso",
          "game_downloaded": "download_finito", "price_dropped": "prezzo_sceso"}
TIMEOUT = 5.0  # secondi


def _valid_url(url) -> bool:
    if not isinstance(url, str):
        return False
    parts = urlsplit(url.strip())
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _body(event: str, data) -> bytes:
    msg = {"event": event, "time": datetime.now(timezone.utc).isoformat(), "data": data}
    return json.dumps(msg, ensure_ascii=False, default=str).encode("utf-8")


def _headers(body: bytes, secret) -> dict:
    h = {"Content-Type": "application/json"}
    if secret:
        h["X-Pozzo-Signature"] = "sha256=" + hmac.new(str(secret).encode("utf-8"), body, hashlib.sha256).hexdigest()
    return h


def _post(url: str, body: bytes, secret):
    """Un tentativo e al massimo un ritentativo (solo su 5xx o errore di rete: un 4xx non cambia riprovando).
    Gli errori finiscono nel log, non bloccano l'app."""
    for attempt in (1, 2):
        try:
            r = httpx.post(url, content=body, headers=_headers(body, secret), timeout=TIMEOUT)
            if 200 <= r.status_code < 300:
                return
            err = f"HTTP {r.status_code}"
            if r.status_code < 500:
                log.warning("webhook %s: rifiutato: %s", url, err)
                return
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        log.warning("webhook %s: tentativo %d fallito: %s", url, attempt, err)


def _fire(cfg, public: str, payload):
    body = None
    for hook in cfg.app.get("webhooks") or []:
        if not isinstance(hook, dict) or not hook.get("enabled", True):
            continue
        if public not in (hook.get("events") or []):
            continue
        if not _valid_url(hook.get("url")):
            log.warning("webhook saltato, URL non valido: %r", hook.get("url"))
            continue
        if body is None:
            body = _body(public, payload)
        threading.Thread(target=_post, args=(hook["url"], body, hook.get("secret")), daemon=True).start()


def register(events_bus, cfg):
    """Si collega al bus eventi (extensions.Events): ogni evento in EVENTS parte verso gli hook interessati."""
    for internal, public in EVENTS.items():
        events_bus.on(internal, lambda payload, p=public: _fire(cfg, p, payload))


def send_test(url, secret=None) -> tuple[bool, str]:
    """Invio sincrono di prova (evento "test"). Ritorna (ok, codice HTTP oppure errore)."""
    if not _valid_url(url):
        return False, "URL non valido (serve http:// o https://)"
    body = _body("test", {})
    try:
        r = httpx.post(url, content=body, headers=_headers(body, secret), timeout=TIMEOUT)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    return 200 <= r.status_code < 300, str(r.status_code)
