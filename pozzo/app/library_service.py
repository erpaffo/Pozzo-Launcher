"""Libreria in memoria (library.db + dati utente) e profilo attivo, usati da server e route."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections import defaultdict
from pathlib import Path

from fastapi import HTTPException

from .. import ownership as OW
from .. import profilecfg as PC
from ..library.userdata import UserData


class _ActiveUser:
    """Dati utente del profilo attivo: il server usa sempre questo oggetto, cambiare profilo cambia quello sotto.
    Il profilo e' per dispositivo: se la richiesta ha il cookie gs_profile (middleware, profilecfg.override) si usa
    quello, altrimenti (thread di sfondo, telefono, richieste senza cookie) il profilo del server, self.ud.
    shortcut: una partita gia' in corso quando si cambia profilo viene registrata sul profilo nuovo; per evitarlo
    il launcher dovrebbe tenere il profilo con cui e' partita."""

    def __init__(self, ud: UserData, user_of=None):
        self.ud, self.switches, self._of = ud, 0, user_of

    def _cur(self) -> UserData:
        pid = PC.active_override()
        return self._of(pid) if pid and self._of else self.ud

    def __getattr__(self, name):
        return getattr(self._cur(), name)

    @property
    def rev(self) -> int:  # cambia anche cambiando profilo: le pagine aperte ricaricano i dati
        return self._cur().rev + self.switches * 1_000_000


class Library:
    """Istantanea in memoria di library.db + dati utente."""

    # colonne servite solo per un gioco alla volta (game()/details()): fuori dalla memoria, ~550 MB su 160.000 giochi
    # (launch da solo ~230: le fonti di download del catalogo). Della descrizione resta il primo carattere: basta a
    # _missing() per sapere se c'e'.
    DETAIL_SQL = {"description": "substr(description, 1, 1) AS description",
                  **{c: f"NULL AS {c}" for c in ("store_pages", "origin", "ratings", "launch", "install_uri", "page",
                                                  "install_dir", "canonical", "crc", "md5", "sha1", "video_url")}}
    # valori ripetuti in migliaia di giochi: una sola copia di ogni stringa invece di una per gioco
    SHARED = ("platform", "store", "region", "developer", "publisher", "release_date", "players", "content")

    def __init__(self, cfg):
        self.cfg = cfg
        self.path = Path(cfg.cache) / "library.db"
        self.games: list[dict] = []
        self.by_id: dict[int, dict] = {}
        self.by_key: dict[str, dict] = {}
        self.groups: dict[str, list[dict]] = defaultdict(list)  # vuoti al primo avvio (libreria non ancora creata)
        self.auto: dict[str, dict] = {}
        self.has_owners = False  # c'e' almeno un gioco non condiviso (profili): serve filtrare per profilo
        self.built_at = 0.0
        self.lock = threading.RLock()
        self.full = threading.Event()  # impostato quando ci sono anche i giochi del catalogo online
        # giochi cambiati senza ricostruire la libreria (copertine appena trovate o scaricate): le pagine aperte
        # chiedono solo quelli (/api/library/patches) invece di ricaricare 150.000 giochi
        self.meta_rev = 0
        self.patches: list[tuple[int, list[int]]] = []
        self.patch_base = 0  # chi e' rimasto indietro di qui ricarica tutto
        self._url_keys: dict | None = None  # pagina dello store -> chiave del gioco (anche le fonti in piu')

    def load(self, online: bool = True):
        """online=False: solo i giochi posseduti (avvio rapido); il catalogo online si carica dopo."""
        if not self.path.exists():
            self.full.set()
            return
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        cols = ", ".join(self.DETAIL_SQL.get(c, c) for c in (r[1] for r in db.execute("PRAGMA table_info(games)")))
        games = [dict(r) for r in db.execute(f"SELECT {cols} FROM games" + ("" if online else " WHERE store IS NOT 'online'"))]
        pool: dict[str, str] = {}
        share = pool.setdefault
        for g in games:
            for k in self.SHARED:
                if g.get(k).__class__ is str:  # get: library.db vecchie senza "content"
                    g[k] = share(g[k], g[k])
            g["genres"] = [share(x, x) for x in json.loads(g["genres"] or "[]")]
            g["files"] = json.loads(g["files"] or "[]")
            g["media"] = {share(k, k): v for k, v in json.loads(g["media"] or "{}").items()}
        auto: dict[str, dict] = {}
        for slug, name in db.execute("SELECT slug, name FROM collections"):
            auto[slug] = {"name": name, "keys": set()}
        for slug, key in db.execute("SELECT slug, key FROM collection_games"):
            auto[slug]["keys"].add(key)
        built = db.execute("SELECT v FROM meta WHERE k='built_at'").fetchone()
        has_owners = OW.apply(db, games)  # proprietari dei giochi non condivisi (profili)
        db.close()
        with self.lock:
            self.games = games
            self.by_id = {g["id"]: g for g in games}
            self.by_key = {g["key"]: g for g in games}
            self.groups: dict[str, list[dict]] = defaultdict(list)
            for g in games:
                self.groups[g["grp"]].append(g)
            self.auto, self.has_owners = auto, has_owners
            self.built_at = float(built[0]) if built else 0.0
            self.patches, self.patch_base, self._url_keys = [], self.meta_rev, None
        if online:
            self.full.set()

    def add_games(self, keys: list[str], drop_key: str | None = None):
        """Giochi appena messi in library.db da library.incremental: entrano in memoria senza ricaricare tutto.
        `drop_key`: la voce online che sostituiscono. Le pagine aperte si accorgono del cambio da built_at."""
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            cols = ", ".join(self.DETAIL_SQL.get(c, c) for c in (r[1] for r in db.execute("PRAGMA table_info(games)")))
            new = [dict(r) for k in keys if (r := db.execute(f"SELECT {cols} FROM games WHERE key=?", (k,)).fetchone())]
            for g in new:
                g["genres"], g["files"] = json.loads(g["genres"] or "[]"), json.loads(g["files"] or "[]")
                g["media"] = json.loads(g["media"] or "{}")
            has_owners = OW.apply(db, new)
            built = db.execute("SELECT v FROM meta WHERE k='built_at'").fetchone()
        finally:
            db.close()
        with self.lock:
            old = self.by_key.pop(drop_key, None) if drop_key else None
            if old:
                self.games.remove(old)
                self.by_id.pop(old["id"], None)
                self.groups[old["grp"]].remove(old)
                if not self.groups[old["grp"]]:
                    del self.groups[old["grp"]]  # un gruppo vuoto romperebbe i conteggi per console
                self._url_keys = None
            for g in new:
                if cur := self.by_key.get(g["key"]):  # gia' presente: solo i file sono cambiati
                    cur["files"] = g["files"]
                    continue
                self.games.append(g)
                self.by_id[g["id"]] = g
                self.by_key[g["key"]] = g
                self.groups[g["grp"]].append(g)
            self.has_owners = self.has_owners or has_owners
            self.built_at = float(built[0]) if built else time.time()

    def touch(self, ids: list[int]):
        """Segna dei giochi come cambiati: le pagine aperte li ridisegnano al prossimo controllo (ogni 3 s)."""
        if not ids:
            return
        with self.lock:
            self.meta_rev += 1
            self.patches.append((self.meta_rev, list(ids)))
            if len(self.patches) > 2000:
                del self.patches[:-2000]
                self.patch_base = self.patches[0][0] - 1

    def patch_store_meta(self, found: dict) -> int:
        """Copertine e descrizioni appena lette dagli store online, subito in libreria (memoria e library.db) senza
        ricostruirla: riempiono solo i vuoti, con la stessa regola della ricostruzione. Ritorna i giochi cambiati."""
        from ..library.build import apply_store_meta
        if not found or not self.path.exists():
            return 0
        cols = ("description", "developer", "publisher", "genres", "players", "release_date", "year", "size", "media")
        changed: list[int] = []
        db = sqlite3.connect(self.path, timeout=10)
        try:
            if self._url_keys is None:
                keys: dict[str, str] = {}
                for key, launch in db.execute("SELECT key, launch FROM games WHERE store='online'"):
                    for s in (json.loads(launch or "{}").get("sources") or []):
                        keys.setdefault(s.get("url"), key)
                self._url_keys = keys
            for url, meta in found.items():
                g = self.by_key.get(self._url_keys.get(url))
                row = g and db.execute(f"SELECT {', '.join(cols)} FROM games WHERE id=?", (g["id"],)).fetchone()
                if not row:
                    continue
                e = dict(zip(cols, row))
                e["genres"], e["media"] = json.loads(e["genres"] or "[]"), json.loads(e["media"] or "{}")
                before = json.dumps(e, sort_keys=True)
                apply_store_meta(e, meta)
                if json.dumps(e, sort_keys=True) == before:
                    continue
                db.execute(f"UPDATE games SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
                           (*(json.dumps(e[c], ensure_ascii=False) if c in ("genres", "media") else e[c] for c in cols),
                            g["id"]))
                with self.lock:
                    g.update({c: e[c] for c in cols if c != "description"})
                    g["description"] = e["description"][:1] if e["description"] else e["description"]  # come DETAIL_SQL
                changed.append(g["id"])
            db.commit()
        finally:
            db.close()
        self.touch(changed)
        return len(changed)

    def get(self, gid: int) -> dict:
        g = self.by_id.get(gid)
        if not g:
            raise HTTPException(404, "Gioco non trovato")
        return g

    def details(self, gid: int) -> dict:
        """Le colonne lasciate fuori dalla memoria (vedi DETAIL_SQL), lette da library.db per un solo gioco."""
        db = sqlite3.connect(self.path)
        out = dict.fromkeys(self.DETAIL_SQL)
        try:
            # library.db di una versione vecchia puo' non avere una colonna (md5/sha1): si leggono quelle presenti
            have = {r[1] for r in db.execute("PRAGMA table_info(games)")}
            keys = [k for k in self.DETAIL_SQL if k in have]
            row = db.execute(f"SELECT {', '.join(keys)} FROM games WHERE id=?", (gid,)).fetchone() if keys else None
            if row:
                out.update(zip(keys, row))
        except sqlite3.OperationalError:
            pass
        finally:
            db.close()
        out["launch"] = json.loads(out["launch"] or "{}")
        return out

    def game(self, gid: int) -> dict:
        """Il gioco con tutte le colonne (una lettura da library.db): per le azioni su un singolo gioco."""
        return {**self.get(gid), **self.details(gid)}
