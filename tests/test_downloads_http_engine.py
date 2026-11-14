"""Motore HTTP: gate dopo la risoluzione, .part sparso su Windows."""
import ctypes
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import asyncio
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.downloads.engines import http as H  # noqa: E402


def test_gate_dopo_resolve_prima_di_fetch_una_volta(monkeypatch):
    ev = []

    async def fetch(*a):
        ev.append("fetch")

    async def gate():
        ev.append("gate")

    monkeypatch.setattr(H, "_fetch", fetch)
    task = SimpleNamespace(options={}, source="s", log=lambda *a, **k: ev.append("log"))
    asyncio.run(H.run(task, None, None, 1, lambda s: ev.append("resolve") or "https://h/f.bin", gate))
    assert [e for e in ev if e != "log"] == ["resolve", "gate", "fetch"]


def test_gate_una_sola_volta_se_il_link_vecchio_fallisce(monkeypatch):
    import time
    import httpx
    ev, n = [], [0]

    async def fetch(*a):
        n[0] += 1
        ev.append("fetch")
        if n[0] == 1:
            raise httpx.TransportError("x")

    async def gate():
        ev.append("gate")

    monkeypatch.setattr(H, "_fetch", fetch)
    task = SimpleNamespace(options={"url": "https://h/old", "url_at": time.time()}, source="s", log=lambda *a, **k: None)
    asyncio.run(H.run(task, None, None, 1, lambda s: "https://h/new", gate))
    assert ev == ["gate", "fetch", "fetch"]


def test_sparse_non_solleva_e_file_resta_valido(tmp_path):
    p = tmp_path / "a.part"
    with open(p, "wb") as f:
        H._sparse(f)
        f.truncate(1024 * 1024)
    assert p.stat().st_size == 1024 * 1024


@pytest.mark.skipif(os.name != "nt", reason="solo Windows")
def test_sparse_imposta_attributo_windows(tmp_path):
    p = tmp_path / "a.part"
    with open(p, "wb") as f:
        H._sparse(f)
        f.truncate(1024 * 1024)
    assert ctypes.windll.kernel32.GetFileAttributesW(str(p)) & 0x200


# ---- SHA-256 + quarantena + failover mirror, SSRF
def _serve(files):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Hd(BaseHTTPRequestHandler):
        def do_GET(self):
            b = files[self.path]
            self.send_response(200)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def log_message(self, *a):
            pass

    s = ThreadingHTTPServer(("127.0.0.1", 0), Hd)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_port}"


def _task(tmp_path, src, **opts):
    from pozzo.downloads.task import DownloadTask
    return DownloadTask(source=src, save_path=str(tmp_path), options=opts)


def _go(task):
    import httpx

    async def main():
        async with httpx.AsyncClient() as c:
            await H.run(task, c, H.Bucket(), 1, lambda u: u)
    asyncio.run(main())


def test_sha_ok_nessun_hash_e_mismatch_con_failover(tmp_path):
    import hashlib
    good = b"gioco vero"
    s, base = _serve({"/bad.bin": b"corrotto!!", "/ok.bin": good})
    try:
        t = _task(tmp_path, base + "/ok.bin")
        _go(t)  # nessun hash: nessun blocco
        assert (tmp_path / "ok.bin").read_bytes() == good
        want = hashlib.sha256(good).hexdigest()
        t = _task(tmp_path / "b", base + "/bad.bin", sha256=want, mirrors=[base + "/ok.bin"])
        (tmp_path / "b").mkdir()
        _go(t)  # primo mirror corrotto -> quarantena, poi il secondo
        assert (tmp_path / "b" / "bad.bin").read_bytes() == good  # il nome del task resta, il contenuto e' del mirror buono
        q = list((tmp_path / "b" / ".quarantena").iterdir())
        assert len(q) == 1 and q[0].read_bytes() == b"corrotto!!"
    finally:
        s.shutdown()


def test_sha_mismatch_senza_mirror_fallisce(tmp_path):
    s, base = _serve({"/bad.bin": b"x"})
    try:
        t = _task(tmp_path, base + "/bad.bin", sha256="0" * 64)
        with pytest.raises(H.HashMismatch):
            _go(t)
        assert not (tmp_path / "bad.bin").exists() and (tmp_path / ".quarantena").exists()
    finally:
        s.shutdown()


def test_assert_public_blocca_rete_locale():
    from pozzo.downloads import hosts
    for u in ("http://127.0.0.1/f", "http://192.168.1.5/f", "http://169.254.169.254/x", "http://[::1]/f", "ftp://example.com/f"):
        with pytest.raises(ValueError):
            hosts.assert_public(u)
    hosts.assert_public("http://host-che-non-esiste.invalid/f")  # non risolve: lo dira' httpx


def test_resolved_verso_lan_rifiutato(tmp_path):
    task = SimpleNamespace(options={}, source="https://ouo.io/x", log=lambda *a, **k: None)
    with pytest.raises(ValueError, match="rete locale"):
        asyncio.run(H.run(task, None, None, 1, lambda s: "http://10.0.0.2/f.bin"))


def test_scanner_ignora_quarantena(tmp_path):
    from pozzo import scanner
    assert scanner._ignored(tmp_path / ".quarantena") is True  # le cartelle col punto non entrano in libreria


@pytest.fixture
def clock(monkeypatch):
    """Orologio finto per il secchiello: chi dorme si sveglia in ordine di scadenza e il tempo salta li'
    (piu' flussi che dormono insieme non sommano le attese)."""
    import heapq
    import itertools
    now, slept, real, sleepers, seq = {"t": 1000.0}, [], asyncio.sleep, [], itertools.count()

    async def sleep(d):
        slept.append(d)
        fut = asyncio.get_running_loop().create_future()
        heapq.heappush(sleepers, (now["t"] + d, next(seq), fut))
        await fut

    def run(coro):
        async def main():
            job = asyncio.ensure_future(coro)
            while not job.done():
                for _ in range(5):  # chi e' stato svegliato arriva alla prossima attesa
                    await real(0)
                if sleepers and not job.done():
                    at, _, fut = heapq.heappop(sleepers)
                    now["t"] = max(now["t"], at)
                    fut.set_result(None)
            return job.result()
        return asyncio.run(main())

    monkeypatch.setattr(H, "time", SimpleNamespace(monotonic=lambda: now["t"], time=lambda: now["t"]))
    monkeypatch.setattr(H.asyncio, "sleep", sleep)
    return now, slept, run


def test_limite_basso_media_giusta_attese_brevi(clock):
    """20 KB/s su 8 segmenti: la media resta il limite, nessuna attesa oltre il secondo, ogni segmento legge spesso."""
    now, slept, run = clock
    b, rate, last, gaps = H.Bucket(), 20 * 1024, {}, []
    b.rate = rate

    async def seg(i):
        for _ in range(10):
            await b.take(H.CHUNK)
            if i in last:
                gaps.append(now["t"] - last[i])
            last[i] = now["t"]

    async def main():
        await asyncio.gather(*(seg(i) for i in range(8)))
    t0 = now["t"]
    run(main())
    total = 8 * 10 * H.CHUNK
    assert (total - H.CHUNK) / rate <= now["t"] - t0 <= total / rate + 1, (now["t"] - t0, total / rate)
    assert max(slept) <= 1.0, max(slept)
    assert max(gaps) <= 8 * 64 * 1024 / rate + 1, max(gaps)  # ~26 s tra due letture dello stesso segmento, non ~100 s


def test_limite_tolto_o_alzato_vale_entro_un_secondo(clock):
    now, slept, run = clock
    b = H.Bucket()
    b.rate = 1024

    async def lifted():
        t0 = now["t"]

        async def lift():
            while now["t"] < t0 + 0.5:
                await H.asyncio.sleep(0.1)
            b.rate = 0  # limite tolto mentre un flusso aspetta un debito di 64 s (64 KB a 1 KB/s)

        await asyncio.gather(b.take(64 * 1024), b.take(64 * 1024), lift())
        return now["t"] - t0
    assert run(lifted()) <= 1.5

    async def faster():
        b.rate = 1024
        await b.take(64 * 1024)
        await b.take(1)
        t0 = now["t"]
        await b.take(64 * 1024)
        b.rate = 1024 * 1024  # il debito rimasto si ripaga al ritmo nuovo
        await b.take(1)
        return now["t"] - t0
    assert run(faster()) <= 1.0
