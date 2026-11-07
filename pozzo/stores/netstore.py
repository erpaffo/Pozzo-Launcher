"""Cartelle di rete come store: installer, archivi e cartelle di giochi su una condivisione (UNC \\\\NAS\\Giochi,
unita' mappata o cartella locale). Le credenziali SMB sono quelle di Windows: l'utente apre/mappa la condivisione.

shortcut: niente WebDAV (servirebbe un client PROPFIND + autenticazione); da aggiungere se serve davvero.
Una voce = un elemento del primo livello della cartella. Per le cartelle, `pozzo.json` puo' dare title/exe/args.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .base import StoreGame, StoreProvider

_SETUP = re.compile(r"^(setup.*\.exe|.*\.msi)$", re.I)  # setup*.exe (anche GOG: setup_gioco_1.0.exe) e .msi
INSTALLED_KEY = "netstore:installed"  # kv: id -> {title, exe, args, cwd, dir}
_RUNS: dict[str, dict] = {}
_LOCK = threading.Lock()


def folders(settings: dict) -> list[Path]:
    return [Path(f.strip().strip('"')) for f in settings.get("folders") or [] if f and f.strip()]


def dest_root(settings: dict) -> Path:
    # shortcut: cartella predefinita fissa se l'utente non ne sceglie una; niente selettore per gioco
    return Path(settings.get("dest") or Path.home() / "Games" / "Pozzo")


def _id(p: Path) -> str:
    return hashlib.sha1(str(p).lower().encode()).hexdigest()[:12]


def find_setup(folder: Path) -> Path | None:
    """Setup in una cartella di installer (primo livello, poi un livello sotto)."""
    for pat in ("*", "*/*"):
        hits = sorted(f for f in folder.glob(pat) if f.is_file() and _SETUP.match(f.name))
        if hits:
            return hits[0]
    return None


def _classify(p: Path) -> str | None:
    """'archive' | 'installer' | 'folder' | None (da ignorare)."""
    from ..downloads import extract
    if p.name.startswith((".", "$")):
        return None
    if p.is_dir():
        return "installer" if find_setup(p) else "folder"
    if _SETUP.match(p.name):
        return "installer"
    return "archive" if extract.archive_group(p) else None


def read_override(folder: Path) -> dict:
    try:
        d = json.loads((folder / "pozzo.json").read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def list_entries(roots: list[Path]) -> list[dict]:
    from ..scanner import clean_title
    out = []
    for root in roots:
        try:
            items = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue  # condivisione non raggiungibile: le altre cartelle contano lo stesso
        for p in items:
            try:
                kind = _classify(p)
            except OSError:
                continue
            if not kind:
                continue
            ov = read_override(p) if p.is_dir() else {}
            out.append({"id": _id(p), "path": p, "kind": kind, "override": ov,
                        "title": str(ov.get("title") or clean_title(p.stem if p.is_file() else p.name))})
    return out


class NetStore(StoreProvider):
    id = "netstore"
    name = "Cartella di rete"

    def detected(self) -> bool:
        return bool(folders(self.settings))

    def account(self) -> dict:
        s = self.settings
        return {"connected": self.detected(), "folders": s.get("folders") or [], "dest": s.get("dest") or "",
                "silent": bool(s.get("silent"))}

    async def fetch(self) -> list[StoreGame]:
        entries = await asyncio.to_thread(list_entries, folders(self.settings))
        done = self.cache.kv_get(INSTALLED_KEY) or {}
        games = [_game(e["id"], e["title"], done.get(e["id"])) for e in entries]
        seen = {e["id"] for e in entries}
        games += [_game(gid, rec["title"], rec) for gid, rec in done.items() if gid not in seen]  # offline o rimossi
        return games


def _game(gid: str, title: str, rec: dict | None) -> StoreGame:
    if rec and Path(rec["exe"]).exists():
        return StoreGame(store="netstore", id=gid, title=title, installed=True, install_dir=rec.get("dir", ""),
                         launch={"type": "exe", "target": rec["exe"], "args": rec.get("args") or [],
                                 "cwd": rec.get("cwd") or str(Path(rec["exe"]).parent)})
    return StoreGame(store="netstore", id=gid, title=title, install_uri=f"pozzo-netstore:{gid}")


# ---------------------------------------------------------------- installazione

def rows() -> list[dict]:
    with _LOCK:
        return [dict(r) for r in _RUNS.values()]


def _state(gid: str, **kw) -> None:
    with _LOCK:
        _RUNS.setdefault(gid, {"id": "ns-" + gid}).update(kw)


def start(cfg, cache_factory, entry: dict, on_done, tr) -> None:
    """Avvia l'installazione di `entry` (da list_entries) in un thread; on_done(ok) a fine lavoro."""
    gid = entry["id"]
    with _LOCK:
        if (_RUNS.get(gid) or {}).get("status") == "running":
            raise ValueError(tr("s.netstore.busy"))
    _state(gid, name=entry["title"], status="running", progress=0.0, started=time.time(), finished=0.0,
           phase=tr("s.netstore.copy"), last=str(entry["path"]))

    def run():
        ok = False
        try:
            rec = install(cfg, entry, lambda f, ph: _state(gid, progress=round(f, 3), phase=ph), tr)
            c = cache_factory()
            try:
                done = c.kv_get(INSTALLED_KEY) or {}
                done[gid] = {"title": entry["title"], **rec}
                c.kv_set(INSTALLED_KEY, done)
            finally:
                c.close()
            ok = True
            _state(gid, status="done", progress=1.0, finished=time.time(), phase=tr("s.netstore.done", title=entry["title"]))
        except Exception as e:  # noqa: BLE001 - l'errore si vede nell'attivita'
            _state(gid, status="error", finished=time.time(), phase=f"{type(e).__name__}: {e}")
        finally:
            on_done(ok)
    threading.Thread(target=run, daemon=True, name="netstore-install").start()


def pick_exe(folder: Path, override: dict | None = None) -> Path | None:
    """Eseguibile da avviare: `exe` di pozzo.json (relativo alla cartella) o l'euristica dei repack (il piu' grande)."""
    from ..downloads import install as I
    exe = (override or {}).get("exe")
    if exe and (folder / exe).is_file():
        return folder / exe
    return I._exe_in(folder)


def _is_inno(setup: Path) -> bool:
    try:
        with open(setup, "rb") as f:
            return b"Inno Setup" in f.read(4 * 1024 * 1024)
    except OSError:
        return False


def install(cfg, entry: dict, progress, tr) -> dict:
    """Copia in locale con fastcopy, poi estrae / avvia il setup / tiene la cartella. Ritorna il record per kv."""
    from ..downloads import extract
    from ..library import fastcopy
    settings = (getattr(cfg, "stores", {}) or {}).get("netstore", {})
    dest = dest_root(settings)
    dest.mkdir(parents=True, exist_ok=True)
    src, kind, ov = Path(entry["path"]), entry["kind"], entry.get("override") or {}
    name = re.sub(r'[<>:"/\\|?*]', "", entry["title"]).strip() or "Gioco"
    half = 1.0 if kind == "folder" else 0.5  # copia = prima meta' della barra se poi c'e' altro da fare
    copy_p = lambda f, txt="": progress(f * half, tr("s.netstore.copy"))  # noqa: E731
    if kind == "folder":
        game_dir = fastcopy.copy(src, dest, on_progress=copy_p)
    else:
        tmp = Path(tempfile.mkdtemp(prefix=".netstore-", dir=dest))
        try:
            if kind == "archive":
                parts = extract.archive_group(src) or [src]  # tutti i volumi
                for part in parts:
                    fastcopy.copy(Path(part), tmp, on_progress=copy_p)
                progress(0.5, tr("s.netstore.extract"))
                game_dir = extract.extract(tmp / src.name, dest / name,
                                           on_progress=lambda f, *a: progress(0.5 + f * 0.5, tr("s.netstore.extract")))[0]
            else:
                setup = find_setup(src) if src.is_dir() else src
                local = fastcopy.copy(src, tmp, on_progress=copy_p)
                game_dir = _run_setup(local / setup.relative_to(src) if src.is_dir() else local,
                                      dest / name, bool(settings.get("silent")), progress, tr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    exe = pick_exe(Path(game_dir), ov)
    if not exe:
        raise RuntimeError(tr("s.netstore.noExe"))
    return {"exe": str(exe), "args": list(ov.get("args") or []), "cwd": str(exe.parent), "dir": str(game_dir)}


def _run_setup(setup: Path, target: Path, silent: bool, progress, tr) -> Path:
    """Esegue il setup. Silenzioso (/SILENT /DIR=) solo per installer Inno/GOG; altrimenti interattivo e il gioco
    nuovo si riconosce come per i repack."""
    from ..downloads import install as I
    progress(0.5, tr("s.netstore.run"))
    if silent and setup.suffix.lower() == ".exe" and _is_inno(setup):
        subprocess.run([str(setup), "/SILENT", "/NORESTART", f"/DIR={target}"], cwd=str(setup.parent), check=False)
        return target
    before = I._snapshot()
    I._launch(setup)
    found = I.detect(before)
    if not found:
        raise RuntimeError(tr("s.netstore.notRecognized"))
    return found["exe"].parent
