"""Schermate su macOS: argv di screencapture/afplay (subprocess finto), mappa della scorciatoia
Windows -> keycode/flag di macOS e confronto puro. Nessun tap vero, nessuna cattura vera."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import macos  # noqa: E402
from pozzo.library import screens as S  # noqa: E402


def _fake_runner(calls, write_on):
    from PIL import Image

    def run(argv, **kw):
        calls.append(argv)
        if len(calls) in write_on:
            Image.new("RGB", (64, 48)).save(argv[-1], "PNG")
    return run


def test_cattura_finestra_e_ripieghi():
    old = macos.window_id_for_pid, macos.frontmost_pid
    try:
        macos.frontmost_pid = lambda: 77
        macos.window_id_for_pid = lambda pid: 4242 if pid == 77 else None
        calls = []
        img = S._mac_capture(runner=_fake_runner(calls, {1}))
        assert calls[0][:5] == ["screencapture", "-x", "-o", "-l", "4242"] and len(calls) == 1 and img.size == (64, 48)
        assert not Path(calls[0][-1]).exists(), "file temporaneo rimosso"
        calls = []  # finestra non catturata -> tutto lo schermo
        S._mac_capture(runner=_fake_runner(calls, {2}))
        assert calls[1][:2] == ["screencapture", "-x"] and len(calls[1]) == 3
        calls = []  # pid esplicito del gioco, senza finestra -> solo schermo intero
        S._mac_capture(pid=5, runner=_fake_runner(calls, {1}))
        assert len(calls) == 1 and calls[0][:2] == ["screencapture", "-x"] and len(calls[0]) == 3
        calls = []  # nessun file: permesso Registrazione schermo mancante -> errore come su Windows
        try:
            S._mac_capture(runner=_fake_runner(calls, set()))
            raise AssertionError("cattura vuota accettata")
        except OSError:
            pass
        assert len(calls) == 2 and not Path(calls[0][-1]).exists()
    finally:
        macos.window_id_for_pid, macos.frontmost_pid = old
    print("ok  screencapture: finestra, schermo intero, permesso mancante")


def test_beep_afplay():
    calls, old_p, old_plat = [], S.subprocess.Popen, sys.platform
    try:
        S.subprocess.Popen = lambda argv, **kw: calls.append(argv)
        sys.platform = "darwin"
        S.beep()
    finally:
        S.subprocess.Popen, sys.platform = old_p, old_plat
    assert calls == [["afplay", "/System/Library/Sounds/Pop.aiff"]]
    print("ok  suono con afplay in background")


def test_mappa_scorciatoia():
    assert S.mac_hotkey("ctrl+shift+s") == (0x01, 0x40000 | 0x20000)
    assert S.mac_hotkey("win+alt+p") == (0x23, 0x100000 | 0x80000)
    assert S.mac_hotkey("f10") == (0x6D, 0) and S.mac_hotkey("f20") == (0x5A, 0)
    assert S.mac_hotkey("ctrl+5") == (0x17, 0x40000) and S.mac_hotkey("printscreen") == (0x69, 0)
    assert S.mac_hotkey("f24") is None and S.mac_hotkey("ctrl+boh") is None and S.mac_hotkey("") is None
    want = S.mac_hotkey("ctrl+shift+s")
    caps = 0x10000  # Bloc Maiusc e altri bit non contano
    assert S.mac_match(0x01, 0x40000 | 0x20000 | caps | 0x100, want)
    assert not S.mac_match(0x01, 0x40000, want), "manca Shift"
    assert not S.mac_match(0x01, 0x40000 | 0x20000 | 0x100000, want), "Cmd in piu'"
    assert not S.mac_match(0x02, 0x40000 | 0x20000, want), "tasto diverso"
    print("ok  scorciatoia -> keycode/flag di macOS")


def test_fuori_da_mac_invariato():
    old = sys.platform
    try:
        sys.platform = "linux"
        assert S.Hotkey("ctrl+shift+s", lambda: None).start() is False
    finally:
        sys.platform = old
    print("ok  Linux: nessuna scorciatoia globale")


if __name__ == "__main__":
    test_cattura_finestra_e_ripieghi()
    test_beep_afplay()
    test_mappa_scorciatoia()
    test_fuori_da_mac_invariato()
    print("TUTTI I TEST OK")
