"""Notifiche fuori da Windows: osascript su macOS, notify-send su Linux; rotta permessi."""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import config, notify  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402

calls = []
ok = lambda cmd, **k: calls.append(cmd) or SimpleNamespace(returncode=0, stdout="")

with mock.patch.object(sys, "platform", "darwin"), mock.patch("pozzo.macos._darwin", return_value=True):
    assert notify._send_native('Ti"tolo', 'a\\b "c"', runner=ok)
    assert calls[-1][-1] == 'display notification "a\\\\b \\"c\\"" with title "Ti\\"tolo"', calls[-1]
with mock.patch.object(sys, "platform", "linux"), mock.patch("shutil.which", return_value="/usr/bin/notify-send"):
    assert notify.available() and notify._send_native("T", "B", runner=ok)
    assert calls[-1] == ["/usr/bin/notify-send", "--", "T", "B"]
with mock.patch.object(sys, "platform", "linux"), mock.patch("shutil.which", return_value=None):
    assert not notify.available() and not notify._send_native("T", "B", runner=ok)
with mock.patch.object(sys, "platform", "win32"):
    assert notify.available()  # Windows: percorso invariato (thread + Shell_NotifyIcon)

tmp = Path(tempfile.mkdtemp())
cfg = config.Config(cache=tmp, output=tmp / "out", roms=tmp / "roms")
cfg.config_path = tmp / "config.toml"
c = TestClient(create_app(cfg))
r = c.get("/api/platform/permissions").json()
assert r["platform"] == sys.platform and (r["accessibility"] is None) == (sys.platform != "darwin"), r
print("ok")
