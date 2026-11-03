"""Aggancio dei preset emulatore all'avvio e rotte; adattatore ed emulatore finti, nessuna rete."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import config as C, emucfg, emuadapters, platforms as P  # noqa: E402
from pozzo.library import launcher as L  # noqa: E402


class FakeAdapter:
    boom = None

    def __init__(self, target):
        self._target = target

    def target(self, exe, game_id, core=None, game_name=None):
        if self.boom:
            raise self.boom
        return self._target

    def running_names(self):
        return ("pozzo-no-such-process",)

    def render(self, text, values):
        return text + "".join(f"{k}={v}\n" for s in values.values() for k, v in s.items())


class FakeProc:
    returncode = 0

    def poll(self):
        return 0


class FakeSub:
    CREATE_NO_WINDOW = 0
    sent: list = []

    @classmethod
    def Popen(cls, cmd, **kw):  # noqa: N802
        cls.sent.append(cmd)
        return FakeProc()


class FakeUser:
    def mark_started(self, key):
        pass

    def record_play(self, key, secs):
        pass


def _setup(tmp, monkeypatch, prof=None, console=None, boom=None):
    exe = tmp / "emu.exe"
    exe.write_bytes(b"")
    rom = tmp / "Gioco.iso"
    rom.write_bytes(b"GALE01" + b"\0" * 64)  # header GameCube: game ID GALE01
    target = tmp / "per-gioco" / "GALE01.ini"
    cfg = C.Config()
    cfg.emulators["dolphin"] = str(exe)
    cfg.launch = {"gc": {"emulator": "dolphin"}}
    if console:
        cfg.app["emu_preset"] = {"gc": console}
    ad = FakeAdapter(target)
    ad.boom = boom
    real = emuadapters.get
    monkeypatch.setattr(emuadapters, "get", lambda n: ad if n == "dolphin" else real(n))
    monkeypatch.setattr(emucfg, "catalog", lambda e, folder=None: {
        "presets": {"quality": {"values": {"S": {"K": "1"}}, "sources": ["https://x"]}}})
    monkeypatch.setattr(L, "subprocess", FakeSub)
    FakeSub.sent = []
    ln = L.Launcher(cfg, FakeUser(), profile_of=lambda k: prof)
    ln.state = {"key": "gc/x", "title": "G", "status": "starting", "message": ""}
    return ln, rom, target, L.plan(cfg, P.get("gc"), prof)


def _go(ln, rom, pl):
    ln._run("gc/x", P.get("gc"), rom, pl)


def test_preset_scritto_e_gioco_avviato(tmp, monkeypatch):
    ln, rom, target, pl = _setup(tmp, monkeypatch, prof={"preset": "quality"})
    _go(ln, rom, pl)
    assert target.read_text() == "K=1\n"
    assert FakeSub.sent and FakeSub.sent[0][0] == pl["exe"] and ln.state["status"] == "finished"


def test_next_args_solo_al_prossimo_avvio(tmp, monkeypatch):
    ln, rom, target, pl = _setup(tmp, monkeypatch)
    ln.next_args = ["-n", "host"]
    _go(ln, rom, pl)
    cmd = FakeSub.sent[0]
    assert cmd[0] == pl["exe"] and cmd[1:3] == ["-n", "host"], cmd
    assert ln.next_args == []
    _go(ln, rom, pl)
    assert "-n" not in FakeSub.sent[1], FakeSub.sent[1]


def test_preset_da_console(tmp, monkeypatch):
    ln, rom, target, pl = _setup(tmp, monkeypatch, console="quality")
    _go(ln, rom, pl)
    assert target.exists() and FakeSub.sent


def test_errore_non_blocca(tmp, monkeypatch):
    for boom in (RuntimeError("guasto"), emucfg.EmuCfgError("aperto")):
        ln, rom, target, pl = _setup(tmp, monkeypatch, prof={"preset": "quality"}, boom=boom)
        _go(ln, rom, pl)
        assert FakeSub.sent and ln.state["status"] == "finished" and not target.exists()


def test_leave_o_assente_non_scrive(tmp, monkeypatch):
    for prof, console in (({"preset": "leave"}, "quality"), (None, None), ({"preset": "inherit"}, None)):
        ln, rom, target, pl = _setup(tmp, monkeypatch, prof=prof, console=console)
        _go(ln, rom, pl)
        assert not target.exists() and FakeSub.sent


def test_preset_non_rende_profilo_personalizzato():
    cfg = C.Config()
    assert L.plan(cfg, P.get("gc"), {"preset": "quality"}) == L.plan(cfg, P.get("gc"))


def test_rotte(tmp):
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    from test_frontend import make_library
    rom = tmp / "g.gba"
    rom.write_bytes(b"x")
    cfg = C.Config(cache=tmp, output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    make_library(tmp, rom)
    c = TestClient(create_app(cfg))
    gid = c.get("/api/library?part=owned").json()["games"]["rows"][0][0]
    r = c.get(f"/api/game/{gid}/emu-preset").json()
    assert r["supported"] is False and r["note"] and r["preview"] is None
    assert c.post(f"/api/game/{gid}/profile", json={"preset": "boh"}).status_code == 400
    assert c.post("/api/emu-presets/console", json={"platform": "gba", "preset": "boh"}).status_code == 400
    assert c.post("/api/emu-presets/console", json={"platform": "xx", "preset": "quality"}).status_code == 400
    assert c.post("/api/emu-presets/console", json={"platform": "gba", "preset": "faithful"}).json() == {"gba": "faithful"}
    assert c.get("/api/emu-presets").json() == {"gba": "faithful"}
