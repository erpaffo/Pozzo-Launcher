"""Gioco scaricato ed estratto: cartella giusta nella libreria, scansione normale, evento, voce online sostituita. Nessuna rete."""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import config, platforms as P  # noqa: E402
from pozzo.app.extensions import Events  # noqa: E402
from pozzo.cache import Cache  # noqa: E402
from pozzo.downloads import ingest as IN  # noqa: E402
from pozzo.scanner import find_platform_dirs, list_entries, scan  # noqa: E402


def make_cfg(tmp, roms=True):
    cfg = config.Config(roms=tmp / "roms", cache=tmp / "cache", output=tmp / "out")
    cfg.config_path = tmp / "config.toml"
    cfg.cache.mkdir()
    if roms:
        cfg.roms.mkdir()
    return cfg


class FakeLib:
    """Libreria minima: lo scan finto la riempie con i file che il vero scanner trova."""

    def __init__(self):
        self.games, self.lock = [], __import__("threading").RLock()

    def get(self, gid):
        from fastapi import HTTPException
        for g in self.games:
            if g["id"] == gid:
                return g
        raise HTTPException(404)


def make_ctx(cfg, lib=None, online=None):
    lib = lib or FakeLib()
    if online:
        lib.games.append(online)
    ev, calls, got = Events(), [], []
    ev.on("game_downloaded", got.append)

    def scan_start(body):
        calls.append(body)
        n = 100
        for p, folder in find_platform_dirs(cfg):
            if p.id in body.get("platforms", ()):
                for path, _ in list_entries(p, folder):
                    n += 1
                    lib.games.append({"id": n, "title": path.stem, "key": f"{p.id}/{n}", "platform": p.id,
                                      "files": [str(path)], "store": None})
        return {}

    return SimpleNamespace(cfg=cfg, lib=lib, events=ev, api_scan_start=scan_start), calls, got


def extracted(tmp, *names):
    d = tmp / "dl" / "Gioco"
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for n in names:
        (d / n).write_bytes(b"x" * 10)
        out.append(d / n)
    return out


def test_target_dir_crea_cartella_riconosciuta_dallo_scanner(tmp):
    cfg = make_cfg(tmp)
    d = IN.target_dir(cfg, "switch")
    assert d.parent == cfg.roms and d.is_dir()
    assert P.detect(d.name).id == "switch"
    assert [(p.id, x) for p, x in find_platform_dirs(cfg)] == [("switch", d)], "lo scanner la trova senza registrazioni"
    assert not cfg.extra_roms and IN.target_dir(cfg, "switch") == d


def test_target_dir_riusa_cartella_esistente_anche_annidata(tmp):
    cfg = make_cfg(tmp)
    nested = cfg.roms / "Myrient" / "Nintendo - Super Nintendo Entertainment System"
    nested.mkdir(parents=True)
    assert IN.target_dir(cfg, "snes") == nested
    own = cfg.roms / "SNES"
    own.mkdir()
    assert IN.target_dir(cfg, "snes") == own, "meglio quella direttamente sotto la cartella ROM"
    cfg.platform_folders["Giochi Switch"] = "switch"
    (cfg.roms / "Giochi Switch").mkdir()
    assert IN.target_dir(cfg, "switch").name == "Giochi Switch", "assegnazione manuale della cartella"


def test_target_dir_senza_cartella_rom_registra_giochi(tmp):
    cfg = make_cfg(tmp, roms=False)
    d = IN.target_dir(cfg, "gba", tmp / "dl")
    assert d == tmp / "dl" / "Giochi" / "Game Boy Advance" and d.is_dir()
    assert cfg.extra_roms == [tmp / "dl" / "Giochi"]
    assert json.loads((tmp / "settings.json").read_text("utf-8"))["paths"]["extra_roms"] == [str(tmp / "dl" / "Giochi")]
    assert [(p.id, x) for p, x in find_platform_dirs(cfg)] == [("gba", d)]
    assert IN.target_dir(cfg, "gba", tmp / "dl") == d and len(cfg.extra_roms) == 1, "nessun doppione"
    with pytest.raises(ValueError):
        IN.target_dir(cfg, "windows")


def test_ingest_sposta_trovata_da_scansione_normale(tmp):
    cfg = make_cfg(tmp)
    (src,) = extracted(tmp, "Mega Quest.xci")
    ctx, calls, got = make_ctx(cfg, online={"id": 7, "title": "Mega Quest", "platform": "switch", "store": "online", "key": "k"})
    r = IN.ingest(ctx, 7, None, [src], poll=0.01)
    dest = cfg.roms / IN.target_dir(cfg, "switch").name / "Mega Quest" / "Mega Quest.xci"
    assert r == {"ok": True, "game_id": 101, "files": [str(dest)]} and dest.is_file() and not src.exists()
    assert calls == [{"platforms": ["switch"]}], "una sola scansione, solo della console"
    assert got == [{"game_id": 101, "from_id": 7, "title": "Mega Quest", "key": "switch/101", "files": [str(dest)]}]
    # scansione vera, come "Cerca nuovi giochi": nessuna cartella speciale registrata
    games = scan(cfg, Cache(cfg.cache), find_platform_dirs(cfg))
    assert [g.path for g in games] == [dest.parent] and not cfg.extra_roms
    # il titolo della voce online e' ricordato per la ricostruzione
    assert Cache(cfg.cache).kv_get("downloaded")[0]["title"] == "Mega Quest"


def test_ingest_collisione_e_non_giocabili(tmp):
    cfg = make_cfg(tmp)
    dest = IN.target_dir(cfg, "switch")
    (dest / "Gioco.nsp").write_bytes(b"old")
    a, junk, wrong = extracted(tmp, "Gioco.nsp", "leggimi.txt", "Gioco.gba")
    ctx, calls, got = make_ctx(cfg)
    r = IN.ingest(ctx, None, "switch", [a, junk, wrong], poll=0.01)
    assert r["ok"] and r["files"] == [str(dest / "Gioco" / "Gioco.nsp")]
    assert (dest / "Gioco.nsp").read_bytes() == b"old" and (dest / "Gioco" / "Gioco.nsp").read_bytes() == b"x" * 10
    assert junk.exists() and wrong.exists(), "i file non giocabili non si toccano"
    r = IN.ingest(ctx, None, "switch", [junk, wrong], poll=0.01)
    assert not r["ok"] and r["game_id"] is None and "Nessun file giocabile" in r["error"]
    assert len(calls) == 1 and len(got) == 1, "nessuna scansione ne' evento se non c'e' nulla da mettere"
    assert not IN.ingest(ctx, None, "windows", [a], poll=0.01)["ok"] and not IN.ingest(ctx, None, None, [a])["ok"]


def test_ingest_dischi_e_aggiornamenti_in_sottocartella(tmp):
    cfg = make_cfg(tmp)
    cue, = extracted(tmp, "Crash.cue")
    (cue.parent / "Crash (Track 1).bin").write_bytes(b"1")
    (cue.parent / "Crash (Track 2).bin").write_bytes(b"2")
    cue.write_text('FILE "Crash (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\nFILE "Crash (Track 2).bin" BINARY\n', "utf-8")
    ctx, calls, got = make_ctx(cfg)
    r = IN.ingest(ctx, None, "psx", [cue], poll=0.01)
    d = IN.target_dir(cfg, "psx") / "Crash"
    assert r["files"] == [str(d / "Crash.cue")]
    assert sorted(x.name for x in d.iterdir()) == ["Crash (Track 1).bin", "Crash (Track 2).bin", "Crash.cue"]
    assert d / "Crash.cue" in [p for p, _ in list_entries(P.PLATFORMS["psx"], d.parent)], "lo scanner la vede"
    # Switch (dir_games): base + aggiornamento = una sola cartella = un solo gioco per lo scanner
    base, upd = extracted(tmp, "Mega.xci", "Mega [upd].nsp")
    r = IN.ingest(ctx, None, "switch", [base, upd], poll=0.01)
    sw = IN.target_dir(cfg, "switch")
    assert [p.parent.name for p in map(Path, r["files"])] == ["Mega", "Mega"] and (sw / "Mega").is_dir()
    assert [(p.name, isdir) for p, isdir in list_entries(P.PLATFORMS["switch"], sw)] == [("Mega", True)]
    # un solo file Switch: comunque in una cartella col nome del gioco
    one, = extracted(tmp, "Solo.nsp")
    IN.ingest(ctx, None, "switch", [one], poll=0.01)
    assert (sw / "Solo" / "Solo.nsp").is_file()


def test_ingest_file_gia_in_cartella_scansionata_non_si_sposta(tmp):
    cfg = make_cfg(tmp)
    sw = IN.target_dir(cfg, "switch")
    f = sw / "Gia.nsp"
    f.write_bytes(b"x")
    ctx, calls, got = make_ctx(cfg)
    r = IN.ingest(ctx, None, "switch", [f], poll=0.01)
    assert r["files"] == [str(f)] and f.is_file() and r["game_id"] == 101


def test_ingest_attende_lavoro_in_corso_e_pending_al_timeout(tmp):
    from fastapi import HTTPException
    cfg = make_cfg(tmp)
    (src,) = extracted(tmp, "Mega.xci")
    ctx, calls, got = make_ctx(cfg)
    real, n = ctx.api_scan_start, []

    def busy_then_ok(body):
        n.append(1)
        if len(n) == 1:
            raise HTTPException(409, "in corso")
        return real(body)
    ctx.api_scan_start = busy_then_ok
    assert IN.ingest(ctx, None, "switch", [src], poll=0.01)["game_id"] == 101 and len(n) == 2
    (src2,) = extracted(tmp, "Altro.xci")
    ctx.api_scan_start = lambda body: {}  # la libreria non si aggiorna
    r = IN.ingest(ctx, None, "switch", [src2], timeout=0.05, poll=0.01)
    assert r["ok"] and r["pending"] and r["game_id"] is None and len(got) == 1


def test_voce_online_sostituita_dal_gioco_posseduto(tmp):
    """Dopo l'ingest la ricostruzione toglie la voce online (titolo posseduto) anche se il file ha un altro nome."""
    from pozzo.catalog import catalog_key
    from pozzo.library import build as B
    from pozzo.scanner import Game
    cfg = make_cfg(tmp)
    url = "https://sw.test/list/"
    cfg.catalogs = {"switch": [url]}
    c = Cache(cfg.cache)
    c.kv_set(catalog_key("switch", url), {"entries": [{"name": "Mega Quest (USA).nsp", "url": "https://sw.test/mq"}], "time": 1})
    sw = P.PLATFORMS["switch"]
    path = IN.target_dir(cfg, "switch") / "mq_final.nsp"
    path.write_bytes(b"x")
    owned = {"k": Game(path=path, platform=sw, size=1, mtime=1)}
    owned = {g.key: g for g in owned.values()}

    def online():
        out, pages = B._catalog_entries(cfg, c, owned)
        return [e["title"] for e in out], pages

    titles, _ = online()
    assert titles == ["Mega Quest"], "senza ingest: la voce online resta accanto al file con un altro nome"
    c.kv_set("downloaded", [{"pid": "switch", "title": "Mega Quest", "paths": [str(path)]}])
    titles, pages = online()
    assert titles == [], "con l'ingest: la voce online non e' piu' tra i giochi da scaricare"
    key = next(iter(owned))
    assert pages[key][0]["url"] == "https://sw.test/mq", "il link al download resta nella scheda del gioco posseduto"
    path.unlink()
    owned.clear()
    assert online()[0] == ["Mega Quest"], "file cancellato: la voce online torna"


def test_ingest_status_e_timeout_breve_di_default(tmp):
    import inspect
    assert inspect.signature(IN.ingest).parameters["timeout"].default <= 60, "non si resta ad aspettare minuti"
    cfg = make_cfg(tmp)
    (src,) = extracted(tmp, "Mega.xci")
    ctx, calls, got = make_ctx(cfg)
    ctx.api_scan_start = lambda body: {}  # la libreria non si aggiorna
    msgs = []
    r = IN.ingest(ctx, None, "switch", [src], timeout=0.05, poll=0.01, on_status=lambda m, lvl="info": msgs.append(m))
    assert r["pending"] and any("scansione" in m for m in msgs), msgs


# ------------------------------------------------------------ aggiunta rapida (library.incremental), libreria vera

COLS = "key, platform, title, sort_title, found, files, media, canonical, crc, origin, size, store_pages, content, is_primary"


def _q(cfg, sql, *a):
    import sqlite3
    db = sqlite3.connect(Path(cfg.cache) / "library.db")
    try:
        return db.execute(sql, a).fetchall()
    finally:
        db.close()


def real_ctx(tmp, monkeypatch):
    """Libreria vera costruita da build() (franchise offline: niente rete), con le voci online «Mega Quest» e «Altro»."""
    from pozzo.app.server import Library
    from pozzo.catalog import catalog_key
    from pozzo.library import build as B

    async def no_franchises(*a, **k):
        return None
    monkeypatch.setattr(B, "_enrich_franchises", no_franchises)
    cfg = make_cfg(tmp)
    url = "https://sw.test/list/"
    cfg.catalogs = {"switch": [url]}
    Cache(cfg.cache).kv_set(catalog_key("switch", url), {"entries": [
        {"name": "Mega Quest (USA).nsp", "url": "https://sw.test/mq"}, {"name": "Altro (USA).nsp", "url": "https://sw.test/al"}], "time": 1})
    gba = cfg.roms / "Game Boy Advance"
    gba.mkdir()
    for n in ("Zelda Clone (USA).gba", "Altro Gioco (USA).gba"):
        (gba / n).write_bytes(n.encode() * 50)
    B.build(cfg, log=lambda m: None)
    lib = Library(cfg)
    lib.load()
    ctx, calls, got = make_ctx(cfg, lib=lib)
    ctx.job, ctx.state = {"current": SimpleNamespace(status="idle")}, {}
    return ctx, calls, got, cfg, lib, B


def forbid_full_work(monkeypatch, B):
    """L'aggiunta rapida non deve ne' ricostruire la libreria ne' scansionare/hashare le cartelle."""
    from pozzo import scanner

    def boom(*a, **k):
        raise AssertionError("lavoro completo nell'aggiunta rapida")
    for mod, name in ((B, "build"), (scanner, "scan"), (scanner, "hash_games"), (scanner, "list_entries")):
        monkeypatch.setattr(mod, name, boom)


def test_aggiunta_rapida_switch_uguale_alla_ricostruzione(tmp, monkeypatch):
    ctx, calls, got, cfg, lib, B = real_ctx(tmp, monkeypatch)
    online = next(g for g in lib.games if g["store"] == "online" and g["title"] == "Mega Quest")
    n_before = len(lib.games)
    (src,) = extracted(tmp, "Mega Quest.xci")
    undo = pytest.MonkeyPatch()
    forbid_full_work(undo, B)
    msgs = []
    try:
        r = IN.ingest(ctx, online["id"], None, [src], poll=0.01, on_status=lambda m, lvl="info": msgs.append(m))
    finally:
        undo.undo()
    dest = IN.target_dir(cfg, "switch") / "Mega Quest" / "Mega Quest.xci"
    assert r["ok"] and not r.get("pending") and r["files"] == [str(dest)] and dest.is_file() and not src.exists()
    g = lib.get(r["game_id"])
    assert g["files"] == [str(dest.parent)] and g["store"] is None and g["title"] == "Mega Quest" and g["platform"] == "switch"
    assert online["id"] not in lib.by_id and online not in lib.games and len(lib.games) == n_before, "voce online sostituita"
    assert all(x in lib.groups[x["grp"]] for x in lib.games)
    assert got and got[0]["game_id"] == g["id"] and got[0]["from_id"] == online["id"]
    assert calls == [{"game": g["id"]}], "poi parte la ricerca dei dati del solo gioco, niente scansione"
    assert any("rapido" in m for m in msgs)
    fast = _q(cfg, f"SELECT {COLS} FROM games WHERE key=?", g["key"])
    assert len(fast) == 1 and not _q(cfg, "SELECT 1 FROM games WHERE title='Mega Quest' AND store='online'")
    assert "https://sw.test/mq" in fast[0][COLS.split(", ").index("store_pages")], "il link allo store passa al gioco"
    # ricostruzione completa dopo: stessa riga, nessun doppione
    B.build(cfg, log=lambda m: None)
    assert _q(cfg, f"SELECT {COLS} FROM games WHERE key=?", g["key"]) == fast
    assert _q(cfg, "SELECT COUNT(*) FROM games WHERE title='Mega Quest'") == [(1,)]
    assert _q(cfg, "SELECT COUNT(*) FROM games WHERE store IS NULL AND platform='switch'") == [(1,)]


def test_aggiunta_rapida_gba_hash_in_cache_stessa_chiave_della_scansione(tmp, monkeypatch):
    ctx, calls, got, cfg, lib, B = real_ctx(tmp, monkeypatch)
    (src,) = extracted(tmp, "Nuovo Gioco (Europe).gba")
    r = IN.ingest(ctx, None, "gba", [src], poll=0.01)
    g = lib.get(r["game_id"])
    assert g["key"].startswith("gba/")
    games = scan(cfg, Cache(cfg.cache), find_platform_dirs(cfg))
    new = next(x for x in games if x.path.name == "Nuovo Gioco (Europe).gba")
    assert not new.needs_hash and new.key == g["key"], "l'impronta e' in cache e la chiave coincide"
    B.build(cfg, log=lambda m: None)
    assert _q(cfg, "SELECT COUNT(*) FROM games WHERE store IS NULL") == [(3,)]
    assert _q(cfg, "SELECT COUNT(*) FROM games WHERE key=?", g["key"]) == [(1,)]


def test_aggiunta_rapida_altra_versione_stesso_gruppo(tmp, monkeypatch):
    ctx, calls, got, cfg, lib, B = real_ctx(tmp, monkeypatch)
    (src,) = extracted(tmp, "Zelda Clone (Europe).gba")
    g = lib.get(IN.ingest(ctx, None, "gba", [src], poll=0.01)["game_id"])
    old = next(x for x in lib.games if x["title"] == "Zelda Clone" and x["id"] != g["id"])
    assert g["grp"] == old["grp"] and not g["is_primary"] and old["is_primary"]
    B.build(cfg, log=lambda m: None)
    rows = _q(cfg, "SELECT grp, is_primary FROM games WHERE store IS NULL AND title='Zelda Clone'")
    assert len(rows) == 2 and rows[0][0] == rows[1][0] and sorted(r[1] for r in rows) == [0, 1]


def test_aggiunta_rapida_con_lavoro_in_corso_e_ricontrollo(tmp, monkeypatch):
    import sqlite3
    from fastapi import HTTPException
    ctx, calls, got, cfg, lib, B = real_ctx(tmp, monkeypatch)
    job = SimpleNamespace(status="running")  # una scansione/scraping gira adesso
    ctx.job = {"current": job}
    seen = []

    def scan_start(body):
        seen.append(body)
        raise HTTPException(409, "in corso")  # come la vera api_scan_start con un lavoro attivo
    ctx.api_scan_start = scan_start
    (src,) = extracted(tmp, "Nuovo (USA).gba")
    msgs = []
    undo = pytest.MonkeyPatch()
    forbid_full_work(undo, B)
    try:
        r = IN.ingest(ctx, None, "gba", [src], poll=0.01, on_status=lambda m, lvl="info": msgs.append((lvl, m)))
    finally:
        undo.undo()
    assert r["ok"] and r["game_id"] and seen == [{"game": r["game_id"]}], "nessuna attesa del lavoro in corso"
    assert any(lvl == "warn" and "altro lavoro" in m for lvl, m in msgs)
    # il lavoro in corso ricostruisce la libreria da una scansione precedente: il gioco sparisce, il ricontrollo lo rimette
    key = lib.get(r["game_id"])["key"]
    db = sqlite3.connect(Path(cfg.cache) / "library.db")
    db.execute("DELETE FROM games WHERE key=?", (key,))
    db.commit()
    db.close()
    lib.load()
    job.status = "done"
    seen.clear()
    ctx.api_scan_start = lambda body: seen.append(body) or {}
    want = [Path(x) for x in r["files"]]
    for _ in range(100):  # il thread di controllo se ne accorge a lavoro finito (poll 1 s)
        if IN._lib_match(lib, want) and seen:
            break
        time.sleep(0.1)
    assert IN._lib_match(lib, want) and len(seen) == 1


def test_switch_aggiornamento_va_nella_cartella_della_base(tmp):
    cfg = make_cfg(tmp)
    ctx, calls, got = make_ctx(cfg)
    base, = extracted(tmp, "Super Mario RPG [0100BC0018138000][v0].nsp")
    IN.ingest(ctx, None, "switch", [base], poll=0.01)
    sw = IN.target_dir(cfg, "switch")
    assert (sw / "Super Mario RPG" / base.name).is_file()
    upd, = extracted(tmp, "Super Mario RPG [0100BC0018138800][v131072].nsp")  # stesso gioco: Title ID uguale fino alla 13a cifra
    other, = extracted(tmp, "Altro Gioco [0100AAAA0000A000][v0].nsp")
    IN.ingest(ctx, None, "switch", [upd], poll=0.01)
    IN.ingest(ctx, None, "switch", [other], poll=0.01)
    assert (sw / "Super Mario RPG" / upd.name).is_file() and (sw / "Altro Gioco" / other.name).is_file()
