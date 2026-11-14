"""Touchpad e tastiera del telefono su macOS/Linux: backend finti, nessun evento reale."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo import macos  # noqa: E402
from pozzo.remote import keyboard, mouse  # noqa: E402

orig = sys.platform
try:
    # --- macOS
    sys.platform = "darwin"
    log = []
    macos.ax_trusted = lambda: True
    macos.screen_size = lambda: (1000, 500)
    macos.post_mouse = lambda x, y, b="move": log.append(("m", round(x), round(y), b)) or True
    macos.post_key = lambda k, d, f=0: log.append(("k", k, d, f)) or True
    mouse._mac_drag = lambda x, y: log.append(("drag", round(x), round(y))) or True
    assert mouse.screen_size() == (1000, 500)
    m = mouse.Mouse()
    assert m.send(1.0, 0.5, True) and log == [("m", 999, 250, "move"), ("m", 999, 250, "left_down")], log
    log.clear()
    m.send(0.0, 0.0, True)
    assert log == [("drag", 0, 0)], log  # tasto tenuto -> trascinamento
    log.clear()
    assert keyboard.press("shift_tab") and log == [("k", 56, True, 0x20000), ("k", 48, True, 0x20000),
                                                   ("k", 48, False, 0x20000), ("k", 56, False, 0x20000)], log
    log.clear()
    assert keyboard.press("left") and log[0] == ("k", 123, True, 0)
    assert not keyboard.press("hdr")  # nessun equivalente su mac
    macos.ax_trusted = lambda: False
    log.clear()
    assert not mouse.Mouse().send(0.5, 0.5) and not keyboard.press("enter") and not log
    try:
        keyboard.press("nope")
        raise SystemExit("ValueError attesa")
    except ValueError:
        pass

    # --- Linux
    sys.platform = "linux"
    calls = []
    keyboard.shutil.which = mouse.shutil.which = lambda n: "/x/xdotool"

    def run(cmd, **kw):
        calls.append(cmd[1:])
        return subprocess.CompletedProcess(cmd, 0, "800 600\n", "")
    keyboard.subprocess.run = mouse.subprocess.run = run
    assert mouse.screen_size() == (800, 600)
    calls.clear()
    assert mouse.Mouse().send(1.0, 0.0, True) and calls[1:] == [["mousemove", "799", "0"], ["mousedown", "1"]], calls
    calls.clear()
    assert keyboard.press("alt_tab") and calls == [["key", "--clearmodifiers", "alt+Tab"]]
finally:
    sys.platform = orig
print("ok")
