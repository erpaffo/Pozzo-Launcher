"""Clip video nella galleria: importati dalle cartelle Xbox/NVIDIA/AMD solo se creati durante la sessione,
registrati senza copia (file originale), serviti con Range (206)."""
import os
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pozzo.app.routes.shots import build_router  # noqa: E402
from pozzo.library import screens as SC  # noqa: E402


def _home(monkeypatch, tmp: Path) -> Path:
    home = tmp / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))  # Path.home() su Windows
    monkeypatch.setenv("HOME", str(home))
    return home


def test_import_session_clips(tmp_path, monkeypatch):
    from PIL import Image
    home = _home(monkeypatch, tmp_path)
    cap, nv, amd = home / "Videos" / "Captures", home / "Videos" / "NVIDIA" / "Gioco", home / "Videos" / "Radeon ReLive" / "Gioco"
    mine = home / "Videos" / "MioGioco"
    for d in (cap, nv, amd, mine):
        d.mkdir(parents=True)
    clip = cap / "Gioco 2026.mp4"
    clip.write_bytes(b"0123456789" * 50)
    Image.new("RGB", (8, 8)).save(cap / "shot.png")
    (nv / "nv.webm").write_bytes(b"w")
    (amd / "amd.mkv").write_bytes(b"m")
    (mine / "mio.mp4").write_bytes(b"x")
    (cap / "note.txt").write_text("no")
    old = cap / "vecchio.mp4"
    old.write_bytes(b"old")
    os.utime(old, (time.time() - 86400, time.time() - 86400))  # creato prima della sessione

    start, end = time.time() - 30, time.time()
    shots = SC.Shots(tmp_path / "cache", tmp_path / "u.db")
    n = SC.import_session(shots, "k:1", "", None, start, end)
    rows = shots.list(["k:1"])
    videos = {r["file"]: r for r in rows if r["kind"] == "video"}
    assert n == 5 and len(rows) == 5 and len(videos) == 4, rows  # 1 immagine copiata + 4 clip registrati
    assert {r["kind"] for r in rows} == {"image", "video"}
    assert str(clip.resolve()) in videos and str(mine.joinpath("mio.mp4").resolve()) in videos, videos
    assert shots.path(next(r["id"] for r in rows if r["file"] == str(clip.resolve()))) == clip.resolve()
    # niente copie dei video nella cache: solo l'immagine e' copiata
    assert not [p for p in (tmp_path / "cache").rglob("*") if p.suffix in SC.VIDEO_EXT]
    # gia' importati: nessun doppione
    assert SC.import_session(shots, "k:1", "", None, start, end) == 0
    # eliminare dalla galleria non tocca il file originale
    shots.delete(next(r["id"] for r in rows if r["file"] == str(clip.resolve())))
    assert clip.exists()
    shots.db.close()


def test_schema_migration_keeps_old_rows(tmp_path):
    db = tmp_path / "u.db"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE screenshots(id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, file TEXT, taken REAL,"
                      " source TEXT, origin TEXT UNIQUE, w INT, h INT);"
                      "INSERT INTO screenshots(key, file, taken, source, origin, w, h) VALUES('k','a.png',1,'s','o',1,1);")
    con.commit()
    con.close()
    shots = SC.Shots(tmp_path, db)
    rows = shots.list()
    assert rows[0]["kind"] == "image" and rows[0]["file"] == "a.png"
    shots.db.close()
    SC.Shots(tmp_path, db).db.close()  # seconda apertura: la colonna c'e' gia'


def test_shots_route_serves_video_with_range(tmp_path, monkeypatch):
    home = _home(monkeypatch, tmp_path)
    clip = home / "Videos" / "Captures" / "c.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"0123456789" * 100)
    shots = SC.Shots(tmp_path / "cache", tmp_path / "u.db")
    shots.add_clip("k:1", clip, "Xbox Game Bar")
    sid = shots.list()[0]["id"]
    app = FastAPI()
    app.include_router(build_router(SimpleNamespace(SC=SC, _thumb=None, cfg=None, launcher=None, lib=None, shots=shots)))
    c = TestClient(app)
    r = c.get(f"/shots/{sid}", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and r.content == b"0123456789", r.status_code
    assert r.headers["content-range"] == "bytes 0-9/1000"
    assert c.get(f"/shots/{sid}").status_code == 200
    assert c.get("/shots/999999").status_code == 404
    shots.db.close()
