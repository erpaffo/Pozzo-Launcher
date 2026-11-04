"""Gioca da disco veloce: copia del gioco su SSD, avvio dalla copia, pulizia a fine partita.

Le copie vivono in root(cfg) (di default cache/fastcopy), marcata da ensure_root() con il file
`.pozzo-fastcopy`: purge_stale() svuota una root solo se si chiama 'fastcopy' o se e' marcata,
cosi' non tocca cartelle non nostre.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

MARKER = ".pozzo-fastcopy"
CHUNK = 8 * 1024 * 1024
_PROGRESS_MIN_S = 0.25  # al massimo ~4 aggiornamenti al secondo
_MB = 1024 * 1024
_GB = 1024**3


class FastCopyError(Exception):
    """Errore con messaggio in italiano, mostrato all'utente."""


def root(cfg) -> Path:
    """Cartella delle copie: dir personalizzata in app.fastcopy, altrimenti cache/fastcopy."""
    custom = (cfg.app.get("fastcopy") or {}).get("dir")
    return Path(custom) if custom else Path(cfg.cache) / "fastcopy"


def ensure_root(cfg) -> Path:
    """Crea root(cfg) e la marca come nostra (anche una cartella personalizzata con un altro nome)."""
    r = root(cfg)
    r.mkdir(parents=True, exist_ok=True)
    (r / MARKER).touch()
    return r


def same(a: Path, b: Path) -> bool:
    """La copia a corrisponde all'originale b: stessi file (siblings inclusi), dimensioni e date (copystat le
    conserva). Una copia interrotta o un gioco aggiornato da allora non corrispondono."""
    def sig(p: Path):
        p = Path(p)
        return sorted((str(f.relative_to(p.parent)), f.stat().st_size, int(f.stat().st_mtime)) for f in _entries(p)[1])
    try:
        return sig(a) == sig(b)
    except OSError:
        return False


def _entries(src: Path) -> tuple[list[Path], list[Path]]:
    """Cartelle e file da copiare. Per un file: anche i siblings (stesso nome senza estensione)."""
    if src.is_file():
        return [], [p for p in src.parent.iterdir() if p.is_file() and p.stem == src.stem]
    items = list(src.rglob("*"))
    return [src] + [p for p in items if p.is_dir()], [p for p in items if p.is_file()]


def _check_space(dest_dir: Path, need: int) -> None:
    """Serve un margine del 5% sulla dimensione: si controlla il primo genitore esistente."""
    probe = dest_dir
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError as e:
        raise FastCopyError(f"Impossibile leggere lo spazio libero su {probe}: {e}") from e
    need = int(need * 1.05)
    if free < need:
        raise FastCopyError(
            f"Spazio insufficiente su {probe}: servono {need / _GB:.1f} GB, "
            f"mancano {(need - free) / _GB:.1f} GB"
        )


class _Progress:
    """Conteggio dei byte copiati: aggiornamenti limitati nel tempo e controllo di annullo."""

    def __init__(self, total: int, cb, cancel: threading.Event | None) -> None:
        self.total, self.done, self.cb, self.cancel = total, 0, cb, cancel
        self.last = -1e9

    def check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise FastCopyError("Copia annullata")

    def add(self, n: int) -> None:
        self.done += n
        now = time.monotonic()
        if self.cb and now - self.last >= _PROGRESS_MIN_S:
            self.last = now
            frac = min(self.done / self.total, 1.0) if self.total else 1.0
            self.cb(frac, f"Copia in corso: {self.done / _MB:.0f} di {self.total / _MB:.0f} MB")


class _Writer:
    """Destinazione di copyfileobj: controlla l'annullo e aggiorna il progresso a ogni blocco."""

    def __init__(self, fo, prog: _Progress) -> None:
        self.fo, self.prog = fo, prog

    def write(self, b: bytes) -> int:
        self.prog.check()
        n = self.fo.write(b)
        self.prog.add(len(b))
        return n


def _rm(p: Path) -> None:
    """Cancella file o cartella senza sollevare; riprova se Windows tiene un file aperto."""
    for tentativo in range(3):
        try:
            if p.is_dir() and not p.is_symlink() and not p.is_junction():  # un link si toglie, non si segue
                shutil.rmtree(p)
            else:
                p.unlink(missing_ok=True)
            return
        except FileNotFoundError:
            return
        except OSError:
            if tentativo < 2:
                time.sleep(0.5)


def _drop_if_empty(d: Path) -> None:
    """Toglie il marcatore e la cartella se non contiene altro."""
    try:
        if {p.name for p in d.iterdir()} <= {MARKER}:
            (d / MARKER).unlink(missing_ok=True)
            d.rmdir()
    except OSError:
        pass


def _inside(p: Path, r: Path) -> bool:
    """True se p sta dentro r (r escluso)."""
    return r.resolve() in p.resolve().parents


def _safe(r: Path) -> bool:
    """Rifiuta radici di disco, home e percorsi troppo corti; accetta solo cartelle 'fastcopy' o marcate."""
    rr = r.resolve()
    if rr.parent == rr or rr == Path.home().resolve() or len(rr.parts) < 3:
        return False
    return rr.name.lower() == "fastcopy" or (rr / MARKER).is_file()


def copy(src: Path, dest_dir: Path, on_progress=None, cancel=None) -> Path:
    """Copia src (file o cartella) dentro dest_dir (creata se manca) e restituisce dest_dir/src.name.

    Per un file copia anche i siblings nella stessa cartella (gioco.cue + gioco.bin, .m3u...).
    on_progress(frazione, testo) al massimo ~4 volte al secondo; cancel interrompe e pulisce.
    """
    src, dest_dir = Path(src), Path(dest_dir)
    if not src.exists():
        raise FastCopyError(f"File non trovato: {src}")
    dirs, files = _entries(src)
    total = sum(f.stat().st_size for f in files)
    _check_space(dest_dir, total)
    base = src.parent
    prog = _Progress(total, on_progress, cancel)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        for d in dirs:
            (dest_dir / d.relative_to(base)).mkdir(parents=True, exist_ok=True)
        for f in files:
            dst = dest_dir / f.relative_to(base)
            with open(f, "rb") as fi, open(dst, "wb") as fo:
                shutil.copyfileobj(fi, _Writer(fo, prog), CHUNK)
            shutil.copystat(f, dst)
    except FastCopyError:
        _cleanup(dest_dir, src, base, files)
        raise
    except OSError as e:
        _cleanup(dest_dir, src, base, files)
        raise FastCopyError(f"Copia fallita: {e.strerror or e}") from e
    if on_progress:
        on_progress(1.0, "Copia completata")
    return dest_dir / src.name


def _cleanup(dest_dir: Path, src: Path, base: Path, files: list[Path]) -> None:
    """Rimuove la copia parziale (file, siblings, cartella) e la destinazione se resta vuota."""
    for f in files:
        _rm(dest_dir / f.relative_to(base))
    _rm(dest_dir / src.name)
    _drop_if_empty(dest_dir)


def remove(path: Path, cfg=None) -> None:
    """Cancella la copia (file o cartella) e la cartella genitore se ora vuota. Non solleva mai.

    Con cfg non tocca nulla fuori da root(cfg); per un file cancella anche i siblings copiati con lui.
    """
    path = Path(path)
    try:
        r = root(cfg) if cfg is not None else None
        if r is not None and not _inside(path, r):
            return
        if r is not None and path.is_file():
            targets = [p for p in path.parent.iterdir() if p.is_file() and p.stem == path.stem]
        else:
            targets = [path]
        for p in targets:
            _rm(p)
        if r is not None and _inside(path.parent, r):
            _drop_if_empty(path.parent)
    except OSError:
        pass


def purge_stale(cfg) -> int:
    """All'avvio: cancella il contenuto di root(cfg) (copie rimaste da un crash). Restituisce le voci tolte."""
    r = root(cfg)
    try:
        if not r.is_dir() or not _safe(r):
            return 0
        voci = [v for v in r.iterdir() if v.name != MARKER]
    except OSError:
        return 0
    for v in voci:
        _rm(v)
    return sum(1 for v in voci if not v.exists())
