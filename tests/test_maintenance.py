import types

import pytest

from pozzo import maintenance as M


def snap(roms=(), bios=(), covers=0, free=None, steps=(("a", True),)):
    return {"time": 1, "rom_missing": [{"game": g, "path": p} for g, p in roms],
            "bios_invalid": [{"console": c, "file": f} for c, f in bios], "covers_missing": covers,
            "freeable_bytes": free, "steps": [{"nome": n, "ok": ok, "note": ""} for n, ok in steps]}


@pytest.mark.parametrize("prev,cur,peggiora", [
    (snap(), snap(), False),
    (snap(), snap(roms=[("g", "p")]), True),
    (snap(roms=[("g", "p")]), snap(), False),
    (snap(), snap(bios=[("ps1", "b.bin")]), True),
    (snap(bios=[("ps1", "b.bin")]), snap(bios=[("ps1", "b.bin")]), False),
    (snap(covers=2), snap(covers=3), True),
    (snap(covers=3), snap(covers=1), False),
    (snap(steps=[("a", True)]), snap(steps=[("a", False)]), True),
    (snap(steps=[("a", False)]), snap(steps=[("a", False)]), False),
])
def test_diff(prev, cur, peggiora):
    assert M.diff(prev, cur)["peggiora"] is peggiora


def test_diff_fields():
    d = M.diff(snap(roms=[("g", "p")], covers=1, free=10), snap(roms=[("h", "q")], covers=4, free=25))
    assert d["rom_nuove_mancanti"] == [{"game": "h", "path": "q"}]
    assert d["rom_ripristinate"] == [{"game": "g", "path": "p"}]
    assert d["covers_delta"] == 3 and d["freeable_delta"] == 15
    assert M.diff(snap(), snap(free=5))["freeable_delta"] is None


def test_run_failure_isolated(tmp_path, monkeypatch):
    cfg = types.SimpleNamespace(cache=str(tmp_path))
    calls = []

    def boom(cfg, s, c):
        raise RuntimeError("x")

    monkeypatch.setattr(M, "_integrity", boom)
    for n in ("_retry_covers", "_stores", "_backup"):
        monkeypatch.setattr(M, n, lambda cfg, s, c, *a, n=n: calls.append(n) or "ok")
    s = M.run(cfg)
    assert calls == ["_retry_covers", "_stores", "_backup"]
    assert [x["ok"] for x in s["steps"][:4]] == [False, True, True, True]
    assert s["covers_missing"] == 0
    r = M.latest(cfg)
    assert r["report"]["time"] == s["time"] and r["diff"] is None
    assert len(M.history(cfg)) == 1
