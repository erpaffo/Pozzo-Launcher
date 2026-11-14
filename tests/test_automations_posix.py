"""Automazioni portabili (fuori da Windows) e polling del primo piano con sorgente di PID finta."""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.library import automation as A, foreground as F

if sys.platform != "win32":
    errs = []
    s = A.Session({"kill": ["sleep"], "power": "performance"}, lambda w: {}, errs.append)
    p = subprocess.Popen(["sleep", "30"])
    log = []
    A.active_profile = lambda: "balanced"
    A.set_profile = log.append
    s.begin()
    s.end()
    assert p.wait(5) != 0 and not errs, errs
    assert log in ([], ["performance", "balanced"]), log  # vuoto se manca powerprofilesctl
    assert A.clean({"kill": "sleep, a.exe", "power": "balanced", "res": "1920x1080"})["kill"] == ["sleep", "a.exe"]
    assert "pad" not in A.clean({"power": "balanced"})

    import shutil
    # polling primo piano: stesso comportamento dell'hook (emette solo ai cambi)
    if sys.platform != "darwin" and not shutil.which("xdotool"):
        print("ok")
        raise SystemExit
    ev, seq = [], iter([10, 10, 99, 99, 10])
    w = F.Watcher(lambda: [10], lambda n, d: ev.append(n))
    w.POLL = 0.02
    w.pid_source = lambda: next(seq, 10)
    w.start()
    end = time.time() + 5  # sotto carico (CI) 0,4 s fissi non bastavano ai 5 campioni: si aspetta l'esito, con un tetto
    while len(ev) < 3 and time.time() < end:
        time.sleep(0.02)
    w.stop()
    assert ev == ["game_foreground", "game_background", "game_foreground"], ev
print("ok")
