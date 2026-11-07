"""Remap del pad: funzione di mappatura (pura), scelta del pad fisico, comandi HidHide e ripristino."""

from __future__ import annotations

import pytest

from pozzo.library import padremap as PR

A, B, LB, UP = PR.BTN["a"], PR.BTN["b"], PR.BTN["lb"], PR.BTN["up"]


def st(buttons=0, lt=0, rt=0, lx=0, ly=0, rx=0, ry=0):
    return {"buttons": buttons, "lt": lt, "rt": rt, "lx": lx, "ly": ly, "rx": rx, "ry": ry}


def test_buttons_and_triggers():
    assert PR.remap(st(A), {"map": {"a": "b"}}, 0)["buttons"] == B
    assert PR.remap(st(A | LB), {}, 0)["buttons"] == A | LB
    o = PR.remap(st(A), {"map": {"a": "rt"}}, 0)
    assert o["buttons"] == 0 and o["rt"] == 255
    assert PR.remap(st(lt=200), {"map": {"lt": "x"}}, 0)["buttons"] == PR.BTN["x"]
    assert PR.remap(st(lt=200), {}, 0)["lt"] == 200  # analogico invariato
    assert PR.remap(st(lt=10), {"map": {"lt": "x"}}, 0)["buttons"] == 0  # sotto soglia


def test_sticks_deadzone_swap_invert():
    c = {"deadzone": 20}
    assert PR.remap(st(lx=3000, ly=3000), c, 0)["lx"] == 0
    o = PR.remap(st(lx=32767), c, 0)
    assert o["lx"] == 32767
    mid = PR.remap(st(lx=16000), c, 0)["lx"]
    assert 0 < mid < 16000  # riscalato
    o = PR.remap(st(lx=1000 * 20, ly=5000, rx=-9000, ry=-20000), {"swap": True, "invert_y": True}, 0)
    assert (o["lx"], o["ly"], o["rx"], o["ry"]) == (-9000, 20000, 20000, -5000)
    assert PR.remap(st(ly=-32768), {"invert_y": True}, 0)["ly"] == 32767


def test_turbo_timing():
    c = {"turbo": {"a": 10}}  # 10 Hz: periodo 100 ms, 50 ms acceso / 50 ms spento
    assert PR.remap(st(A), c, 0.01)["buttons"] == A
    assert PR.remap(st(A), c, 0.06)["buttons"] == 0
    assert PR.remap(st(A), c, 0.11)["buttons"] == A
    assert PR.remap(st(), c, 0.01)["buttons"] == 0  # non premuto: niente


def test_clean():
    c = PR.clean({"enabled": True, "map": "a=b, lb=lt", "turbo": "x:8", "deadzone": "50", "swap": True})
    assert c["map"] == {"a": "b", "lb": "lt"} and c["turbo"] == {"x": 8} and c["deadzone"] == 30 and c["swap"]
    assert PR.clean({"map": "a=b"}) == {}
    for bad in ({"map": "a=zz"}, {"turbo": "a:99"}):
        with pytest.raises(ValueError):
            PR.clean({"enabled": True, **bad})


def test_pick_physical_skips_virtual():
    assert PR.pick_physical([0, 1, 2], {0}) == 1
    assert PR.pick_physical([0], {0}) is None
    assert PR.pick_physical([2, 3], set()) == 2


def _hh(calls, fail_on=None):
    def run(args):
        calls.append(args)
        if fail_on and args[0] == fail_on:
            raise OSError("boom")
        return {"--cloak-state": "false", "--dev-gaming": '[{"devices": [{"deviceInstancePath": "HID\\\\X", "present": true}]}]'}.get(args[0], "")
    return PR.HidHide("cli", run)


def test_hidhide_commands_and_restore():
    calls = []
    h = _hh(calls)
    devs = h.gaming_devices()
    assert devs == ["HID\\X"]
    h.hide(devs, "py.exe")
    assert ["--app-reg", "py.exe"] in calls and ["--dev-hide", "HID\\X"] in calls and calls[-1] == ["--cloak-on"]
    h.restore()
    assert calls[-3:] == [["--dev-unhide", "HID\\X"], ["--app-unreg", "py.exe"], ["--cloak-off"]]
    n = len(calls)
    h.restore()  # idempotente
    assert len(calls) == n


def test_hidhide_restores_on_exception():
    calls = []
    h = _hh(calls, fail_on="--cloak-on")
    with pytest.raises(OSError):
        h.hide(["HID\\X"], "py.exe")
    assert ["--dev-unhide", "HID\\X"] in calls and ["--app-unreg", "py.exe"] in calls
