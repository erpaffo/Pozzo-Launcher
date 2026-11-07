"""Pausa del gioco: processi sospesi (CPU ferma), tempo in pausa escluso dal tempo di gioco."""

from __future__ import annotations

import subprocess
import sys
import time
import types

import psutil
import pytest

from pozzo.library import launcher as L

win = pytest.mark.skipif(sys.platform != "win32", reason="NtSuspendProcess solo su Windows")


def _launcher():
    ln = L.Launcher(types.SimpleNamespace(app={}), types.SimpleNamespace())
    ln.state = {"status": "running", "key": "k"}
    return ln


def _cpu(p):
    t = psutil.Process(p.pid).cpu_times()
    return t.user + t.system


@win
def test_suspend_stops_cpu_and_resume_restarts_it():
    p = subprocess.Popen([sys.executable, "-c", "while True: pass"])
    try:
        time.sleep(0.5)
        assert L._suspend(p.pid, True)
        a = _cpu(p)
        time.sleep(0.7)
        assert _cpu(p) - a < 0.05
        assert L._suspend(p.pid, False)
        time.sleep(0.7)
        assert _cpu(p) - a > 0.2
    finally:
        p.kill()


@win
def test_pause_resume_via_launcher_with_job():
    ln = _launcher()
    job = L._Job.new()
    p = subprocess.Popen([sys.executable, "-c", "while True: pass"])
    assert job.add(p)
    ln._job, ln._proc = job, p
    try:
        assert p.pid in job.pids()
        assert ln.pause() and ln.running()["paused"]
        a = _cpu(p)
        time.sleep(0.6)
        assert _cpu(p) - a < 0.05
        assert not ln.pause()  # gia' in pausa
        assert ln.toggle_pause() is True and not ln.running()["paused"]
    finally:
        ln._unfreeze()
        p.kill()
        job.close()


def test_paused_interval_excluded_from_playtime(monkeypatch):
    ln = _launcher()
    now = [1000.0]
    monkeypatch.setattr(L.time, "time", lambda: now[0])
    now[0] += 10  # 10 s di gioco
    ln._frozen, ln._pause_t0 = [], now[0]  # pausa
    now[0] += 30  # 30 s in pausa
    now[0] += 20  # la sessione finisce ancora in pausa: _unfreeze chiude l'intervallo
    assert ln.played_since(1000.0) == pytest.approx(10)
