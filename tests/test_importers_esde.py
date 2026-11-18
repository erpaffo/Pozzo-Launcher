"""Importatore ES-DE (gamelist.xml). PYTHONUTF8=1 python tests/test_importers_esde.py"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pozzo import importers as IMP  # noqa: E402
from pozzo.importers.formats import PARSERS  # noqa: E402
from pozzo.library.userdata import UserData  # noqa: E402

SNES = """<?xml version="1.0"?>
<gameList>
	<game><path>./Zelda.sfc</path><name>Zelda</name><favorite>true</favorite></game>
	<game><path>./Tom.sfc</path><name>Tom &amp; Jerry</name></game>
</gameList>
"""
GBA = """<?xml version="1.0"?>
<gameList>
	<game><path>./Metroid.gba</path><name>Metroid</name><lastplayed>20240501T123000</lastplayed><playcount>3</playcount></game>
	<game><path>./Senza Nome.gba</path></game>
</gameList>
"""


def main():
    tmp = Path(tempfile.mkdtemp())
    for c, x in (("snes", SNES), ("gba", GBA)):
        (tmp / c).mkdir()
        (tmp / c / "gamelist.xml").write_text(x, encoding="utf-8")
    recs = {r["title"]: r for r in PARSERS["esde"](tmp)}
    assert sorted(recs) == ["Metroid", "Senza Nome", "Tom & Jerry", "Zelda"], recs.keys()
    assert recs["Zelda"]["favorite"] and not recs["Metroid"]["favorite"]
    assert recs["Metroid"]["last_played"] > 1.7e9 and recs["Metroid"]["playtime"] == 0 and not recs["Zelda"]["scripts"]
    assert recs["Zelda"]["collections"] == ["snes"] and recs["Metroid"]["collections"] == ["gba"]

    one = PARSERS["esde"](tmp / "snes" / "gamelist.xml")  # file singolo: nessuna raccolta
    assert len(one) == 2 and all(r["collections"] == [] for r in one)

    bad = tmp / "bad.xml"
    for txt in ("<gameList><game>", '<!DOCTYPE x [<!ENTITY a "b">]><gameList/>'):
        bad.write_text(txt)
        try:
            PARSERS["esde"](bad)
            raise SystemExit("atteso errore")
        except IMP.ImportError_:
            pass
    try:
        PARSERS["esde"](tmp / "snes")  # cartella senza sottocartelle console
        raise SystemExit("atteso errore")
    except IMP.ImportError_:
        pass

    user = UserData(tmp / "u.db")
    lib = SimpleNamespace(games=[{"key": "snes/zelda.sfc", "title": "Zelda", "store": None}])
    out = IMP.apply(user, lib, list(recs.values()))
    assert out["matched"] == 1 and out["favorites"] == 1 and out["skipped"] == 3 and out["scripts_ignored"] == 0, out
    print("ok")


if __name__ == "__main__":
    main()
