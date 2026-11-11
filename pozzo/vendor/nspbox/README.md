# NSP-Box (moduli headless)

Copia parziale di https://github.com/smarkyie/NSP-Box, licenza MIT (`LICENSE.txt`, testo originale).

- Commit: `c3de7a120cb4b3c86cd5b5bcdbf5f33bbffe0fc0` (cartella `src/`).
- File copiati: `container_format.py`, `verify_format.py`, `nup_format.py`, `nup_tools.py`, `engine.py`, `dlc.py`, `artwork.py`.
- Non copiati: interfaccia tkinter (`app.py`, `ui.py`, `*_panel.py`, `*_dialog.py`, `ambient.py`, `startup_notice.py`), `nup_cli.py`, patch dell'emulatore (`emulator_*.py`, `native/`) e `compatibility.py` (scrive chiavi segnaposto nella cartella dell'emulatore: Pozzo non tocca le chiavi).
- Modifiche rispetto all'originale, solo queste:
  - import tra moduli resi relativi (`from . import ...`) in `nup_tools.py`, `engine.py`, `dlc.py`;
  - in `engine.py` tolti `from compatibility import placeholder_text` e la funzione `placeholder_keys()`.
- Dipendenze: Pillow, zstandard (BSD-3-Clause).
- Usato solo da `pozzo/switch2pack.py`. Per aggiornare: ricopia i file dal nuovo commit e riapplica le modifiche qui sopra.

Lavora solo su contenuti già in chiaro: nessuna chiave, nessuna decifratura, nessun file Nintendo incluso.
