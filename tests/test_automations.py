"""Automazioni per gioco e script globali: variabili d'ambiente, ordine, ripristino dopo un crash."""

from __future__ import annotations

import sys
import time

import pytest

from pozzo import config as C
from pozzo.app.extensions import Events
from pozzo.library import automation as A, launcher as L

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="automazioni di sistema solo su Windows")


class FakeUser:
    def record_play(self, *a): pass
    def mark_started(self, *a): pass


def _py(out, body):
    return f'"{sys.executable}" -c "{body}" "{out}"'


def _wait(ln, status, timeout=30):
    end = time.time() + timeout
    while ln.state.get("status") not in status and time.time() < end:
        time.sleep(0.1)


def test_clean_validates():
    assert A.clean({"res": "1920x1080@60", "kill": "a.exe, b.exe;c", "hdr": True})["kill"] == ["a.exe", "b.exe"]
    assert A.clean({"before_cmd": "x"})["before_wait"] is True and A.clean({"after_cmd": "x"})["after_wait"] is False
    for bad in ({"res": "big"}, {"power": "nope"}):
        with pytest.raises(ValueError):
            A.clean(bad)


def test_env_and_order_and_restore_after_crash(tmp_path, monkeypatch):
    log = tmp_path / "log.txt"
    dump = "import os,sys;open(sys.argv[1],'a').write(os.environ['POZZO_EVENT']+'|'+os.environ['POZZO_GAME_ID']+'|'+os.environ['POZZO_TITLE']+'|'+os.environ['POZZO_PLATFORM']+'|'+os.environ['POZZO_EXE']+chr(10))"
    calls = []
    monkeypatch.setattr(A, "display_mode", lambda: "saved-mode")
    monkeypatch.setattr(A, "set_display", lambda w, h, hz: calls.append(("res", w, h, hz)))
    monkeypatch.setattr(A, "restore_display", lambda saved: calls.append(("restore", saved)))
    monkeypatch.setattr(A, "active_plan", lambda: "prev-plan-guid")
    monkeypatch.setattr(A, "set_plan", lambda g: calls.append(("plan", g)))
    monkeypatch.setattr(A, "toggle_hdr", lambda: calls.append(("hdr",)))
    monkeypatch.setattr(A, "kill_processes", lambda names: calls.append(("kill", names)))
    auto = A.clean({"before_cmd": _py(log, dump), "after_cmd": _py(log, dump), "after_wait": True, "res": "1280x720@120",
                    "power": "11111111-2222-3333-4444-555555555555", "kill": "Foo.exe", "hdr": True})
    ln = L.Launcher(C.Config(), FakeUser(), profile_of=lambda k: {A.KEY: auto})
    ln.launch_pc("steam:1", "Gioco", {"type": "exe", "target": sys.executable,
                                      "args": ["-c", "import sys;sys.exit(3)"]}, "", "Steam", "steam")
    _wait(ln, ("finished", "error"))
    time.sleep(0.3)
    lines = log.read_text().splitlines()
    assert lines[0].startswith("before|steam:1|Gioco|Steam|") and lines[-1].startswith("after|steam:1|")
    assert calls == [("kill", ["Foo.exe"]), ("res", 1280, 720, 120), ("plan", "11111111-2222-3333-4444-555555555555"), ("hdr",),
                     ("hdr",), ("plan", "prev-plan-guid"), ("restore", "saved-mode")]


def test_restore_runs_when_launch_raises(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(A, "display_mode", lambda: "m")
    monkeypatch.setattr(A, "set_display", lambda *a: None)
    monkeypatch.setattr(A, "restore_display", lambda s: calls.append("restored"))
    ln = L.Launcher(C.Config(), FakeUser(), profile_of=lambda k: {A.KEY: A.clean({"res": "800x600"})})
    ln.launch_pc("x:1", "G", {"type": "exe", "target": str(tmp_path / "missing.exe")}, "", "Steam", "steam")
    _wait(ln, ("finished", "error"))
    time.sleep(0.3)
    assert ln.state["status"] == "error" and calls == ["restored"]


def test_before_failure_still_launches(tmp_path):
    ran = tmp_path / "ran.txt"
    auto = A.clean({"before_cmd": "exit 7"})
    ln = L.Launcher(C.Config(), FakeUser(), profile_of=lambda k: {A.KEY: auto})
    ln.launch_pc("x:1", "G", {"type": "exe", "target": sys.executable,
                              "args": ["-c", f"open(r'{ran}','w').write('1')"]}, "", "Steam", "steam")
    _wait(ln, ("finished", "error"))
    assert ran.exists() and ln.state["status"] == "finished"


def test_global_event_scripts(tmp_path):
    log = tmp_path / "g.txt"
    dump = "import os,sys;open(sys.argv[1],'a').write(os.environ['POZZO_EVENT']+'|'+os.environ['POZZO_TITLE']+'|'+os.environ.get('POZZO_DOWNLOAD_NAME','-')+chr(10))"
    cfg = C.Config()
    cfg.app["scripts"] = {k: _py(log, dump) for k in ("game_started", "game_stopped", "download_finished")}
    ev = Events()
    A.register_global(ev, cfg)
    ev.emit("game_started", {"key": "k", "title": "T"})
    ev.emit("game_stopped", {"key": "k", "title": "T"})
    ev.emit("game_downloaded", {"title": "Dl"})
    end = time.time() + 15
    while (not log.exists() or len(log.read_text().splitlines()) < 3) and time.time() < end:
        time.sleep(0.1)
    assert sorted(log.read_text().splitlines()) == ["download_finished|Dl|Dl", "game_started|T|-", "game_stopped|T|-"]
