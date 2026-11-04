"""Coda del browser nascosto: la fase "In attesa" compare solo se il lock e' gia' occupato. Nessuna finestra."""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import storelinks as SL  # noqa: E402
from pozzo.app import browserdl as B  # noqa: E402
from pozzo.downloads import resolvers  # noqa: E402

WAIT = "In attesa del browser (un altro download lo sta usando)"


class _Lock:
    """Lock finto: `locked()` dice se e' occupato, il `with` non blocca."""

    def __init__(self, busy):
        self.busy = busy

    def locked(self):
        return self.busy

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _spy(monkeypatch):
    seen = []
    monkeypatch.setattr(resolvers, "phase", lambda name: seen.append(name))
    return seen


def test_with_browser_mostra_attesa_solo_se_occupato(monkeypatch):
    monkeypatch.setitem(SL.RESOLVER, "fn", lambda url: "https://x.example/file.zip")
    monkeypatch.setitem(SL.RESOLVER, "reason", None)

    monkeypatch.setattr(SL, "_LOCK", _Lock(busy=True))
    seen = _spy(monkeypatch)
    assert SL.with_browser("https://short.example/a", timeout=5) == "https://x.example/file.zip"
    assert WAIT in seen

    monkeypatch.setattr(SL, "_LOCK", _Lock(busy=False))
    seen = _spy(monkeypatch)
    assert SL.with_browser("https://short.example/a", timeout=5) == "https://x.example/file.zip"
    assert WAIT not in seen


def test_browserdl_resolve_mostra_attesa_solo_se_occupato(monkeypatch):
    monkeypatch.setattr(B, "_resolve", lambda link, timeout: "ok")

    monkeypatch.setattr(B, "_LOCK", _Lock(busy=True))
    seen = _spy(monkeypatch)
    assert B.resolve("https://host.example/f", timeout=5) == "ok"
    assert WAIT in seen

    monkeypatch.setattr(B, "_LOCK", _Lock(busy=False))
    seen = _spy(monkeypatch)
    assert B.resolve("https://host.example/f", timeout=5) == "ok"
    assert WAIT not in seen
