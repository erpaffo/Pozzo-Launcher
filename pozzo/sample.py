"""Gioco d'esempio al primo avvio: Doom (Chocolate Doom 3.1.0 + Freedoom 0.13.0), nel pacchetto di Windows.

Lo zip (pozzo/data/esempi/doom.zip) si estrae nella cartella dati e il gioco entra in libreria come gioco PC aggiunto a mano.
Lo fa una sola volta: se lo togli dalla libreria non torna. Licenze: FREEDOOM-COPYING.txt e COPYING.html dentro lo zip.
"""

from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

from . import config as C

ZIP = Path(__file__).parent / "data" / "esempi" / "doom.zip"
VERSION = "1"  # cambia se lo zip cambia: al prossimo avvio il gioco viene estratto di nuovo
WINDOWS = sys.platform == "win32"  # chocolate-doom.exe: solo Windows


def seed(cfg, user, dest: Path | None = None) -> bool:
    """Estrae Doom e lo aggiunge alla libreria. True se l'ha aggiunto ora."""
    done = dict(cfg.app.get("esempio") or {})
    if not WINDOWS or done.get("doom") == VERSION or not ZIP.is_file():
        return False
    dest = dest or C.app_data_dir() / "esempi" / "doom"
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(tmp)  # zipfile tiene fuori i percorsi con «..» o assoluti
    shutil.rmtree(dest, ignore_errors=True)
    tmp.rename(dest)
    user.add_manual("Doom (Freedoom)", str(dest / "chocolate-doom.exe"), ["-iwad", str(dest / "freedoom1.wad")],
                    str(dest), "game")
    C.save_settings(cfg, app={"esempio": {**done, "doom": VERSION}})
    cfg.app["esempio"] = {**done, "doom": VERSION}
    return True
