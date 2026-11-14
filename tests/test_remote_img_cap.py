"""Immagini remote: il corpo si legge a pezzi e oltre MAX_UPLOAD si interrompe (niente file enorme in RAM o su disco)."""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

from test_apiv1 import BASE, make_library, tmp_cfg  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 8
CAP = 25 * 1024 * 1024
sent = {"n": 0}


def _stream(size: int):
    def gen():
        chunk = b"\0" * (1 << 20)
        yield PNG
        left = size - len(PNG)
        while left > 0:
            sent["n"] += min(left, len(chunk))
            yield chunk[:left]
            left -= len(chunk)
    return gen()


def handler(req):
    size = CAP * 4 if "grande" in req.url.path else 1000
    return httpx.Response(200, content=_stream(size))


def test_cap(tmp_path):
    from pozzo.app.server import create_app
    rom = tmp_path / "game.gba"
    rom.write_bytes(b"x" * 100)
    make_library(tmp_path, rom)
    real = httpx.Client
    httpx.Client = lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    try:
        app = create_app(tmp_cfg(tmp_path, rom))
    finally:
        httpx.Client = real
    with TestClient(app, base_url=BASE) as c:
        assert c.get("/remote-img", params={"u": "https://cdn.akamai.steamstatic.com/piccola.png"}).status_code == 200
        sent["n"] = 0
        r = c.get("/remote-img", params={"u": "https://cdn.akamai.steamstatic.com/grande.png"})
        assert r.status_code == 404, r.status_code
        # letto solo fino al limite (la rotta riprova una volta: due letture troncate, non 2 x 100 MB)
        assert sent["n"] < 2 * (CAP + (2 << 20)), sent["n"]
        net = Path(tmp_path)
        assert not [p for p in net.rglob("*") if p.is_file() and p.stat().st_size > CAP]


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_cap(Path(d))
    print("ok")
