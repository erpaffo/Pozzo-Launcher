"""Sincronizzazione dei dati personali tra PC.

Un "pacchetto" (bundle) contiene i dati personali di un profilo: per ogni gioco preferito, nascosto, stato, nota,
voto, versione principale e ultima partita, ognuno con l'ora della sua ultima modifica (tabella sync_times di
userdata.db); le sessioni di gioco; collezioni, modifiche alle collezioni e lista desideri, con le cancellazioni.
merge() unisce il pacchetto di un altro PC: per ogni dato vince la modifica piu' recente, le sessioni si sommano
senza doppioni (il tempo di gioco e' la somma delle sessioni dei due PC). Unire due volte lo stesso pacchetto non
cambia nulla.

Facoltativo (what = "all"): anche le impostazioni non legate al PC (store online, fonti, tema, collezioni
intelligenti...): vince la versione salvata piu' di recente. Percorsi, emulatori, account degli store, telefono e
profili restano sempre del singolo PC.

Facoltativo (saves = true): anche i file di salvataggio dei giochi scelti in saves_games. Il confronto e' a tre
stati (questo PC, l'altro PC e l'ultima sincronizzazione nota): se ha cambiato solo un lato vince quello, se hanno
cambiato entrambi non si sovrascrive niente e la versione dell'altro PC va tra le copie del gioco. Mai mentre il
gioco e' in esecuzione.

Trasporti:
- cartella condivisa (OneDrive, Dropbox, NAS, Syncthing): <cartella>/PozzoLauncher-sync/<profilo>/<pc>.json, ogni PC
  scrive solo il proprio file, quindi il servizio di sincronizzazione non crea conflitti;
- rete locale: il server HTTPS del telefono accetta i PC abbinati (vedi remote/phone.py); il certificato del PC
  remoto e' verificato con l'impronta salvata all'abbinamento.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import ssl
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from . import config as C
from .library import saves as SV
from .library.userdata import DELETED, UserData

FORMAT = 1
GAME_FIELDS = ("favorite", "hidden", "preferred", "status", "note", "my_rating", "last_played")
WISH_FIELDS = ("title", "steam_appid", "itad_id", "target", "added")
# impostazioni sincronizzabili (what = "all"): sezioni intere di settings.json e voci di "app"
SETTINGS_SECTIONS = ("catalogs", "pc_stores", "limits", "screenscraper", "igdb", "rawg", "thegamesdb", "custom_platforms")
APP_KEYS = ("theme", "smart_collections", "disabled_plugins", "skip_duplicates", "wishlist", "retroachievements")
DIR = "PozzoLauncher-sync"
SAVES_DIR = "saves"  # dentro DIR: un JSON per PC e la sua sottocartella con i file
SAVE_FILE_MAX = 256 << 20  # un file piu' grande non si sincronizza (si salta con un avviso)
SAVE_MAX_BYTES = 512 << 20  # byte presi dagli altri PC in un giro
SAVE_REQ_MAX = 32 << 20  # tetto di una singola richiesta di file al PC remoto
CONFLICTS = "_conflicts"  # nello stato: chiavi "gioco\tfile" gia' archiviate come conflitto
INTERVAL = 300  # secondi tra due sincronizzazioni automatiche


# ---------------------------------------------------------------- configurazione e profili

def conf(cfg) -> dict:
    """Impostazioni della sincronizzazione (app.sync), con l'identita' di questo PC creata la prima volta."""
    c = {"folder": "", "what": "personal", "peers": [], "saves": False, "saves_games": [],
         **(cfg.app.get("sync") or {})}
    if not c.get("pc_id"):
        c["pc_id"] = uuid.uuid4().hex[:12]
        save_conf(cfg, c)
    return c


def save_conf(cfg, c: dict):
    cfg.app["sync"] = c
    C.save_settings(cfg, app={"sync": c})


def _entries(cfg) -> dict[str, dict]:
    """Voci salvate dei profili (con pin_hash: non escono da questo modulo, vedi profiles())."""
    return {p["id"]: dict(p) for p in cfg.app.get("profiles") or [] if p.get("id")}


def _public(pid: str, p: dict | None, name: str) -> dict:
    p = p or {}
    return {"id": pid, "name": p.get("name") or name, "avatar": p.get("avatar") or "", "color": p.get("color") or "",
            "locked": bool(p.get("pin_hash"))}


def profiles(cfg) -> list[dict]:
    """Profili utente; "default" (Principale, rinominabile) usa sempre cache/userdata.db. Mai il PIN, solo se c'e'."""
    raw = _entries(cfg)
    return [_public("default", raw.get("default"), "Principale")] + [_public(i, p, i) for i, p in raw.items() if i != "default"]


def _save_profiles(cfg, raw: dict[str, dict]):
    lst = list(raw.values())
    cfg.app["profiles"] = lst
    C.save_settings(cfg, app={"profiles": lst})


def profile_path(cfg, pid: str) -> Path:
    base = Path(cfg.cache)
    return base / "userdata.db" if pid == "default" else base / "profiles" / f"{pid}.db"


def profile_id(name: str) -> str:
    """Id dal nome: lo stesso nome su due PC e' lo stesso profilo (cosi' si sincronizzano)."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "profilo"


def open_profile(cfg, pid: str) -> UserData:
    path = profile_path(cfg, pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    return UserData(path, shared=profile_path(cfg, "default"), profile=pid)


def add_profile(cfg, name: str) -> dict:
    """Nuovo profilo (o quello che esiste gia' con lo stesso nome)."""
    name = name.strip()[:40]
    if not name:
        raise ValueError("Serve un nome")
    pid = profile_id(name)
    if pid == "default":
        pid = "default-2"
    hit = next((p for p in profiles(cfg) if p["id"] == pid), None)
    if hit:
        return hit
    _save_profiles(cfg, {**_entries(cfg), pid: {"id": pid, "name": name}})
    return {"id": pid, "name": name}


def rename_profile(cfg, pid: str, name: str):
    """Cambia solo il nome mostrato: l'id resta, cosi' il profilo continua a sincronizzarsi con gli altri PC."""
    name = name.strip()[:40]
    if not name:
        raise ValueError("Serve un nome")
    raw = _entries(cfg)
    raw.setdefault(pid, {"id": pid})["name"] = name
    _save_profiles(cfg, raw)


def update_profile(cfg, pid: str, avatar: str | None = None, color: str | None = None, pin: str | None = None):
    """Icona, colore e PIN (pin "" = nessun PIN). None = invariato. Il PIN e' salvato solo come hash."""
    from . import profilecfg as PC
    if avatar is not None and len(avatar) > 16:
        raise ValueError("Icona troppo lunga")
    if color is not None and color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError("Colore non valido: usa #rrggbb")
    if pin is not None and pin and not re.fullmatch(r"\d{4,8}", pin):
        raise ValueError("Il PIN e' di 4-8 cifre")
    raw = _entries(cfg)
    e = raw.setdefault(pid, {"id": pid})
    for k, v in (("avatar", avatar), ("color", color)):
        if v is not None:
            e[k] = v
    if pin is not None:
        if pin:
            e["pin_hash"] = PC.hash_pin(pin)
        else:
            e.pop("pin_hash", None)
    _save_profiles(cfg, raw)


def delete_profile(cfg, pid: str) -> Path | None:
    """Toglie il profilo; il suo database e i suoi account vanno in profiles/eliminati/ (non si cancella nulla)."""
    if pid == "default":
        raise ValueError("Il profilo principale non si elimina")
    raw = _entries(cfg)
    raw.pop(pid, None)
    _save_profiles(cfg, raw)
    from . import profilecfg as PC
    stamp = time.strftime("%Y%m%d-%H%M%S")
    pj = PC.path(cfg, pid)
    if pj and pj.exists():
        (pj.parent / "eliminati").mkdir(parents=True, exist_ok=True)
        pj.replace(pj.parent / "eliminati" / f"{pid}-{stamp}.json")
    from .cache import Cache  # le liste degli store di questo profilo (kv "store:<id>:<profilo>") non servono piu'
    c = Cache(cfg.cache)
    try:
        c.db.execute("DELETE FROM kv WHERE k LIKE ?", (f"store:%:{pid}",))
        c.commit()
    finally:
        c.close()
    src = profile_path(cfg, pid)
    if not src.exists():
        return None
    dst = src.parent / "eliminati" / f"{pid}-{stamp}.db"
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dst)
    for ext in ("-wal", "-shm"):  # il database e' chiuso dal server prima di chiamare questa funzione
        Path(f"{src}{ext}").unlink(missing_ok=True)
    return dst


# ---------------------------------------------------------------- pacchetto e unione

def _stamps(ud: UserData) -> dict:
    return {(t, i, f): v for t, i, f, v in ud._q("SELECT tbl, id, field, t FROM sync_times")}


def export(ud: UserData, profile: dict, pc: dict, settings: dict | None = None) -> dict:
    st = _stamps(ud)
    games = {}
    for key, g in ud.games().items():
        f = {k: [g[k], st.get(("game", key, k), 0)] for k in GAME_FIELDS
             if g[k] not in (None, 0, "") or ("game", key, k) in st}
        if f:
            games[key] = f
    colls = {slug: {**c, "t": st.get(("coll", slug, ""), 0)} for slug, c in ud.collections().items()}
    edits = {f"{s}\t{k}": [a, st.get(("edit", f"{s}\t{k}", ""), 0)] for s, k, a in ud.edits()}
    wish = {w["id"]: {**{k: w[k] for k in WISH_FIELDS}, "t": st.get(("wish", w["id"], ""), 0)} for w in ud.wishlist()}
    deleted = {}
    for (tbl, i, f), t in st.items():
        if f == DELETED:
            deleted.setdefault(tbl, {})[i] = t
    out = {"format": FORMAT, "pc": pc["pc_id"], "pc_name": pc.get("pc_name", ""), "time": time.time(),
           "profile": {"id": profile["id"], "name": profile["name"]}, "games": games, "sessions": [list(s) for s in ud.sessions()],
           "colls": colls, "edits": edits, "wish": wish, "deleted": deleted}
    if settings is not None:
        out["settings"] = settings
    return out


def _newer(rt: float, lt: float, local_value, remote_value) -> bool:
    """Vince il dato modificato piu' di recente; a parita' (dati mai toccati da quando esiste la sincronizzazione)
    vince il valore impostato su quello vuoto, cosi' al primo giro si uniscono i preferiti dei due PC."""
    return rt > lt or (rt == lt and local_value in (None, 0, "") and remote_value not in (None, 0, ""))


def merge(ud: UserData, b: dict) -> dict:
    """Unisce il pacchetto di un altro PC nel profilo. Ritorna quante cose sono cambiate."""
    if b.get("format") != FORMAT:
        raise ValueError("Pacchetto di sincronizzazione di una versione diversa di PozzoLauncher: aggiorna entrambi i PC")
    st, local = _stamps(ud), ud.games()
    n = {"games": 0, "sessions": 0, "colls": 0, "wish": 0}
    stamps = []
    with ud.lock:
        db = ud.db
        for key, fields in (b.get("games") or {}).items():
            lg = local.get(key, {})
            for f, (val, rt) in fields.items():
                if f not in GAME_FIELDS:
                    continue
                if _newer(rt, st.get(("game", key, f), 0), lg.get(f), val):
                    db.execute(f"INSERT INTO user_games(key, {f}) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET {f}=excluded.{f}",
                               (key, val))
                    stamps.append(("game", key, f, rt))
                    n["games"] += 1
        have = {(k, round(s, 3)) for k, s, _ in db.execute("SELECT key, start, seconds FROM play_sessions")}
        for key, start, secs in b.get("sessions") or []:
            if (key, round(start, 3)) in have:
                continue
            have.add((key, round(start, 3)))
            db.execute("INSERT INTO play_sessions VALUES(?, ?, ?)", (key, start, secs))
            db.execute("INSERT INTO user_games(key, play_count, playtime) VALUES(?, 1, ?) ON CONFLICT(key) DO UPDATE "
                       "SET play_count=COALESCE(play_count, 0)+1, playtime=COALESCE(playtime, 0)+excluded.playtime",
                       (key, secs))
            n["sessions"] += 1
        dels = b.get("deleted") or {}
        lcolls = {r[0] for r in db.execute("SELECT slug FROM user_collections")}
        for slug, c in (b.get("colls") or {}).items():
            lt = max(st.get(("coll", slug, ""), 0), st.get(("coll", slug, DELETED), 0))
            if c["t"] > lt or (c["t"] == lt == 0 and slug not in lcolls):
                db.execute("INSERT INTO user_collections(slug, name, custom, hidden, created) VALUES(?, ?, ?, ?, ?) "
                           "ON CONFLICT(slug) DO UPDATE SET name=excluded.name, custom=excluded.custom, "
                           "hidden=excluded.hidden", (slug, c.get("name"), c.get("custom") or 0, c.get("hidden") or 0, time.time()))
                stamps.append(("coll", slug, "", c["t"]))
                n["colls"] += 1
        for slug, t in (dels.get("coll") or {}).items():
            if t > st.get(("coll", slug, ""), 0) and t > st.get(("coll", slug, DELETED), 0):
                db.execute("DELETE FROM user_collections WHERE slug=?", (slug,))
                db.execute("DELETE FROM collection_edits WHERE slug=?", (slug,))
                stamps.append(("coll", slug, DELETED, t))
                n["colls"] += 1
        ledits = {f"{s}\t{k}": a for s, k, a in db.execute("SELECT slug, key, action FROM collection_edits")}
        for sk, (action, rt) in (b.get("edits") or {}).items():
            if _newer(rt, st.get(("edit", sk, ""), 0), ledits.get(sk), action) and ledits.get(sk) != action:
                slug, key = sk.split("\t", 1)
                db.execute("INSERT OR REPLACE INTO collection_edits VALUES(?, ?, ?)", (slug, key, action))
                stamps.append(("edit", sk, "", rt))
                n["colls"] += 1
        lwish = {r[0] for r in db.execute("SELECT id FROM wishlist")}
        for wid, w in (b.get("wish") or {}).items():
            lt = max(st.get(("wish", wid, ""), 0), st.get(("wish", wid, DELETED), 0))
            if w["t"] > lt or (w["t"] == lt == 0 and wid not in lwish):
                vals = [w.get(k) for k in WISH_FIELDS]
                db.execute(f"INSERT INTO wishlist(id, {', '.join(WISH_FIELDS)}) VALUES(?{', ?' * len(WISH_FIELDS)}) "
                           f"ON CONFLICT(id) DO UPDATE SET {', '.join(f'{k}=excluded.{k}' for k in WISH_FIELDS)}",
                           (wid, *vals))
                stamps.append(("wish", wid, "", w["t"]))
                n["wish"] += 1
        for wid, t in (dels.get("wish") or {}).items():
            if t > st.get(("wish", wid, ""), 0) and t > st.get(("wish", wid, DELETED), 0):
                db.execute("DELETE FROM wishlist WHERE id=?", (wid,))
                db.execute("DELETE FROM wish_prices WHERE id=?", (wid,))
                stamps.append(("wish", wid, DELETED, t))
                n["wish"] += 1
        # l'ora resta quella della modifica originale: un terzo PC confronta sempre la stessa ora
        db.executemany("INSERT OR REPLACE INTO sync_times VALUES(?, ?, ?, ?)", stamps)
        db.commit()
        if any(n.values()):
            ud.rev += 1
    return n


# ---------------------------------------------------------------- impostazioni (what = "all")

def _settings_subset(cfg) -> dict:
    s = C.read_settings(cfg)
    return {"sections": {k: s[k] for k in SETTINGS_SECTIONS if k in s},
            "app": {k: (s.get("app") or {})[k] for k in APP_KEYS if k in (s.get("app") or {})}}


def settings_bundle(cfg, c: dict) -> dict:
    """Impostazioni sincronizzabili con l'ora dell'ultima modifica (si accorge da solo dei cambiamenti)."""
    data = _settings_subset(cfg)
    h = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if c.get("settings_hash") != h:
        c.update(settings_hash=h, settings_t=time.time())
        save_conf(cfg, c)
    return {"t": c["settings_t"], "data": data}


def merge_settings(cfg, c: dict, remote: dict | None) -> bool:
    if not remote or remote.get("t", 0) <= c.get("settings_t", 0):
        return False
    data = remote["data"]

    def change(s):
        for k in SETTINGS_SECTIONS:
            if k in data.get("sections", {}):
                s[k] = data["sections"][k]
            else:
                s.pop(k, None)
        app = s.setdefault("app", {})
        for k in APP_KEYS:
            if k in data.get("app", {}):
                app[k] = data["app"][k]
            else:
                app.pop(k, None)
    C._update_settings(cfg, change)
    h = hashlib.sha256(json.dumps(_settings_subset(cfg), sort_keys=True).encode()).hexdigest()
    c.update(settings_hash=h, settings_t=remote["t"])
    save_conf(cfg, c)
    return True


# ---------------------------------------------------------------- file di salvataggio (percorsi relativi)

_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def _safe_rel(rel) -> bool:
    """Chiave relativa usabile come percorso. Arriva da un altro PC, quindi niente risalite (..), unita' di disco,
    percorsi assoluti, caratteri di controllo o nomi riservati di Windows."""
    if not isinstance(rel, str) or not rel or len(rel) > 200 or "\\" in rel or rel.startswith("/"):
        return False
    for part in rel.split("/"):
        if not part or part in (".", "..") or ":" in part or any(ord(ch) < 32 for ch in part):
            return False
        if part.split(".")[0].strip().lower() in _RESERVED:
            return False
    return True


def _rel_of(p: Path) -> str:
    """Chiave stabile di un file di salvataggio: gli ultimi tre pezzi del percorso (la radice cambia da PC a PC)."""
    return "/".join(p.parts[-3:])


def _file_sha(p: Path | None) -> str:
    if not p:
        return ""
    try:
        return SV._sha1(p)
    except OSError:  # file sparito o riscritto dal gioco in questo momento
        return ""


def _mb(n: int) -> str:
    return f"{n / (1 << 20):.1f} MB" if n >= 1 << 20 else f"{max(1, n // 1024)} KB"


def _inside(base: Path, dest: Path) -> bool:
    b, d = base.resolve(), dest.resolve()
    return d == b or b in d.parents


def _write_file(base: Path, dest: Path, data: bytes | None = None, src: Path | None = None) -> bool:
    """Scrive (o copia) un file di salvataggio dentro base: mai fuori, mai a meta' (tmp + replace)."""
    if not _inside(base, dest):
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".tmp")
        if data is not None:
            tmp.write_bytes(data)
        else:
            shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
        return True
    except OSError:
        return False


def _read_published(base: Path, rel: str) -> bytes | None:
    """Byte di un file che un altro PC ha pubblicato nella sua sottocartella (mai fuori da li')."""
    if not _safe_rel(rel):
        return None
    f = base / rel
    try:
        if not _inside(base, f) or not f.is_file() or f.stat().st_size > SAVE_FILE_MAX:
            return None
        return f.read_bytes()
    except OSError:
        return None


# ---------------------------------------------------------------- un giro di sincronizzazione

class Sync:
    """Stato e giro di sincronizzazione (cartella + PC in rete) per tutti i profili."""

    def __init__(self, cfg, user_of, playing=None, saves_of=None):
        self.cfg, self.user_of = cfg, user_of  # user_of(pid) -> UserData del profilo (gia' aperto dal server)
        self.last: dict = {}
        self.busy = False
        # salvataggi: gioco in esecuzione (mai sincronizzare) e file di salvataggio di un gioco
        self.playing = playing or (lambda: False)
        self.saves_of = saves_of or (lambda key, title: SV.resolved_manual(cfg, key))
        self.title_of = None  # opzionale: key -> titolo (l'app lo imposta con la libreria)

    def pc(self) -> dict:
        c = conf(self.cfg)
        return {"pc_id": c["pc_id"], "pc_name": c.get("pc_name") or socket.gethostname()}

    def bundles(self, only: set | None = None) -> dict:
        c, pc = conf(self.cfg), self.pc()
        out = {}
        for p in profiles(self.cfg):
            if only is None or p["id"] in only:
                sett = settings_bundle(self.cfg, c) if c["what"] == "all" and p["id"] == "default" else None
                out[p["id"]] = export(self.user_of(p["id"]), p, pc, sett)
        return out

    def receive(self, bundles: dict) -> dict:
        """Unisce i pacchetti ricevuti (crea i profili che qui non esistono)."""
        c, n = conf(self.cfg), {}
        known = {p["id"] for p in profiles(self.cfg)}
        for pid, b in bundles.items():
            if pid not in known:
                add_profile(self.cfg, (b.get("profile") or {}).get("name") or pid)
            r = merge(self.user_of(pid), b)
            if c["what"] == "all" and pid == "default" and merge_settings(self.cfg, c, b.get("settings")):
                r["settings"] = 1
            n[pid] = r
        return n

    # ------------------------------------------------------------ salvataggi: elenco, manifest, stato
    def _is_playing(self) -> bool:
        try:
            return bool(self.playing())
        except Exception:
            return True  # se non si sa, meglio non toccare i salvataggi

    def saves_enabled(self) -> bool:
        """Sincronizzazione dei salvataggi attiva, con almeno un gioco scelto e nessun gioco in esecuzione."""
        c = conf(self.cfg)
        return bool(c.get("saves")) and bool(self._saves_keys(c)) and not self._is_playing()

    @staticmethod
    def _saves_keys(c: dict) -> list[str]:
        return [k.strip() for k in dict.fromkeys(c.get("saves_games") or []) if isinstance(k, str) and k.strip()]

    def saves_title(self, key: str) -> str:
        f = getattr(self, "title_of", None)
        if f:
            try:
                return str(f(key) or key)[:200]
            except Exception:
                pass
        return key[:200]

    def saves_files(self, key: str, title: str | None = None) -> tuple[list[tuple[Path, str]], list[str]]:
        """File di salvataggio del gioco come (percorso, chiave relativa), con gli avvisi di quelli scartati."""
        warn: list[str] = []
        try:
            paths = [Path(p) for p in (self.saves_of(key, title or self.saves_title(key)) or [])]
        except Exception as e:  # emulatore non configurato, cartella sparita...
            return [], [f"{key}: {e}"]
        found: dict[str, Path] = {}
        for p in paths:
            if p.is_file():
                cand = [(p, p.name)]
            elif p.is_dir():
                cand = [(f, _rel_of(f)) for f in sorted(p.rglob("*")) if f.is_file()]
            else:
                cand = []
            for f, rel in cand:
                if not _safe_rel(rel):
                    warn.append(f"{key}: percorso scartato («{str(rel)[:80]}»)")
                elif rel in found:
                    return [], warn + [f"{key}: due file con la stessa chiave «{rel}», gioco saltato"]
                else:
                    found[rel] = f
        return [(f, rel) for rel, f in sorted(found.items())], warn

    def saves_file(self, key: str, rel: str) -> Path | None:
        """Il file di salvataggio locale con quella chiave relativa (per il PC remoto che lo chiede)."""
        if not _safe_rel(rel):
            return None
        return next((f for f, r in self.saves_files(key)[0] if r == rel), None)

    def saves_manifest(self) -> dict:
        return self._saves_manifest()[0]

    def _saves_manifest(self) -> tuple[dict, list[str]]:
        """Manifest dei salvataggi di questo PC: hash, ora e dimensione di ogni file, per i giochi inclusi."""
        c, pc, games, warn = conf(self.cfg), self.pc(), {}, []
        for key in self._saves_keys(c):
            title = self.saves_title(key)
            files, w = self.saves_files(key, title)
            warn.extend(w)
            entries = {}
            for f, rel in files:
                try:
                    st = f.stat()
                    entries[rel] = {"sha1": SV._sha1(f), "mtime": int(st.st_mtime), "size": st.st_size}
                except OSError:
                    continue
            if entries:
                games[key] = {"title": title, "files": entries}
        return {"format": FORMAT, "pc": pc["pc_id"], "pc_name": pc.get("pc_name") or "", "time": time.time(),
                "games": games}, warn

    def _saves_state_path(self) -> Path:
        return Path(self.cfg.cache) / "sync" / "saves-state.json"

    def _saves_state(self) -> dict:
        """Ultimo stato sincronizzato: {gioco: {chiave: sha1}}. Serve a capire chi ha cambiato un file."""
        try:
            d = json.loads(self._saves_state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}

    def _write_saves_state(self, state: dict):
        p = self._saves_state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name("saves-state.json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)

    def _saves_dirs(self, key: str, title: str) -> list[Path]:
        try:
            paths = [Path(p) for p in (self.saves_of(key, title) or [])]
        except Exception:
            return []
        return list(dict.fromkeys(p if p.is_dir() else p.parent for p in paths))

    def _saves_dest(self, local: dict[str, Path], dirs: list[Path], rel: str) -> tuple[Path, Path] | None:
        """Dove scrivere qui un file che c'e' solo sull'altro PC: (radice per il controllo, destinazione)."""
        parts = rel.split("/")
        for f in local.values():  # stessa profondita' dei file gia' noti dello stesso gioco
            k = len(parts) - 1
            if k < len(f.parents):
                base = f.parents[k]
                return base, base.joinpath(*parts)
        for d in dirs:  # nessun file locale: entro la cartella dei salvataggi che compare nella chiave
            hit = [i for i, p in enumerate(parts[:-1]) if p == d.name]
            if hit:
                return d, d.joinpath(*parts[hit[-1] + 1:])
        if dirs:
            return dirs[0], dirs[0].joinpath(*parts)
        return None

    def _saves_fetch(self, key: str, rel: str, size: int, get, res: dict, sent: list[int]) -> bytes | None:
        """Byte del file remoto, con i tetti di dimensione (per file e per giro)."""
        if size > SAVE_FILE_MAX:
            res["warnings"].append(f"{key}: {rel} troppo grande ({_mb(size)}), saltato")
            return None
        if sent[0] + max(size, 0) > SAVE_MAX_BYTES:
            res["warnings"].append(f"{key}: salvataggi da copiare troppi per un giro ({_mb(SAVE_MAX_BYTES)}), saltato")
            return None
        if get is None:
            res["warnings"].append(f"{key}: {rel} non richiedibile a questo trasporto, saltato")
            return None
        try:
            data = get(key, rel)
        except Exception as e:
            res["warnings"].append(f"{key}: {rel} non letto ({e})")
            return None
        if data is None:
            res["warnings"].append(f"{key}: {rel} non disponibile sull'altro PC")
            return None
        sent[0] += len(data)
        return data

    def saves_apply(self, remote: dict, res: dict, get_remote=None) -> None:
        """Unisce i salvataggi dell'altro PC ai nostri, a tre stati: locale, remoto e ultima sincronizzazione nota.
        Se ha cambiato solo un lato vince quello; se hanno cambiato entrambi non si tocca il file locale e la
        versione remota va tra le copie del gioco."""
        c = conf(self.cfg)
        state = self._saves_state()
        rname = str(remote.get("pc_name") or remote.get("pc") or "altro PC")[:60]
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        sent = [0]
        for key in self._saves_keys(c):
            g = (remote.get("games") or {}).get(key)
            if not isinstance(g, dict):
                continue
            title = str(g.get("title") or self.saves_title(key))[:200]
            rfiles = g.get("files") if isinstance(g.get("files"), dict) else {}
            lfiles, warn = self.saves_files(key, title)
            res["warnings"].extend(warn)
            local = {rel: f for f, rel in lfiles}
            dirs = self._saves_dirs(key, title)
            base = state.get(key) if isinstance(state.get(key), dict) else {}
            now: dict[str, str] = {}
            for rel in sorted(set(rfiles) | set(local)):
                if not _safe_rel(rel):  # manifest di un altro PC: non ci si fida dei percorsi
                    res["warnings"].append(f"{title}: percorso scartato dal manifest di {rname} («{str(rel)[:80]}»)")
                    continue
                lp = local.get(rel)
                r = rfiles[rel] if isinstance(rfiles.get(rel), dict) else {}
                rh = str(r.get("sha1") or "")
                lh = _file_sha(lp) if lp else ""
                b = str(base.get(rel) or "")
                if lh == rh or not rh or (lp and rh == b):
                    # allineati, oppure c'e' solo qui, oppure ha cambiato solo questo PC: resta com'e' e la nostra
                    # versione si pubblica a fine giro; negli altri casi si prende quella dell'altro o e' conflitto
                    if lh == rh:  # contenuti uguali: il conflitto (se c'era) e' risolto
                        (state.get(CONFLICTS) or {}).pop(f"{key}\t{rel}", None)
                        now[rel] = lh
                    elif lp and rh == b:  # solo questo PC: la base avanza quando l'altro conferma il contenuto
                        now[rel] = b
                    else:
                        now[rel] = lh
                    continue
                try:
                    size = int(r.get("size") or 0)
                except (TypeError, ValueError):
                    size = 0
                data = self._saves_fetch(key, rel, size, get_remote, res, sent)
                if data is None:
                    now[rel] = lh
                    continue
                if lp and lh != b:  # hanno cambiato tutti e due: nessuna sovrascrittura
                    cid = f"{key}\t{rel}"
                    if (state.get(CONFLICTS) or {}).get(cid) != rh:  # la versione remota si archivia una volta sola
                        try:
                            out = SV._store(self.cfg, key, title, {SV._mkey(lp): (None, data)},
                                            reason=f"conflitto {rname} {when}", dirs=[])
                            SV.set_meta(self.cfg, key, out.name, note=f"{title} (conflitto {rname} {when})")
                            state.setdefault(CONFLICTS, {})[cid] = rh
                        except (OSError, ValueError) as e:  # copia non archiviata: il file resta comunque intatto
                            res["warnings"].append(f"{title}: conflitto non archiviato ({e})")
                    res["conflicts"].append(f"{title}: {rel} (conflitto con {rname}, {when})")
                    now[rel] = b  # base invariata: il conflitto resta finche' i due file non combaciano
                    continue
                if lp:  # la versione che si perde resta tra le copie del gioco
                    SV.backup(self.cfg, key, title, [lp], reason="sync", name=title)
                    root, dest = next((d for d in dirs if _inside(d, lp)), lp.parent), lp
                else:
                    spot = self._saves_dest(local, dirs, rel)
                    if spot is None:
                        res["warnings"].append(f"{title}: {rel} non scritto (cartella dei salvataggi non trovata)")
                        now[rel] = lh
                        continue
                    root, dest = spot
                if not _write_file(root, dest, data):
                    res["warnings"].append(f"{title}: {rel} non scritto (percorso non valido)")
                    now[rel] = lh
                    continue
                now[rel] = _file_sha(dest)
                res["updated"].append(f"{key}/{rel}")
            if now:
                state[key] = now
        self._write_saves_state(state)

    def fetch_save(self, peer: dict, key: str, rel: str) -> bytes | None:
        """Byte di un file di salvataggio di un altro PC: una richiesta per file, con il suo tetto."""
        r = request(peer["url"], "/api/sync/saves/file", {"key": key, "rel": rel},
                    token=peer["token"], fp=peer.get("fp"))
        data = r.get("data") or ""
        return base64.b64decode(data) if data else None

    def run(self) -> dict:
        if self.busy:
            return self.last
        self.busy = True
        res = {"time": time.time(), "folder": None, "peers": {}}
        try:
            c = conf(self.cfg)
            if self._is_playing():  # l'emulatore o il gioco riscriverebbero i salvataggi mentre li copiamo
                res["saves"] = {"skipped": "gioco in esecuzione"}
            if c.get("folder"):
                try:
                    res["folder"] = self.via_folder(Path(c["folder"]))
                except Exception as e:  # cartella scollegata, OneDrive in pausa...: si riprova al prossimo giro
                    res["folder"] = {"error": f"{type(e).__name__}: {e}"}
                if self.saves_enabled():
                    try:
                        res["saves"] = self.saves_folder(Path(c["folder"]))
                    except Exception as e:  # i dati personali si sincronizzano lo stesso
                        res["saves"] = {"error": f"{type(e).__name__}: {e}"}
            for peer in c.get("peers") or []:
                try:
                    res["peers"][peer["id"]] = self.via_peer(peer)
                except Exception as e:  # PC spento o fuori dalla rete
                    res["peers"][peer["id"]] = {"error": f"{type(e).__name__}: {e}"}
        finally:
            self.busy = False
            self.last = res
        return res

    # ------------------------------------------------------------ cartella condivisa
    def via_folder(self, folder: Path) -> dict:
        if not folder.is_dir():
            raise FileNotFoundError(f"Cartella non raggiungibile: {folder}")
        root, me = folder / DIR, self.pc()["pc_id"]
        incoming: dict = {}
        if root.is_dir():
            for pdir in root.iterdir():
                for f in pdir.glob("*.json") if pdir.is_dir() else []:
                    if f.stem != me:
                        try:
                            incoming.setdefault(f"{pdir.name}\t{f.stem}", json.loads(f.read_text(encoding="utf-8")))
                        except (OSError, ValueError):
                            continue  # file a meta' scrittura sull'altro PC: si legge al prossimo giro
        merged = {}
        for k, b in incoming.items():
            merged[k] = self.receive({k.split("\t")[0]: b})
        for pid, b in self.bundles().items():
            d = root / pid
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / f".{me}.tmp"
            tmp.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, d / f"{me}.json")
        return {"ok": True, "from": len(incoming), "merged": merged}

    # ------------------------------------------------------------ PC in rete locale
    def via_peer(self, peer: dict) -> dict:
        on, body = self.saves_enabled(), {"pc": self.pc(), "bundles": self.bundles()}
        if on:
            body["saves"] = self.saves_manifest()
        r = request(peer["url"], "/api/sync/exchange", body, token=peer["token"], fp=peer.get("fp"))
        out = {"ok": True, "merged": self.receive(r.get("bundles") or {})}
        if on:
            res = {"ok": True, "from": 1 if isinstance(r.get("saves"), dict) else 0,
                   "updated": [], "conflicts": [], "warnings": []}
            if res["from"]:
                self.saves_apply(r["saves"], res, get_remote=lambda k, rel: self.fetch_save(peer, k, rel))
            out["saves"] = res
        return out

    # ------------------------------------------------------------ salvataggi nella cartella condivisa
    def saves_folder(self, folder: Path) -> dict:
        """Salvataggi nella cartella condivisa: ognuno scrive la propria sottocartella e legge quelle degli altri."""
        root = folder / DIR / SAVES_DIR
        me, res = self.pc()["pc_id"], {"ok": True, "from": 0, "updated": [], "conflicts": [], "warnings": []}
        remotes: dict[str, dict] = {}
        if root.is_dir():
            for f in sorted(root.glob("*.json")):
                if f.stem == me:
                    continue
                try:
                    remotes[f.stem] = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue  # file a meta' scrittura sull'altro PC: si legge al prossimo giro
        res["from"] = len(remotes)
        for pid, rem in remotes.items():
            if isinstance(rem, dict):
                self.saves_apply(rem, res, get_remote=lambda k, rel, d=root / pid:
                                        _read_published(d / SV.folder(self.cfg, k).name, rel))
        self._saves_publish(root, res)
        return res

    def _saves_publish(self, root: Path, res: dict):
        """La nostra versione dei file e il nostro manifest nella nostra sottocartella, poi lo stato aggiornato."""
        me, manifest = self.pc()["pc_id"], self._saves_manifest()[0]
        base = root / me
        for key, g in manifest.get("games", {}).items():
            entries = g.get("files") or {}
            for f, rel in self.saves_files(key, g.get("title") or key)[0]:
                dest = base / SV.folder(self.cfg, key).name / rel
                if entries.get(rel, {}).get("sha1") and entries[rel]["sha1"] == _file_sha(dest):
                    continue  # gia' pubblicato
                if not _write_file(base, dest, None, src=f):
                    res["warnings"].append(f"{key}: {rel} non pubblicato")
        root.mkdir(parents=True, exist_ok=True)
        tmp = root / f".{me}.tmp"
        tmp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, root / f"{me}.json")
        state = self._saves_state()
        for key, g in manifest.get("games", {}).items():
            cur = state.get(key) if isinstance(state.get(key), dict) else {}
            # quello che l'unione ha gia' deciso non si sovrascrive: un conflitto resta tale finche' i file non combaciano
            state[key] = {**{rel: (v or {}).get("sha1") or "" for rel, v in (g.get("files") or {}).items()}, **cur}
        self._write_saves_state(state)


def request(url: str, path: str, body: dict, token: str | None = None, fp: str | None = None) -> dict:
    """POST HTTPS al PC remoto. Il certificato (autofirmato) si verifica con l'impronta salvata all'abbinamento,
    prima di mandare il token: un altro computer sulla rete non puo' fingersi quel PC."""
    u = urlparse(url)
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE  # verifica fatta qui sotto con l'impronta
    conn = http.client.HTTPSConnection(u.hostname, u.port or 8766, context=ctx, timeout=60)
    try:
        conn.connect()
        got = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
        if fp and got != fp:
            raise RuntimeError("Il certificato del PC remoto e' cambiato: abbinalo di nuovo")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Cookie"] = f"gs_phone={token}"
        conn.request("POST", path, json.dumps(body), headers)
        r = conn.getresponse()
        data = json.loads(r.read() or b"{}")
        if r.status >= 400:
            raise RuntimeError(data.get("detail") or f"HTTP {r.status}")
        data["_fp"] = got
        return data
    finally:
        conn.close()
