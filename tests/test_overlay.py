"""Overlay in gioco: impostazioni, coda degli avvisi, rotte (la finestra nativa non si prova)."""

import types

import pytest

from pozzo import overlay as OV


def test_settings_defaults_and_validation():
    cfg = types.SimpleNamespace(app={})
    cur = OV.settings(cfg)
    assert cur["hotkey"] == "ctrl+shift+o" and cur["achievements"] and cur["sound"] == "soft"
    assert cur["hud"] is False and cur["hud_corner"] == "tl"  # HUD spento di default
    assert OV.clean({"hotkey": " Ctrl+Alt+F9 ", "sound": "none", "achievements": 0}, cur) == {
        "hotkey": "ctrl+alt+f9", "sound": "none", "achievements": False, "hud": False, "hud_corner": "tl"}
    assert OV.clean({"hud": 1, "hud_corner": "br"}, cur)["hud"] is True
    assert OV.clean({"hotkey": ""}, cur)["hotkey"] == ""  # vuota = spenta
    for bad in ({"hotkey": "ctrl+ciao"}, {"hotkey": "foo+o"}, {"sound": "loud"}, {"hud_corner": "centro"}):
        with pytest.raises(ValueError):
            OV.clean(bad, cur)


def test_retroarch_network_commands(tmp_path):
    import socket
    from pozzo.emuadapters import retroarch as RA
    exe = tmp_path / "retroarch.exe"
    cfg = tmp_path / "retroarch.cfg"
    cfg.write_text('network_cmd_enable = "false"\n')
    assert not RA.net_ready(exe) and RA.command(exe, "save") is False  # spento: non si invia nulla
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0)); rx.settimeout(2)
    cfg.write_text(f'network_cmd_enable = "true"\nnetwork_cmd_port = "{rx.getsockname()[1]}"\n')
    assert RA.command(exe, "save") and rx.recvfrom(64)[0] == b"SAVE_STATE"
    assert RA.command(exe, "reset") and rx.recvfrom(64)[0] == b"RESET"
    assert RA.command(exe, "format") is False  # comando sconosciuto
    rx.close()


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
    assert "h-time" in c.get("/overlay/hud").text
    assert st["emu"] is None  # nessun emulatore in esecuzione: la scheda non compare
    stats = c.get("/api/overlay/stats").json()
    assert 0 <= stats["cpu"] <= 100 and 0 <= stats["ram"] <= 100 and "battery" in stats
    assert c.post("/api/overlay/emu", json={"action": "save"}).status_code == 409


def test_emu_route_retroarch(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pozzo.app.routes import overlay as R
    exe = tmp_path / "retroarch.exe"
    (tmp_path / "retroarch.cfg").write_text('network_cmd_enable = "false"\n')
    cfg = types.SimpleNamespace(app={})
    launcher = types.SimpleNamespace(running=lambda: {"status": "running", "key": "k", "emulator_id": "retroarch", "exe": str(exe)})
    ctx = types.SimpleNamespace(cfg=cfg, launcher=launcher, lib=types.SimpleNamespace(by_key={}), overlay=OV.Overlay(cfg, launcher))
    app = FastAPI()
    app.include_router(R.build_router(ctx))
    c = TestClient(app)
    assert c.get("/api/overlay/state").json()["emu"] == {"id": "retroarch", "ready": False}
    assert c.post("/api/overlay/emu", json={"action": "save"}).status_code == 409  # comandi di rete spenti: nessun invio di nascosto
