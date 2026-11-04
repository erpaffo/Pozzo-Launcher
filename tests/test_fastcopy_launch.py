"""«Gioca da disco veloce» nel Launcher: copia, percorsi rimappati, pulizia; copia/emulatore/processo finti."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from pozzo import config as C, platforms as P  # noqa: E402
from pozzo.library import fastcopy, launcher as L  # noqa: E402


class FakeProc:
    returncode = 0

    def __init__(self, calls):
        self.calls, self.alive = calls, True

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout=None):
        raise TimeoutError

    def terminate(self):
        self.alive = False


class FakeSub:
    CREATE_NO_WINDOW = 0

    def __init__(self):
        self.sent, self.proc = [], None
        self.finish_now = True

    def Popen(self, cmd, **kw):  # noqa: N802
        self.sent.append((cmd, kw))
        self.proc = FakeProc(self.sent)
        self.proc.alive = not self.finish_now
        return self.proc


class FakeUser:
    def mark_started(self, key):
        pass

    def record_play(self, key, secs):
        pass


def _wait(ln, status, secs=10):
    end = time.time() + secs
    while ln.state.get("status") != status and time.time() < end:
        time.sleep(0.02)
    assert ln.state.get("status") == status, ln.state


@pytest.fixture
def env(tmp, monkeypatch):
    calls = []
    sub = FakeSub()
    monkeypatch.setattr(L, "subprocess", sub)
    monkeypatch.setattr(fastcopy, "purge_stale", lambda cfg: 0)
    monkeypatch.setattr(fastcopy, "root", lambda cfg: tmp / "fast")
    monkeypatch.setattr(fastcopy, "same", lambda a, b: True)

    def fake_copy(src, dest_dir, on_progress=None, cancel=None):
        calls.append(("copy", Path(src)))
        out = Path(dest_dir) / Path(src).name
        out.mkdir(parents=True, exist_ok=True) if Path(src).is_dir() else (out.parent.mkdir(parents=True, exist_ok=True), out.write_bytes(b"x"))
        if on_progress:
            on_progress(0.5, "")
        return out

    monkeypatch.setattr(fastcopy, "copy", fake_copy)
    monkeypatch.setattr(fastcopy, "remove", lambda p, cfg=None: calls.append(("remove", Path(p))))
    exe = tmp / "emu.exe"
    exe.write_bytes(b"")
    rom = tmp / "Gioco.iso"
    rom.write_bytes(b"x")
    cfg = C.Config()
    cfg.emulators["dolphin"] = str(exe)
    cfg.launch = {"gc": {"emulator": "dolphin"}}
    ln = L.Launcher(cfg, FakeUser())
    presets = []
    monkeypatch.setattr(ln, "_apply_preset", lambda key, platform, path, pl: presets.append(Path(path)))
    return ln, cfg, rom, calls, sub, presets, tmp


def test_senza_fast_niente_copia(env):
    ln, cfg, rom, calls, sub, presets, tmp = env
    ln.launch("gc/x", "G", P.get("gc"), rom)
    _wait(ln, "finished")
    assert calls == [] and str(rom) in sub.sent[0][0]


@pytest.mark.parametrize("delete_after", [True, False])
def test_emulatore_copia_e_pulizia(env, delete_after):
    ln, cfg, rom, calls, sub, presets, tmp = env
    cfg.app["fastcopy"] = {"delete_after": delete_after}
    ln.launch("gc/x", "G", P.get("gc"), rom, fast=True)
    _wait(ln, "finished")
    copia = tmp / "fast" / "gc_x" / "Gioco.iso"
    assert str(copia) in sub.sent[0][0] and str(rom) not in sub.sent[0][0]
    assert presets == [rom]  # il preset identifica il gioco dall'originale
    assert [c[0] for c in calls if c[0] == "remove"] == (["remove"] if delete_after else [])


def test_errore_di_copia_pulisce(env, monkeypatch):
    ln, cfg, rom, calls, sub, presets, tmp = env
    cfg.app["fastcopy"] = {"delete_after": False}

    def boom(*a, **k):
        raise fastcopy.FastCopyError("Disco pieno")

    monkeypatch.setattr(fastcopy, "copy", boom)
    ln.launch("gc/x", "G", P.get("gc"), rom, fast=True)
    _wait(ln, "error")
    assert ln.state["message"] == "Disco pieno"
    assert ("remove", tmp / "fast" / "gc_x") in calls  # anche con delete_after = false
    assert not sub.sent


def test_chiudi_gioco_durante_copia(env, monkeypatch):
    ln, cfg, rom, calls, sub, presets, tmp = env
    started = threading.Event()

    def slow(src, dest_dir, on_progress=None, cancel=None):
        started.set()
        cancel.wait(5)
        raise fastcopy.FastCopyError("interrotta")

    monkeypatch.setattr(fastcopy, "copy", slow)
    ln.launch("gc/x", "G", P.get("gc"), rom, fast=True)
    assert started.wait(5)
    assert ln.stop()
    _wait(ln, "error")
    assert ln.state["message"] == "Copia annullata" and not sub.sent
    assert ("remove", tmp / "fast" / "gc_x") in calls


def test_remove_solo_a_gioco_finito(env):
    ln, cfg, rom, calls, sub, presets, tmp = env
    sub.finish_now = False  # il processo resta vivo finche' non si chiude
    ln.launch("gc/x", "G", P.get("gc"), rom, fast=True)
    _wait(ln, "running")
    time.sleep(0.8)
    assert not [c for c in calls if c[0] == "remove"]  # gioco vivo: copia intatta
    sub.proc.alive = False
    _wait(ln, "finished")
    assert [c[0] for c in calls] == ["copy", "remove"]


def test_pc_rimappa_percorsi(env):
    ln, cfg, rom, calls, sub, presets, tmp = env
    inst = tmp / "Giochi" / "Foo"
    (inst / "bin").mkdir(parents=True)
    exe = inst / "bin" / "foo.exe"
    exe.write_bytes(b"")
    launch = {"type": "exe", "target": str(exe), "args": ["-x"], "cwd": str(inst / "bin"), "track_dir": str(inst)}
    ln.launch_pc("manual:1", "Foo", launch, str(inst), "manual", fast=True)
    # Path.exists() sul finto exe copiato: la copia finta crea solo la cartella, quindi creiamo il file
    _wait(ln, "error")  # target copiato inesistente (copia finta): comunque rimappato e ripulito
    assert str(tmp / "fast" / "manual_1" / "Foo" / "bin" / "foo.exe") in ln.state["message"]
    assert ("remove", tmp / "fast" / "manual_1") in calls


def test_pc_target_fuori_cartella(env):
    ln, cfg, rom, calls, sub, presets, tmp = env
    inst = tmp / "Giochi" / "Foo"
    inst.mkdir(parents=True)
    with pytest.raises(L.LaunchError):
        ln.launch_pc("manual:1", "Foo", {"type": "exe", "target": str(tmp / "altro.exe")}, str(inst), "manual", fast=True)
    with pytest.raises(L.LaunchError):
        ln.launch_pc("steam:1", "Foo", {"type": "uri", "target": "steam://x"}, str(inst), "Steam", "steam", fast=True)
    assert calls == []
