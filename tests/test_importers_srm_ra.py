"""Importatori Steam ROM Manager e RetroArch + anteprima (dry-run). PYTHONUTF8=1 python tests/test_importers_srm_ra.py"""
import json
import struct
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pozzo import importers as IMP  # noqa: E402
from pozzo.importers.formats import PARSERS  # noqa: E402
from pozzo.library.userdata import UserData  # noqa: E402


def _s(k, v):
    return b"\x01" + k.encode() + b"\0" + v.encode() + b"\0"


def _vdf(entries):
    b = b"\x00shortcuts\x00"
    for i, e in enumerate(entries):
        b += b"\x00" + str(i).encode() + b"\0"
        b += _s("AppName", e["name"]) + _s("Exe", '"%s"' % e["exe"]) + _s("LaunchOptions", e.get("opts", ""))
        b += b"\x02LastPlayTime\0" + struct.pack("<I", e.get("last", 0))
        b += b"\x00tags\x00" + b"".join(_s(str(j), t) for j, t in enumerate(e.get("tags", []))) + b"\x08"
        b += b"\x08"
    return b + b"\x08\x08"


def main():
    tmp = Path(tempfile.mkdtemp())
    user = UserData(tmp / "u.db")
    lib = SimpleNamespace(games=[{"key": "snes/zelda.sfc", "title": "Zelda", "store": None}])
    exe = tmp / "game.exe"
    exe.write_bytes(b"MZ")

    # SRM shortcuts.vdf
    v = tmp / "shortcuts.vdf"
    v.write_bytes(_vdf([{"name": "Nuovo Gioco", "exe": str(exe), "tags": ["Retro"], "last": 1700000000},
                        {"name": "Zelda", "exe": "C:/x/emu.exe", "opts": "--fullscreen"}]))
    recs = PARSERS["srm"](v)
    assert [r["title"] for r in recs] == ["Nuovo Gioco", "Zelda"]
    assert recs[0]["collections"] == ["Retro"] and recs[0]["last_played"] == 1700000000 and recs[0]["exe"] == str(exe)
    assert recs[1]["scripts"] and not recs[0]["scripts"]

    # SRM userConfigurations.json
    roms = tmp / "roms"
    roms.mkdir()
    (roms / "Metroid.sfc").write_text("x")
    (tmp / "userConfigurations.json").write_text(json.dumps(
        [{"configTitle": "SNES", "romDirectory": str(roms), "executableArgs": "-f"}, {"configTitle": "x", "romDirectory": "/no/dir"}]))
    (r,) = PARSERS["srm"](tmp / "userConfigurations.json")
    assert r["title"] == "Metroid" and r["collections"] == ["SNES"] and r["scripts"]

    # RetroArch
    pl = tmp / "playlists"
    pl.mkdir()
    (pl / "SNES.lpl").write_text(json.dumps({"version": "1.5", "items": [
        {"path": "a.sfc", "label": "Zelda", "runtime_hours": 1, "runtime_minutes": 30, "runtime_seconds": 0,
         "last_played_year": 2024, "last_played_month": 5, "last_played_day": 1},
        {"path": "b.sfc", "label": "Metroid"}]}))
    (pl / "content_favorites.lpl").write_text(json.dumps({"items": [{"label": "Zelda"}]}))
    (pl / "content_history.lpl").write_text(json.dumps({"items": [{"label": "Cronologia"}]}))
    recs = {r["title"]: r for r in PARSERS["retroarch"](pl)}
    assert recs["Zelda"]["playtime"] == 5400 and recs["Zelda"]["favorite"] and recs["Zelda"]["collections"] == ["SNES"]
    assert recs["Cronologia"]["collections"] == []
    (pl / "old.lpl").write_text("/path\nlabel\n")
    try:
        PARSERS["retroarch"](pl / "old.lpl")
        raise SystemExit("atteso errore")
    except IMP.ImportError_:
        pass

    # anteprima: nessuna scrittura, conteggi corretti
    recs = PARSERS["srm"](v) + PARSERS["retroarch"](pl / "SNES.lpl")
    pv = IMP.preview(user, lib, recs)
    assert (pv["new"], pv["present"]) == (1, 2) and pv["ignored"] == 1 and pv["total"] == 4, pv
    assert pv["scripts_ignored"] == 1 and pv["playtime"] == 1 and pv["collections"] >= 2
    assert pv["samples"]["new"] == ["Nuovo Gioco"]
    assert user.games() == {} or not user.games().get("snes/zelda.sfc", {}).get("playtime")
    assert not [c for c in user.collections().values() if c.get("custom")]
    out = IMP.apply(user, lib, recs)
    assert out["added"] == 1 and out["matched"] == 2 and out["skipped"] == 1
    print("ok")


if __name__ == "__main__":
    main()
