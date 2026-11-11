"""Il file prodotto da uno strumento diventa il file del gioco: i dati utente passano alla nuova chiave e l'originale,
se l'utente vuole, va nel Cestino. Il gioco resta in dashboard e libreria con note, ore e preferiti."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .. import platforms as P, relink as RL
from ..scanner import Game
from . import trash


def _old_key(cfg, old: Path) -> str | None:
    f = Path(cfg.cache) / "library.db"
    if not f.exists():  # libreria mai costruita: niente dati da spostare
        return None
    db = sqlite3.connect(f)
    try:
        for key, files in db.execute("SELECT key, files FROM games WHERE store IS NULL OR store=''"):
            if str(old) in [str(Path(x)) for x in json.loads(files or "[]")]:
                return key
    except sqlite3.OperationalError:
        pass
    finally:
        db.close()
    return None


def adopt(cfg, platform_id: str, old, new, move_old: bool) -> dict:
    """Ritorna {relinked, trashed}. L'originale è toccato solo dopo aver controllato il nuovo file e spostato i dati."""
    old, new = Path(old), Path(new)
    if not new.exists() or (new.is_file() and new.stat().st_size == 0):
        raise ValueError("il file prodotto non esiste o è vuoto: l'originale non viene toccato")
    if old.resolve() == new.resolve():
        raise ValueError("il nuovo file coincide con l'originale")
    plat = P.PLATFORMS.get(platform_id)
    out = {"relinked": False, "trashed": None}
    okey = _old_key(cfg, old)
    # shortcut: la chiave nuova è calcolata senza hash (nome+dimensione, giusta per i sistemi su disco);
    # per le cartucce con CRC i dati si riassociano al prossimo scan, da trattare se serve
    if okey and plat and plat.cd:
        nkey = Game(path=new, platform=plat, size=0 if new.is_dir() else new.stat().st_size, mtime=0,
                    is_dir=new.is_dir()).key
        if nkey != okey:
            RL.apply(cfg, [(okey, nkey, "", str(new))], log=lambda m: None)
        out["relinked"] = True
    if move_old:
        out["trashed"] = trash.to_trash(old)
    return out
