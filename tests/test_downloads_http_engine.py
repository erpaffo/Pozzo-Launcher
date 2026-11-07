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
