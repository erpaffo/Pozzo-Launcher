"""Stanze multiplayer di Eden: Pozzo avvia la stanza (senza interfaccia) e precompila «Direct Connect».

Eden tunnella il gioco locale (LDN) su UDP attraverso una stanza. La stanza si avvia con `eden-room` (accanto a eden.exe)
oppure con `eden --room`; senza --token/--web-api-url resta privata. L'ingresso da riga di comando e' `-m nick:password@host:porta`
(Core::ParseLaunchParams); se la finestra Qt lo ignorasse, restano i campi di Direct Connect gia' compilati in qt-config.ini.
"""

from __future__ import annotations

import atexit
import os
import re
import subprocess
import sys
from pathlib import Path

from .remote import emusetup

PROCS = ("eden.exe", "eden")
_NAME = re.compile(r"[^A-Za-z0-9 _-]")
_rooms: list[subprocess.Popen] = []


def room_cmd(exe: str, name: str, port: int, password: str, game: str = "", max_members: int = 4) -> list[str]:
    """Riga di comando della stanza: `eden-room` accanto all'exe, altrimenti `eden --room`."""
    base = Path(exe)
    for n in ("eden-room.exe", "eden-room"):
        if (base.parent / n).is_file():
            head = [str(base.parent / n)]
            break
    else:
        head = [str(base), "--room"]
    name = _NAME.sub("", name).strip()[:20]
    name = name if len(name) >= 4 else (name + "Pozzo")[:20]
    out = head + ["--room-name", name, "--port", str(int(port)), "--max-members", str(int(max_members))]
    if password:
        out += ["--password", password]
    if game:
        out += ["--preferred-game", game[:60]]
    return out


def start(cmd: list[str]) -> subprocess.Popen:
    """Avvia la stanza in sottofondo (senza finestra); si chiude con Pozzo o con stop()."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    _rooms.append(p)
    return p


def alive(p: subprocess.Popen, wait: float = 0.7) -> bool:
    """La stanza e' ancora in piedi dopo un attimo? (argomenti sbagliati = esce subito)"""
    try:
        p.wait(wait)
    except subprocess.TimeoutExpired:
        return True
    return False


def stop(p: subprocess.Popen | None) -> None:
    if p is None:
        return
    if p in _rooms:
        _rooms.remove(p)
    if p.poll() is None:
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()


atexit.register(lambda: [stop(p) for p in list(_rooms)])


def config_file(exe: str | None) -> Path | None:
    """qt-config.ini di Eden: portatile (cartella `user` accanto all'exe), altrimenti dati dell'utente."""
    base = Path(exe).parent if exe else None
    c = [base / "user" / "config" / "qt-config.ini" if base else None,
         Path(os.environ["APPDATA"]) / "eden" / "config" / "qt-config.ini" if os.environ.get("APPDATA") else None,
         Path.home() / ".local" / "share" / "eden" / "config" / "qt-config.ini"]
    c = [p for p in c if p]
    return next((p for p in c if p.is_file()), c[0] if c else None)


def prefill(exe: str | None, nick: str, host: str, port: int) -> Path | None:
    """Compila Direct Connect (nick, indirizzo, porta). Eden chiuso; None se non si puo' (resta da compilare a mano)."""
    p = config_file(exe)
    if not p or not p.is_file() or emusetup._running(PROCS):
        return None
    raw = p.read_bytes().decode("utf-8-sig", errors="replace")
    keys = {"Multiplayer\\nickname": nick, "Multiplayer\\ip": host, "Multiplayer\\port": str(int(port))}
    ch = {}
    for k, v in keys.items():
        ch[k] = v
        ch[k + "\\default"] = "false"
    new = emusetup.ini_update(raw, {"UI": ch}, sep="=")  # prima il contenuto, poi il file
    emusetup.backup(p)
    p.write_text(new.replace("\n", "\r\n") if "\r\n" in raw else new, encoding="utf-8", newline="")
    return p


STEPS = "In Eden: Multiplayer › Direct Connect › Connetti (indirizzo, porta e nome sono già compilati). Poi apri la modalità locale del gioco."
