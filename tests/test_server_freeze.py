"""L'interfaccia non deve fermarsi mentre l'app lavora in sottofondo.

1. I flussi SSE non occupano i thread delle richieste: con piu' flussi aperti che thread nel pool (40) una
   richiesta normale risponde lo stesso, e un flusso chiuso sparisce subito.
2. L'hash dei file non lascia aperta una scrittura su cache.db mentre aspetta il file successivo: le altre
   scritture (durate, obiettivi... chieste aprendo la scheda di un gioco) non restano ferme fino a 60 s.

Esegui: python -m pytest -q tests/test_server_freeze.py
"""
import http.client
import os
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pozzo import config, scanner  # noqa: E402
from pozzo.cache import Cache  # noqa: E402
from test_apiv1 import make_library, tmp_cfg  # noqa: E402


def test_sse_streams_hold_no_thread(tmp_path: Path):
    import uvicorn

    from pozzo.app.server import create_app
    rom = tmp_path / "game.gba"
    rom.write_bytes(b"x" * 100)
    make_library(tmp_path, rom)
    app = create_app(tmp_cfg(tmp_path, rom))
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", timeout_graceful_shutdown=1))
    threading.Thread(target=srv.run, daemon=True).start()
    while not srv.started:
        time.sleep(0.05)
    streams = []
    try:
        for _ in range(45):  # piu' dei 40 thread del pool
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", "/api/downloads/events")
            streams.append(c)
        deadline = time.time() + 10
        while len(app.state.events.subs) < 45 and time.time() < deadline:
            time.sleep(0.05)
        assert len(app.state.events.subs) == 45, f"flussi aperti: {len(app.state.events.subs)}"
        t0 = time.time()
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/api/game/1")  # endpoint sincrono: passa dal pool di thread
        assert c.getresponse().status == 200
        c.close()
        assert time.time() - t0 < 3, "una richiesta normale non deve aspettare i flussi SSE"
        for c in streams:
            c.sock.close()
        streams.clear()
        deadline = time.time() + 5
        while app.state.events.subs and time.time() < deadline:
            time.sleep(0.05)
        assert not app.state.events.subs, "un flusso chiuso dal client va tolto subito, non al prossimo ping"
    finally:
        for c in streams:
            c.close()
        srv.should_exit = True


def test_hash_does_not_hold_cache_write(tmp_path: Path, monkeypatch):
    (tmp_path / "roms" / "snes").mkdir(parents=True)
    (tmp_path / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n[scrape]\nsources = []\nfull_hash = true\n',
                                          encoding="utf-8")
    cfg = config.load(tmp_path / "config.toml")
    cfg.full_hash = True
    for name in ("Fast (USA).sfc", "Slow (USA).sfc"):
        (tmp_path / "roms" / "snes" / name).write_bytes(name.encode() * 50)
    cache = Cache(cfg.cache)
    games = scanner.scan(cfg, cache, scanner.find_platform_dirs(cfg))
    cache.commit()
    fast = next(g for g in games if g.path.name.startswith("Fast"))
    gate = threading.Event()

    def fake_hash(job):  # il file «grande» resta in lettura finche' il test non lo sblocca
        if "Slow" in job[0]:
            gate.wait(30)
        return {"crc": "0000ABCD", "md5": "", "sha1": ""}

    monkeypatch.setattr(scanner, "ProcessPoolExecutor", ThreadPoolExecutor)
    monkeypatch.setattr(scanner, "_hash_job", fake_hash)
    cache.close()

    def run():  # sqlite3 lega la connessione al thread che l'ha creata: si riapre nel thread dell'hash
        c = Cache(cfg.cache)
        scanner.hash_games(cfg, c, games, log=lambda *a: None)
        c.close()

    th = threading.Thread(target=run, daemon=True)
    th.start()
    try:
        deadline = time.time() + 10
        while fast.needs_hash and time.time() < deadline:
            time.sleep(0.02)
        assert not fast.needs_hash
        other = Cache(cfg.cache)  # come un endpoint dell'app che salva un risultato in cache
        other.db.execute("PRAGMA busy_timeout=5000")
        t0 = time.time()
        other.kv_set("hltb:x", {"main": 1})  # prima: «database is locked» (in app: 60 s di attesa per richiesta)
        assert time.time() - t0 < 5
        other.close()
    finally:
        gate.set()
        th.join(10)
    assert not th.is_alive() and all(not g.needs_hash for g in games)
