"""Gioco posseduto = mai tra gli online: ™/® nei titoli, lingue diverse (Spada/Sword), Title ID Switch."""

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pozzo import config, storemeta  # noqa: E402
from pozzo.cache import Cache  # noqa: E402
from pozzo.gametdb import parse_xml_text  # noqa: E402
from pozzo.library import build as B  # noqa: E402
from pozzo.matching import normalize  # noqa: E402

URL = "https://example-c.test/switch"
TDB = """<datafile><SwitchTDB version="1" games="6"/>
%s</datafile>"""


def _g(i, en, it):
    return (f'<game name="{en}"><id>{i}</id><region>EUR</region>'
            f'<locale lang="EN"><title>{en}</title></locale><locale lang="IT"><title>{it}</title></locale></game>')


GAMES = [("AAAAA", "Pokémon Sword", "Pokémon Spada"), ("BBBBB", "Pokémon Shield", "Pokémon Scudo"),
         ("CCCCC", "Pokémon Scarlet", "Pokémon Scarlatto"), ("DDDDD", "Pokémon Violet", "Pokémon Violetto"),
         ("EEEEE", "Pokémon: Let's Go, Pikachu!", "Pokémon: Let's Go, Pikachu!"),
         ("FFFFF", "Pokémon: Let's Go, Eevee!", "Pokémon: Let's Go, Eevee!")]
ONLINE = ["Pokémon™ Sword", "Pokémon™ Shield", "Pokémon™ Scarlet", "Pokémon™ Violet",
          "Pokémon™: Let's Go, Pikachu!", "Pokémon™: Let's Go, Eevee!"]


def _env(tmp_path, names, tdb=True):
    (tmp_path / "roms").mkdir()
    (tmp_path / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\n',
                                          encoding="utf-8")
    cfg = config.load(tmp_path / "config.toml")
    cfg.catalogs = {"switch": [URL]}
    cache = Cache(cfg.cache)
    cache.kv_set(f"catalog:type_c:{URL}", {"url": URL, "index_url": URL, "pid": "switch", "time": time.time(),
                 "entries": [{"name": f"{n} Switch NSP", "size": None, "url": f"https://example-c.test/{i}/",
                              "magnet": None} for i, n in enumerate(names)]})
    if tdb:
        (cfg.cache / "gametdb").mkdir(parents=True)
        idx = parse_xml_text(TDB % "".join(_g(*x) for x in GAMES))
        (cfg.cache / "gametdb" / "index.json").write_text(json.dumps(idx), encoding="utf-8")
    return cfg, cache


def _owned(stem, key, **data):
    return SimpleNamespace(key=key, platform=SimpleNamespace(id="switch"), stem=stem, inner_name="",
                           data=data, search_name=stem, path=Path("C:/roms") / (stem + ".nsp"))


def test_normalize_trademark():
    assert normalize("Pokémon™: Let's Go, Eevee!") == normalize("Pokémon: Let's Go, Eevee!") == "pokemon lets go eevee"
    assert normalize("Sonic® the Hedgehog©") == "sonic hedgehog"


def test_owned_other_language_hidden(tmp_path):
    """Possiedi Spada, Violetto, Eevee, Pikachu: le voci online omonime spariscono, Scarlet e Shield restano."""
    cfg, cache = _env(tmp_path, ONLINE)
    owned = {f"switch/{i}": _owned(n, f"switch/{i}") for i, n in enumerate(
        ["Pokémon Spada", "Pokémon Violetto", "Pokémon: Let's Go, Eevee!", "Pokémon: Let's Go, Pikachu!"])}
    entries, pages = B._catalog_entries(cfg, cache, owned)
    cache.close()
    assert sorted(e["title"] for e in entries) == ["Pokémon™ Scarlet", "Pokémon™ Shield"], [e["title"] for e in entries]
    # le schede possedute conservano il link allo store
    assert {k: [s["name"] for s in v] for k, v in pages.items()} == {
        "switch/0": ["Pokémon™ Sword Switch NSP"], "switch/1": ["Pokémon™ Violet Switch NSP"],
        "switch/2": ["Pokémon™: Let's Go, Eevee! Switch NSP"], "switch/3": ["Pokémon™: Let's Go, Pikachu! Switch NSP"]}, pages


def test_sword_vs_shield_stay_apart(tmp_path):
    cfg, cache = _env(tmp_path, ONLINE)
    entries, pages = B._catalog_entries(cfg, cache, {"switch/0": _owned("Pokémon Sword", "switch/0")})
    cache.close()
    assert len(entries) == 5 and not any(e["title"].endswith("Sword") for e in entries), [e["title"] for e in entries]
    assert [s["name"] for s in pages["switch/0"]] == ["Pokémon™ Sword Switch NSP"]


def test_title_id_without_gametdb(tmp_path):
    """Senza GameTDB: il Title ID nel nome file (o letto dal pacchetto) o nella pagina dello store basta."""
    cfg, cache = _env(tmp_path, ["Uno Strano Titolo", "Altro Gioco", "Terzo"], tdb=False)
    storemeta.put(cache, "https://example-c.test/0/", {"title_id": "0100ABF008968000"}, "page")
    storemeta.put(cache, "https://example-c.test/1/", {"title_id": "0100ABF008969000"}, "page")
    owned = {"switch/a": _owned("Gioco Locale [0100ABF008968000][v0]", "switch/a"),
             # solo l'aggiornamento (…800) non fa possedere il gioco
             "switch/b": _owned("Altro [0100ABF008969800][v65536]", "switch/b"),
             "switch/c": _owned("Terzo Locale", "switch/c", titleid="0100000000010000")}
    entries, pages = B._catalog_entries(cfg, cache, owned)
    cache.close()
    assert sorted(e["title"] for e in entries) == ["Altro Gioco", "Terzo"], [e["title"] for e in entries]
    assert list(pages) == ["switch/a"], pages
    assert B._game_tid("x [0100ABF008968001]") == "" and B._game_tid("0100ABF008968000") == "0100ABF008968000"


def test_dlc_not_hidden_by_base_id(tmp_path):
    """La DLC del gioco posseduto resta una voce a parte (stesso ID base, ma non e' il gioco)."""
    cfg, cache = _env(tmp_path, ["Pokémon Sword Expansion Pass DLC"])
    storemeta.put(cache, "https://example-c.test/0/", {"title_id": "0100ABF008969001"}, "page")
    entries, _ = B._catalog_entries(cfg, cache, {"switch/a": _owned("Pokémon Spada [0100ABF008968000]", "switch/a")})
    cache.close()
    assert [e["content"] for e in entries] == ["dlc"], entries


def test_downloaded_kv_with_trademark(tmp_path):
    cfg, cache = _env(tmp_path, ["Pokémon™ Sword"], tdb=False)
    g = _owned("Sword", "switch/dl")
    cache.kv_set("downloaded", [{"title": "Pokémon Sword", "pid": "switch", "paths": [str(g.path)]}])
    entries, pages = B._catalog_entries(cfg, cache, {"switch/dl": g})
    cache.close()
    assert entries == [] and list(pages) == ["switch/dl"], (entries, pages)
