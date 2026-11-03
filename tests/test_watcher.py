"""RomWatcher: cartelle temporanee, orologio e sleep finti (niente attese vere, niente rete)."""
import os
import threading
from pathlib import Path

import pytest

from pozzo import config
from pozzo.library.watcher import RomWatcher


class Clk:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path):
    cfg = config.Config(roms=tmp_path / "roms", cache=tmp_path / "cache", output=tmp_path / "out")
    cfg.config_path = tmp_path / "config.toml"
    cfg.cache.mkdir()
    (cfg.roms / "gba").mkdir(parents=True)
    (cfg.roms / "ps3").mkdir()
    return cfg


def mk(cfg, **kw):
    calls, clk, flags = [], Clk(), {"busy": False, "low": False, "fail": 0}

    def on_new(pid, paths, low):
        if flags["fail"]:
            flags["fail"] -= 1
            raise RuntimeError("boom")
        calls.append((pid, sorted(p.name for p in paths), low))

    w = RomWatcher(lambda: cfg, on_new, busy=lambda: flags["busy"], low=lambda: flags["low"],
                   debounce=10, interval=20, low_interval=90, clock=clk, sleep=lambda s: None, **kw)
    return w, calls, clk, flags


def settle(w, clk, n=3):
    for _ in range(n):
        clk.t += 11
        w.tick()


def test_baseline_non_riportata_e_nuovo_dopo_debounce(env):
    g = env.roms / "gba"
    (g / "vecchio.gba").write_bytes(b"x" * 10)
    w, calls, clk, _ = mk(env)
    w.tick()
    settle(w, clk)
    assert calls == []
    (g / "nuovo.gba").write_bytes(b"y" * 10)
    clk.t += 1
    w.tick()  # visto ora: in attesa
    assert calls == [] and w.status()["pending"]
    clk.t += 5
    w.tick()
    assert calls == []  # debounce non ancora passato
    settle(w, clk, 2)
    assert calls == [("gba", ["nuovo.gba"], False)]
    assert w.status()["added"] == 1 and not w.status()["pending"]
    settle(w, clk)
    assert len(calls) == 1  # mai riportato due volte


def test_file_che_cresce_e_ritardato(env):
    g = env.roms / "gba"
    w, calls, clk, _ = mk(env)
    w.tick()
    f = g / "x.gba"
    f.write_bytes(b"1")
    clk.t += 11
    w.tick()
    for i in range(3):  # cresce a ogni controllo, anche oltre il debounce
        f.write_bytes(b"1" * (10 + i))
        os.utime(f, ns=(1, 1 + i))
        clk.t += 11
        w.tick()
    assert calls == []
    settle(w, clk, 2)
    assert len(calls) == 1


def test_cartella_gioco_dir_games(env):
    w, calls, clk, _ = mk(env)
    w.tick()
    d = env.roms / "ps3" / "Gioco"
    d.mkdir()
    (d / "a.iso").write_bytes(b"z" * 5)
    settle(w, clk, 3)
    assert calls == [("ps3", ["Gioco"], False)]


def test_temporanei_ignorati(env):
    g = env.roms / "gba"
    w, calls, clk, _ = mk(env)
    w.tick()
    for n in ("a.gba.part", "b.gba.crdownload", "c.gba.tmp", "d.gba.!qB"):
        (g / n).write_bytes(b"1")
    (env.roms / "ps3" / ".estrazione-1").mkdir()
    settle(w, clk, 3)
    assert calls == [] and not w.status()["pending"]


def test_busy_rimanda_senza_perdere(env):
    w, calls, clk, fl = mk(env)
    w.tick()
    (env.roms / "gba" / "n.gba").write_bytes(b"1")
    clk.t += 1
    w.tick()
    fl["busy"] = True
    settle(w, clk, 3)
    assert calls == [] and w.status()["pending"]
    fl["busy"] = False
    settle(w, clk, 2)
    assert len(calls) == 1


def test_low_una_cartella_per_passaggio(env):
    w, calls, clk, fl = mk(env)
    w.tick()
    (env.roms / "gba" / "n.gba").write_bytes(b"1")
    (env.roms / "ps3" / "G").mkdir()
    (env.roms / "ps3" / "G" / "a.iso").write_bytes(b"1")
    clk.t += 1
    w.tick()
    fl["low"] = True
    clk.t += 11
    assert w.tick() == 1 and len(calls) == 1 and calls[0][2] is True
    clk.t += 11
    assert w.tick() == 1 and len(calls) == 2
    # il thread usa low_interval quando low() e' vero
    waits = []
    w._stop.wait = lambda t: (waits.append(t), w._stop.set())[0]
    w._run()
    assert waits == [90]


def test_on_new_errore_retry_con_backoff(env):
    w, calls, clk, fl = mk(env)
    w.tick()
    fl["fail"] = 1
    (env.roms / "gba" / "n.gba").write_bytes(b"1")
    settle(w, clk, 2)
    assert w.status()["errors"] == 1 and calls == []
    clk.t += 1
    w.tick()
    assert calls == []  # backoff: non subito
    settle(w, clk, 4)
    assert len(calls) == 1 and w.status()["pending"] == []


def test_radice_scollegata_non_riporta_nulla(env, tmp_path):
    (env.roms / "gba" / "a.gba").write_bytes(b"1")
    w, calls, clk, _ = mk(env)
    w.tick()
    moved = tmp_path / "roms_off"
    env.roms.rename(moved)
    settle(w, clk, 3)
    assert calls == []
    moved.rename(env.roms)  # ricollegato, stessi file: nulla di nuovo
    settle(w, clk, 3)
    assert calls == []


def test_known_e_stop(env):
    g = env.roms / "gba"
    w, calls, clk, _ = mk(env, known=lambda pid: {os.path.normcase(os.path.normpath(g / "k.gba"))})
    w.tick()
    (g / "k.gba").write_bytes(b"1")
    settle(w, clk, 3)
    assert calls == []
    w2 = RomWatcher(lambda: env, lambda *a: None, interval=0.01)
    w2.start()
    w2.start()
    assert any(t.name == "rom-watcher" for t in threading.enumerate())
    w2.stop()
    w2.stop()
    assert not w2.status()["running"]


# ---- comportamenti dell'altra versione, ora nel motore unico
def test_impostazioni_di_default_e_limiti():
    from types import SimpleNamespace
    from pozzo.library import watcher as W
    cfg = SimpleNamespace(app={})
    assert W.settings_of(cfg) == {"enabled": True, "poll": W.DEFAULT_POLL, "debounce": W.DEFAULT_DEBOUNCE}
    cfg.app["watch_roms"] = {"enabled": False, "poll": 0.1, "debounce": 9999}
    s = W.settings_of(cfg)
    assert s["enabled"] is False and s["poll"] == 2.0 and s["debounce"] == 120.0


def test_acceso_e_spento_a_caldo(env):
    cfg = env
    calls, clk = [], Clk()
    w = RomWatcher(lambda: cfg, lambda pid, paths, low: calls.append(pid), clock=clk, sleep=lambda s: None)
    settle(w, clk)
    cfg.app["watch_roms"] = {"enabled": False}
    (cfg.roms / "gba" / "Nuovo.gba").write_bytes(b"x" * 100)
    settle(w, clk, 4)
    assert calls == [] and w.status()["enabled"] is False
    cfg.app["watch_roms"] = {"enabled": True}  # riattivato a caldo, senza riavvio
    settle(w, clk, 4)
    assert calls == ["gba"]


def test_tempi_dalle_impostazioni(env):
    cfg = env
    cfg.app["watch_roms"] = {"poll": 30, "debounce": 40}
    w = RomWatcher(lambda: cfg, lambda *a: None)
    assert (w.interval, w.debounce, w.low_interval) == (30, 40, 180)


def test_in_partita_i_file_grandi_aspettano(env, monkeypatch):
    from pozzo.library import watcher as W
    monkeypatch.setattr(W, "LIGHT_MAX", 1000)
    w, calls, clk, flags = mk(env)
    settle(w, clk)
    flags["low"] = True
    (env.roms / "gba" / "Piccolo.gba").write_bytes(b"x" * 500)
    (env.roms / "gba" / "Grande.gba").write_bytes(b"x" * 5000)
    settle(w, clk, 4)
    assert calls == [("gba", ["Piccolo.gba"], True)], "il grande non si legge dal disco mentre si gioca"
    flags["low"] = False
    settle(w, clk, 3)
    assert ("gba", ["Grande.gba"], False) in calls


def test_tetto_di_giochi_per_chiamata(env, monkeypatch):
    from pozzo.library import watcher as W
    monkeypatch.setattr(W, "MAX_PER_CALL", 2)
    w, calls, clk, flags = mk(env)
    settle(w, clk)
    for i in range(5):
        (env.roms / "gba" / f"G{i}.gba").write_bytes(b"x" * 100)
    settle(w, clk, 8)
    assert sorted(n for _, names, _ in calls for n in names) == [f"G{i}.gba" for i in range(5)]
    assert max(len(names) for _, names, _ in calls) == 2


# ---- API e interruttore: app vera su una cartella temporanea
from test_frontend import client  # noqa: E402,F401  (fixture)


def test_api_stato_e_interruttore(client):
    r = client.get("/api/library/watch").json()
    assert r["enabled"] is True and {"pending", "added", "last_scan", "running", "errors"} <= set(r)
    off = client.post("/api/app/watch-roms", json={"enabled": False}).json()
    assert off["enabled"] is False
    assert client.get("/api/library/watch").json()["enabled"] is False
    assert client.post("/api/app/watch-roms", json={"enabled": True}).json()["enabled"] is True
