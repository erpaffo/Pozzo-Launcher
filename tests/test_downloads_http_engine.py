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
