"""Rotte /api/tools: percorsi vincolati alle cartelle ROM, spazio controllato, adozione del file prodotto."""
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from pozzo import config  # noqa: E402
from pozzo.app.server import create_app  # noqa: E402
from pozzo.tools import jobs as J  # noqa: E402

tmp = Path(tempfile.mkdtemp())
try:
    cfg = config.Config(cache=tmp, output=tmp / "out", roms=tmp / "roms")
    cfg.config_path = tmp / "config.toml"
    (tmp / "roms").mkdir()
    g = tmp / "roms" / "Gioco.iso"
    g.write_bytes(b"x" * 100)

    def run(src, dst, progress, cancel, o):
        out = dst / "Gioco.chd"
        out.write_bytes(b"y" * 40)
        return out

    J.register(J.Tool("tchd", "T", lambda p, f: f.suffix == ".iso", lambda s, o: s.stat().st_size, run))
    J.register(J.Tool("tbig", "B", lambda p, f: True, lambda s, o: 10**18, run))
    c = TestClient(create_app(cfg))

    ids = [t["id"] for t in c.get("/api/tools", params={"platform": "psx", "path": str(g)}).json()["tools"]]
    assert "tchd" in ids and "nup" not in ids  # il NUP vale solo per Switch 2

    # percorso relativo, fuori dalle cartelle ROM, strumento ignoto, non applicabile
    assert c.post("/api/tools/run", json={"tool": "tchd", "path": "Gioco.iso"}).status_code == 400
    assert c.post("/api/tools/run", json={"tool": "tchd", "path": str(tmp / "x.iso")}).status_code == 400
    assert c.post("/api/tools/run", json={"tool": "nope", "path": str(g)}).status_code == 404
    other = tmp / "roms" / "a.bin"
    other.write_bytes(b"z")
    assert c.post("/api/tools/run", json={"tool": "tchd", "platform": "psx", "path": str(other)}).status_code == 400
    # spazio insufficiente: 507 e nessun file scritto
    r = c.post("/api/tools/run", json={"tool": "tbig", "platform": "psx", "path": str(g)})
    assert r.status_code == 507 and "liberi" in r.json()["detail"]

    j = c.post("/api/tools/run", json={"tool": "tchd", "platform": "psx", "path": str(g)}).json()
    for _ in range(50):
        j = c.get(f"/api/tools/job/{j['id']}").json()
        if j["status"] != "running":
            break
        time.sleep(0.1)
    assert j["status"] == "done" and Path(j["out"]).exists()
    assert c.get("/api/tools/job/nope").status_code == 404

    # adopt: l'originale va nel cestino solo se richiesto
    with mock.patch("pozzo.tools.trash._fixed_drive", return_value=False), \
         mock.patch("pozzo.tools.trash.Path.anchor", new_callable=mock.PropertyMock, return_value=str(tmp)):
        r = c.post(f"/api/tools/job/{j['id']}/adopt", json={"move_old": False})
        assert r.status_code == 200 and g.exists()
        r = c.post(f"/api/tools/job/{j['id']}/adopt", json={"move_old": True})
        assert r.status_code == 200 and not g.exists() and Path(r.json()["trashed"]).exists()
    assert c.get("/api/tools/drives").json() == {"drives": []} or "drives" in c.get("/api/tools/drives").json()
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("ok")
