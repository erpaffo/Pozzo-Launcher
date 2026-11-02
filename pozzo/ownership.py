"""Chi vede quale gioco (profili sullo stesso PC).

Progetto, in 10 righe:
1. Libreria, metadati, copertine e cache.db sono UNA sola copia per PC: library.db e' l'unione delle fonti di tutti i profili.
2. La chiave del gioco non dipende dal profilo: lo stesso gioco in due fonti e' un solo record, con piu' proprietari.
3. Ogni gioco porta i proprietari: nessuno = condiviso (visibile a tutti), altrimenti l'elenco degli id profilo.
4. Cartelle ROM globali (cfg.roms, cfg.extra_roms) = condivise; la chiave "roms_extra" di un profilo (profilecfg) =
   sue. Una cartella aggiunta da due profili ha entrambi i proprietari; un file anche in una cartella condivisa e' condiviso.
5. Giochi a mano: colonna `profile` in manual_games (NULL = condiviso, anche le righe di prima della migrazione).
6. Store con account (Steam, Epic, GOG): ogni profilo ha la sua lista in cache (kv "store:<id>:<profilo>"; la chiave
   "store:<id>" e' del Principale). Un gioco installato sul PC e' condiviso; uno solo posseduto e' del profilo.
7. Store del sistema (Battle.net, Amazon, Xbox, Riot, Minecraft, port): della macchina = condivisi.
8. La ricostruzione scrive in library.db la tabella game_owners(key, owner) solo per i giochi NON condivisi.
9. Library.load() mette g["owners"] (lista) sui soli giochi non condivisi; visible(g, profilo) e' tutto qui.
10. /api/library e /api/library/patches filtrano con visible(): il profilo vede solo i suoi giochi e quelli condivisi.

Limiti noti: le altre rotte per id (scheda gioco, azioni) non controllano la visibilita' (l'id si ottiene solo dall'elenco).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import profilecfg as PC


def visible(game: dict, profile_id: str) -> bool:
    """Il gioco e' visibile al profilo? Senza proprietari (condiviso) si', altrimenti solo se il profilo e' tra loro."""
    o = game.get("owners")
    return not o or profile_id in o


def members(group: list[dict], profile_id: str) -> list[dict]:
    """Le versioni di un gioco visibili al profilo (se nessuna lo e', tutte: il gruppo non resta mai vuoto)."""
    return [g for g in group if visible(g, profile_id)] or group


def profile_roots(cfg) -> dict[Path, list[str]]:
    """Cartelle ROM proprie dei profili, {cartella: [profili]}, senza quelle gia' condivise (globali)."""
    shared = {Path(r) for r in [cfg.roms, *getattr(cfg, "extra_roms", [])] if r}
    out: dict[Path, list[str]] = {}
    for pid, lst in PC.values(cfg, "roms_extra").items():
        for x in lst if isinstance(lst, list) else []:
            p = Path(x)
            if p not in shared:
                out.setdefault(p, []).append(pid)
    return out


def visible_roots(cfg) -> list[tuple[Path, bool]]:
    """Cartelle ROM aggiuntive che il profilo attivo vede, [(cartella, propria?)]: prima le globali (di tutti), poi
    quelle proprie. Le cartelle degli altri profili non compaiono (nemmeno il percorso)."""
    out = [(Path(r), False) for r in getattr(cfg, "extra_roms", []) if r]
    own = PC.get(cfg, "roms_extra", [])
    out += [(Path(r), True) for r in (own if isinstance(own, list) else []) if r]
    return out


def file_owners(cfg, files: dict[str, list[str]]) -> dict[str, list[str]]:
    """{chiave: [profili]} per i giochi ROM che stanno solo in cartelle di profilo. Gli altri non compaiono (condivisi)."""
    prof = profile_roots(cfg)
    if not prof:
        return {}
    shared = [Path(r) for r in [cfg.roms, *getattr(cfg, "extra_roms", [])] if r]
    out = {}
    for key, paths in files.items():
        ps = [Path(f) for f in paths]
        if any(f.is_relative_to(r) for f in ps for r in shared):
            continue
        pids = sorted({pid for f in ps for r, lst in prof.items() if f.is_relative_to(r) for pid in lst})
        if pids:
            out[key] = pids
    return out


def apply(db, games: list[dict]) -> bool:
    """Library.load(): legge game_owners da library.db e mette g["owners"] sui giochi non condivisi (library.db di
    prima della tabella: tutto condiviso)."""
    try:
        rows = db.execute("SELECT key, owner FROM game_owners").fetchall()
    except sqlite3.Error:
        return False
    owners: dict[str, list[str]] = {}
    for k, o in rows:
        owners.setdefault(k, []).append(o)
    for g in games:
        if g["key"] in owners:
            g["owners"] = owners[g["key"]]
    return bool(owners)
