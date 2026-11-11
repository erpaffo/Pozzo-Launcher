"""Copie di sicurezza dei dati dell'utente: preferiti, tempi di gioco, stati, collezioni personali (userdata.db)
e impostazioni dell'app (settings.json: emulatori, cartelle associate).

Anche profiles/*.json (account e impostazioni di ogni profilo: Epic, GOG, Steam, Spotify, chiavi, token): ATTENZIONE,
la copia contiene credenziali, va tenuta come le password.

Non si salvano cache, metadati e immagini: si possono riscaricare. Ogni copia e' uno zip in <cache>/backups.
userdata.db si copia con l'API di backup di sqlite, quindi la copia e' coerente anche con l'app aperta (database in WAL).
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from . import config as C

KEEP = 10  # copie conservate; le piu' vecchie si cancellano
AUTO_EVERY = 7 * 86400  # copia automatica settimanale all'avvio dell'app


def folder(cfg) -> Path:
    return Path(cfg.cache) / "backups"


def list_backups(cfg) -> list[dict]:
    d = folder(cfg)
    if not d.exists():
        return []
    out = [{"name": p.name, "size": p.stat().st_size, "time": p.stat().st_mtime} for p in d.glob("userdata-*.zip")]
    return sorted(out, key=lambda x: -x["time"])


def create(cfg, reason: str = "manuale") -> Path:
    d = folder(cfg)
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = d / f"userdata-{stamp}-{reason}.zip"
    with tempfile.TemporaryDirectory() as t:
        cache = Path(cfg.cache)
        # userdata.db (profilo principale) e gli altri profili utente in profiles/
        names = ["userdata.db", *(f"profiles/{f.name}" for f in sorted((cache / "profiles").glob("*.db")))]
        # file degli account per profilo: stanno accanto a settings.json, si zippano cosi' come sono
        pj = C.settings_path(cfg).parent / "profiles"
        jsons = sorted(f for f in pj.glob("*.json") if not f.name.endswith(".rotto.json")) if pj.is_dir() else []
        for n in names:
            if (cache / n).exists():
                (Path(t) / n).parent.mkdir(parents=True, exist_ok=True)
                src, dst = sqlite3.connect(cache / n), sqlite3.connect(Path(t) / n)
                src.backup(dst)
                src.close()
                dst.close()
        with zipfile.ZipFile(out.with_suffix(".part"), "w", zipfile.ZIP_DEFLATED) as z:
            for n in names:
                if (Path(t) / n).exists():
                    z.write(Path(t) / n, n)
            for f in jsons:
                z.write(f, f"profiles/{f.name}")
            s = C.settings_path(cfg)
            if s.exists():
                z.write(s, "settings.json")
    out.with_suffix(".part").replace(out)
    for old in list_backups(cfg)[KEEP:]:
        (d / old["name"]).unlink(missing_ok=True)
    return out


def auto(cfg) -> Path | None:
    """All'avvio: una copia se l'ultima ha piu' di una settimana (o non ce n'e' nessuna)."""
    last = list_backups(cfg)
    if last and time.time() - last[0]["time"] < AUTO_EVERY:
        return None
    if not (Path(cfg.cache) / "userdata.db").exists():
        return None
    return create(cfg, "auto")


def _db_commands(con) -> int:
    """Profili di avvio con comandi shell (prima/dopo il gioco) dentro un userdata.db."""
    from .library import automation as A
    try:
        rows = con.execute("SELECT data FROM game_profiles").fetchall()
    except sqlite3.Error:
        return 0
    n = 0
    for (d,) in rows:
        try:
            n += bool(A.commands(json.loads(d or "{}")))
        except ValueError:
            pass
    return n


def _settings_commands(raw: bytes) -> int:
    """Comandi globali (prima/dopo ogni gioco, eventi) in un settings.json."""
    from .library import automation as A
    try:
        app = json.loads(raw).get("app") or {}
    except ValueError:
        return 0
    return sum(1 for k, v in [*((app.get("launch") or {}).items()), *((app.get(A.GLOBAL_KEY) or {}).items())]
               if k in ("before", "after", *A.GLOBAL_EVENTS.values()) and str(v or "").strip())


def restore(cfg, name: str, user=None, profiles: dict | None = None) -> dict:
    """Ripristina una copia. Prima ne crea una dei dati attuali, cosi' il ripristino si puo' annullare.
    `user` (UserData del profilo principale) e `profiles` ({id: UserData} degli altri profili aperti) permettono di
    riscrivere i database aperti senza riavviare."""
    p = folder(cfg) / Path(name).name  # solo nomi della cartella delle copie, niente percorsi arbitrari
    if not p.is_file() or not zipfile.is_zipfile(p):
        raise FileNotFoundError(f"Copia non trovata: {name}")
    before = create(cfg, "prima-del-ripristino")
    restored = []
    cmds = 0  # profili/impostazioni ripristinati che eseguono comandi: l'utente va avvisato
    with tempfile.TemporaryDirectory() as t, zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        if "userdata.db" in names:
            tmp = Path(z.extract("userdata.db", t))
            src = sqlite3.connect(tmp)
            if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                src.close()
                raise ValueError("La copia di userdata.db e' danneggiata")
            cmds += _db_commands(src)
            if user is not None:
                with user.lock:
                    src.backup(user.db)
            else:
                dst = sqlite3.connect(Path(cfg.cache) / "userdata.db")
                src.backup(dst)
                dst.close()
            src.close()
            restored.append("userdata.db")
        for n in sorted(x for x in names if x.startswith("profiles/") and x.endswith(".db") and "/" not in x[9:]):
            tmp = Path(z.extract(n, t))
            src = sqlite3.connect(tmp)
            if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                src.close()
                continue  # un profilo danneggiato non blocca il ripristino degli altri
            cmds += _db_commands(src)
            ud = (profiles or {}).get(Path(n).stem)
            if ud is not None:
                with ud.lock:
                    src.backup(ud.db)
            else:
                (Path(cfg.cache) / "profiles").mkdir(parents=True, exist_ok=True)
                dst = sqlite3.connect(Path(cfg.cache) / n)
                src.backup(dst)
                dst.close()
            src.close()
            restored.append(n)
        pj = C.settings_path(cfg).parent / "profiles"
        for n in sorted(x for x in names if x.startswith("profiles/") and x.endswith(".json") and "/" not in x[9:]):
            try:
                json.loads(z.read(n))
            except ValueError:
                continue  # file danneggiato: non sovrascrive quello attuale
            pj.mkdir(parents=True, exist_ok=True)
            tmp = pj / (Path(n).name + ".tmp")
            tmp.write_bytes(z.read(n))
            C._replace(tmp, pj / Path(n).name)
            restored.append(n)
        if "settings.json" in names:
            cmds += _settings_commands(z.read("settings.json"))
            s = C.settings_path(cfg)
            s.write_bytes(z.read("settings.json"))
            C.apply_settings(cfg)
            restored.append("settings.json")
    return {"restored": restored, "safety_copy": before.name, "runs_commands": cmds}
