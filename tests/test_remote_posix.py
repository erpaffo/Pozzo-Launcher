"""Sunshine, microfono e batteria pad fuori da Windows: comandi finti, nessun hardware."""
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.remote import dualsense as D, mic, sunshine as S  # noqa: E402

# --- sunshine (macOS/brew e Linux/systemd)
calls = []


def fake_run(table):
    def run(cmd):
        calls.append(cmd)
        for k, (rc, out) in table.items():
            if k in " ".join(cmd):
                return subprocess.CompletedProcess(cmd, rc, out, "")
        return subprocess.CompletedProcess(cmd, 1, "", "")
    return run


saved = S._run, S._brew, sys.platform, S.shutil.which
S._brew = lambda: "/x/brew"
S._run = fake_run({"info sunshine": (0, '[{"running": true, "loaded": true}]'), "services start": (0, "")})
S.sys.platform = "darwin"
assert S.service_state() == "running" and S.start_mode() == "auto" and S.start_service()
assert ["/x/brew", "services", "start", "sunshine"] in calls
S._run = fake_run({"info sunshine": (0, '[{"running": false, "loaded": false}]')})
assert S.service_state() == "stopped" and S.start_mode() == "manual"
S.sys.platform = "linux"
S.shutil.which = lambda n: "/bin/" + n
S._run = fake_run({"is-active": (0, "active\n"), "is-enabled": (1, "disabled\n"), "enable --now": (0, "")})
assert S.service_state() == "running" and S.start_mode() == "manual" and S.start_service()
S._run = fake_run({"is-active": (3, "unknown\n")})
assert S.service_state() == ""
S._run, S._brew, S.sys.platform, S.shutil.which = saved

# --- mic: Popen finto con una pipe vera (serve fileno per select)
sys.platform_saved = sys.platform
mic.sys.platform = "linux"
mic._player_cmd = lambda: ["fake"]
assert mic.devices() == ["default"] and mic.pick(["default"]) == 0
r, w = os.pipe()


class FakeProc:
    stdin = os.fdopen(w, "wb")
    terminated = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True


proc = FakeProc()
mic.subprocess.Popen = lambda *a, **k: proc
p = mic.Player(0)
assert p.play(b"\x01\x00\x02\x00") and os.read(r, 8) == b"\x01\x00\x02\x00"
assert not p.play(b"\x01")
p.close()
assert proc.terminated
mic._player_cmd = lambda: None
assert mic.devices() == []
mic.sys.platform = sys.platform_saved

# --- dualsense: ioreg e sysfs finti
D.sys.platform = "darwin"
out = plistlib.dumps([{"Product": "Keyboard"}, {"Product": "DualSense Wireless Controller", "BatteryPercent": 73}])
orig = subprocess.run
subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 0, out, b"")
b = D.read_battery()
subprocess.run = orig
assert b == {"present": True, "name": "DualSense", "percent": 73, "charging": False, "full": False}, b
D.sys.platform = "linux"
with tempfile.TemporaryDirectory() as t:
    d = Path(t) / "ps-controller-battery-aa"
    d.mkdir()
    (d / "capacity").write_text("40\n")
    (d / "status").write_text("Charging\n")
    D.SYSFS = t
    assert D.read_battery() == {"present": True, "name": "DualSense", "percent": 40, "charging": True, "full": False}
    D.SYSFS = str(Path(t) / "nope")
    assert D.read_battery() == {"present": False}
print("ok")
