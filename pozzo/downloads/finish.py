"""Dopo il download: estrae gli archivi (anche a piu' parti), porta il gioco nella libreria e pulisce.

Gira in un thread appena un task e' completato (Manager.on_completed). Un archivio a piu' parti parte quando
l'ultimo volume e' arrivato: ogni volume e' un download a se', quindi ognuno rilancia il controllo.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from .. import platforms as P
from ..matching import best
from . import extract as X, ingest as I, install
from .task import record_extract

_LOCK = threading.Lock()
_BUSY: set[str] = set()  # insiemi di volumi in estrazione adesso (due volumi finiti insieme non la fanno due volte)


def _files(t) -> list[Path]:
    root = Path(t.save_path)
    if t.type == "torrent":
        return [root / f["name"] for f in t.options.get("files") or [] if f.get("priority")]
    return [root / t.name] if t.name else []


def _first(f: Path) -> Path | None:
    """Primo volume dell'insieme di cui `f` fa parte (o `f` stesso se e' un archivio singolo)."""
    if X.archive_group(f):
        return f
    for c in sorted(f.parent.iterdir()):
        g = X.archive_group(c) if c != f and X.is_archive(c) else None
        if g and f in g:
            return c
    return None


def _platform(ctx, t):
    gid = t.options.get("game_id")
    try:
        return P.PLATFORMS.get(ctx.lib.get(gid)["platform"]) if gid is not None else None
    except Exception:  # noqa: BLE001 - gioco non piu' in libreria: si estrae e basta
        return None


def _guess(ctx, t, files: list[Path]):
    """Download non nato da un gioco (link incollato nella pagina Download): console dalle estensioni dei file (se una
    sola le usa) e gioco online dal titolo del nome. Ritorna (console | None, id del gioco | None)."""
    by: dict[str, set[str]] = {}
    for p in P.PLATFORMS.values():
        if not p.virtual:
            for e in p.exts:
                by.setdefault("." + e.lower(), set()).add(p.id)
    own = {next(iter(s)) for f in files if len(s := by.get(f.suffix.lower(), ())) == 1}
    plat = P.PLATFORMS[own.pop()] if len(own) == 1 else None
    stem = re.sub(r"\.(part\d+|r\d+|z\d+|\d{3})$", "", Path(t.name or "").stem, flags=re.I)
    with ctx.lib.lock:
        online = [g for g in ctx.lib.games if g.get("store") == "online" and (not plat or g["platform"] == plat.id)]
    g, _ = best(stem, online, key=lambda g: g["title"], min_score=90) if stem else (None, 0)
    if g and not plat:
        plat = P.PLATFORMS.get(g["platform"])
    return plat, (g["id"] if g else None)


def run(t, mgr, ctx) -> None:
    try:
        _run(t, mgr, ctx)
    except Exception as e:  # noqa: BLE001 - un errore qui non deve toccare il download, che e' finito
        t.fail_stage()
        t.log(f"Dopo il download: {type(e).__name__}: {e}", "error")
    finally:
        t.phase = ""
        t.options["post_done"] = True
        mgr.store.save([t])
        mgr._poke()


def _run(t, mgr, ctx) -> None:
    s = mgr.settings()
    plat = _platform(ctx, t)
    exts = {"." + e.lower().lstrip(".") for e in plat.exts} if plat else set()
    games: list[Path] = []
    loose: list[Path] = []
    firsts: dict[str, Path] = {}
    for f in (f for f in _files(t) if f.is_file()):
        if X.is_archive(f):
            first = _first(f)
            if first:
                firsts[str(first)] = first
        else:
            loose.append(f)
            if f.suffix.lower() in exts:
                games.append(f)

    done: list[tuple[Path, list[Path]]] = []
    for first in firsts.values():
        if not s.get("auto_extract"):
            t.log("Archivio scaricato: estrazione automatica disattivata nelle impostazioni")
            break
        with _LOCK:
            if str(first) in _BUSY:
                continue
            _BUSY.add(str(first))
        try:
            missing = X.missing_volumes(first)
            if missing:
                t.log(f"Mancano {', '.join(missing)}: l'estrazione parte quando ci sono tutti i volumi", "warn")
                continue
            group = X.archive_group(first)
            last = [-1]

            def progress(d, total):
                pct = d * 100 // total if total else 0
                if pct != last[0]:
                    if pct // 10 > max(last[0], 0) // 10 and pct < 100:
                        t.log(f"Estrazione {pct // 10 * 10}%")
                    last[0] = pct
                    t.phase = f"Estraggo {first.name}… {pct}%"
                    t.set_stage("extract", "active", pct)
                    mgr._poke()

            t.log(f"Estraggo {first.name}")
            t.set_stage("extract", "active", 0)
            t1 = time.time()
            out = X.extract(first, first.parent, on_progress=progress, log=t.log)
            t.set_stage("extract", "done")
            record_extract(sum(v.stat().st_size for v in group if v.exists()), time.time() - t1)
            found = X.find_games(out[0], exts) if exts else []
            games += found
            done.append((out[0], group))
            t.options["placed"] = str(out[0])  # «Apri cartella» porta qui, non piu' all'archivio
            t.log(f"Estratto in {out[0].name}: {len(found)} file di gioco")
        except X.ArchiveError as e:
            t.set_stage("extract", "error")
            t.log(f"Estrazione non riuscita: {e}", "error")
        finally:
            with _LOCK:
                _BUSY.discard(str(first))
    t.phase = ""
    if t._stage("extract")["state"] in ("todo", "active"):  # niente da estrarre (non e' un archivio, o estrazione disattivata)
        t.set_stage("extract", "skip")

    # repack PC: c'e' un setup da avviare. I file restano sul disco finche' l'installazione non e' finita
    if (plat is None or plat.id == "windows") and (setup := install.find_setup(
            [*loose, *(f for r, _ in done for f in r.rglob("*") if f.is_file())])):
        t.options["setup"] = {"exe": str(setup), "dir": str(setup.parent)}
        t.set_stage("library", "active", note="In attesa dell'installazione")
        t.log(f"Repack pronto: «📦 Installa» avvia {setup.name} e a fine installazione il gioco entra in libreria")
        return

    game_id = t.options.get("game_id")
    if plat is None and (done or loose):  # link incollato a mano: la console si ricava da cio' che e' arrivato
        plat, gid = _guess(ctx, t, [*loose, *(f for r, _ in done for f in r.rglob("*") if f.is_file())])
        if plat:
            game_id = gid
            ex = {"." + e.lower() for e in plat.exts}
            games = [*(f for f in loose if f.suffix.lower() in ex), *(g for r, _ in done for g in X.find_games(r, ex))]
            t.log(f"Console riconosciuta: {plat.name}" + (" (gioco del catalogo trovato dal nome)" if gid is not None else ""))
    if not games or plat is None:
        t.set_stage("library", "error")
        if done and plat and not games:
            t.log(f"Nessun file di gioco per {plat.name} nell'archivio (servono: {', '.join(plat.exts)})", "warn")
        if done and plat is None:
            t.log(f"Estratto in {done[0][0]}: non capisco di che console sia, non lo aggiungo alla libreria "
                  "(scaricalo dalla scheda del gioco, o spostalo nella cartella ROM e fai una scansione)", "warn")
        return
    t0 = time.time()

    def status(msg, level="info"):  # passi dell'ingest nel log del download, con i secondi trascorsi
        msg = f"{msg} ({time.time() - t0:.0f} s)"
        t.log(msg, level)
        if not t.options.get("post_done"):  # un passo tardivo (thread di controllo) non deve riaccendere la fase
            t.phase = msg
            mgr._poke()

    status("Aggiungo alla libreria…")
    t.set_stage("library", "active")
    res = I.ingest(ctx, game_id, plat.id, games, on_status=status)
    if not res.get("ok"):
        t.set_stage("library", "error")
        t.log(f"Libreria: {res.get('error') or 'non riuscito'}", "error")
        return
    mgr.ctx = ctx  # per il controllo periodico dei task in attesa della scansione (Manager.mark_ready)
    if not res.get("pending"):  # il gioco e' giocabile. Dati e copertina li cerca una scansione in background che
        t.set_stage("library", "done")  # non segnala la fine: li diamo per fatti qui
        t.set_stage("data", "done")
    t.log("Nella libreria: " + ", ".join(Path(p).name for p in res.get("files") or []))
    if res.get("files"):
        t.options["placed"] = str(res["files"][0])
        with mgr.lock:
            mgr.store.save([t])
    if res.get("pending"):
        t.options["pending_files"] = res.get("files") or []
        t.set_stage("library", "active", note="In attesa della scansione")
        t.log("Il gioco e' a posto ma la libreria non si e' aggiornata in tempo: comparira' con la prossima scansione "
              "(«Cerca nuovi giochi» o aggiornamento libreria)", "warn")
    for folder, group in done:  # file messi a posto: l'archivio e la cartella d'appoggio non servono piu'
        if s.get("delete_archive", True):
            X.delete_archive_set(group)
        try:
            folder.rmdir()  # solo se vuota: il resto e' della persona
        except OSError:
            pass
