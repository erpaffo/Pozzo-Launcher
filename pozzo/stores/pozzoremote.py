"""Pozzo remoto: la libreria condivisa di un altro Pozzo (famiglia, amici) come store. I giochi condivisi compaiono
come posseduti da installare; «Installa» li scarica dal PC remoto.

Sicurezza: l'abbinamento usa il codice dell'invito e salva il token e l'impronta SHA-256 del certificato del server
(TOFU: la prima volta ci si fida, poi il certificato deve essere sempre quello). OGNI connessione, anche quelle dei
download, controlla l'impronta PRIMA di mandare il token: se non combacia si rifiuta e non parte nulla. Il motore dei
download (downloads/engines/http.py) usa un client httpx condiviso con la verifica TLS normale, quindi qui il
download e' un piccolo scaricatore proprio (con ripresa per le ROM sole) che fissa l'impronta a ogni connessione.
Quello che arriva dal server si tratta come ostile: le copertine passano dal controllo dei primi byte, gli zip
dall'estrazione sicura di downloads/extract.py (niente «..», tetto alle dimensioni) e i nomi dei file si ripuliscono.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
import re
import shutil
import ssl
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from .base import StoreGame, StoreProvider

INSTALLED_KEY = "pozzoremote:installed"  # kv: id -> {title, exe, args, cwd, dir}
LIST_KEY = "pozzoremote:list:"  # kv: ultimo elenco del server (visibile anche se spento)
PORT = 8766
MAX_COVER = 8 * 1024 * 1024
_RUNS: dict[str, dict] = {}
_LOCK = threading.Lock()


class PinError(RuntimeError):
    """Il certificato del server non e' quello fissato all'abbinamento."""


def norm_url(raw: str) -> str:
    """«host», «host:porta» o «https://host:porta» -> https://host:porta (solo https, nessun percorso)."""
    raw = (raw or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    u = urlparse(raw)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment:
        raise ValueError("Indirizzo non valido: serve https://indirizzo:porta")
    host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
    return f"https://{host}:{u.port or PORT}"


def open_pinned(url: str, fp: str | None, method: str, path: str, token: str | None = None, body: dict | None = None,
                headers: dict | None = None, timeout: float = 60):
    """(connessione, risposta, impronta). Con fp=None (solo l'abbinamento) ci si fida del certificato che arriva."""
    u = urlparse(url)
    ctx = ssl.create_default_context()
    # shortcut: nessuna catena di fiducia (certificato del server autofirmato/di una CA locale): si verifica l'impronta
    # qui sotto, prima di mandare qualsiasi cosa. Da rivedere se i server avranno certificati pubblici.
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    conn = http.client.HTTPSConnection(u.hostname, u.port or PORT, context=ctx, timeout=timeout)
    try:
        conn.connect()
        got = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
        if fp is not None and got != fp:
            raise PinError("Il certificato del server e' cambiato: rifiuto di collegarmi (rifai l'abbinamento solo se ti fidi)")
        h = {"Accept": "application/json", **(headers or {})}
        data = None
        if body is not None:
            data, h["Content-Type"] = json.dumps(body), "application/json"
        if token:
            h["Cookie"] = f"gs_phone={token}"
        conn.request(method, path, data, h)
        return conn, conn.getresponse(), got
    except BaseException:
        conn.close()
        raise


def call(server: dict, method: str, path: str, body: dict | None = None) -> dict:
    conn, r, _ = open_pinned(server["url"], server["fp"], method, path, server["token"], body)
    try:
        raw = r.read(64 * 1024 * 1024)
        if r.status >= 400:
            try:
                msg = json.loads(raw).get("detail")
            except ValueError:
                msg = None
            raise RuntimeError(msg or f"HTTP {r.status}")
        return json.loads(raw or b"{}")
    finally:
        conn.close()


def pair(raw_url: str, code: str, name: str) -> dict:
    """Abbina questo Pozzo al server: ritorna {url, token, fp}. L'impronta e' quella vista adesso (TOFU)."""
    url = norm_url(raw_url)
    conn, r, fp = open_pinned(url, None, "POST", "/l/api/pair", None, {"code": code, "name": name, "client": True})
    try:
        data = json.loads(r.read(1 << 20) or b"{}")
        if r.status >= 400 or not data.get("token"):
            raise RuntimeError(data.get("detail") or f"HTTP {r.status}")
        return {"url": url, "token": data["token"], "fp": fp}
    finally:
        conn.close()


def servers(settings: dict) -> list[dict]:
    return [s for s in settings.get("servers") or [] if s.get("url") and s.get("token") and s.get("fp")]


def dest_root(settings: dict) -> Path:
    return Path(settings.get("dest") or Path.home() / "Games" / "Pozzo" / "Remoto")


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", Path(str(name)).name).strip(" .") or "gioco"


def list_remote(server: dict) -> list[dict]:
    # ref finisce in nomi di file e cartelle locali: un server malevolo non deve poterci mettere «..» o separatori
    return [g for g in call(server, "GET", "/api/lib-share/list")["games"] if re.fullmatch(r"[0-9a-f]{12}", str(g.get("ref", "")))]


def fetch_cover(server: dict, g: dict, folder: Path) -> str:
    """Copertina in locale (controllata dai primi byte al momento dell'uso); "" se non c'e' o non scarica."""
    if not g.get("cover") or not str(g["cover"]).startswith("/api/lib-share/cover/"):
        return ""
    dest = folder / f"{server['id']}_{g['ref']}"
    for old in folder.glob(dest.name + ".*"):
        return str(old)
    try:
        conn, r, _ = open_pinned(server["url"], server["fp"], "GET", f"/api/lib-share/cover/{int(g['id'])}", server["token"])
        try:
            data = r.read(MAX_COVER + 1) if r.status == 200 else b""
        finally:
            conn.close()
    except (OSError, PinError, ValueError):
        return ""
    from ..net import sniff
    ext = sniff(data[:16]) if 0 < len(data) <= MAX_COVER else None
    if not ext or ext in ("mp4", "webm"):
        return ""
    folder.mkdir(parents=True, exist_ok=True)
    out = dest.with_suffix("." + ext)
    out.write_bytes(data)
    return str(out)


class PozzoRemote(StoreProvider):
    id = "pozzoremote"
    name = "Pozzo remoto"

    def detected(self) -> bool:
        return bool(servers(self.settings))

    def account(self) -> dict:
        s = self.settings
        # mai il token: solo nome, indirizzo e impronta (da confrontare a voce col proprietario)
        return {"connected": self.detected(), "dest": s.get("dest") or "",
                "servers": [{"id": x["id"], "name": x.get("name") or x["url"], "url": x["url"], "fp": x["fp"][:16]}
                            for x in servers(s)]}

    async def fetch(self) -> list[StoreGame]:
        done = self.cache.kv_get(INSTALLED_KEY) or {}
        games: list[StoreGame] = []
        seen = set()
        for sv in servers(self.settings):
            key = LIST_KEY + sv["id"]
            try:
                rows = await asyncio.to_thread(list_remote, sv)
                self.cache.kv_set(key, rows)
            except Exception as e:  # noqa: BLE001 - server spento o certificato cambiato: si mostra l'ultimo elenco
                self.log(f"Pozzo remoto {sv.get('name')}: {type(e).__name__}: {e}")
                rows = self.cache.kv_get(key) or []
            covers = Path(self.cache.folder) / "pozzoremote"
            for g in rows:
                gid = f"{sv['id']}:{g['ref']}"
                seen.add(gid)
                cover = await asyncio.to_thread(fetch_cover, sv, g, covers) if g.get("cover") else ""
                games.append(_game(gid, g["title"], done.get(gid), int(g.get("size") or 0), cover, g.get("platform") or ""))
        games += [_game(gid, rec["title"], rec, 0, "", "") for gid, rec in done.items() if gid not in seen]
        return games


def _game(gid: str, title: str, rec: dict | None, size: int, cover: str, platform: str) -> StoreGame:
    imgs = {"cover": "file:" + cover} if cover else {}
    if rec and rec.get("exe") and Path(rec["exe"]).exists():
        return StoreGame(store="pozzoremote", id=gid, title=title, installed=True, install_dir=rec.get("dir", ""), size=size, images=imgs,
                         launch={"type": "exe", "target": rec["exe"], "args": rec.get("args") or [],
                                 "cwd": rec.get("cwd") or str(Path(rec["exe"]).parent)})
    return StoreGame(store="pozzoremote", id=gid, title=title, install_uri=f"pozzo-pozzoremote:{gid}", size=size, images=imgs)


# ---------------------------------------------------------------- installazione

def rows() -> list[dict]:
    with _LOCK:
        return [dict(r) for r in _RUNS.values()]


def _state(gid: str, **kw) -> None:
    with _LOCK:
        _RUNS.setdefault(gid, {"id": "pr-" + gid}).update(kw)


def start(cfg, cache_factory, gid: str, on_done, tr) -> None:
    """Avvia lo scaricamento e l'installazione del gioco `gid` («id server:ref») in un thread."""
    sid, _, rf = gid.partition(":")
    settings = (getattr(cfg, "stores", {}) or {}).get("pozzoremote", {})
    sv = next((s for s in servers(settings) if s["id"] == sid), None)
    if not sv:
        raise LookupError(tr("s.pozzoremote.noServer"))
    with _LOCK:
        if (_RUNS.get(gid) or {}).get("status") == "running":
            raise ValueError(tr("s.netstore.busy"))
    _state(gid, name=gid, status="running", progress=0.0, started=time.time(), finished=0.0,
           phase=tr("s.pozzoremote.download"), last=sv["url"])

    def run():
        ok = False
        try:
            entry = next((g for g in list_remote(sv) if g["ref"] == rf), None)  # elenco fresco: i numeri cambiano
            if not entry:
                raise RuntimeError(tr("s.pozzoremote.gone"))
            _state(gid, name=entry["title"])
            rec = install(settings, sv, entry, lambda f, ph: _state(gid, progress=round(f, 3), phase=ph), tr)
            if rec.get("exe"):
                c = cache_factory()
                try:
                    done = c.kv_get(INSTALLED_KEY) or {}
                    done[gid] = {"title": entry["title"], **rec}
                    c.kv_set(INSTALLED_KEY, done)
                finally:
                    c.close()
            ok = True
            _state(gid, status="done", progress=1.0, finished=time.time(),
                   phase=tr("s.pozzoremote.done" if rec.get("exe") else "s.pozzoremote.savedOnly", title=entry["title"], dir=rec["dir"]))
        except Exception as e:  # noqa: BLE001 - l'errore si vede nell'attivita'
            _state(gid, status="error", finished=time.time(), phase=f"{type(e).__name__}: {e}")
        finally:
            on_done(ok)
    threading.Thread(target=run, daemon=True, name="pozzoremote-install").start()


def download(sv: dict, entry: dict, folder: Path, progress, tr) -> Path:
    """Scarica il gioco in `folder`. ROM sola: file con ripresa (.part + Range). Cartella: zip in streaming, da capo."""
    folder.mkdir(parents=True, exist_ok=True)
    zipped = entry.get("kind") == "zip"
    name = _safe(entry["title"]) + ".zip" if zipped else _safe(entry.get("name") or entry["title"])
    final, part = folder / name, folder / (name + ".part")
    total = int(entry.get("size") or 0)
    if total and shutil.disk_usage(folder).free < total * 1.1:
        raise OSError(tr("s.pozzoremote.space"))
    errors = 0
    while True:
        have = 0 if zipped or not part.exists() else part.stat().st_size
        try:
            conn, r, _ = open_pinned(sv["url"], sv["fp"], "GET", f"/api/lib-share/download/{int(entry['id'])}", sv["token"],
                                     headers={"Range": f"bytes={have}-"} if have else None, timeout=60)
        except PinError:
            raise
        except OSError:
            errors += 1
            if errors > 5:
                raise
            time.sleep(3)
            continue
        try:
            if r.status == 429:  # l'ospite ha ancora un flusso aperto (appena interrotto): si aspetta che si liberi
                errors += 1
                if errors > 8:
                    raise RuntimeError(tr("s.pozzoremote.busy"))
                time.sleep(10)
                continue
            if r.status == 416:  # il .part non combacia col file: da capo
                part.unlink(missing_ok=True)
                continue
            if r.status not in (200, 206):
                raise RuntimeError(f"HTTP {r.status}")
            if r.status == 200 or not (r.getheader("Content-Range") or "").startswith(f"bytes {have}-"):
                have = 0  # il server manda tutto (o da un altro punto): niente ripresa
                if r.status == 206:
                    raise RuntimeError("Risposta parziale inattesa")
            try:
                with open(part, "ab" if have else "wb") as f:
                    while b := r.read(256 * 1024):
                        f.write(b)
                        have += len(b)
                        if total:
                            progress(min(0.99, have / total) * (0.5 if zipped else 1.0), tr("s.pozzoremote.download"))
                part_done = True
            except (OSError, http.client.HTTPException):
                part_done = False
                if zipped or not part.exists():
                    raise
        finally:
            conn.close()
        if part_done:
            break
        errors += 1
        if errors > 8:
            raise RuntimeError(tr("s.pozzoremote.dropped"))
        time.sleep(3)
    part.replace(final)
    return final


def install(settings: dict, sv: dict, entry: dict, progress, tr) -> dict:
    """Scarica, estrae (zip) e cerca l'eseguibile. Ritorna {exe, args, cwd, dir} (exe vuoto = niente da avviare)."""
    from ..downloads import extract
    from . import netstore
    dest = dest_root(settings)
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / (".pozzoremote-" + entry["ref"])
    try:
        got = download(sv, entry, tmp, progress, tr)
        name = _safe(entry["title"])
        if entry.get("kind") == "zip":
            progress(0.5, tr("s.pozzoremote.extract"))
            game_dir = extract.extract(got, dest / name,
                                       on_progress=lambda f, *a: progress(0.5 + f * 0.5, tr("s.pozzoremote.extract")))[0]
        else:
            game_dir = dest / name
            game_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(got), str(game_dir / got.name))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    exe = netstore.pick_exe(Path(game_dir)) if entry.get("kind") == "zip" else None
    if not exe:
        return {"exe": "", "dir": str(game_dir)}
    return {"exe": str(exe), "args": [], "cwd": str(exe.parent), "dir": str(game_dir)}
