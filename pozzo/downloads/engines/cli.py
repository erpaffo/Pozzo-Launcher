"""Download di Epic, GOG e Amazon senza il client: lancia legendary / gogdl / nile e ne legge l'avanzamento.

Pausa e annulla fermano il processo (con tutto l'albero: su Windows l'exe di PyInstaller ha un processo figlio);
alla ripresa il programma riparte dallo stato che ha salvato. Il task ha source «noclient://<store>/<id>» e in
options store, game_id, action (install | update | verify), path, title, with_dlcs, dlcs, profile.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys

from ... import noclient as NC
from ... import profilecfg as PC

SCHEME = "noclient://"
TAIL = 6  # ultime righe del programma da mostrare in un errore


def is_cli(source: str) -> bool:
    return source.strip().lower().startswith(SCHEME)


def source_of(store: str, gid: str) -> str:
    return f"{SCHEME}{store}/{gid}"


def kill(proc) -> None:
    if proc.returncode is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NC.NO_WINDOW)
    else:
        proc.terminate()


def apply(t, store: str, info: dict) -> None:
    """Porta una riga letta sul task (size/done/error). legendary da' i byte totali solo in «Download size»."""
    if info.get("size"):
        t.size = info["size"]
    if info.get("total"):
        t.size, t.done = info["total"], info["done"]
    elif "pct" in info and t.size:
        t.done = int(t.size * info["pct"] / 100)


async def run(t, cfg, spawn=None) -> None:
    o = t.options
    store, gid, action = o["store"], o["game_id"], o.get("action") or "install"
    for sid, state in (("extract", "skip"), ("library", "done"), ("data", "skip")):
        t.set_stage(sid, state)  # nessuna estrazione: il programma installa da solo
    o["post_done"] = True  # niente finish.run (estrazione e inserimento nella libreria)
    with PC.override(o.get("profile")):
        NC.prepare(cfg, store)
    if not NC.available(cfg, store):
        raise RuntimeError(f"{NC.STORES[store][1]} non e' installato: scaricalo dal dettaglio del gioco")
    argv = NC.command(cfg, store, action, gid, o)
    t.log(f"Avvio {NC.STORES[store][1]} ({action})")
    spawn = spawn or asyncio.create_subprocess_exec
    proc = await spawn(*argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=NC.env(cfg),
                       creationflags=NC.NO_WINDOW)
    tail: list[str] = []
    try:
        while line := await proc.stdout.readline():
            text = line.decode("utf-8", "replace").strip()
            if not text:
                continue
            info = NC.parse_line(store, text)
            if info:
                apply(t, store, info)
            else:
                tail = [*tail, text][-TAIL:]
        rc = await proc.wait()
    finally:
        if proc.returncode is None:  # pausa, annulla o chiusura: il processo non resta orfano
            kill(proc)
    NC.sync_back(cfg, store)
    if rc:
        raise RuntimeError(f"{NC.STORES[store][1]} ha fallito (codice {rc}): " + " | ".join(tail))
    t.name = o.get("title") or gid
    t.done = t.size = t.size or t.done or 1
    with PC.override(o.get("profile")):
        NC.finished(cfg, store, gid, action, o)
