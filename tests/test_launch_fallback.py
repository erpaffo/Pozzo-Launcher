"""Crash veloci ripetuti: stato di errore con crash/fallback; un'uscita riuscita azzera; "apply" riprova da solo."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from pozzo import config as C, platforms as P  # noqa: E402
from pozzo.library import launcher as L  # noqa: E402


class FakeUser:
    def mark_started(self, key):
        pass

    def record_play(self, key, secs):
        pass


def _wait(ln, statuses, secs=10):
    end = time.time() + secs
    while ln.state.get("status") not in statuses and time.time() < end:
        time.sleep(0.02)
    assert ln.state.get("status") in statuses, ln.state


def _run(ln, rom):
    ln.state = {}
    ln.launch("gba/x", "G", P.get("gba"), rom)
    _wait(ln, ("finished", "error"))
    time.sleep(0.1)


@pytest.fixture
def env(tmp, monkeypatch):
    script = tmp / "emu.py"
    script.write_text("import os, sys\nprint('boom', file=sys.stderr)\n"
                      "if 'gpsp' in ' '.join(sys.argv) and os.path.exists(sys.argv[-1] + '.gpspok'): sys.exit(0)\n"
                      "sys.exit(int(open(sys.argv[-1] + '.code').read()))\n")
    bat = tmp / ("emu.cmd" if sys.platform == "win32" else "emu.sh")
    bat.write_text(f'@"{sys.executable}" "{script}" %*\n' if sys.platform == "win32" else f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    bat.chmod(0o755)
    rom = tmp / "g.gba"
    rom.write_bytes(b"x")
    cfg = C.Config()
    cfg.cache = tmp / "cache"
    cfg.emulators["mgba"] = str(bat)
    cfg.emulators["retroarch"] = str(bat)
    for c in ("mgba", "gpsp"):
        core = L._core_path(cfg, c)
        core.parent.mkdir(parents=True, exist_ok=True)
        core.write_bytes(b"")
    cfg.launch = {}
    ln = L.Launcher(cfg, FakeUser())
    monkeypatch.setattr(ln, "_apply_preset", lambda *a: None)
    monkeypatch.setitem(L.PRESETS, "gba", [("retroarch", "mgba"), ("retroarch", "gpsp")])
    return ln, cfg, rom


def test_due_crash_poi_fallback_e_reset(env, tmp):
    ln, cfg, rom = env
    code = Path(str(rom) + ".code")
    code.write_text("1")
    _run(ln, rom)
    assert ln.state["status"] == "finished"  # un solo crash: nessuna proposta
    _run(ln, rom)
    st = ln.state
    assert st["status"] == "error" and st["crash"]["code"] == 1 and "boom" in st["crash"]["log"]
    assert st["fallback"] == {"kind": "core", "id": "retroarch:gpsp", "label": "core gpsp"}
    assert L.last_crash(cfg, "gba/x")["code"] == 1
    code.write_text("0")  # uscita riuscita: azzera
    _run(ln, rom)
    assert ln.state["status"] == "finished", ln.state
    code.write_text("1")
    _run(ln, rom)
    assert ln.state["status"] == "finished"  # di nuovo il primo della serie


def test_apply_riprova_e_ricorda(env, tmp):
    ln, cfg, rom = env
    cfg.app["crash_fallback"] = "apply"
    Path(str(rom) + ".code").write_text("1")
    Path(str(rom) + ".gpspok").write_text("")  # col core gpsp il gioco parte
    _run(ln, rom)
    _run(ln, rom)  # secondo crash: riprova da solo con gpsp, che funziona
    assert ln.state["status"] == "finished", ln.state
    assert L._crash_load(cfg)["gba/x"]["fallback"] == "retroarch:gpsp"
    _run(ln, rom)  # il prossimo avvio usa direttamente l'alternativa ricordata
    assert ln.state["status"] == "finished" and "gpsp" in ln.state["message"], ln.state


def test_off_non_propone_alternativa(env, tmp):
    ln, cfg, rom = env
    cfg.app["crash_fallback"] = "off"
    Path(str(rom) + ".code").write_text("1")
    _run(ln, rom)
    _run(ln, rom)  # secondo crash di fila: con "off" niente proposta né riprova
    assert ln.state["status"] == "error" and ln.state.get("fallback") is None, ln.state
    assert L._crash_load(cfg)["gba/x"]["runs"]  # il crash resta registrato
