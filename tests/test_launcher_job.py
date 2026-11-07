"""Job Object: la sessione resta viva finche' ha figli, «Chiudi tutto» li termina."""

from __future__ import annotations

import subprocess
import sys
import time

import pytest

from pozzo.library.launcher import _Job

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Job Object solo su Windows")

# il genitore avvia un figlio che dorme e esce subito
PARENT = "import subprocess,sys;subprocess.Popen([sys.executable,'-c','import time;time.sleep(%s)']);"


def _start(sleep):
    job = _Job.new()
    proc = subprocess.Popen([sys.executable, "-c", PARENT % sleep])
    assert job.add(proc)
    proc.wait()
    return job


def _wait(job, n, timeout=10):
    end = time.time() + timeout
    while job.active() != n and time.time() < end:
        time.sleep(0.1)
    return job.active()


def test_session_lives_until_child_exits():
    job = _start(2)
    assert job.active() >= 1  # il genitore e' uscito ma il figlio e' ancora nel Job
    assert _wait(job, 0) == 0
    job.close()


def test_kill_terminates_child():
    job = _start(60)
    assert job.active() >= 1
    job.kill()
    assert _wait(job, 0) == 0
    job.close()
