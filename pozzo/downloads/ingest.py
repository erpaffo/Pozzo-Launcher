"""Dopo l'estrazione: i file giocabili vanno nella cartella console della libreria e compaiono subito come posseduti.

Regola delle cartelle (stessa logica della scansione normale, nessuna registrazione speciale):
- cartella console gia' usata dallo scanner (scanner.find_platform_dirs, anche annidata o assegnata a mano), meglio
  se sotto la cartella ROM principale; altrimenti `<cartella ROM>/<nome canonico della console>` (platforms.detect lo
  riconosce); solo senza cartella ROM: `<download>/Giochi` registrata come cartella ROM aggiuntiva.
- file singolo: direttamente nella cartella console (console dir_games come la Switch: sempre in una cartella col nome
  del gioco, riusata se contiene gia' la base/l'aggiornamento/i DLC dello stesso Title ID); disco a piu' file (.cue/.gdi/.m3u + tracce): in una sottocartella
  col nome del gioco (i nomi dentro non cambiano, i riferimenti restano validi); console dir_games (Switch, PS3...) con
  piu' file (base + aggiornamenti): tutti in una sottocartella, che lo scanner legge come un solo gioco.
- Il gioco entra in libreria subito con l'aggiunta rapida (library.incremental: solo la sua riga, senza scansione ne'
  ricostruzione, anche con un altro lavoro in corso) e la ricerca dei dati parte in background; se non riesce, si
  chiede la scansione normale della console e si aspetta al massimo `timeout` secondi.
- La voce online del catalogo non si "converte": alla ricostruzione scompare perche' il suo titolo e' posseduto
  (build._catalog_entries) e il gioco locale prende il suo posto; il titolo si ricorda in cache (kv "downloaded")
  cosi' il collegamento regge anche se il nome del file estratto non somiglia a quello dell'archivio.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
from pathlib import Path

from fastapi import HTTPException

from .. import config as C, platforms as P, switchfiles as SF
from ..cache import Cache
from ..library import incremental
from ..scanner import find_platform_dirs

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _platform(pid: str | None) -> P.Platform | None:
    p = P.PLATFORMS.get(pid or "")
    return p if p and not p.virtual else None


def _dirs(cfg, pid: str) -> list[Path]:
    try:
        return [d for q, d in find_platform_dirs(cfg) if q.id == pid]
    except FileNotFoundError:
        return []


def target_dir(cfg, platform_id: str, downloads_dir: str | Path | None = None) -> Path:
    """Cartella console dove mettere i giochi scaricati (creata se manca)."""
    p = _platform(platform_id)
    if not p:
        raise ValueError(f"Console non valida: {platform_id!r}")
    dirs = _dirs(cfg, p.id)
    if dirs:
        return min(dirs, key=lambda d: (not d.is_relative_to(Path(cfg.roms)), len(d.parts)))  # sotto la ROM principale, la piu' vicina
    if Path(cfg.roms).is_dir():
        d = Path(cfg.roms) / _BAD.sub("", p.name if P.detect(p.name) is p else p.id)  # nome che lo scanner riconosce
    else:
        root = Path(downloads_dir or Path.home() / "Downloads" / "Pozzo") / "Giochi"
        d = root / _BAD.sub("", p.name)
        if root not in [Path(x) for x in cfg.extra_roms]:
            root.mkdir(parents=True, exist_ok=True)
            C.save_settings(cfg, paths={"extra_roms": [*map(str, cfg.extra_roms), str(root)]})
    d.mkdir(parents=True, exist_ok=True)
    return d


def _norm(p) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(p))))


def _refs(f: Path) -> list[Path]:
    """File citati da un .cue/.gdi/.m3u (tracce) che stanno accanto ad esso."""
    ext = f.suffix.lower()
    if ext not in (".cue", ".gdi", ".m3u"):
        return []
    try:
        txt = f.read_text("utf-8", "replace")
    except OSError:
        return []
    if ext == ".m3u":
        names = [x.strip() for x in txt.splitlines() if x.strip() and not x.startswith("#")]
    elif ext == ".cue":
        names = [a or b for a, b in re.findall(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', txt, re.I | re.M)]
    else:  # gdi: "n lba tipo settori nome offset"
        names = [a or b for a, b in re.findall(r'^\s*\d+\s+\d+\s+\d+\s+\d+\s+(?:"([^"]+)"|(\S+))', txt, re.M)]
    return [f.parent / n for n in names if (f.parent / n).is_file()]


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while (c := path.with_name(f"{path.stem} ({n}){path.suffix}")).exists():
        n += 1
    return c


def _name(stem: str) -> str:
    """Nome della cartella di un gioco: il titolo senza [Title ID][v..] e (regione)."""
    return _BAD.sub("", re.sub(r"\s*[\[(][^\])]*[\])]", "", stem)).strip()


def _tid_folder(dest: Path, files: list[Path]) -> Path | None:
    """Cartella gia' in `dest` con un file dello stesso gioco (base gia' presente, ora arriva l'aggiornamento o il DLC)."""
    keys = {k for f in files if (k := SF.family(f.name)) is not None}
    if keys:
        for d in sorted(dest.iterdir()):
            if d.is_dir() and any(SF.family(x.name) in keys for x in d.iterdir() if x.is_file()):
                return d
    return None


def _place(p: P.Platform, files: list[Path], dest: Path) -> list[Path]:
    """Sposta i file nella cartella console (regola in cima). Ritorna i percorsi giocabili nuovi.
    shortcut: i file accanto non citati dal .cue/.gdi/.m3u (.sbi, .sub...) non seguono; da estendere se servono."""
    folder = (_tid_folder(dest, files) or _unique(dest / (_name(files[0].stem) or "Gioco"))) if p.dir_games else None
    out = []
    for f in files:
        members = list(dict.fromkeys([f, *_refs(f)]))
        sub = folder or (_unique(dest / (_BAD.sub("", f.stem).strip() or "Gioco")) if len(members) > 1 else None)
        base = sub or dest
        base.mkdir(parents=True, exist_ok=True)
        for m in members:
            if not m.exists():
                continue  # gia' spostato (citato da due insiemi)
            t = _unique(base / m.name)
            shutil.move(str(m), str(t))
            if m == f:
                out.append(t)
    return out


def _lib_match(lib, paths: list[Path]) -> dict | None:
    """Gioco posseduto della libreria con uno di questi file (o con la cartella che li contiene)."""
    want = [_norm(p) for p in paths]
    with lib.lock:
        for g in lib.games:
            if g.get("store"):
                continue
            for f in g["files"]:
                n = _norm(f)
                if any(w == n or w.startswith(n + os.sep) for w in want):
                    return g
    return None


def _busy(ctx) -> bool:
    job, state = getattr(ctx, "job", None), getattr(ctx, "state", None) or {}
    return bool(state.get("building")) or (job is not None and job["current"].status == "running")


def _fast(ctx, pid: str, placed: list[Path], drop: str | None, say) -> dict | None:
    """Aggiunta rapida (library.incremental): il gioco o None se non si puo' (si passa alla scansione normale)."""
    if not hasattr(ctx.lib, "add_games"):
        return None
    try:
        keys = incremental.add_games(ctx.cfg, pid, placed, drop)
        if keys:
            ctx.lib.add_games(keys, drop)
    except Exception as e:  # noqa: BLE001 - la scansione normale resta
        say(f"Aggiornamento rapido non riuscito ({type(e).__name__}: {e}): provo con la scansione", "warn")
        return None
    return _lib_match(ctx.lib, placed) if keys else None


def _scrape(ctx, g: dict, say) -> None:
    """Ricerca dati e copertina del solo gioco nuovo, in background (come «Cerca dati mancanti» nel dettaglio)."""
    try:
        ctx.api_scan_start({"game": g["id"]})
        say("Ricerca di dati e copertina avviata in background")
    except HTTPException as e:
        if e.status_code != 409:
            raise
        say("Un altro lavoro e' in corso: dati e copertina si cercano con la prossima ricerca", "warn")


def _recheck(ctx, pid: str, placed: list[Path], drop: str | None, say, poll: float) -> None:
    """Un lavoro era in corso: se ricostruisce la libreria da una scansione fatta prima dell'ingest, il gioco sparisce.
    A lavoro finito lo si rimette (e si avvia la ricerca dei dati)."""
    t0 = time.time()
    while _busy(ctx) and time.time() - t0 < 3600:
        time.sleep(poll)
    if not _lib_match(ctx.lib, placed) and (g := _fast(ctx, pid, placed, drop, say)):
        _scrape(ctx, g, say)


def ingest(ctx, game_id: int | None, platform: str | None, files: list[Path | str], timeout: float = 60,
           poll: float = 1.0, on_status=None) -> dict:
    """Mette in libreria i giochi scaricati ed estratti (da chiamare in un thread).
    `ctx`: cfg, lib, events, api_scan_start; opzionali job/state (lavori in corso) e downloads (cartella download).
    `on_status(msg, level="info")`: cosa sta facendo, per il log del download. Dopo `timeout` secondi senza il gioco in
    libreria (solo scansione normale) smette di aspettare: pending, la scansione continua da sola.
    Ritorna {"ok", "game_id" (id del gioco posseduto, None se non ancora in libreria), "files" (percorsi finali),
    "error"? (ok False), "pending"? (file a posto ma libreria non ancora aggiornata)}.
    Emette `game_downloaded` {game_id, from_id (la voce online), title, key, files} appena il gioco e' in libreria."""
    say = on_status or (lambda *a: None)
    cfg, lib = ctx.cfg, ctx.lib
    online = None
    if game_id is not None:
        try:
            online = lib.get(game_id)
        except HTTPException:
            pass
    p = _platform(platform or (online or {}).get("platform"))
    if not p:
        return {"ok": False, "game_id": None, "files": [], "error": f"Console non valida: {platform!r}"}
    exts = {"." + e for e in p.exts}
    good = [Path(f) for f in files if Path(f).is_file() and Path(f).suffix.lower() in exts]
    if not good:
        return {"ok": False, "game_id": None, "files": [],
                "error": f"Nessun file giocabile per {p.name} (servono: {', '.join(p.exts)})"}
    mgr = getattr(ctx, "downloads", None)
    dest = target_dir(cfg, p.id, mgr.settings().get("dir") if mgr else None)
    scanned = _dirs(cfg, p.id)
    # file gia' sotto una cartella console scansionata (es. download dentro la cartella ROM): restano dove sono
    say(f"Cartella della console: {dest}")
    placed = good if all(any(Path(_norm(f)).is_relative_to(_norm(d)) for d in scanned) for f in good) else _place(p, good, dest)
    drop = online["key"] if online and online.get("store") == "online" else None
    if drop:  # il titolo della voce online resta "posseduto" alla ricostruzione
        c = Cache(cfg.cache)
        try:
            rec = [r for r in (c.kv_get("downloaded") or []) if (r.get("pid"), r.get("title")) != (p.id, online["title"])]
            c.kv_set("downloaded", [*rec, {"pid": p.id, "title": online["title"],
                                           "paths": [str(x) for x in placed] + [str(x.parent) for x in placed]}][-500:])
        finally:
            c.close()
    t0 = time.time()
    g = _lib_match(lib, placed)
    fast = False
    if not g:
        say("Aggiungo alla libreria: aggiornamento rapido…")
        busy = _busy(ctx)
        g = _fast(ctx, p.id, placed, drop, say)
        fast = bool(g)
        if g and busy:
            threading.Thread(target=_recheck, args=(ctx, p.id, placed, drop, say, max(poll, 1.0)), daemon=True).start()
    if not g:
        say("Aggiungo alla libreria: scansione della console…")
        started = seen = False
        last = t0
        while not (g := _lib_match(lib, placed)) and time.time() - t0 < timeout:
            busy = _busy(ctx)
            seen = seen or busy
            if not started and not busy:
                try:
                    ctx.api_scan_start({"platforms": [p.id]})
                    started = True
                    say("Aggiungo alla libreria: scansione avviata, aggiorno la libreria…")
                except HTTPException as e:  # 409: un altro lavoro in corso, si riprova
                    if e.status_code != 409:
                        raise
            elif started and ((seen and not busy) or time.time() - t0 > 60 and not seen):
                g = _lib_match(lib, placed)  # lavoro finito e il file non c'e': non arrivera' da solo
                break
            if time.time() - last >= 10:
                last = time.time()
                say("Aggiungo alla libreria: " + ("aggiornamento in corso…" if started else "attendo un altro lavoro in corso…"))
            time.sleep(poll)
    out = {"ok": True, "game_id": g["id"] if g else None, "files": [str(x) for x in placed]}
    if not g:
        return {**out, "pending": True}
    ctx.events.emit("game_downloaded", {"game_id": g["id"], "from_id": game_id, "title": g["title"], "key": g["key"],
                                        "files": out["files"]})
    if fast:
        _scrape(ctx, g, say)
    return out
