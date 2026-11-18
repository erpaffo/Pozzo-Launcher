"""Mod dei giochi PC della libreria da Thunderstore, con le dipendenze, nella cartella d'installazione del gioco.

Layout come r2modman per BepInEx: il pacchetto BepInExPack va nella radice del gioco, ogni altra mod in
BepInEx/plugins/<Owner-Name>/ (le cartelle standard dell'archivio nelle rispettive cartelle di BepInEx). Le mod che
non passano da BepInEx (MelonLoader e altri) non si installano: resta il link al sito. Lo stato (installed_mods, con
deps e auto = installata come dipendenza) sta nello userdata; archivi e backup in <dati app>/mods/<gioco>/<mod>/."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from . import config as C
from . import mods as M
from . import modsites as MS
from . import ports as PT

download = M.download  # sostituibile nei test: si risolve a ogni chiamata
_running = PT._running  # un processo usa la cartella del gioco


class ModError(ValueError):
    """Errore da mostrare all'utente: chiave i18n + parametri, la traduce la rotta."""

    def __init__(self, key: str, **kw):
        super().__init__(key)
        self.key, self.kw = key, kw


def _dl(*a, **k):
    return download(*a, **k)


def is_loader(mod_id: str) -> bool:
    """Il pacchetto di BepInEx (BepInEx-BepInExPack, denikson-BepInExPack_Valheim...)."""
    return mod_id.rsplit("-", 1)[-1].lower().startswith("bepinexpack")


def layout(mod_id: str, rel: str) -> str:
    """Percorso nel gioco di un file dell'archivio Thunderstore (relativo alla radice del gioco)."""
    parts = rel.split("/")
    if is_loader(mod_id):  # il pacchetto ha il loader dentro BepInExPack*/: va nella radice del gioco
        return "/".join(parts[1:]) if len(parts) > 1 and parts[0].lower().startswith("bepinexpack") else rel
    if len(parts) > 1 and parts[0].lower() == "bepinex":
        parts = parts[1:]
    head = parts[0].lower()
    if head == "config" and len(parts) > 1:
        return "BepInEx/config/" + "/".join(parts[1:])
    if head in ("plugins", "patchers", "core") and len(parts) > 1:
        return f"BepInEx/{head}/{mod_id}/" + "/".join(parts[1:])
    return f"BepInEx/plugins/{mod_id}/" + "/".join(parts)


def community(game: dict) -> str:
    return MS.thunderstore_for(game.get("title") or "", game.get("canonical") or "", platform=game.get("platform") or "")


def catalog(cache, slug: str) -> list[dict]:
    """Pacchetti della community Thunderstore (in cache come quelli dei port), i piu' scaricati prima."""
    return M.mod_list(cache, {"sources": [{"provider": "thunderstore", "sourceUrl": f"https://thunderstore.io/c/{slug}/"}]})


def game_dest(cfg, user, game: dict) -> M.Dest:
    """Dest del gioco: la sua cartella d'installazione, con lo stato nello userdata (comune ai profili)."""
    folder = game.get("install_dir") or ""
    if not folder or not Path(folder).is_dir():
        raise ModError("s.mods.gameNotInstalled")
    key, base = game["key"], C.settings_path(cfg).parent
    return M.Dest(Path(folder), "", base / "mods" / re.sub(r"[^\w.-]+", "_", key), base,
                  lambda: user.game_mods(key), lambda mods: user.set_game_mods(key, mods), layout)


def _check(dest: M.Dest):
    if _running(dest.root):
        raise ModError("s.mods.gameRunning")


def plan(index: dict, mod_id: str) -> list[str]:
    """Pacchetti per mod_id con tutte le dipendenze, le dipendenze prima; i cicli si fermano al primo ritorno.
    shortcut: si prende sempre l'ultima versione di ogni dipendenza, ignorando la minima dichiarata; basta finche'
    Thunderstore tiene compatibili le versioni nuove, altrimenti va scelta la versione dalla lista completa."""
    out, seen = [], set()

    def visit(i):
        if i in seen:
            return
        seen.add(i)
        if i not in index:
            raise ModError("s.mods.depMissing", mod=i)
        for d in index[i].get("deps") or []:
            visit(d)
        out.append(i)
    visit(mod_id)
    if not any(is_loader(i) for i in out):
        raise ModError("s.mods.unsupportedLoader")  # MelonLoader & co.: solo link
    return out


def installable(index: dict, mod_id: str) -> bool:
    try:
        return bool(plan(index, mod_id))
    except ModError:
        return False


def needed_by(mods: dict, mod_id: str, enabled_only: bool = False) -> list[str]:
    """Nomi delle mod installate che richiedono mod_id (solo quelle attive, con enabled_only).
    shortcut: due mod che si richiedono a vicenda restano bloccate, rimuovibili solo a mano; Thunderstore non ne ha."""
    return [r.get("name") or i for i, r in mods.items()
            if mod_id in (r.get("deps") or []) and (not enabled_only or r.get("enabled", True))]


def preview(cfg, user, game: dict, index: dict, mod_id: str) -> dict:
    """Cosa farebbe install(): pacchetti da scaricare, quelli gia' presenti e i file del gioco che verrebbero
    sostituiti (salvati nel backup). Scarica gli archivi in una cartella temporanea.
    shortcut: install() li riscarica; se pesa, tenere gli archivi dell'anteprima nella cartella della mod."""
    dest = game_dest(cfg, user, game)
    order = plan(index, mod_id)
    have = dest.load_state()
    todo = [i for i in order if i not in have or i == mod_id]
    owned = {f for r in have.values() for f in r.get("files") or []}
    over: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for n, i in enumerate(todo):
            arc = Path(tmp) / f"{n}.zip"
            _dl(index[i]["url"], arc, index[i].get("provider") or "thunderstore")
            over += [f for f in M.would_replace(dest, i, arc) if f not in owned and f not in over]
    pick = ("id", "name", "version")
    return {"install": [{k: index[i].get(k) for k in pick} for i in todo],
            "present": [{k: index[i].get(k) for k in pick} for i in order if i not in todo], "overwrite": over}


def install(cfg, user, game: dict, index: dict, mod_id: str, say=print, progress=None) -> dict:
    """Installa mod_id e le dipendenze mancanti (quelle disattivate si riattivano); mod_id si reinstalla se c'e'."""
    dest = game_dest(cfg, user, game)
    order = plan(index, mod_id)
    _check(dest)
    for n, i in enumerate(order):
        if progress:
            progress(n, len(order))
        have = dest.load_state()
        if i in have and i != mod_id:
            if not have[i].get("enabled", True):
                M.set_enabled(dest, i, True)
            continue
        if i in have:  # aggiornamento: via i file della versione di prima, poi quella nuova con il suo backup
            M.remove(dest, i)
        say(f"{index[i].get('name') or i} {index[i].get('version') or ''}".strip())
        M.install(dest, index[i], _dl)
        mods = dest.load_state()
        mods[i] = {**mods[i], "deps": index[i].get("deps") or [], "auto": i != mod_id}
        dest.save_state(mods)
    if progress:
        progress(len(order), len(order))
    return dest.load_state()


def _drop(dest: M.Dest, mod_id: str):
    deps = dest.load_state()[mod_id].get("deps") or []
    M.remove(dest, mod_id)
    for d in deps:  # dipendenze messe da noi e non piu' richieste da nessuno
        mods = dest.load_state()
        if d in mods and mods[d].get("auto") and not needed_by(mods, d):
            _drop(dest, d)


def remove(cfg, user, game: dict, mod_id: str) -> dict:
    dest = game_dest(cfg, user, game)
    mods = dest.load_state()
    if mod_id not in mods:
        raise KeyError(mod_id)
    if need := needed_by(mods, mod_id):
        raise ModError("s.mods.requiredBy", mods=", ".join(need))
    _check(dest)
    _drop(dest, mod_id)
    return dest.load_state()


def _enable(dest: M.Dest, mod_id: str, seen: set):
    if mod_id in seen:
        return
    seen.add(mod_id)
    mods = dest.load_state()
    for d in mods[mod_id].get("deps") or []:
        if d in mods:
            _enable(dest, d, seen)
    M.set_enabled(dest, mod_id, True)


def _disable(dest: M.Dest, mod_id: str):
    deps = dest.load_state()[mod_id].get("deps") or []
    M.set_enabled(dest, mod_id, False)
    for d in deps:
        mods = dest.load_state()
        if d in mods and mods[d].get("auto") and mods[d].get("enabled", True) and not needed_by(mods, d, True):
            _disable(dest, d)


def set_enabled(cfg, user, game: dict, mod_id: str, enabled: bool) -> dict:
    """Attivare una mod attiva anche le sue dipendenze; disattivarla e' vietato se una mod attiva la richiede."""
    dest = game_dest(cfg, user, game)
    mods = dest.load_state()
    if mod_id not in mods:
        raise KeyError(mod_id)
    if not enabled and (need := needed_by(mods, mod_id, enabled_only=True)):
        raise ModError("s.mods.requiredBy", mods=", ".join(need))
    _check(dest)
    if enabled:
        _enable(dest, mod_id, set())
    else:
        _disable(dest, mod_id)
    return dest.load_state()
