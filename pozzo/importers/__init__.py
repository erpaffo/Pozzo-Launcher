"""Importatori di libreria da altri launcher: giochi, tempo di gioco, preferiti, raccolte. MAI file di gioco.

Ogni formato e' una funzione `parse_*(path) -> list[record]` (modulo formats); `apply` li porta nei dati utente.
record = {"title", "playtime" (secondi), "favorite" (bool), "last_played" (epoch|0), "collections" [nomi],
          "exe" (percorso gia' esistente sul disco, opzionale), "scripts" (bool: la fonte ha script/comandi,
          mai importati: solo contati in `scripts_ignored` per avvisare l'utente)}"""

from __future__ import annotations

from pathlib import Path

MAX_BYTES = 64 * 1024 * 1024   # tetto per ogni file letto (database di migliaia di giochi: pochi MB)
MAX_GAMES = 100_000


class ImportError_(ValueError):
    """Percorso o file non valido: il messaggio e' per l'utente."""


def safe_file(path, suffixes: tuple[str, ...] = ()) -> Path:
    """File regolare esistente, non un link simbolico, entro MAX_BYTES e con estensione attesa."""
    p = Path(str(path or "").strip().strip('"'))
    if ".." in p.parts:
        raise ImportError_("path")
    if p.is_symlink() or not p.is_file():
        raise ImportError_("notfile")
    if suffixes and p.suffix.lower() not in suffixes:
        raise ImportError_("ext")
    if p.stat().st_size > MAX_BYTES:
        raise ImportError_("toobig")
    return p


def read_bytes(path, suffixes=()) -> bytes:
    return safe_file(path, suffixes).read_bytes()


def apply(user, lib, records: list[dict]) -> dict:
    """Abbina per titolo normalizzato ai giochi della libreria. Mai sovrascrive: il tempo di gioco sale solo se
    l'importato e' maggiore, i preferiti si aggiungono, le raccolte sono nuove raccolte personali."""
    from ..matching import normalize
    by_title: dict[str, list[str]] = {}
    for g in lib.games:
        if g.get("store") == "online":
            continue
        by_title.setdefault(normalize(g["title"]), []).append(g["key"])
    colls = {c["name"].lower(): s for s, c in user.collections().items() if c.get("custom")}
    out = {"matched": 0, "added": 0, "skipped": 0, "favorites": 0, "playtime": 0, "collections": 0,
           "scripts_ignored": sum(1 for r in records[:MAX_GAMES] if r.get("scripts"))}
    for r in records[:MAX_GAMES]:
        title = (r.get("title") or "").strip()
        keys = by_title.get(normalize(title)) if title else None
        if not keys:
            exe = r.get("exe")
            if title and exe and Path(exe).is_file():  # solo un collegamento al gioco, nessuna copia
                keys = [f"windows/manual:{user.add_manual(title, str(exe), [], str(Path(exe).parent))}"]
                out["added"] += 1
            else:
                out["skipped"] += 1
                continue
        else:
            out["matched"] += 1
        cur = user.games()
        for k in keys[:1]:
            if r.get("favorite") and not cur.get(k, {}).get("favorite"):
                user.set_flag(k, "favorite", 1)
                out["favorites"] += 1
            pt = float(r.get("playtime") or 0)
            if pt > (cur.get(k, {}).get("playtime") or 0):
                user.set_playtime(k, pt, float(r.get("last_played") or 0))
                out["playtime"] += 1
        for name in r.get("collections") or []:
            name = str(name).strip()[:80]
            if not name:
                continue
            slug = colls.get(name.lower())
            if not slug:
                slug = colls[name.lower()] = user.create_collection(name)
                out["collections"] += 1
            for k in keys[:1]:
                user.edit_membership(slug, k, "add")
    return out
