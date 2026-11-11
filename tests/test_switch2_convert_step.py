"""Step «convert» (Switch 2) del post-download e rotte /api/switch2: con switch2pack finto, nessun gioco vero."""
import sys
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import config, switch2pack as S  # noqa: E402
from pozzo.downloads import finish  # noqa: E402
from test_downloads_finish import Mgr, _ctx, _task  # noqa: E402


def _run(tmp, monkeypatch, supported, convert, **s):
    ctx, calls, got, cfg = _ctx(tmp)
    z = tmp / "dl" / "Gioco.zip"
    z.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("Gioco/Gioco [0100AAAA].nsp", b"PFS0" + b"x" * 50)
    monkeypatch.setattr(S, "supported", lambda cfg: supported)
    monkeypatch.setattr(S, "convert", convert)
    t = _task(tmp, "Gioco.zip")
    ctx.lib.get = lambda gid: {"platform": "switch2"}
    finish.run(t, Mgr(**s), ctx)
    return t, cfg


def _conv(src, fmt, dst, progress=None, cancel=None):
    out = Path(dst) / (Path(src).stem + "." + fmt)
    out.write_bytes(b"NUP\x01")
    return out


def test_converte_e_sostituisce(tmp, monkeypatch):
    t, cfg = _run(tmp, monkeypatch, (True, ""), _conv, switch2_format="nup")
    assert [p.name for p in cfg.roms.rglob("*.nup")] and not list(cfg.roms.rglob("*.nsp"))
    assert any(s["id"] == "convert" and s["state"] == "done" for s in t.stages)


def test_non_supportato_tiene_l_originale(tmp, monkeypatch):
    t, cfg = _run(tmp, monkeypatch, (False, "Eglantine non è installato"), _conv, switch2_format="nup")
    assert list(cfg.roms.rglob("*.nsp")) and not list(cfg.roms.rglob("*.nup"))
    assert any("saltata" in l["msg"] for l in t.log_after(0)[0])


def test_errore_tiene_l_originale(tmp, monkeypatch):
    def boom(*a, **k):
        raise S.SwitchPackError("NSP cifrato")
    t, cfg = _run(tmp, monkeypatch, (True, ""), boom, switch2_format="nup")
    assert list(cfg.roms.rglob("*.nsp")) and any("tengo l'originale" in l["msg"] for l in t.log_after(0)[0])


def test_off_e_stesso_formato_non_convertono(tmp, monkeypatch):
    seen = []
    t, cfg = _run(tmp, monkeypatch, (True, ""), lambda *a, **k: seen.append(a), switch2_format="off")
    assert not seen and list(cfg.roms.rglob("*.nsp"))
    (tmp / "b").mkdir()
    t, cfg = _run(tmp / "b", monkeypatch, (True, ""), lambda *a, **k: seen.append(a), switch2_format="nsp")
    assert not seen


def test_rotte(tmp, monkeypatch):
    from fastapi.testclient import TestClient

    from pozzo.app.server import create_app
    cfg = config.Config(cache=tmp, output=tmp / "out", roms=tmp / "roms")
    cfg.config_path = tmp / "config.toml"
    (tmp / "roms").mkdir()
    g = tmp / "roms" / "Gioco.nsp"
    g.write_bytes(b"PFS0")
    monkeypatch.setattr(S, "supported", lambda cfg: (True, ""))
    monkeypatch.setattr(S, "convert", _conv)
    c = TestClient(create_app(cfg))
    assert c.get("/api/switch2/status").json()["supported"] is True
    assert c.post("/api/switch2/convert", json={"path": str(g), "format": "zip"}).status_code == 400
    assert c.post("/api/switch2/convert", json={"path": str(tmp / "roms" / ".." / "x.nsp"), "format": "nup"}).status_code == 400
    j = c.post("/api/switch2/convert", json={"path": str(g), "format": "nup"}).json()
    for _ in range(50):
        st = c.get(f"/api/switch2/job/{j['id']}").json()
        if st["status"] != "running":
            break
        time.sleep(0.1)
    assert st["status"] == "done" and (tmp / "roms" / "Gioco.nup").exists()
    assert c.get("/api/switch2/job/nope").status_code == 404
