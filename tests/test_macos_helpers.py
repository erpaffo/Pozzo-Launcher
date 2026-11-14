"""Helper macOS: no-op fuori da darwin, chiamate reali (non invasive) su Mac."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pozzo import macos  # noqa: E402

real = sys.platform
sys.platform = "linux"
try:
    macos._libs.clear()
    assert macos.osascript("return 1") is None
    assert macos.screen_size() is None
    assert macos.post_mouse(1, 1) is False
    assert macos.post_key(0, True) is False
    assert macos.ax_trusted() is False
    assert macos.frontmost_pid() is None
    assert macos.window_id_for_pid(1) is None
    assert macos._libs == {}  # nessun ctypes toccato
finally:
    sys.platform = real

if sys.platform != "darwin":
    print("SKIP: test macOS reali (non darwin)")
else:
    w, h = macos.screen_size()
    assert w > 0 and h > 0
    assert macos.osascript("return 1") == "1"
    assert isinstance(macos.ax_trusted(), bool)
    wid = macos.window_id_for_pid(os.getpid())
    assert wid is None or isinstance(wid, int)
    assert macos.post_mouse(0, 0, "bogus") is False  # input invalido, nessun evento
    # post_mouse/post_key reali non testati: muoverebbero il mouse dell'utente
print("ok")
