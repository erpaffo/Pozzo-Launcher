"""Controllo automatico degli aggiornamenti degli emulatori (pozzo/app/routes/emulators_extra.py).

Nessuna rete: check_updates, install e notify sono sostituiti da finti che registrano le chiamate.
Esegui: python tests/test_emu_autoupdate.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import config, emuinstall as EI, notify as N  # noqa: E402
from pozzo.app.routes import emulators_extra as E  # noqa: E402

AGGIORNAMENTI = [
    {"id": "dolphin", "name": "Dolphin", "current": "1", "latest": "2", "update": True},
    {"id": "pcsx2", "name": "PCSX2", "current": "3", "latest": "3", "update": False},
]


def _giro(tmp: Path, mode):
    (tmp / "config.toml").write_text(f'[paths]\nroms = "{(tmp / "roms").as_posix()}"\n'
                                     f'cache = "{(tmp / "cache").as_posix()}"\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    if mode is not None:
        cfg.app["emu_autoupdate"] = mode
    installati, avvisi = [], []
    with mock.patch.object(EI, "check_updates", create=True, return_value=AGGIORNAMENTI) as check, \
            mock.patch.object(EI, "install", create=True, side_effect=lambda c, emu, **kw: installati.append(emu)), \
            mock.patch.object(N, "send", side_effect=lambda c, titolo, testo="", action=None: avvisi.append(testo)):
        trattati = E.autoupdate_pass(cfg)
    return check.called, installati, avvisi, trattati


def test_modalita_aggiornamenti(tmp: Path):
    controllati, installati, avvisi, _ = _giro(tmp, "notify")
    assert controllati and installati == [] and avvisi == ["Aggiornamento disponibile: Dolphin 2"], (installati, avvisi)

    controllati, installati, avvisi, _ = _giro(tmp, "install")
    assert installati == ["dolphin"] and avvisi == ["Aggiornato Dolphin a 2"], (installati, avvisi)

    controllati, installati, avvisi, _ = _giro(tmp, "off")
    assert not controllati and installati == [] and avvisi == [], "off: nessun controllo, nessuna azione"

    # emulatore aperto: install rifiuta, niente avviso di guasto, si riprova il giorno dopo
    with mock.patch.object(EI, "install", create=True, side_effect=EI.EmulatorRunning("chiudi dolphin prima di aggiornarlo")):
        cfg = config.load(tmp / "config.toml")
        cfg.app["emu_autoupdate"] = "install"
        avvisi = []
        with mock.patch.object(EI, "check_updates", create=True, return_value=AGGIORNAMENTI), \
                mock.patch.object(N, "send", side_effect=lambda c, t, b="", a=None: avvisi.append(b)):
            E.autoupdate_pass(cfg)
        assert avvisi == [], avvisi
    print("ok  aggiornamenti: notify avvisa, install installa, off non fa nulla, emulatore aperto saltato")


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        test_modalita_aggiornamenti(Path(t))
    print("TUTTI I TEST OK")


if __name__ == "__main__":
    main()
