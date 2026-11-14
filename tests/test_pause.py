"""Pausa del gioco: processi sospesi (CPU ferma), tempo in pausa escluso dal tempo di gioco."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

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


def test_api_running_can_pause(monkeypatch):
    """Il flag arriva dal server (il telefono ha un altro OS): ora c'e' la pausa anche su posix."""
    import types

    from fastapi.testclient import TestClient

    from pozzo import config
    from pozzo.app.routes import stream
    from pozzo.app.server import create_app
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        d = Path(t)
        cfg = config.Config(cache=d / "cache", output=d / "out")
        cfg.config_path = d / "config.toml"
        with TestClient(create_app(cfg)) as c:
            assert c.get("/api/running").json()["can_pause"] is True


posix = pytest.mark.skipif(sys.platform == "win32", reason="SIGSTOP/gruppi di processi solo posix")


@posix
def test_posix_pause_resume_and_tree_kill():
    ln = _launcher()
    job = L._Job.new()
    p = subprocess.Popen(["sh", "-c", "sleep 30 & wait"], start_new_session=True)
    assert job.add(p)
    ln._job, ln._proc = job, p
    try:
        end = time.time() + 5
        while len(job.pids()) < 2 and time.time() < end:  # sh + sleep
            time.sleep(0.1)
        assert len(job.pids()) >= 2
        assert ln.pause() and ln.running()["paused"]
        assert all(psutil.Process(x).status() == psutil.STATUS_STOPPED for x in job.pids())
        assert ln.resume()
        time.sleep(0.2)
        assert all(psutil.Process(x).status() != psutil.STATUS_STOPPED for x in job.pids())
        pids = job.pids()
        job.kill()
        p.wait(5)
        end = time.time() + 5
        while job.active() and time.time() < end:
            time.sleep(0.1)
        assert job.active() == 0 and not any(psutil.pid_exists(x) and psutil.Process(x).status() != psutil.STATUS_ZOMBIE for x in pids)
    finally:
        ln._unfreeze()
        job.kill()


def test_ryujinx_data_dir_per_os(monkeypatch, tmp_path):
    monkeypatch.setattr(L.Path, "home", classmethod(lambda c: Path("/h")))
    exe = tmp_path / "Ryujinx"
    monkeypatch.setattr(L.sys, "platform", "darwin")
    assert L.ryujinx_data_dir(exe) == Path("/h/Library/Application Support/Ryujinx")
    monkeypatch.setattr(L.sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert L.ryujinx_data_dir(exe) == Path("/h/.config/Ryujinx")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/x")
    assert L.ryujinx_data_dir(exe) == Path("/x/Ryujinx")
