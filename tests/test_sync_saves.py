"""Sincronizzazione dei file di salvataggio veri tra due PC (cartella condivisa). Niente rete, niente emulatori."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config, sync  # noqa: E402
from pozzo.library import saves as SV  # noqa: E402

KEY = "snes/x"


def pc(root: Path, name: str, shared: Path, saves: dict[str, Path] | None = None, playing=None):
    """Un PC con la sua cartella dati, una cartella condivisa e i salvataggi dei giochi indicati."""
    d = root / name
    (d / "cache").mkdir(parents=True, exist_ok=True)
    (d / "config.toml").write_text("[paths]", encoding="utf-8")
    cfg = config.Config(cache=d / "cache", output=d / "out")
    cfg.config_path = d / "config.toml"

    def saves_of(key, title):
        return [saves[key]] if saves and key in saves else []

    sync.save_conf(cfg, {**sync.conf(cfg), "folder": str(shared), "pc_name": name,
                         "saves": True, "saves_games": sorted(saves or {})})
    return cfg, sync.Sync(cfg, lambda pid: sync.open_profile(cfg, pid),
                          playing=playing or (lambda: False), saves_of=saves_of)


def saves_dir(root: Path, name: str) -> Path:
    d = root / name / "saves" / "Game1"
    d.mkdir(parents=True)
    return d


def real_files(root: Path) -> list[Path]:
    """File davvero presenti: su Windows «aux.txt» risulta esistere sempre (e' il dispositivo AUX), os.walk no."""
    return [Path(dp) / n for dp, _dirs, names in os.walk(root) for n in names]


def test_api_sync_saves(tmp):
    """Le rotte dell'app: impostazioni dei salvataggi, elenco dei giochi con salvataggi, rotta dei file ai soli PC."""
    import base64

    from fastapi.testclient import TestClient

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_frontend import make_library

    from pozzo.app.server import create_app

    cache = tmp / "cache"
    cache.mkdir()
    rom = tmp / "game.gba"
    rom.write_bytes(b"x")
    make_library(cache, rom)
    saved = tmp / "salvataggi" / "AAA"
    saved.mkdir(parents=True)
    (saved / "slot1.sav").write_bytes(b"ciao")
    cfg = config.Config(cache=cache, output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    SV.set_paths(cfg, "gba/AAA", [str(saved)])
    app = create_app(cfg)
    c = TestClient(app)

    st = c.get("/api/sync").json()
    assert st["saves"] == {"enabled": False, "games": []}, st
    found = c.get("/api/sync/saves").json()
    assert found["enabled"] is False, found
    game = next(g for g in found["games"] if g["key"] == "gba/AAA")
    assert game["files"] == 1 and game["size"] == 4 and game["included"] is False, game
    print("ok  elenco dei salvataggi della libreria con dimensioni e giochi inclusi")

    st = c.post("/api/sync", json={"saves": True, "saves_games": ["gba/AAA", "", "gba/AAA"]}).json()
    assert st["saves"] == {"enabled": True, "games": ["gba/AAA"]}, st
    assert c.get("/api/sync/saves").json()["games"][0]["included"] is True
    assert c.post("/api/sync", json={"saves_games": "gba/AAA"}).status_code == 400
    print("ok  impostazioni: interruttore e giochi scelti (chiavi vuote e doppioni scartati)")

    assert c.post("/api/sync/saves/file", json={"key": "gba/AAA", "rel": "salvataggi/AAA/slot1.sav"}).status_code == 403

    from pozzo.remote.phone import PhoneGate
    hub = app.state.phone_hub
    gate = TestClient(PhoneGate(app, hub), base_url="https://testserver")
    pc_token = gate.post("/api/sync/pair", json={"code": hub.new_code(), "name": "Portatile"}).json()
    gate.cookies.set("gs_phone", pc_token["token"])
    got = gate.post("/api/sync/saves/file", json={"key": "gba/AAA", "rel": "salvataggi/AAA/slot1.sav"})
    assert got.status_code == 200, got.text
    assert base64.b64decode(got.json()["data"]) == b"ciao" and got.json()["size"] == 4, got.json()
    assert gate.post("/api/sync/saves/file", json={"key": "gba/AAA", "rel": "../fuori.txt"}).status_code == 400
    assert gate.post("/api/sync/saves/file", json={"key": "gba/BBB", "rel": "salvataggi/AAA/slot1.sav"}).status_code == 403
    print("ok  la rotta dei file risponde ai PC abbinati, solo per i giochi scelti e con percorsi validi")


def test_saves_unchanged(tmp_path):
    """Stessi file sui due PC: nessuna copia, nessun conflitto."""
    shared = tmp_path / "shared"
    shared.mkdir()
    a, b = saves_dir(tmp_path, "A"), saves_dir(tmp_path, "B")
    (a / "slot1.sav").write_bytes(b"uguale")
    (b / "slot1.sav").write_bytes(b"uguale")
    cfg_a, sa = pc(tmp_path, "A", shared, {KEY: a})
    cfg_b, sb = pc(tmp_path, "B", shared, {KEY: b})

    ra, rb = sa.run(), sb.run()
    assert ra["saves"]["ok"] and rb["saves"]["ok"], (ra, rb)
    assert ra["saves"]["updated"] == [] and rb["saves"]["updated"] == []
    assert ra["saves"]["conflicts"] == [] and rb["saves"]["conflicts"] == []
    assert rb["saves"]["from"] == 1, "il manifest dell'altro PC viene letto"
    assert SV.list_backups(cfg_a, KEY) == [] and SV.list_backups(cfg_b, KEY) == []
    assert (b / "slot1.sav").read_bytes() == b"uguale"
    published = shared / sync.DIR / sync.SAVES_DIR
    assert (published / f"{sa.pc()['pc_id']}.json").is_file(), "manifest nella cartella condivisa"
    assert (published / sa.pc()["pc_id"] / SV.folder(cfg_a, KEY).name / "saves" / "Game1" / "slot1.sav").is_file()


def test_saves_one_side_changed(tmp_path):
    """Cambia un solo PC: l'altro riceve il contenuto nuovo e la versione sovrascritta va tra le copie."""
    shared = tmp_path / "shared"
    shared.mkdir()
    a, b = saves_dir(tmp_path, "A"), saves_dir(tmp_path, "B")
    (a / "slot1.sav").write_bytes(b"prima")
    (b / "slot1.sav").write_bytes(b"prima")
    cfg_a, sa = pc(tmp_path, "A", shared, {KEY: a})
    cfg_b, sb = pc(tmp_path, "B", shared, {KEY: b})
    sa.run(), sb.run()

    (a / "slot1.sav").write_bytes(b"nuovo di A")
    ra = sa.run()
    assert ra["saves"]["conflicts"] == [], ra["saves"]
    rb = sb.run()
    assert rb["saves"]["conflicts"] == [], rb["saves"]
    assert (b / "slot1.sav").read_bytes() == b"nuovo di A"
    assert any(f"{KEY}/" in u for u in rb["saves"]["updated"]), rb["saves"]
    back = SV.list_backups(cfg_b, KEY)
    assert back and back[0]["reason"] == "sync", back
    assert (a / "slot1.sav").read_bytes() == b"nuovo di A", "A tiene la sua versione"


def test_saves_conflict_keeps_local_version(tmp_path):
    """Cambiano tutti e due: il file locale resta, la versione dell'altro PC va tra le copie con la nota."""
    shared = tmp_path / "shared"
    shared.mkdir()
    a, b = saves_dir(tmp_path, "A"), saves_dir(tmp_path, "B")
    (a / "slot1.sav").write_bytes(b"prima")
    (b / "slot1.sav").write_bytes(b"prima")
    cfg_a, sa = pc(tmp_path, "A", shared, {KEY: a})
    cfg_b, sb = pc(tmp_path, "B", shared, {KEY: b})
    sa.run(), sb.run()

    (a / "slot1.sav").write_bytes(b"cambia A")
    (b / "slot1.sav").write_bytes(b"cambia B")
    ra = sa.run()  # A ha ancora il manifest vecchio di B: vince il locale
    assert ra["saves"]["conflicts"] == [], ra["saves"]
    rb = sb.run()  # B vede il nuovo di A e il base vecchio: conflitto
    assert rb["saves"]["conflicts"], rb["saves"]
    assert (b / "slot1.sav").read_bytes() == b"cambia B", "il file locale non si sovrascrive"
    back = SV.list_backups(cfg_b, KEY)
    assert back and "(conflitto" in back[0]["note"], back
    assert back[0]["reason"].startswith("conflitto"), back


def test_saves_apply_from_peer_bytes(tmp_path):
    """Come nel trasporto peer: i byte arrivano da una funzione (una richiesta per file), non da una cartella."""
    shared = tmp_path / "shared"
    shared.mkdir()
    a = saves_dir(tmp_path, "A")
    (a / "slot1.sav").write_bytes(b"vecchio")
    cfg, s = pc(tmp_path, "A", shared, {KEY: a})
    s.run()  # primo giro: registra lo stato di partenza

    remote = {"format": sync.FORMAT, "pc": "peer", "pc_name": "Portatile", "time": 0,
              "games": {KEY: {"title": "snes/x", "files": {"saves/Game1/slot1.sav": {"sha1": "0" * 40, "size": 5}}}}}
    asked, res = [], {"ok": True, "from": 1, "updated": [], "conflicts": [], "warnings": []}
    s.saves_apply(remote, res, get_remote=lambda k, rel: (asked.append((k, rel)), b"nuovo")[1])

    assert asked == [(KEY, "saves/Game1/slot1.sav")], asked
    assert (a / "slot1.sav").read_bytes() == b"nuovo"
    back = SV.list_backups(cfg, KEY)
    assert back and back[0]["reason"] == "sync", back
    assert res["updated"] == [f"{KEY}/saves/Game1/slot1.sav"], res


def test_saves_skipped_while_playing(tmp_path):
    """Gioco in esecuzione: nessun file toccato, il resto della sincronizzazione continua."""
    shared = tmp_path / "shared"
    shared.mkdir()
    a = saves_dir(tmp_path, "A")
    (a / "slot1.sav").write_bytes(b"prima")
    cfg, s = pc(tmp_path, "A", shared, {KEY: a}, playing=lambda: True)
    r = s.run()
    assert r["saves"] == {"skipped": "gioco in esecuzione"}, r["saves"]
    assert not (shared / sync.DIR / sync.SAVES_DIR).exists()
    assert SV.list_backups(cfg, KEY) == []
    assert r["folder"]["ok"], "i dati personali si sincronizzano lo stesso"


def test_saves_malicious_manifest_ignored(tmp_path):
    """Un manifest con percorsi pericolosi: scartati, niente scritto fuori dalla cartella dei salvataggi."""
    shared = tmp_path / "shared"
    shared.mkdir()
    a = saves_dir(tmp_path, "A")
    cfg, s = pc(tmp_path, "A", shared, {KEY: a})
    root = shared / sync.DIR / sync.SAVES_DIR
    root.mkdir(parents=True)
    (root / "evil" / SV.folder(cfg, KEY).name / "Game1").mkdir(parents=True)
    (root / "evil" / SV.folder(cfg, KEY).name / "Game1" / "ok.txt").write_bytes(b"va bene")
    bad = {"format": sync.FORMAT, "pc": "evil", "pc_name": "PC cattivo", "time": 0,
           "games": {KEY: {"title": "snes/x", "files": {
               "../evil.txt": {"sha1": "a" * 40, "size": 3},
               "aux.txt": {"sha1": "b" * 40, "size": 3},
               "C:/Windows/evil.dll": {"sha1": "c" * 40, "size": 3},
               "Game1/ok.txt": {"sha1": "d" * 40, "size": 8}}}}}
    (root / "evil.json").write_text(json.dumps(bad), encoding="utf-8")

    r = s.run()
    assert any("scartato" in w for w in r["saves"]["warnings"]), r["saves"]["warnings"]
    written = {p.name for p in real_files(tmp_path)}
    assert "evil.txt" not in written and "evil.dll" not in written, written
    assert "aux.txt" not in written, "un nome riservato di Windows non si scrive mai"
    assert (a / "ok.txt").read_bytes() == b"va bene", "il percorso valido invece arriva"


def test_saves_file_too_big_is_skipped(tmp_path, monkeypatch):
    """Oltre il tetto per file: saltato con un avviso (nessun file enorme creato grazie al monkeypatch)."""
    monkeypatch.setattr(sync, "SAVE_FILE_MAX", 8)
    shared = tmp_path / "shared"
    shared.mkdir()
    a, b = saves_dir(tmp_path, "A"), saves_dir(tmp_path, "B")
    (a / "big.sav").write_bytes(b"x" * 100)
    cfg_a, sa = pc(tmp_path, "A", shared, {KEY: a})
    cfg_b, sb = pc(tmp_path, "B", shared, {KEY: b})
    sa.run()
    r = sb.run()
    assert not (b / "big.sav").exists()
    assert any("troppo grande" in w for w in r["saves"]["warnings"]), r["saves"]["warnings"]

def test_saves_conflict_does_not_overwrite_on_the_next_round(tmp_path):
    """Il conflitto non si "risolve" da solo al giro dopo: nessuno dei due file viene sovrascritto."""
    shared = tmp_path / "shared"
    shared.mkdir()
    a, b = saves_dir(tmp_path, "A"), saves_dir(tmp_path, "B")
    (a / "slot1.sav").write_bytes(b"prima")
    (b / "slot1.sav").write_bytes(b"prima")
    cfg_a, sa = pc(tmp_path, "A", shared, {KEY: a})
    cfg_b, sb = pc(tmp_path, "B", shared, {KEY: b})
    sa.run(), sb.run()

    (a / "slot1.sav").write_bytes(b"cambia A")
    (b / "slot1.sav").write_bytes(b"cambia B")
    sa.run()
    assert sb.run()["saves"]["conflicts"], "primo giro: conflitto su B"
    ra = sa.run()  # secondo giro: la base non deve far sembrare "solo remoto" il file dell'altro PC
    assert ra["saves"]["conflicts"], ra["saves"]
    assert (a / "slot1.sav").read_bytes() == b"cambia A", "il file locale non si sovrascrive"
    assert (b / "slot1.sav").read_bytes() == b"cambia B"
    assert len([x for x in SV.list_backups(cfg_a, KEY) if "conflitto" in x["reason"]]) == 1, "una sola copia di conflitto"
