"""Correzione manuale del match: salvata in userdata, vince su cache e rescan, annullabile.

Esegui: python tests/test_match_override.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import config, matching, pipeline, platforms as P  # noqa: E402
from pozzo.cache import Cache  # noqa: E402
from pozzo.library.userdata import UserData  # noqa: E402
from pozzo.scanner import Game  # noqa: E402

# make_override: solo campi noti e serializzabili, titolo obbligatorio
ov = matching.make_override("  Super   Mario World ", "igdb", {"description": "d", "genres": ["Platform"], "x": 1, "developer": ""})
assert ov["title"] == "Super Mario World" and ov["fields"]["title"] == "Super Mario World"
assert "x" not in ov["fields"] and "developer" not in ov["fields"] and ov["fields"]["genres"] == ["Platform"]
try:
    matching.make_override("   ")
    raise SystemExit("titolo vuoto accettato")
except ValueError:
    pass

# la correzione ha la priorita' piu' alta
assert pipeline._rank("title", "manual") < pipeline._rank("title", "igdb")

with tempfile.TemporaryDirectory() as tmp:
    cfg = config.Config(cache=Path(tmp) / "cache", output=Path(tmp) / "out")
    cfg.sources = ["igdb", "libretro"]
    cache = Cache(cfg.cache)
    snes = P.PLATFORMS["snes"]
    g = Game(Path("Wrong Match.sfc"), snes, 100, 0, crc="AABBCCDD")
    h = Game(Path("Other.sfc"), snes, 200, 0, crc="11223344")
    # dati del match automatico (sbagliato) in cache: igdb + libretro
    cache.put(g.key, "igdb", "title", "Wrong Game")
    cache.put(g.key, "igdb", "description", "wrong text")
    cache.put(g.key, "libretro", "canonical", "Wrong Match (USA)")
    cache.put(h.key, "igdb", "title", "Other Game")
    cache.commit()

    assert pipeline.load_match_overrides(cfg) == {}  # nessun userdata.db: nessuna correzione
    ud = UserData(cfg.cache / "userdata.db")
    ud.set_match_override([g.key], matching.make_override("Right Game", "igdb", {"description": "right text"}))
    assert ud.match_overrides()[g.key]["title"] == "Right Game"
    ud.close()

    games = [g, h]
    pipeline.load_cached(cfg, cache, games)
    assert g.data["title"] == "Right Game" and g.data["description"] == "right text", g.data
    assert g.origin["title"] == "manual" and g.canonical == "Right Game" and g.match_by == "manual"
    assert g.search_name == "Right Game"  # le sorgenti cercano col titolo scelto
    assert h.data["title"] == "Other Game" and h.match_by == ""  # gli altri giochi non cambiano

    # un rescan che porta un titolo da una sorgente non scavalca la correzione
    pipeline.apply_field(g, "title", "Another Wrong", "igdb")
    pipeline.apply_field(g, "match_by", "hash", "libretro")
    assert g.data["title"] == "Right Game" and g.data["match_by"] == "manual"

    # purge: via i dati delle sorgenti, resta l'identificazione offline (libretro)
    pipeline.purge_keys(cache, [g.key])
    res = cache.resources(g.key)
    assert "igdb" not in res and res["libretro"]["canonical"] == "Wrong Match (USA)"
    assert cache.resources(h.key)["igdb"]["title"] == "Other Game"

    # annulla: senza correzione tornano i dati del match automatico
    ud = UserData(cfg.cache / "userdata.db")
    ud.set_match_override([g.key], None)
    assert ud.match_overrides() == {}
    ud.close()
    g2 = Game(Path("Wrong Match.sfc"), snes, 100, 0, crc="AABBCCDD")
    pipeline.load_cached(cfg, cache, [g2])
    assert g2.canonical == "Wrong Match (USA)" and g2.match_by == "" and "title" not in g2.origin.get("title", "manual")
    cache.close()

# ricerca manuale: la copia interrogata non ha hash e cerca col nome digitato
import asyncio  # noqa: E402
from pozzo.sources.base import Result, Source  # noqa: E402

seen = []


class Fake(Source):
    name = "fake"

    async def lookup(self, game):
        seen.append(game)
        return Result(fields={"title": game.search_name + " DX", "description": "x", "junk": 1}, media={"cover": "http://x/c.png"})


pipeline.SOURCES["fake"] = Fake
with tempfile.TemporaryDirectory() as tmp:
    cfg = config.Config(cache=Path(tmp) / "cache", output=Path(tmp) / "out")
    cfg.sources = ["fake", "libretro"]
    cache = Cache(cfg.cache)
    g = Game(Path("Wrong Match.sfc"), P.PLATFORMS["snes"], 100, 0, crc="AABBCCDD", md5="ab", canonical="Wrong")
    cands = asyncio.run(pipeline.search_candidates(cfg, cache, g, "Zelda: A Link?"))
    assert len(cands) == 1 and cands[0]["source"] == "fake" and cands[0]["title"] == "Zelda A Link DX", cands
    assert "junk" not in cands[0]["fields"] and cands[0]["cover"] == "http://x/c.png"
    p0 = seen[0]
    assert not p0.crc and not p0.md5 and p0.data == {} and g.crc == "AABBCCDD" and g.canonical == "Wrong"
    assert asyncio.run(pipeline.search_candidates(cfg, cache, g, "  ")) == []
    cache.close()
del pipeline.SOURCES["fake"]

print("OK")
