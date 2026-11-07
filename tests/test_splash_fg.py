"""Splash di avvio e primo piano: PID della sessione, eventi, timeout."""

from __future__ import annotations

import threading
import types

from pozzo.library import foreground as F, launcher as L


def test_is_game_pid():
    assert F.is_game_pid(10, [3, 10])
    assert not F.is_game_pid(11, [3, 10])
    assert not F.is_game_pid(0, [0])


def test_watcher_emits_only_on_change():
    out = []
    w = F.Watcher(lambda: [10, 11], lambda n, d: out.append(n))
    for pid in (5, 10, 11, 5, 5, 10):
        w.on_foreground(pid)
    assert out == ["game_background", "game_foreground", "game_background", "game_foreground"]


def test_watcher_ignores_pid_errors():
    def boom():
        raise OSError
    w = F.Watcher(boom, lambda n, d: (_ for _ in ()).throw(AssertionError))
    w.on_foreground(1)


def test_splash_timeout_emits_splash_end():
    ev, out = threading.Event(), []
    F.splash_timer(lambda n, d: (out.append((n, d)), ev.set()), 0.05)
    assert ev.wait(2)
    assert out == [("splash_end", {"reason": "timeout"})]


def _launcher(app):
    out = []
    ln = L.Launcher(types.SimpleNamespace(app=app), types.SimpleNamespace(), on_event=lambda n, d: out.append(n))
    return ln, out


def test_launcher_splash_setting(monkeypatch):
    monkeypatch.setattr(F, "splash_timer", lambda emit, s=None: None)
    ln, out = _launcher({})
    ln.splash(1, "Gioco")
    assert out == ["game_splash"]
    ln, out = _launcher({"launch": {"splash": False}})
    ln.splash(1, "Gioco")
    assert out == []
