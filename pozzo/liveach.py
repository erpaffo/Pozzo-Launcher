"""Obiettivi dal vivo: durante la partita si guardano i file degli obiettivi scritti dagli emulatori Steam
(Goldberg/GSE, EMPRESS, CODEX, RUNE) e, a ogni obiettivo nuovo, si mostra un avviso nell'overlay.

Percorsi e nomi come in Achievement Watcher (xan105/Achievement-Watcher, app/parser/steam.js).
shortcut: sondaggio ogni 2 s della data di modifica di pochi file (come watcher.py non serve: il watcher
guarda cartelle intere e qui i file sono 10 al massimo e a volte nascono a partita iniziata); RPCS3 (TROPUSR.DAT,
binario) e SmartSteamEmu/CreamAPI/3DM (binari o formati diversi) non ci sono: aggiungere un parser in PARSERS."""

from __future__ import annotations

import configparser
import json
import os
import re
import threading
from pathlib import Path

POLL = 2.0
# (variabile d'ambiente, percorso sotto di essa, sottocartella dopo l'appid)
ROOTS = [("APPDATA", "Goldberg SteamEmu Saves", ""), ("APPDATA", "GSE Saves", ""),
         ("APPDATA", "EMPRESS", "remote"), ("PUBLIC", "Documents/EMPRESS", "remote"),
         ("PUBLIC", "Documents/Steam/CODEX", ""), ("APPDATA", "Steam/CODEX", ""),
         ("PUBLIC", "Documents/Steam/RUNE", ""), ("APPDATA", "Steam/RUNE", "")]
FILES = ("achievements.json", "achievements.ini")


def appid_of(key: str | None) -> str | None:
    """'windows/steam:220' -> '220' (solo i giochi della libreria Steam)."""
    store, _, sid = (key or "").partition("/")[2].partition(":")
    return sid if store == "steam" and sid.isdigit() else None


def candidate_files(appid: str, env=None) -> list[Path]:
    env = os.environ if env is None else env
    out = []
    for var, sub, after in ROOTS:
        if env.get(var):
            for name in FILES:
                out.append(Path(env[var], *sub.split("/"), appid, *([after] if after else []), name))
    return out


def parse_json(text: str) -> dict[str, int]:
    """Goldberg / GSE: {"ACH": {"earned": true, "earned_time": 123}} -> {id: tempo} dei soli sbloccati."""
    d = json.loads(text.lstrip("﻿"))
    return {k: int(v.get("earned_time") or 0) for k, v in d.items() if isinstance(v, dict) and v.get("earned")}


def parse_ini(text: str) -> dict[str, int]:
    """CODEX / RUNE: [ACH] Achieved=1 (o HaveAchieved=1) UnlockTime=123 -> {id: tempo} dei soli sbloccati."""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str.lower
    cp.read_string(text.lstrip("﻿"))
    out = {}
    for sec in cp.sections():
        s = cp[sec]
        if str(s.get("achieved", s.get("haveachieved", "0"))).strip().lower() in ("1", "true"):
            t = s.get("unlocktime", s.get("haveachievedtime", "0")).strip()
            out[sec] = int(t) if t.isdigit() else 0
    return out


PARSERS = {".json": parse_json, ".ini": parse_ini}


def read_unlocked(path: Path) -> dict[str, int]:
    try:
        return PARSERS[path.suffix.lower()](path.read_text("utf-8", errors="replace"))
    except (OSError, ValueError, configparser.Error):
        return {}  # file a meta' scrittura dal gioco: si riprova al prossimo giro


def new_unlocks(old: dict, new: dict) -> list[str]:
    """Id sbloccati in `new` e non in `old`, per tempo di sblocco."""
    return sorted((k for k in new if k not in old), key=lambda k: (new[k], k))


def pretty(ach_id: str) -> str:
    """'ACH_FIRST_KILL' -> 'First Kill'."""
    s = re.sub(r"^(ACH|ACHIEVEMENT|NEW_ACHIEVEMENT_\d+_\d+)[_\s-]*", "", ach_id, flags=re.I) or ach_id
    return re.sub(r"[_\s]+", " ", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)).strip().title()


def steam_schema(key: str, appid: str, timeout: float = 8.0) -> dict[str, dict]:
    """{apiname: {name, description, icon}} dallo schema Steam; vuoto senza chiave o in caso di errore."""
    if not key:
        return {}
    from . import achievements as ACH
    try:
        with ACH.http(timeout=timeout) as c:
            d = ACH._json(lambda: c.get(f"{ACH.STEAM}/ISteamUserStats/GetSchemaForGame/v2/",
                                        params={"key": key, "appid": appid}), "Steam")
    except Exception:
        return {}
    return {a["name"]: {"name": a.get("displayName"), "description": a.get("description") or "", "icon": a.get("icon")}
            for a in ((d.get("game") or {}).get("availableGameStats") or {}).get("achievements") or []}


class LiveAch:
    """Si aggancia a game_started / game_stopped; `overlay.toast` mostra gli avvisi."""

    def __init__(self, cfg, overlay, files=candidate_files, schema=steam_schema):
        self.cfg, self.overlay, self.files, self.schema = cfg, overlay, files, schema
        self._stop = threading.Event()
        self._th = None

    def game_started(self, st: dict):
        from . import overlay as OV
        appid = appid_of((st or {}).get("key"))
        if not appid or not OV.settings(self.cfg).get("achievements"):
            return
        self.game_stopped()
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._run, args=(appid, self._stop), daemon=True)
        self._th.start()

    def game_stopped(self, _st=None):
        self._stop.set()

    def _run(self, appid: str, stop: threading.Event):
        known: dict[str, dict] = {}  # file -> sbloccati; il primo giro e' la base di partenza e non avvisa
        mtimes: dict[Path, float] = {}
        first, schema = True, None
        while not stop.is_set():
            for f in self.files(appid):
                try:
                    mt = f.stat().st_mtime
                except OSError:
                    continue
                if mtimes.get(f) == mt:
                    continue
                mtimes[f] = mt
                cur = read_unlocked(f)
                fresh = [] if first else new_unlocks(known.get(f, {}), cur)
                known[f] = {**known.get(f, {}), **cur}
                for ach in fresh:
                    if schema is None:  # una volta sola, al primo sblocco
                        from . import profilecfg as PC
                        schema = self.schema(PC.get(self.cfg, "steam", {}).get("api_key") or "", appid)
                    self._notify(appid, ach, schema.get(ach) or {})
            first = False
            stop.wait(POLL)

    def _notify(self, appid: str, ach: str, info: dict):
        from . import overlay as OV
        s = OV.settings(self.cfg)
        if not s.get("achievements"):
            return
        self.overlay.toast({"id": f"{appid}:{ach}", "key": "o.toast.unlocked", "title": "Achievement unlocked",
                            "text": info.get("name") or pretty(ach), "desc": info.get("description") or "",
                            "icon": info.get("icon"), "sound": s.get("sound")})
