"""Impostazioni e account di ogni profilo, in <cartella dei dati>/profiles/<id>.json.

Qui stanno le cose personali: Discord (presenza e voce), Spotify, RetroAchievements, Epic e GOG, Steam (chiave API e
id), chiavi della lista desideri, token GitHub dei port, tema ed esperienza, cartelle ROM proprie (roms_extra). Il
resto resta in settings.json (percorsi, emulatori, store). get() legge dal profilo attivo: quello del dispositivo
(ContextVar impostata dal middleware del server dal cookie gs_profile, vedi override()) oppure cfg.app["profile"].

Migrazione: al primo avvio il profilo principale copia i valori globali di prima (i globali restano, non si cancellano).
Le chiavi aggiunte dopo (tema, Steam...) si copiano una sola volta anche se il file c'e' gia' (campo "_done").
Un profilo nuovo parte vuoto: non eredita gli account del principale (tema ed esperienza si', sono solo gusti). Finche' un profilo non ha un file (config.toml
senza cartella, test) si legge il globale, come prima.

Il PIN e' solo un blocco per chi usa il PC: chi ha accesso ai file del profilo ne vede gli account.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from . import config as C

# dati di profilo (campi di profiles/<id>.json) e dove stavano prima: app, stores, oppure la cache (kv)
KEYS = ("discord", "spotify", "discord_voice", "retroachievements", "epic", "gog",
        "steam", "wishlist", "github_token", "theme", "experience", "roms_extra")
KV_KEYS = ("epic", "gog")  # token salvati in cache.db (kv "auth:epic", "auth:gog")
OPEN_KEYS = ("theme", "experience")  # non segrete: un profilo senza scelta propria usa quella globale
# chiavi che il profilo-UI puo' leggere e scrivere (mai segreti)
SETTINGS_KEYS = ("theme", "experience")
PIN_ITERATIONS = 200_000
PIN_TRIES, PIN_WAIT = 5, 30  # dopo 5 PIN sbagliati si aspetta 30 secondi

_LOCK = threading.Lock()  # lettura e scrittura del file di un profilo, un thread alla volta
_current: ContextVar[str | None] = ContextVar("gs_profile", default=None)  # profilo del dispositivo / del lavoro in corso


@contextmanager
def override(pid: str | None):
    """Per il codice dentro il `with` il profilo attivo e' `pid` (None = niente cambia). Serve al middleware (cookie
    del dispositivo) e ai lavori che girano per ogni profilo (aggiornamento degli store)."""
    tok = _current.set(pid) if pid else None
    try:
        yield
    finally:
        if tok is not None:
            _current.reset(tok)


def active_override() -> str | None:
    """Il profilo imposto a questo contesto (cookie del dispositivo), None se non c'e'."""
    return _current.get()


def active(cfg) -> str:
    return _current.get() or cfg.app.get("profile") or "default"


def profile_ids(cfg) -> list[str]:
    """Id di tutti i profili (il principale per primo)."""
    return ["default"] + [p["id"] for p in cfg.app.get("profiles") or [] if p.get("id") and p["id"] != "default"]


def values(cfg, key: str) -> dict:
    """{profilo: valore} di una chiave, per chi guarda tutti i profili insieme (cartelle ROM, store)."""
    out = {}
    for pid in profile_ids(cfg):
        with override(pid):
            v = get(cfg, key)
        if v is not None:
            out[pid] = v
    return out


def path(cfg, pid: str) -> Path | None:
    """File del profilo, nella cartella di settings.json. None se il config non ha un percorso (test)."""
    if getattr(cfg, "config_path", None) is None:
        return None
    return C.settings_path(cfg).parent / "profiles" / f"{pid}.json"


def _legacy(cfg, key: str):
    """Valore globale di prima (settings.json o cache.db)."""
    if key in KV_KEYS:
        db = Path(cfg.cache) / "cache.db"
        if not db.exists():
            return None
        con = sqlite3.connect(db)
        try:
            r = con.execute("SELECT v FROM kv WHERE k=?", (f"auth:{key}",)).fetchone()
        finally:
            con.close()
        return json.loads(r[0]) if r else None
    if key == "steam":
        return {k: v for k, v in (getattr(cfg, "stores", {}) or {}).get("steam", {}).items() if k in ("api_key", "steamid")} or None
    return cfg.app.get(key)


def _load(p: Path) -> dict:
    """Legge il file del profilo. Se e' illeggibile (bloccato) alza l'errore: ripartire da {} cancellerebbe gli account.
    Un JSON rotto va in <nome>.rotto.json, come settings.json."""
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        os.replace(p, p.with_suffix(".rotto.json"))
        return {}


def _save(p: Path, data: dict):
    tmp = p.with_suffix(".tmp")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    C._replace(tmp, p)


def get(cfg, key: str, default=None):
    """Valore di `key` nel profilo attivo."""
    pid = active(cfg)
    p = path(cfg, pid)
    if p is None:  # senza cartella dati (test): stessa memoria di set()
        v = cfg.app.get(key)
        if key not in cfg.app and pid == "default":
            v = _legacy(cfg, key)
    elif not p.exists():  # prima del primo avvio: globale per il principale, vuoto per gli altri
        v = _legacy(cfg, key) if pid == "default" else None
    else:
        with _LOCK:
            try:
                v = _load(p).get(key)
            except OSError:
                v = None
    if v is None and key in OPEN_KEYS and pid != "default":
        v = cfg.app.get(key)
    return default if v is None else v


def set(cfg, key: str, value):
    """Scrive `key` nel profilo attivo (None = toglie la voce)."""
    pid = active(cfg)
    p = path(cfg, pid)
    if p is None:  # senza cartella dati (test): resta solo in memoria, come le altre impostazioni
        cfg.app[key] = value
        return
    with _LOCK:
        data = _load(p)  # se il file non si legge, l'errore si ferma qui (niente riscrittura da zero)
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
        _save(p, data)


def put(cfg, key: str, value, mirror: bool = False):
    """set() + (mirror) copia globale in settings.json quando il profilo attivo e' il principale: le voci che la
    sincronizzazione delle impostazioni o le versioni precedenti leggono ancora dal globale."""
    set(cfg, key, value)
    if mirror and active(cfg) == "default":
        C.save_settings(cfg, app={key: value})


def migrate(cfg):
    """Primo avvio: il profilo principale copia i valori globali. Una volta sola: se il file c'e' non si tocca."""
    p = path(cfg, "default")
    if p is None:
        return
    data = _load(p) if p.exists() else {}
    done = {*(data.get("_done") or (KEYS[:6] if p.exists() else ()))}  # file di prima di "_done": le prime sei chiavi erano gia' migrate
    todo = [k for k in KEYS if k not in done and (not p.exists() or k not in data)]
    if p.exists() and not todo:
        return
    for k in todo:
        v = _legacy(cfg, k)
        if v not in (None, "", {}):
            data[k] = v
    # file nuovo: tutte le chiavi sono migrate; file esistente (versioni precedenti): solo quelle mai viste
    data["_done"] = sorted(done | {*KEYS})
    _save(p, data)


# ---------------------------------------------------------------- PIN

def hash_pin(pin: str) -> str:
    salt = os.urandom(16).hex()
    return f"{salt}${hashlib.pbkdf2_hmac('sha256', pin.encode(), salt.encode(), PIN_ITERATIONS).hex()}"


def check_pin(stored: str, pin: str) -> bool:
    salt, _, digest = stored.partition("$")
    got = hashlib.pbkdf2_hmac("sha256", str(pin).encode(), salt.encode(), PIN_ITERATIONS).hex()
    return hmac.compare_digest(got, digest)


class PinLimiter:
    """Tentativi di PIN per profilo: dopo PIN_TRIES errori si aspetta PIN_WAIT secondi."""

    def __init__(self, clock=time.monotonic):
        self.clock, self.fails, self.until = clock, {}, {}

    def wait(self, pid: str) -> int:
        """Secondi da aspettare prima del prossimo tentativo (0 = si puo' provare)."""
        return max(0, int(self.until.get(pid, 0) - self.clock() + 0.999))

    def fail(self, pid: str):
        self.fails[pid] = self.fails.get(pid, 0) + 1
        if self.fails[pid] >= PIN_TRIES:
            self.fails.pop(pid)
            self.until[pid] = self.clock() + PIN_WAIT

    def ok(self, pid: str):
        self.fails.pop(pid, None)
        self.until.pop(pid, None)
