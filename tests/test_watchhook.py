"""Watcher delle cartelle ROM collegato alla libreria: giochi nuovi in libreria, evento, ricerca dei dati rimandata in
partita, impostazione acceso/spento. Nessun file reale toccato.

Esegui: python -m pytest tests/test_watchhook.py -q
"""

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo.library import incremental, watchhook as WH  # noqa: E402


class FakeLib:
    def __init__(self):
        self.games, self.by_key, self.lock = [], {}, threading.RLock()
        self.added = []

    def add_games(self, keys, drop=None):
        self.added.append(list(keys))

    def put(self, key, title, pid="gba", files=()):
        g = {"id": len(self.games) + 1, "key": key, "title": title, "platform": pid, "files": list(files)}
        self.games.append(g)
        self.by_key[key] = g
        return g


class Events:
    def __init__(self):
        self.out = []

    def emit(self, name, data):
        self.out.append((name, data))


def make_hook(tmp_path, scan=None, busy=lambda: False, playing=lambda: False):
    lib, ev = FakeLib(), Events()
    calls = []

    def default_scan(body):
        calls.append(body)

    hook = WH.Hook(SimpleNamespace(cache=tmp_path), lib, ev, scan or default_scan, busy, playing)
    return hook, lib, ev, calls


def test_impostazione_default_acceso():
    assert WH.enabled(SimpleNamespace(app={})) is True
    assert WH.enabled(SimpleNamespace(app={"watch_roms": {"enabled": False}})) is False
    assert WH.enabled(SimpleNamespace(app={"watch_roms": {}})) is True
    assert WH.enabled(SimpleNamespace(app={"watch_roms": False})) is False


def test_known_sono_i_giochi_posseduti_della_console(tmp_path):
    hook, lib, _, _ = make_hook(tmp_path)
    lib.put("a", "A", "gba", [str(tmp_path / "A.gba")])
    lib.put("b", "B", "snes", [str(tmp_path / "B.sfc")])
    lib.put("c", "Online", "gba", [])
    lib.games[-1]["store"] = "online"
    assert hook.known("gba") == {WH._norm(tmp_path / "A.gba")}


def test_gioco_nuovo_in_libreria_evento_e_ricerca_dati(tmp_path, monkeypatch):
    called = threading.Event()
    hook, lib, ev, calls = make_hook(tmp_path, scan=lambda b: (calls.append(b), called.set()))
    g = lib.put("k1", "Nuovo Gioco")
    monkeypatch.setattr(incremental, "add_games", lambda cfg, pid, paths, drop=None: ["k1"])
    hook.on_new("gba", [tmp_path / "Nuovo Gioco.gba"], False)
    assert lib.added == [["k1"]]
    name, data = ev.out[0]
    assert name == "library_watch" and data["count"] == 1 and data["titles"] == ["Nuovo Gioco"]
    assert called.wait(5) and calls == [{"game": g["id"]}]


def test_libreria_non_costruita_non_fa_nulla(tmp_path, monkeypatch):
    hook, lib, ev, calls = make_hook(tmp_path)
    monkeypatch.setattr(incremental, "add_games", lambda *a, **k: None)
    hook.on_new("gba", [tmp_path / "x.gba"], False)
    assert not lib.added and not ev.out


def test_in_partita_la_ricerca_dati_aspetta(tmp_path, monkeypatch):
    state = {"playing": True}
    called = threading.Event()
    hook, lib, ev, calls = make_hook(tmp_path, playing=lambda: state["playing"], scan=lambda b: (calls.append(b), called.set()))
    lib.put("k1", "Nuovo")
    monkeypatch.setattr(incremental, "add_games", lambda *a, **k: ["k1"])
    real = hook._search
    hook._search = lambda: real(poll=0.02)
    hook.on_new("gba", [tmp_path / "x.gba"], True)
    assert ev.out and lib.added, "il gioco entra subito anche in partita"
    time.sleep(0.15)
    assert calls == [], "ma i dati si cercano solo a partita finita"
    state["playing"] = False
    assert called.wait(5) and len(calls) == 1


def test_409_si_riprova(tmp_path, monkeypatch):
    n = {"k": 0}
    done = threading.Event()

    def scan(body):
        n["k"] += 1
        if n["k"] == 1:
            raise HTTPException(409, "gia' in corso")
        done.set()

    hook, lib, ev, _ = make_hook(tmp_path, scan=scan)
    lib.put("k1", "Nuovo")
    monkeypatch.setattr(incremental, "add_games", lambda *a, **k: ["k1"])
    real = hook._search
    hook._search = lambda: real(poll=0.02)
    hook.on_new("gba", [tmp_path / "x.gba"], False)
    assert done.wait(5) and n["k"] == 2


def test_errore_in_add_games_arriva_al_watcher(tmp_path, monkeypatch):
    hook, *_ = make_hook(tmp_path)

    def boom(*a, **k):
        raise OSError("disco")

    monkeypatch.setattr(incremental, "add_games", boom)
    with pytest.raises(OSError):  # il watcher lo conta e riprova piu' tardi
        hook.on_new("gba", [tmp_path / "x.gba"], False)


def test_modalita_fondo_non_rompe_su_nessuna_piattaforma():
    with WH.background_mode(True):
        pass
    with WH.background_mode(False):
        pass


# ---- di punta in bianco: libreria vera + RomWatcher vero, orologio finto
def test_copio_una_rom_ed_e_in_libreria(tmp, monkeypatch):
    from pozzo.library.watcher import RomWatcher
    from test_downloads_ingest import real_ctx

    ctx, calls, got, cfg, lib, B = real_ctx(tmp, monkeypatch)
    ev = Events()
    hook = WH.Hook(cfg, lib, ev, ctx.api_scan_start, busy=lambda: False, playing=lambda: False)
    t = [0.0]
    w = RomWatcher(lambda: cfg, hook.on_new, known=hook.known, clock=lambda: t[0], sleep=lambda s: None, debounce=10)
    assert w.tick() == 0, "la prima passata e' solo il punto di partenza: nulla viene riportato"
    assert not ev.out
    n = len(lib.games)
    gba = cfg.roms / "Game Boy Advance"
    (gba / "Nuovo Arrivato (USA).gba").write_bytes(b"nuovo" * 100)
    t[0] += 5
    w.tick()
    assert len(lib.games) == n, "prima dei 10 s di calma non succede nulla"
    t[0] += 20
    w.tick()
    t[0] += 20
    w.tick()
    assert len(lib.games) == n + 1 and any(g["title"].startswith("Nuovo Arrivato") for g in lib.games)
    assert ev.out and ev.out[0][0] == "library_watch" and ev.out[0][1]["count"] == 1
    t[0] += 60
    w.tick()
    assert len(ev.out) == 1, "lo stesso file non si riporta due volte"
