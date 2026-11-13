"""Copie di sicurezza dei dati dell'utente: preferiti, tempi di gioco, stati, collezioni personali (userdata.db)
e impostazioni dell'app (settings.json: emulatori, cartelle associate).

Anche profiles/*.json (account e impostazioni di ogni profilo: Epic, GOG, Steam, Spotify, chiavi, token): ATTENZIONE,
la copia contiene credenziali, va tenuta come le password.

Anche i temi personali (themes/*), le schermate registrate nel database e un manifest.json (versione, ora, contenuto).
Le credenziali si possono escludere (impostazione app.backup_secrets): al ripristino quelle attuali restano al loro posto.

Non si salvano cache, metadati e immagini: si possono riscaricare. Ogni copia e' uno zip in <cache>/backups.
userdata.db si copia con l'API di backup di sqlite, quindi la copia e' coerente anche con l'app aperta (database in WAL).
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from . import config as C

KEEP = 10  # copie conservate (predefinito); le piu' vecchie si cancellano
AUTO_EVERY = 7 * 86400  # copia automatica settimanale all'avvio dell'app (solo se attivata)
THEME_MAX = 1_000_000  # un tema personale e' piccolo: file piu' grandi non entrano nella copia
SECRET_KEY = re.compile(r"api_?key|token|secret|passw|cookie|credential|oauth|session_?id|bearer|^key$", re.I)
# tabelle di userdata.db mostrate nell'anteprima del ripristino (nome -> chiave i18n dell'etichetta)
PREVIEW_TABLES = {"user_games": "e.backup.t.games", "play_sessions": "e.backup.t.sessions",
                  "user_collections": "e.backup.t.collections", "wishlist": "e.backup.t.wishlist",
                  "game_profiles": "e.backup.t.launchProfiles", "manual_games": "e.backup.t.manual",
                  "web_saves": "e.backup.t.webSaves", "screenshots": "e.backup.t.screens"}


def options(cfg) -> dict:
    """Impostazioni della copia: automatica (accesa di default, come prima), quante tenerne, se includere le credenziali."""
    a = getattr(cfg, "app", None) or {}
    try:
        keep = max(1, min(50, int(a.get("backup_keep") or KEEP)))
    except (TypeError, ValueError):
        keep = KEEP
    return {"auto": a.get("backup_auto", True) is not False, "keep": keep, "secrets": a.get("backup_secrets", True) is not False}


def _secret(k, v) -> bool:
    return isinstance(k, str) and bool(SECRET_KEY.search(k)) and not isinstance(v, (dict, list))


def _strip(o):
    """Copia del JSON senza i valori che sembrano credenziali."""
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if not _secret(k, v)}
    if isinstance(o, list):
        return [_strip(v) for v in o]
    return o


def _graft(new, cur):
    """Rimette in `new` le credenziali presenti in `cur` e assenti nella copia (copia fatta senza credenziali)."""
    if isinstance(new, dict) and isinstance(cur, dict):
        for k, v in cur.items():
            if k in new:
                new[k] = _graft(new[k], v)
            elif _secret(k, v):
                new[k] = v
    return new


def _json_bytes(raw: bytes, secrets: bool) -> bytes:
    if secrets:
        return raw
    try:
        return json.dumps(_strip(json.loads(raw)), indent=2, ensure_ascii=False).encode("utf-8")
    except ValueError:
        return raw


def folder(cfg) -> Path:
    return Path(cfg.cache) / "backups"


def list_backups(cfg) -> list[dict]:
    d = folder(cfg)
    if not d.exists():
        return []
    out = [{"name": p.name, "size": p.stat().st_size, "time": p.stat().st_mtime} for p in d.glob("userdata-*.zip")]
    return sorted(out, key=lambda x: -x["time"])


def _themes(cfg) -> list[Path]:
    d = C.settings_path(cfg).parent / "themes"
    if not d.is_dir():
        return []
    return [f for f in sorted(d.iterdir())[:200] if f.is_file() and f.stat().st_size <= THEME_MAX]


def create(cfg, reason: str = "manuale", secrets: bool | None = None) -> Path:
    d = folder(cfg)
    if secrets is None:
        secrets = options(cfg)["secrets"]
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
                z.writestr(f"profiles/{f.name}", _json_bytes(f.read_bytes(), secrets))
            s = C.settings_path(cfg)
            if s.exists():
                z.writestr("settings.json", _json_bytes(s.read_bytes(), secrets))
            for f in _themes(cfg):
                z.write(f, f"themes/{f.name}")
            try:
                from . import __version__
            except ImportError:
                __version__ = ""
            z.writestr("manifest.json", json.dumps({"format": 2, "app": __version__, "created": time.time(), "reason": reason,
                                                    "secrets": bool(secrets), "files": z.namelist()}, indent=1))
    out.with_suffix(".part").replace(out)
    for old in list_backups(cfg)[options(cfg)["keep"]:]:
        (d / old["name"]).unlink(missing_ok=True)
    return out


def auto(cfg) -> Path | None:
    """All'avvio, salvo che l'utente l'abbia spenta (app.backup_auto): una copia se l'ultima ha piu' di una settimana (o non ce n'e' nessuna)."""
    if not options(cfg)["auto"]:
        return None
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
        data = json.loads(raw)
    except ValueError:
        return 0
    app = (data.get("app") if isinstance(data, dict) else None) or {}  # JSON valido ma non un oggetto: niente comandi
    return sum(1 for k, v in [*((app.get("launch") or {}).items()), *((app.get(A.GLOBAL_KEY) or {}).items())]
               if k in ("before", "after", *A.GLOBAL_EVENTS.values()) and str(v or "").strip())


def _manifest(z: zipfile.ZipFile) -> dict:
    try:
        m = json.loads(z.read("manifest.json"))
        return m if isinstance(m, dict) else {}
    except (KeyError, ValueError):
        return {}


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _counts(db: Path) -> dict:
    """Righe di ogni tabella mostrata nell'anteprima (0 se il database o la tabella non esistono)."""
    out = {t: 0 for t in PREVIEW_TABLES}
    if not db.exists():
        return out
    try:
        con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error:
        return out
    try:
        for t in out:
            try:
                out[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                pass
    finally:
        con.close()
    return out


def preview(cfg, name: str) -> dict:
    """Cosa farebbe il ripristino, senza toccare niente: per ogni file se viene sovrascritto o creato, e per i database
    quante righe ci sono ora e quante nella copia."""
    p = folder(cfg) / Path(name).name
    if not p.is_file() or not zipfile.is_zipfile(p):
        raise FileNotFoundError(f"Copia non trovata: {name}")
    cache, items, cmds = Path(cfg.cache), [], 0
    with tempfile.TemporaryDirectory() as t, zipfile.ZipFile(p) as z:
        man = _manifest(z)
        pj = C.settings_path(cfg).parent / "profiles"
        for n in sorted(z.namelist()):
            if n == "settings.json":
                dst = C.settings_path(cfg)
            elif n == "userdata.db":
                dst = cache / n
            elif n.startswith("profiles/") and "/" not in n[9:] and n.endswith(".db"):
                dst = cache / n
            elif n.startswith("profiles/") and "/" not in n[9:] and n.endswith(".json"):
                dst = pj / Path(n).name
            elif n.startswith("themes/") and "/" not in n[7:] and n[7:]:
                dst = C.settings_path(cfg).parent / n
            else:
                continue
            it = {"file": n, "action": "overwrite" if dst.exists() else "create", "size": z.getinfo(n).file_size}
            if n.endswith(".db"):
                tmp = Path(z.extract(n, t))
                try:
                    c = sqlite3.connect(tmp)
                    cmds += _db_commands(c)
                    c.close()
                except sqlite3.Error:
                    pass
                new, now = _counts(tmp), _counts(dst)
                it["counts"] = [{"table": k, "label": PREVIEW_TABLES[k], "now": now[k], "backup": new[k]}
                                for k in PREVIEW_TABLES if now[k] or new[k]]
            elif n == "settings.json":
                cmds += _settings_commands(z.read(n))
            items.append(it)
    return {"name": p.name, "created": man.get("created") or p.stat().st_mtime, "app": man.get("app", ""),
            "secrets": man.get("secrets", True) is not False, "items": items, "runs_commands": cmds}


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
        keep_secrets = _manifest(z).get("secrets", True) is False  # copia senza credenziali: restano quelle attuali
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
                data = json.loads(z.read(n))
            except ValueError:
                continue  # file danneggiato: non sovrascrive quello attuale
            if keep_secrets:
                data = _graft(data, _read_json(pj / Path(n).name))
            pj.mkdir(parents=True, exist_ok=True)
            tmp = pj / (Path(n).name + ".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            C._replace(tmp, pj / Path(n).name)
            restored.append(n)
        if "settings.json" in names:
            raw = z.read("settings.json")
            cmds += _settings_commands(raw)
            s = C.settings_path(cfg)
            if keep_secrets:
                try:
                    raw = json.dumps(_graft(json.loads(raw), _read_json(s)), indent=2, ensure_ascii=False).encode("utf-8")
                except ValueError:
                    pass
            data = json.loads(raw)  # una copia con settings.json rotto si ferma qui, prima di toccare il file
            if not isinstance(data, dict):
                raise ValueError("settings.json della copia non valido")
            C._update_settings(cfg, lambda cur: (cur.clear(), cur.update(data)))  # lock + scrittura atomica come gli altri
            restored.append("settings.json")
        td = C.settings_path(cfg).parent / "themes"
        for n in sorted(x for x in names if x.startswith("themes/") and "/" not in x[7:] and x[7:]):
            td.mkdir(parents=True, exist_ok=True)
            (td / Path(n).name).write_bytes(z.read(n))
            restored.append(n)
    return {"restored": restored, "safety_copy": before.name, "runs_commands": cmds}
