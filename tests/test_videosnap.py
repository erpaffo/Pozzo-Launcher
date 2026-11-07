"""Video snap: scelta del media ScreenScraper, tetto di peso, interruttore (spento di default) e servizio con Range."""
import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import config, net, platforms as P  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from pozzo.scanner import Game  # noqa: E402
from pozzo.sources.screenscraper import ScreenScraper  # noqa: E402
from test_apiv1 import BASE, make_library, tmp_cfg  # noqa: E402

MP4 = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 8
J = {"noms": [{"region": "ss", "text": "T"}], "medias": [
    {"type": "box-2D", "region": "eu", "url": "https://ss/box.png"},
    {"type": "video", "region": "wor", "url": "https://ss/v.mp4"},
    {"type": "video-normalized", "region": "wor", "url": "https://ss/vn.mp4"}]}


def parse(cfg):
    return ScreenScraper._parse(SimpleNamespace(cfg=cfg), J, Game(Path("a.sfc"), P.get("snes"), 1, 0))


def test_screenscraper_video_only_when_enabled():
    cfg = config.Config()
    assert "video" not in parse(cfg).media  # spento di default
    cfg.app["video_snap"] = True
    assert parse(cfg).media["video"] == "https://ss/vn.mp4"  # normalizzato prima del grezzo
    assert parse(cfg).media["cover"] == "https://ss/box.png"


def test_disabled_means_not_wanted():
    cfg = config.Config()
    assert not cfg.wants_media("video") and "media:video" not in cfg.wanted and cfg.wants_media("cover")
    cfg.media.append("video")  # elencato a mano in scrape.media
    assert cfg.wants_media("video")


async def test_size_cap(tmp: Path):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=MP4))) as c:
        assert await net.download_media(c, "https://x/v.mp4", tmp / "a", max_bytes=100) is None
        p = await net.download_media(c, "https://x/v.mp4", tmp / "b", max_bytes=10_000)
        assert p and p.suffix == ".mp4"


def test_serve_with_range_and_toggle(tmp: Path):
    rom = tmp / "game.gba"
    rom.write_bytes(b"x" * 100)
    make_library(tmp, rom)
    (tmp / "media" / "net").mkdir(parents=True)
    (tmp / "media" / "net" / "v.mp4").write_bytes(MP4)
    db = sqlite3.connect(tmp / "library.db")
    db.execute("UPDATE games SET media=? WHERE key='gba/AAA'", (json.dumps({"cover": "x", "video": "media/net/v.mp4"}),))
    db.commit()
    db.close()
    cfg = tmp_cfg(tmp, rom)
    with TestClient(create_app(cfg), base_url=BASE) as c:
        gid = sqlite3.connect(tmp / "library.db").execute("SELECT id FROM games WHERE key='gba/AAA'").fetchone()[0]
        r = c.get(f"/img/{gid}/video", headers={"Range": "bytes=0-9"})
        assert r.status_code == 206 and r.content == MP4[:10] and r.headers["content-type"] == "video/mp4"
        assert c.get(f"/img/{gid + 1}/video").status_code == 404  # un gioco senza video
        assert c.get("/api/app/video-snap").json() == {"enabled": False, "max_mb": 30}
        assert c.post("/api/app/video-snap", json={"enabled": True, "max_mb": 1}).json() == {"enabled": True, "max_mb": 5}
        assert cfg.wants_media("video")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
