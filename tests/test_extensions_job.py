"""gs.job (lavori periodici dei plugin) e misura del tempo di register()."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pozzo.app import extensions as X  # noqa: E402


class FakeApp:
    def __init__(self):
        self.handlers = []

    def add_event_handler(self, event, fn):
        self.handlers.append((event, fn))


def make_api(app=None, logs=None):
    api = X.PluginAPI.__new__(X.PluginAPI)  # salta la lettura delle impostazioni da disco
    api.app, api.cfg, api.id, api.events = app or FakeApp(), None, "prova", X.Events()
    api.log, api.settings = (logs.append if logs is not None else (lambda m: None)), {}
    return api


@pytest.fixture(autouse=True)
def _clean():
    yield
    X.stop_jobs()


def wait_for(cond, timeout=5.0):  # i runner di CI sono lenti: il margine costa solo se il test fallisce
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


def test_job_runs_periodically_and_stops_on_shutdown():
    app, hits = FakeApp(), []
    j = make_api(app).job("tick", lambda: hits.append(1), every=0.01)
    assert wait_for(lambda: len(hits) >= 3)
    assert [e for e, _ in app.handlers] == ["shutdown"]
    app.handlers[0][1]()  # come fa FastAPI alla chiusura
    assert j.stopped.is_set() and X.JOBS == []
    n = len(hits)
    time.sleep(0.05)
    assert len(hits) <= n + 2  # al massimo un giro gia' in corso (due su runner lenti)


def test_run_at_start_and_errors_are_logged():
    logs, calls = [], []

    def boom():
        calls.append(1)
        raise RuntimeError("rotto")

    j = make_api(logs=logs).job("boom", boom, every=60, run_at_start=True)
    assert wait_for(lambda: j.runs >= 1)
    assert j.last_error == "RuntimeError: rotto"
    assert logs == ["Plugin prova, lavoro boom: RuntimeError: rotto"]
    j.tick()  # il lavoro sopravvive all'errore
    assert len(calls) == 2


def test_no_run_at_start_waits_interval():
    hits = []
    make_api().job("lento", lambda: hits.append(1), every=60)
    time.sleep(0.05)
    assert hits == []


def test_invalid_interval():
    with pytest.raises(ValueError):
        make_api().job("x", lambda: None, every=0)


def test_shutdown_hook_registered_once_per_app():
    app = FakeApp()
    api = make_api(app)
    api.job("a", lambda: None, every=60)
    api.job("b", lambda: None, every=60)
    assert len(app.handlers) == 1


def test_shutdown_hook_not_skipped_when_an_old_app_is_freed():
    """L'id() di un'app liberata viene riusato da quella dopo (su macOS quasi sempre): l'hook va registrato lo stesso."""
    for _ in range(50):
        app = FakeApp()
        make_api(app).job("a", lambda: None, every=60)
        assert [e for e, _ in app.handlers] == ["shutdown"]
        del app


def test_load_time_and_jobs_in_listing(tmp_path, monkeypatch):
    d = tmp_path / "plugins" / "lento"
    d.mkdir(parents=True)
    (d / "plugin.toml").write_text('[plugin]\nname = "Lento"\napi = 1\n', encoding="utf-8")
    (d / "backend.py").write_text(
        "import time\n"
        "def register(gs):\n"
        "    time.sleep(0.02)\n"
        "    gs.job('j', lambda: None, every=60)\n", encoding="utf-8")

    class Cfg:
        config_path = tmp_path / "config.toml"
        app = {}

    monkeypatch.setattr(X, "BUILTIN_PLUGINS", tmp_path / "nessuno")
    monkeypatch.setattr(X.C, "read_settings", lambda cfg: {})
    errors = X.load_backends(FakeApp(), Cfg(), X.Events(), log=lambda m: None)
    assert errors == {}
    p = next(p for p in X.list_plugins(Cfg()) if p["id"] == "lento")
    assert p["load_ms"] >= 10  # sleep(0.02): su Windows il timer puo' tornare un po' prima
    assert p["jobs"] == [{"name": "j", "every": 60.0, "runs": 0, "error": None}]
