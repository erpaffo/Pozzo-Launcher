"""Overlay in gioco: impostazioni, coda degli avvisi, rotte (la finestra nativa non si prova)."""

import types

import pytest

from pozzo import overlay as OV


def test_settings_defaults_and_validation():
    cfg = types.SimpleNamespace(app={})
    cur = OV.settings(cfg)
    assert cur["hotkey"] == "ctrl+shift+o" and cur["achievements"] and cur["sound"] == "soft"
    assert OV.clean({"hotkey": " Ctrl+Alt+F9 ", "sound": "none", "achievements": 0}, cur) == {
        "hotkey": "ctrl+alt+f9", "sound": "none", "achievements": False}
    assert OV.clean({"hotkey": ""}, cur)["hotkey"] == ""  # vuota = spenta
    for bad in ({"hotkey": "ctrl+ciao"}, {"hotkey": "foo+o"}, {"sound": "loud"}):
        with pytest.raises(ValueError):
            OV.clean(bad, cur)


def test_toast_queue_order_dedupe_and_limit():
    q = OV.ToastQueue(limit=3)
    for i in (1, 2, 2, 3, 4, 5):
        q.push({"id": i})
    assert [q.pop()["id"] for _ in range(3)] == [3, 4, 5]  # 2 una volta sola, i piu' vecchi scartati
    assert q.pop() is None


def test_routes(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pozzo import config as C
    from pozzo.app.routes import overlay as R
    saved = []
    monkeypatch.setattr(C, "save_settings", lambda cfg, **kw: saved.append(kw))
    cfg = types.SimpleNamespace(app={})
    launcher = types.SimpleNamespace(running=lambda: {"status": "running", "key": "k", "title": "T", "started": 5.0})
    ov = OV.Overlay(cfg, launcher)  # senza attach(): niente finestra, toggle risponde False
    ctx = types.SimpleNamespace(cfg=cfg, launcher=launcher, lib=types.SimpleNamespace(by_key={"k": {"id": 7, "title": "Titolo"}}), overlay=ov)
    app = FastAPI()
    app.include_router(R.build_router(ctx))
    c = TestClient(app)
    st = c.get("/api/overlay/state").json()
    assert st["running"] and st["gid"] == 7 and st["title"] == "Titolo" and st["settings"]["hotkey"] == "ctrl+shift+o"
    assert c.post("/api/overlay/toggle").json() == {"ok": False}
    assert c.post("/api/overlay/settings", json={"sound": "classic"}).json()["settings"]["sound"] == "classic"
    assert saved and cfg.app["overlay"]["sound"] == "classic"
    assert c.post("/api/overlay/settings", json={"hotkey": "zz+zz"}).status_code == 400
    assert "showToast" in c.get("/overlay/toast").text
    assert "ov-card" in c.get("/overlay").text
