"""Elenco lettori ottici su macOS con output diskutil finti."""
import plistlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.tools.impl import dump as D

LIST = {"WholeDisks": ["disk4", "disk5"]}
INFO = {"disk4": {"OpticalDeviceType": "DVD-ROM", "VolumeName": "MYDISC", "TotalSize": 1000},
        "disk5": {"VolumeName": "USB", "TotalSize": 5}}


D._diskutil = lambda *a: LIST if a[0] == "list" else INFO[a[-1]]
D.sys = type("S", (), {"platform": "darwin"})
assert D.drives() == [{"id": "/dev/rdisk4", "label": "/dev/rdisk4 (MYDISC)"}]
assert D._volume("/dev/rdisk4") == "MYDISC"
assert D._estimate(None, {"drive": "/dev/rdisk4"}) == 1200
assert plistlib.loads(plistlib.dumps(LIST)) == LIST
print("ok")
