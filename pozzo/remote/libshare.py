"""Libreria condivisa: il PC fa da server per famiglia e amici (altro Pozzo o browser), che sfogliano i giochi
CONDIVISI, li scarichino o li giochino nel browser.

Sicurezza (vedi anche remote/phone.py, PhoneGate):
  - niente e' condiviso finche' il proprietario non sceglie console intere o giochi singoli;
  - l'ospite ha un invito suo (nome, scadenza, una persona sola): del codice il PC conserva solo l'impronta SHA-256,
    il token dell'ospite (cookie HttpOnly o intestazione di Pozzo) pure; si revoca dalla lista degli inviti;
  - il cancello nega tutto cio' che non e' nell'elenco LIB_ALLOWED e controlla anche che il gioco sia condiviso;
  - i percorsi vengono SOLO dalla libreria del PC (file dei giochi condivisi), mai dalla richiesta; i link simbolici
    dentro le cartelle dei giochi non si seguono.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
import zipfile
from pathlib import Path

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # senza 0/O/1/I
CODE_LEN = 10
MAX_FAILS, FAIL_WINDOW = 10, 600  # codici sbagliati ammessi in 10 minuti per indirizzo; in totale 10 volte tanti (rete di sicurezza)
GLOBAL_FAILS = MAX_FAILS * 10
CHECK_EVERY = 1.0  # ogni quanto un flusso in corso ricontrolla che l'ospite non sia stato revocato o scaduto
LEASE = 30  # un download alla volta per ospite: si libera da solo se il flusso si ferma per 30 s
CHUNK = 256 * 1024
_ACTIVE: dict[str, tuple[str, float]] = {}  # ospite -> (token del flusso, ultimo movimento)
_LOCK = threading.Lock()


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ------------------------------------------------------------------ cosa si condivide
def conf(cfg) -> dict:
    d = cfg.app.get("libshare") or {}
    return {"platforms": [str(x) for x in d.get("platforms") or []], "games": [str(x) for x in d.get("games") or []],
            "internet": bool(d.get("internet"))}


def save_conf(cfg, **kw) -> dict:
    from .. import config as C
    c = {**conf(cfg), **kw}
    cfg.app["libshare"] = c
    C.save_settings(cfg, app={"libshare": c})
    return c


def shared(cfg, g: dict) -> bool:
    """Gioco condiviso: file della libreria (non di uno store) e console o gioco scelti dal proprietario. Default: no."""
    if not g or g.get("store") or not g.get("files"):
        return False
    c = conf(cfg)
    return g.get("platform") in c["platforms"] or g.get("key") in c["games"]


def ref(g: dict) -> str:
    """Identificativo stabile del gioco (il numero cambia a ogni ricostruzione della libreria)."""
    return hashlib.sha1(str(g["key"]).encode()).hexdigest()[:12]


def _link(p: Path) -> bool:
    """Link simbolico o giunzione NTFS (is_symlink() non vede le giunzioni su Windows)."""
    return p.is_symlink() or bool(getattr(os.path, "isjunction", lambda _: False)(p))


def entries(g: dict) -> list[tuple[Path, str]]:
    """[(file, nome nello zip)] dei file del gioco. Solo quelli elencati dalla libreria (le cartelle per intero),
    senza link simbolici: una cartella condivisa non puo' portare fuori file di altre parti del disco."""
    out, seen = [], set()

    def add(p: Path, arc: str):
        if arc not in seen:
            seen.add(arc)
            out.append((p, arc))
    for f in g.get("files") or []:
        p = Path(f)
        if _link(p):
            continue
        if p.is_file():
            add(p, p.name)
        elif p.is_dir():
            for root, dirs, names in os.walk(p):  # followlinks=False
                dirs[:] = sorted(d for d in dirs if not _link(Path(root) / d))
                for n in sorted(names):
                    fp = Path(root) / n
                    if not _link(fp) and fp.is_file():
                        add(fp, "/".join([p.name, *fp.relative_to(p).parts]))
    return out


def single_file(g: dict) -> Path | None:
    """Il file se il gioco e' una ROM sola (scaricabile con ripresa); altrimenti None (zip al volo)."""
    files = g.get("files") or []
    if len(files) == 1:
        p = Path(files[0])
        if p.is_file() and not _link(p):
            return p
    return None


# ------------------------------------------------------------------ inviti
def new_invite(hub, name: str, days: float = 30) -> tuple[dict, str]:
    """Crea un invito: ritorna (scheda, codice). Il codice si vede solo adesso: il PC ne tiene l'impronta."""
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
    days = min(365.0, max(0.04, float(days)))
    inv = {"id": secrets.token_hex(6), "name": (name or "Ospite").strip()[:40] or "Ospite", "hash": _sha(code),
           "created": time.time(), "exp": time.time() + days * 86400, "used": False, "device": ""}
    hub._save(lib_invites=[*hub.conf.get("lib_invites", []), inv])
    return inv, code


def _norm(code: str) -> str:
    return "".join(str(code).upper().split()).replace("-", "")


def pair(hub, code: str, name: str, ip: str = "") -> str:
    """Token dell'ospite; ValueError se il codice e' sbagliato, scaduto, gia' usato o ci sono stati troppi tentativi."""
    with hub.lock:
        now = time.time()
        hub.lib_fails[:] = [t for t in hub.lib_fails if now - t < FAIL_WINDOW]
        mine = [t for t in hub.lib_ip_fails.get(ip, []) if now - t < FAIL_WINDOW]
        for k in [k for k, v in hub.lib_ip_fails.items() if not v or now - v[-1] >= FAIL_WINDOW]:
            del hub.lib_ip_fails[k]  # niente crescita senza fine
        hub.lib_ip_fails[ip] = mine
        if len(mine) >= MAX_FAILS or len(hub.lib_fails) >= GLOBAL_FAILS:
            raise ValueError("Troppi tentativi sbagliati: riprova tra qualche minuto")
        h = _sha(_norm(code))
        invites = [dict(i) for i in hub.conf.get("lib_invites", [])]
        hit = None
        for i in invites:  # confronto a tempo costante su tutti
            if secrets.compare_digest(i["hash"], h):
                hit = i
        if not hit or hit["used"] or now > hit["exp"]:
            hub.lib_fails.append(now)
            mine.append(now)
            raise ValueError("Invito non valido, scaduto o gia' usato")
        token = secrets.token_urlsafe(32)
        dev = {"id": secrets.token_hex(6), "name": (name or hit["name"]).strip()[:40], "token": _sha(token),
               "created": now, "last": now, "kind": "lib", "exp": hit["exp"], "invite": hit["id"]}
        hit["used"], hit["device"] = True, dev["id"]
        hub._save(devices=[*hub.conf["devices"], dev], lib_invites=invites)
    return token


def revoke_invite(hub, iid: str) -> None:
    """Toglie l'invito e, se era stato usato, l'accesso dell'ospite (il suo token smette di funzionare subito)."""
    hub._save(lib_invites=[i for i in hub.conf.get("lib_invites", []) if i["id"] != iid],
              devices=[d for d in hub.conf["devices"] if d.get("invite") != iid])


def invites(hub) -> list[dict]:
    now = time.time()
    last = {d["id"]: d.get("last", 0) for d in hub.conf["devices"]}
    return [{"id": i["id"], "name": i["name"], "created": i["created"], "exp": i["exp"], "used": i["used"],
             "expired": now > i["exp"], "last": last.get(i.get("device"), 0)} for i in hub.conf.get("lib_invites", [])]


# ------------------------------------------------------------------ internet (UPnP)
def open_upnp(hub) -> dict:
    """Apre la porta del server sul router (solo se il proprietario lo chiede). {"on", "external", "error"}."""
    from .. import upnp
    close_upnp(hub)
    m = upnp.open_port(int(hub.conf["port"]), "TCP", "Pozzo Launcher (libreria)", lease_s=7 * 86400)
    if not m:
        return {"on": False, "external": "", "error": "upnp"}
    hub.lib_upnp = m
    return {"on": True, "external": f"{m['external_ip']}:{m['port']}" if m.get("external_ip") else "", "error": ""}


def close_upnp(hub) -> None:
    from .. import upnp
    m, hub.lib_upnp = hub.lib_upnp, None
    try:
        upnp.close_port(m)
    except Exception:  # router che non risponde: la mappatura scade da sola
        pass


# ------------------------------------------------------------------ download
def take(dev: str) -> str | None:
    """Un download alla volta per ospite: ritorna il token del flusso (None se ce n'e' gia' uno attivo)."""
    with _LOCK:
        cur = _ACTIVE.get(dev)
        if cur and time.time() - cur[1] < LEASE:
            return None
        tok = secrets.token_hex(8)
        _ACTIVE[dev] = (tok, time.time())
        return tok


def _touch(dev: str, tok: str):
    with _LOCK:
        if (_ACTIVE.get(dev) or ("",))[0] == tok:
            _ACTIVE[dev] = (tok, time.time())


def _free(dev: str, tok: str):
    with _LOCK:  # un flusso scaduto non libera il turno di quello nuovo
        if (_ACTIVE.get(dev) or ("",))[0] == tok:
            del _ACTIVE[dev]


def parse_range(h: str | None, size: int) -> tuple[int, int] | None:
    """(inizio, fine) inclusi per «bytes=a-b»; None se assente o non gestito (si manda tutto); ValueError se fuori file."""
    if not h or not h.startswith("bytes=") or "," in h:
        return None
    a, _, b = h[6:].strip().partition("-")
    try:
        if a == "":
            n = int(b)
            if n <= 0:
                return None
            start, end = max(0, size - n), size - 1
        else:
            start, end = int(a), min(int(b) if b else size - 1, size - 1)
    except ValueError:
        return None
    if start < 0 or start > end or start >= size:
        raise ValueError("range")
    return start, end


def file_chunks(path: Path, start: int, end: int, dev: str, tok: str, alive=lambda: True):
    left, nxt = end - start + 1, time.time() + CHECK_EVERY
    try:
        with open(path, "rb") as f:
            f.seek(start)
            while left > 0 and (b := f.read(min(CHUNK, left))):
                left -= len(b)
                _touch(dev, tok)
                if time.time() >= nxt:
                    if not alive():  # ospite revocato o scaduto durante il download
                        return
                    nxt = time.time() + CHECK_EVERY
                yield b
    finally:
        _free(dev, tok)


class _Sink:
    """Destinazione non riavvolgibile per zipfile: accumula i byte e li consegna a blocchi."""

    def __init__(self):
        self.buf, self.n = bytearray(), 0

    def write(self, b):
        self.buf += b
        self.n += len(b)
        return len(b)

    def tell(self):
        return self.n

    def flush(self):
        pass

    def take(self) -> bytes:
        d = bytes(self.buf)
        self.buf.clear()
        return d


def zip_chunks(items: list[tuple[Path, str]], dev: str, tok: str, alive=lambda: True):
    """Zip senza compressione (ZIP_STORED) prodotto mentre si scarica: niente file temporaneo, ma nemmeno ripresa."""
    sink, nxt = _Sink(), time.time() + CHECK_EVERY
    try:
        with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
            for p, arc in items:
                try:
                    st = p.stat()
                    f = open(p, "rb")
                except OSError:
                    continue
                dt = time.localtime(st.st_mtime)[:6]
                zi = zipfile.ZipInfo(arc, dt if dt[0] >= 1980 else (1980, 1, 1, 0, 0, 0))
                zi.compress_type, zi.external_attr = zipfile.ZIP_STORED, 0o644 << 16
                with f, z.open(zi, "w", force_zip64=True) as out:
                    while b := f.read(CHUNK):
                        out.write(b)
                        _touch(dev, tok)
                        if time.time() >= nxt:
                            if not alive():
                                return
                            nxt = time.time() + CHECK_EVERY
                        if sink.buf:
                            yield sink.take()
        yield sink.take()
    finally:
        _free(dev, tok)
