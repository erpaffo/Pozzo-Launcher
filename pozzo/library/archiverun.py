"""«Archivi senza estrazione fissa»: il gioco (o la ROM) resta un .zip/.7z/.rar, si estrae in una cartella
temporanea all'avvio e la si cancella a fine partita.

I file nuovi o cambiati durante la partita (salvataggi, config) si copiano prima in `run_overlay/<chiave>/`
accanto ai dati utente e si riapplicano all'estrazione successiva. Se la copia fallisce la cartella
temporanea NON si cancella (si perderebbero i dati): resta, marcata, e l'utente viene avvisato.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from pathlib import Path

from ..downloads import extract as X

log = logging.getLogger(__name__)

KEEP = ".pozzo-keep"  # cartella conservata perche' la copia dei file e' fallita


class ArchiveRunError(Exception):
    """Errore con messaggio in italiano per l'utente."""


def enabled(profile: dict | None, path) -> bool:
    return bool(((profile or {}).get("auto") or {}).get("archive")) and Path(path).is_file() and X.is_archive(path)


def temp_root(cfg) -> Path:
    custom = (cfg.app.get("archive_run") or {}).get("dir")
    if custom:
        return Path(custom)
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "Pozzo" / "run" if base else Path(cfg.cache) / "run"


def _safe(key: str) -> str:
    return re.sub(r"[^\w.-]+", "_", key).strip(".") or "_"


def _snap(root: Path) -> dict[str, tuple[int, int]]:
    # shortcut: i file cancellati dal gioco non si rilevano (solo nuovi/cambiati), estendere se serve
    out = {}
    for f in root.rglob("*"):
        if f.is_file():
            st = f.stat()
            out[f.relative_to(root).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


class Run:
    def __init__(self, cfg, data_dir: Path, key: str, archive):
        self.archive = Path(archive)
        self.dir = temp_root(cfg) / _safe(key)
        self.overlay = Path(data_dir) / "run_overlay" / _safe(key)
        self.root: Path | None = None
        self.before: dict = {}

    def prepare(self, on_status=lambda m: None, cancelled=lambda: False) -> Path:
        """Estrae (controllando lo spazio) e riapplica i file salvati; ritorna la cartella estratta."""
        if (self.dir / KEEP).exists():
            raise ArchiveRunError(f"Una partita precedente ha lasciato dei file da recuperare in {self.dir}: "
                                  "copiali altrove e cancella la cartella, poi riprova")
        shutil.rmtree(self.dir, ignore_errors=True)
        try:
            self.root = X.extract(self.archive, self.dir, cancelled=cancelled,
                                  on_progress=lambda d, t: on_status(f"Estrazione di {self.archive.name}… {d * 100 // max(t, 1)}%"))[0]
        except X.ArchiveError as e:
            shutil.rmtree(self.dir, ignore_errors=True)
            raise ArchiveRunError(str(e)) from e
        if self.overlay.is_dir():
            for f in self.overlay.rglob("*"):
                if f.is_file():
                    dst = self.root / f.relative_to(self.overlay)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst)
        self.before = _snap(self.root)
        return self.root

    def finish(self) -> str | None:
        """Copia i file cambiati nell'overlay e cancella la cartella. Ritorna un avviso se la cartella e' rimasta."""
        if self.root is None:
            shutil.rmtree(self.dir, ignore_errors=True)
            return None
        try:
            for rel, sig in _snap(self.root).items():
                if self.before.get(rel) != sig:
                    dst = self.overlay / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(self.root / rel, dst)
        except Exception as e:  # noqa: BLE001 - qualunque errore: i file dell'utente non si toccano
            log.warning("copia dei file della partita fallita: %s", e)
            try:
                (self.dir / KEEP).touch()
            except OSError:
                pass
            return f"Impossibile salvare i file della partita ({e}): cartella conservata in {self.dir}"
        shutil.rmtree(self.dir, ignore_errors=True)
        return None
