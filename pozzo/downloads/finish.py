"""Dopo il download: estrae gli archivi (anche a piu' parti), porta il gioco nella libreria e pulisce.

Gira in un thread appena un task e' completato (Manager.on_completed). Un archivio a piu' parti parte quando
l'ultimo volume e' arrivato: ogni volume e' un download a se', quindi ognuno rilancia il controllo.
"""
from __future__ import annotations

import re
import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from .. import platforms as P
from ..tools import space as TS, trash as TT
from ..matching import best
from . import extract as X, ingest as I, install
from .task import PAUSED, QUEUED, RUNNING, record_extract

_LOCK = threading.Lock()
_BUSY: set[str] = set()  # insiemi di volumi in estrazione adesso (due volumi finiti insieme non la fanno due volte)
_SEEN: set[str] = set()  # cartelle dove questo processo ha gia' estratto: li' gli avanzi non si toccano piu'

# Passi del post-download, in ordine. Stato in t.options["steps"]: todo | active | done | error, scritto solo da _step():
# e' da quello (piu' options["extracted"]) che si riparte dopo una chiusura a meta'. Ogni passo: fn(t, mgr, ctx, c) con
# c = stato condiviso tra i passi; ritorna False per fermare la catena (errore, o attesa di altri volumi).
STEPS: list[str] = []
_FN: dict = {}


def register_step(name: str, fn, dopo: str | None = None) -> None:
    """Aggiunge (o sostituisce) un passo; `dopo` = nome del passo che lo precede, senza: subito prima di «library»."""
    _FN[name] = fn
    if name not in STEPS:
        STEPS.insert(STEPS.index(dopo) + 1 if dopo in STEPS else STEPS.index("library") if "library" in STEPS else len(STEPS), name)


def _step(t, mgr, name: str, state: str) -> None:
    t.options.setdefault("steps", {})[name] = state
    mgr.store.save([t])  # subito su disco: e' cio' che si rilegge al prossimo avvio


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
    prev = t.options.pop("post_wait", None)  # messaggio dell'attesa precedente: _run lo rimette se si aspetta ancora
    try:
        _run(t, mgr, ctx, prev)
    except Exception as e:  # noqa: BLE001 - un errore qui non deve toccare il download, che e' finito
        t.fail_stage()
        t.log(f"Dopo il download: {type(e).__name__}: {e}", "error")
    finally:
        if not t.options.get("post_wait"):  # in attesa: la fase resta come messaggio e post_done lo mette chi finisce
            t.phase = ""
            t.options["post_done"] = True
        mgr.store.save([t])
        mgr._poke()


def _wait(t, mgr, prev, msg: str) -> bool:
    """Il post-download aspetta (volumi o task del gruppo): messaggio una volta sola, lo ricontrolla Manager._tick."""
    t.options["post_wait"] = msg
    t.phase = msg
    if prev != msg:
        t.log(msg, "warn")
    mgr._poke()
    return False


def _group_open(t, mgr) -> list:
    """Altri task dello stesso gruppo (gioco + aggiornamenti + DLC) non ancora scaricati."""
    t.classify()
    if not t.group:
        return []
    out = []
    for x in list(getattr(mgr, "tasks", {}).values()):
        if x is not t and x.status in (QUEUED, RUNNING, PAUSED):
            x.classify()
            if x.group == t.group:
                out.append(x)
    return out


def _passwords(t, mgr, s) -> list:
    """Password da provare: quelle del pacchetto (task o gruppo) e poi quelle comuni; [None] se nessuna."""
    own = [t.options.get("password")]
    if t.group:
        own += [x.options.get("password") for x in list(getattr(mgr, "tasks", {}).values()) if x.group == t.group]
    own = list(dict.fromkeys(p for p in own if isinstance(p, str) and p))
    common = [p for p in s.get("passwords") or [] if isinstance(p, str) and p]
    return list(dict.fromkeys([*own, *common])) or [None]


def _extract_pw(first, dest, pws, t, **kw):
    for i, pw in enumerate(pws):
        try:
            return X.extract(first, dest, password=pw, log=t.log, **kw)
        except (X.PasswordRequired, X.BadPassword):
            if i == len(pws) - 1:
                raise
            t.log("Password non valida per questo archivio: provo la successiva")  # mai la password nel log


def _run(t, mgr, ctx, prev=None) -> None:
    s = mgr.settings()
    steps = t.options.setdefault("steps", {})
    if steps.get("library") == "done":  # chiuso tra l'ultimo passo e post_done: non c'e' altro da fare
        return
    if prev and not any(f.exists() for f in _files(t)):  # il set l'ha estratto un altro task del gruppo
        for sid in ("extract", "library", "data"):
            t.set_stage(sid, "done")
        t.log("Gestito insieme agli altri file del gruppo")
        return
    t.classify()
    rule = I.match_rule(s.get("rules"), t.name, t.group_title, log=t.log)
    plat = _platform(ctx, t)
    if rule and P.PLATFORMS.get(rule.get("platform") or ""):
        plat = P.PLATFORMS[rule["platform"]]
    c = SimpleNamespace(s=s, plat=plat, rule=rule, prev=prev, games=[], loose=[], firsts={}, done=[],
                        game_id=t.options.get("game_id"),
                        resumed=steps.get("extract") == "active")  # estrazione interrotta dalla chiusura del launcher
    for name in list(STEPS):
        if steps.get(name) == "done" and name != "extract":  # extract si rifa': ritrova la cartella gia' estratta
            continue
        _step(t, mgr, name, "active")
        if _FN[name](t, mgr, ctx, c) is False:
            st = next((x["state"] for x in t.stages if x["id"] == name), "")
            _step(t, mgr, name, "error" if st == "error" else "todo")
            return
        _step(t, mgr, name, "done")
    for sid in ("convert", "verify"):  # niente da fare = saltato (la UI non lo mostra)
        if t._stage(sid)["state"] in ("todo", "active"):
            t.set_stage(sid, "skip")


def _s_extract(t, mgr, ctx, c) -> bool:
    s, plat = c.s, c.plat
    exts = {"." + e.lower().lstrip(".") for e in plat.exts} if plat else set()
    for f in (f for f in _files(t) if f.is_file()):
        if X.is_archive(f):
            first = _first(f)
            if first:
                c.firsts[str(first)] = first
        else:
            c.loose.append(f)
            if f.suffix.lower() in exts:
                c.games.append(f)
    extracted = t.options.setdefault("extracted", {})  # primo volume -> cartella estratta: non si rifa' alla ripresa

    if c.firsts and s.get("auto_extract"):  # tutto il gruppo scaricato e tutti i volumi presenti, prima di estrarre
        if open_ := _group_open(t, mgr):
            return _wait(t, mgr, c.prev, f"In attesa degli altri file del gruppo ({len(open_)} da scaricare)")
        for first in c.firsts.values():
            if missing := X.missing_volumes(first):
                return _wait(t, mgr, c.prev, f"Mancano {', '.join(missing)}: l'estrazione parte quando ci sono tutti i volumi")
    pws = _passwords(t, mgr, s)
    for first in c.firsts.values():
        if not s.get("auto_extract"):
            t.log("Archivio scaricato: estrazione automatica disattivata nelle impostazioni")
            break
        with _LOCK:
            if str(first) in _BUSY:
                continue
            _BUSY.add(str(first))
            fresh = str(first.parent) not in _SEEN
            _SEEN.add(str(first.parent))
        try:
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

            if (prev := extracted.get(str(first))) and Path(prev).is_dir():
                out = [Path(prev)]
                t.log(f"{first.name} era già estratto: riprendo da lì")
            else:
                if c.resumed and fresh:
                    X.clear_stale(first.parent)
                t.log(f"Estraggo {first.name}")
                t.set_stage("extract", "active", 0)
                t1 = time.time()
                out = _extract_pw(first, first.parent, pws, t, on_progress=progress)
                record_extract(sum(v.stat().st_size for v in group if v.exists()), time.time() - t1)
                extracted[str(first)] = str(out[0])
                mgr.store.save([t])
            t.set_stage("extract", "done")
            found = X.find_games(out[0], exts) if exts else []
            c.games += found
            c.done.append((out[0], group))
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
    return True


def _s_convert(t, mgr, ctx, c) -> bool:
    """Switch 2: porta i giochi estratti nel formato scelto (impostazioni: switch2_format). Mai perdere il file: si
    sostituisce l'originale solo a conversione riuscita; non supportato o errore -> avviso e si prosegue con l'originale."""
    fmt = str(c.s.get("switch2_format") or "nsp")
    if not c.plat or c.plat.id != "switch2" or fmt == "off" or not c.games:
        t.set_stage("convert", "skip")
        return True
    from .. import switch2pack as S
    if fmt == "folder":  # la libreria accetta file, non cartelle: da qui non si puo' ingerire
        t.log("Conversione Switch 2 in cartella saltata: usa lo strumento «Converti» nelle impostazioni", "warn")
        t.set_stage("convert", "skip")
        return True
    todo = [(g, k) for g in c.games if (k := S.detect_format(g)) and k != fmt]
    if not todo:
        t.set_stage("convert", "skip")
        return True
    ok, why = S.supported(ctx.cfg)
    if not ok:
        t.log(f"Conversione Switch 2 saltata: {why}", "warn")
        t.set_stage("convert", "skip")
        return True
    t.set_stage("convert", "active", 0)
    for g, _ in todo:
        t.phase = f"Converto {g.name}…"
        try:
            TS.check(TS.tree_size(g) * 2, g.parent)  # l'originale resta finche' il nuovo non e' pronto
            out = S.convert(g, fmt, g.parent, lambda d, n: (t.set_stage("convert", "active", d), mgr._poke()))
        except (S.SwitchPackError, InterruptedError, OSError) as e:
            t.log(f"Conversione di {g.name} non riuscita, tengo l'originale: {e}", "warn")
            continue
        try:
            TT.to_trash(g)  # recuperabile dal Cestino, mai cancellazione definitiva
        except OSError as e:
            t.log(f"Convertito in {out.name}, ma non riesco a spostare l'originale nel Cestino: {e}", "warn")
        c.games[c.games.index(g)] = out
        t.log(f"Convertito in {out.name}")
    t.phase = ""
    t.set_stage("convert", "done")
    return True


def _s_verify(t, mgr, ctx, c) -> bool:
    """Controlla lo SHA-256 dichiarato (options["sha256"]) del file scaricato. Il motore HTTP lo ha gia' fatto durante
    lo scarico (e mette in quarantena): qui servono gli altri motori, per un file solo."""
    want = str(t.options.get("sha256") or "").lower()
    files = [f for f in _files(t) if f.is_file()]
    if not want or t.type == "http" or len(files) != 1:
        t.set_stage("verify", "skip")
        return True
    from .. import ports  # pesante: import qui
    t.set_stage("verify", "active")
    t.phase = f"Verifico {files[0].name}…"
    mgr._poke()
    if ports._sha256(files[0]) != want:
        t.set_stage("verify", "error")
        t.log(f"SHA-256 diverso da quello atteso: {files[0].name}", "error")
        return False
    t.set_stage("verify", "done")
    t.log("SHA-256 verificato")
    return True


def _s_library(t, mgr, ctx, c) -> bool:
    s, plat, games, loose, done = c.s, c.plat, c.games, c.loose, c.done
    # repack PC: c'e' un setup da avviare. I file restano sul disco finche' l'installazione non e' finita
    if (plat is None or plat.id == "windows") and (setup := install.find_setup(
            [*loose, *(f for r, _ in done for f in r.rglob("*") if f.is_file())])):
        t.options["setup"] = {"exe": str(setup), "dir": str(setup.parent)}
        t.set_stage("library", "active", note="In attesa dell'installazione")
        t.log(f"Repack pronto: «📦 Installa» avvia {setup.name} e a fine installazione il gioco entra in libreria")
        return False

    game_id = c.game_id
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
        return False
    t0 = time.time()

    def status(msg, level="info"):  # passi dell'ingest nel log del download, con i secondi trascorsi
        msg = f"{msg} ({time.time() - t0:.0f} s)"
        t.log(msg, level)
        if not t.options.get("post_done"):  # un passo tardivo (thread di controllo) non deve riaccendere la fase
            t.phase = msg
            mgr._poke()

    status("Aggiungo alla libreria…")
    t.set_stage("library", "active")
    res = I.ingest(ctx, game_id, plat.id, games, on_status=status, rule=c.rule)
    if not res.get("ok"):
        t.set_stage("library", "error")
        t.log(f"Libreria: {res.get('error') or 'non riuscito'}", "error")
        return False
    _step(t, mgr, "library", "done")  # prima della pulizia: i file sono gia' spostati, rifarlo non li troverebbe
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
    return True


for _n, _f in (("extract", _s_extract), ("convert", _s_convert), ("verify", _s_verify), ("library", _s_library)):
    register_step(_n, _f)
