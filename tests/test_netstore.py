"""Cartella di rete come store: elenco, pozzo.json, installazione di zip e cartella (senza rete)."""
import asyncio
import json
import types
import zipfile
from pathlib import Path

from pozzo.cache import Cache
from pozzo.stores import netstore as NS

tr = lambda k, **kw: k  # noqa: E731


def _tree(root: Path):
    (root / "Cool Game (v1.2)").mkdir()
    (root / "Cool Game (v1.2)" / "game.exe").write_bytes(b"MZ" + b"0" * 500)
    (root / "Cool Game (v1.2)" / "unins000.exe").write_bytes(b"MZ" + b"0" * 900)
    (root / "Custom").mkdir()
    (root / "Custom" / "a.exe").write_bytes(b"MZ" + b"0" * 900)
    (root / "Custom" / "b.exe").write_bytes(b"MZ" + b"0" * 100)
    (root / "Custom" / "pozzo.json").write_text(json.dumps({"title": "Nome Bello", "exe": "b.exe", "args": ["-w"]}))
    (root / "Inst").mkdir()
    (root / "Inst" / "setup.exe").write_bytes(b"MZ")
    with zipfile.ZipFile(root / "Zipped_Game.zip", "w") as z:
        z.writestr("Zipped_Game/zip.exe", b"MZ" + b"1" * 300)
    (root / "setup_gog_game_1.0.exe").write_bytes(b"MZ")
    (root / "readme.txt").write_text("x")
    (root / ".hidden").mkdir()


def test_list_and_install(tmp):
    share = tmp / "share"
    share.mkdir()
    _tree(share)
    by = {e["title"]: e for e in NS.list_entries([share, tmp / "nonexistent"])}
    assert {e["kind"] for e in by.values()} == {"folder", "installer", "archive"}
    assert by["Cool Game (v1.2)".split(" (")[0]]["kind"] == "folder"
    assert by["Nome Bello"]["override"]["exe"] == "b.exe"
    assert by["Zipped Game"]["kind"] == "archive" and by["Inst"]["kind"] == "installer"
    assert len(by) == 5 and "readme" not in by

    dest = tmp / "games"
    cfg = types.SimpleNamespace(stores={"netstore": {"folders": [str(share)], "dest": str(dest)}})
    steps = []
    rec = NS.install(cfg, by["Zipped Game"], lambda f, ph: steps.append(f), tr)
    assert Path(rec["exe"]).name == "zip.exe" and Path(rec["exe"]).is_file() and steps[-1] > 0.9
    assert not [p for p in dest.iterdir() if p.name.startswith(".netstore-")]  # temporanea ripulita
    rec = NS.install(cfg, by["Nome Bello"], lambda f, ph: None, tr)
    assert Path(rec["exe"]).name == "b.exe" and rec["args"] == ["-w"]  # pozzo.json batte l'euristica
    rec = NS.install(cfg, by["Cool Game"], lambda f, ph: None, tr)
    assert Path(rec["exe"]).name == "game.exe"  # unins000.exe escluso, anche se piu' grande


def test_provider_installed_state(tmp):
    share = tmp / "s"
    share.mkdir()
    _tree(share)
    cache = Cache(tmp / "cache")
    exe = tmp / "game.exe"
    exe.write_bytes(b"MZ")
    gid = next(e["id"] for e in NS.list_entries([share]) if e["title"] == "Cool Game")
    cache.kv_set(NS.INSTALLED_KEY, {gid: {"title": "Cool Game", "exe": str(exe), "args": [], "cwd": "", "dir": str(tmp)}})
    cfg = types.SimpleNamespace(stores={"netstore": {"folders": [str(share)]}})
    games = asyncio.run(NS.NetStore(cfg, cache, None, print).fetch())
    g = {x.id: x for x in games}[gid]
    assert g.installed and g.launch["target"] == str(exe)
    others = [x for x in games if x.id != gid]
    assert others and not any(x.installed for x in others) and all(x.install_uri.startswith("pozzo-netstore:") for x in others)
    cache.close()
