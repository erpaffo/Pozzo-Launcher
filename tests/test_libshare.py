"""Libreria condivisa: cancello dell'ospite (nega tutto il resto), giochi non condivisi, percorsi, Range, zip,
webplay e client con impronta del certificato fissata. Nessuna rete."""
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from pozzo.app.server import create_app  # noqa: E402
from pozzo.remote import libshare as LS, phone as PH  # noqa: E402
from pozzo.stores import pozzoremote as PR  # noqa: E402
from test_phone_extras import make_cfg  # noqa: E402


def game(gid, platform, files, **kw):
    return {"id": gid, "key": f"k{gid}", "platform": platform, "title": f"Gioco {gid}", "files": [str(f) for f in files],
            "store": None, "media": {}, **kw}


@pytest.fixture
def env(tmp_path):
    cfg = make_cfg(tmp_path)
    app = create_app(cfg)
    hub, lib = app.state.phone_hub, app.state.lib
    rom = tmp_path / "roms" / "mario.nes"
    rom.write_bytes(b"NES\x1a" + bytes(range(200)))
    folder = tmp_path / "roms" / "Cartella"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.bin").write_bytes(b"A" * 1000)
    (folder / "sub" / "b.bin").write_bytes(b"B" * 500)
    secret = tmp_path / "segreto.txt"
    secret.write_text("no")
    other = tmp_path / "roms" / "altro.nes"
    other.write_bytes(b"x")
    for g in (game(1, "nes", [rom]), game(2, "windows", [folder]), game(3, "snes", [other]),
              game(4, "windows", [secret], store="steam")):
        lib.by_id[g["id"]] = g
        lib.games.append(g)
    cfg.app["libshare"] = {"platforms": ["nes"], "games": ["k2"]}  # 1 per console, 2 singolo; 3 NON condiviso
    gate = TestClient(PH.PhoneGate(app, hub), base_url="https://testserver")
    _, code = LS.new_invite(hub, "Zia", 30)
    token = LS.pair(hub, code, "Zia")
    LS._ACTIVE.clear()
    yield app, hub, gate, token, cfg, code
    for h in getattr(app.router, "on_shutdown", []):
        try:
            h()
        except Exception:
            pass
    gate.close()


def H(token):
    return {"Cookie": f"{PH.COOKIE}={token}"}


def _flat(routes):
    for r in routes:
        if hasattr(r, "original_router"):  # router incluso: si guarda dentro (nessun prefisso in questa app)
            yield from _flat(r.original_router.routes)
        else:
            yield r


def _paths(app):
    for r in _flat(app.routes):
        if isinstance(r, APIRoute):
            p = r.path.replace("{rel:path}", "x/y")
            p = re.sub(r"\{[^}]+\}", "1", p)
            for m in r.methods - {"HEAD", "OPTIONS"}:
                yield m, p


def test_hash_e_scadenza(env):
    app, hub, gate, token, cfg, code = env
    raw = str(hub.conf)
    assert code not in raw and token not in raw  # su disco solo impronte
    dev = hub.device_for(token)
    assert dev["kind"] == "lib"
    dev["exp"] = 1
    assert hub.device_for(token) is None


def test_senza_token_tutto_401(env):
    app, hub, gate, *_ = env
    n = 0
    for m, p in _paths(app):
        if any(mm == m and r.match(p) for mm, r in PH._PUBLIC + PH._GUEST_PUBLIC):
            continue
        r = gate.request(m, p)
        assert r.status_code == 401, (m, p, r.status_code)
        n += 1
    assert n > 100


def test_ruolo_lib_nega_il_resto(env):
    app, hub, gate, token, *_ = env
    n = 0
    for m, p in _paths(app):
        if any(mm == m and r.match(p) for mm, r in PH._PUBLIC + PH._GUEST_PUBLIC + PH._LIB_ALLOWED):
            continue
        r = gate.request(m, p, headers=H(token))
        assert r.status_code in (401, 403), (m, p, r.status_code)
        n += 1
    assert n > 100
    for m, p in (("GET", "/api/library"), ("POST", "/api/game/1/play"), ("GET", "/api/phone"), ("POST", "/api/libshare/invite"),
                 ("GET", "/api/libshare"), ("GET", "/api/play/1/save"), ("GET", "/api/play/1/bios/x"), ("GET", "/m/api/pad")):
        assert gate.request(m, p, headers=H(token)).status_code == 403, (m, p)


def test_revocato_401(env):
    app, hub, gate, token, *_ = env
    assert gate.get("/api/lib-share/list", headers=H(token)).status_code == 200
    LS.revoke_invite(hub, hub.conf["lib_invites"][0]["id"])
    assert gate.get("/api/lib-share/list", headers=H(token)).status_code == 401


def test_codice_una_volta_e_limite(env):
    app, hub, gate, token, cfg, code = env
    with pytest.raises(ValueError):
        LS.pair(hub, code, "bis")  # gia' usato
    for _ in range(LS.MAX_FAILS):
        with pytest.raises(ValueError):
            LS.pair(hub, "SBAGLIATO1", "x")
    _, code2 = LS.new_invite(hub, "B", 1)
    with pytest.raises(ValueError):
        LS.pair(hub, code2, "x")  # troppi tentativi: anche il codice giusto aspetta


def test_elenco_solo_condivisi(env):
    app, hub, gate, token, *_ = env
    ids = {g["id"] for g in gate.get("/api/lib-share/list", headers=H(token)).json()["games"]}
    assert ids == {1, 2}


def test_download_non_condiviso_e_traversal(env):
    app, hub, gate, token, *_ = env
    for gid in (3, 4, 999):
        assert gate.get(f"/api/lib-share/download/{gid}", headers=H(token)).status_code == 403
    assert gate.get("/api/lib-share/cover/3", headers=H(token)).status_code == 403
    for p in ("/api/lib-share/download/..%2F..%2Fsegreto.txt", "/api/lib-share/download/1/../3", "/api/lib-share/download/%2e%2e/3",
              "/api/lib-share/download/1%2F..%2F3", "/play/1/../3", "/api/play/1/rom/..%2F..%2Fsegreto.txt"):
        r = gate.get(p, headers=H(token))
        assert r.status_code in (403, 404, 422) and r.content != b"no", (p, r.status_code)


def test_rom_range(env):
    app, hub, gate, token, *_ = env
    full = gate.get("/api/lib-share/download/1", headers=H(token))
    assert full.status_code == 200 and full.content.startswith(b"NES\x1a") and full.headers["accept-ranges"] == "bytes"
    LS._ACTIVE.clear()
    part = gate.get("/api/lib-share/download/1", headers={**H(token), "Range": "bytes=0-3"})
    assert part.status_code == 206 and part.content == b"NES\x1a" and part.headers["content-range"].startswith("bytes 0-3/")
    LS._ACTIVE.clear()
    assert gate.get("/api/lib-share/download/1", headers={**H(token), "Range": "bytes=9999-"}).status_code == 416


def test_cartella_zip_esatto_e_un_download_alla_volta(env):
    app, hub, gate, token, *_ = env
    r = gate.get("/api/lib-share/download/2", headers=H(token))
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ["Cartella/a.bin", "Cartella/sub/b.bin"]
    assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist()) and z.testzip() is None
    LS._ACTIVE.clear()
    dev = hub.device_for(token)["id"]
    assert LS.take(dev) and not LS.take(dev)  # il secondo e' rifiutato finche' il primo e' aperto
    LS._ACTIVE.clear()


def test_zip_senza_symlink(tmp_path):
    folder = tmp_path / "g"
    folder.mkdir()
    (folder / "ok.bin").write_bytes(b"1")
    try:
        (folder / "link.txt").symlink_to(tmp_path)
    except OSError:
        pytest.skip("symlink non permessi")
    assert [a for _, a in LS.entries({"files": [str(folder)]})] == ["g/ok.bin"]


def test_webplay_solo_condivisi(env):
    app, hub, gate, token, *_ = env
    for p in ("/play/3", "/api/play/3/status", "/api/play/3/rom/x.nes", "/play/999"):
        assert gate.get(p, headers=H(token)).status_code == 403, p
    assert gate.post("/api/play/3/prepare", headers=H(token)).status_code == 403
    assert gate.get("/play/1", headers=H(token)).status_code == 200
    assert gate.get("/api/play/1/rom/mario.nes", headers=H(token)).content.startswith(b"NES")
    assert gate.get("/api/play/1/save", headers=H(token)).status_code == 403  # salvataggi: fuori dal ruolo
    assert gate.post("/api/play/1/save", content=b"x", headers=H(token)).status_code == 403


def test_gestione_solo_locale(env):
    app, hub, gate, token, *_ = env
    assert TestClient(app).get("/api/libshare").json()["count"] == 2
    assert TestClient(app, client=("10.0.0.5", 1)).get("/api/libshare").status_code == 403


# ------------------------------------------------------------------ client
class FakeResp:
    def __init__(self, status, body):
        self.status, self._b = status, body

    def read(self, n=-1):
        return self._b


class Conn:
    def close(self):
        pass


def test_client_pairing_salva_token_e_impronta(monkeypatch):
    seen = {}

    def fake_open(url, fp, method, path, token=None, body=None, headers=None, timeout=60):
        seen.update(fp=fp, path=path)
        return Conn(), FakeResp(200, b'{"ok": true, "token": "TKN"}'), "ab" * 32
    monkeypatch.setattr(PR, "open_pinned", fake_open)
    p = PR.pair("host.example", "CODE", "me")
    assert p == {"url": "https://host.example:8766", "token": "TKN", "fp": "ab" * 32} and seen["fp"] is None  # TOFU


def test_client_impronta_diversa_rifiutata(monkeypatch):
    sent = []

    class Sock:
        def getpeercert(self, binary_form=False):
            return b"altro-certificato"

    class FakeConn:
        def __init__(self, *a, **k):
            self.sock = Sock()

        def connect(self):
            pass

        def request(self, *a, **k):
            sent.append(a)

        def getresponse(self):
            return FakeResp(200, b"{}")

        def close(self):
            pass
    monkeypatch.setattr(PR.http.client, "HTTPSConnection", FakeConn)
    with pytest.raises(PR.PinError):
        PR.open_pinned("https://h:8766", "00" * 32, "GET", "/api/lib-share/list", "TOKEN")
    assert not sent  # il token non e' stato mandato
    PR.open_pinned("https://h:8766", hashlib.sha256(b"altro-certificato").hexdigest(), "GET", "/x", "TOKEN")
    assert sent  # impronta giusta: la richiesta parte


def test_norm_url():
    assert PR.norm_url("pc.local") == "https://pc.local:8766"
    for bad in ("http://x", "https://u:p@x", "https://x/a/b"):
        with pytest.raises(ValueError):
            PR.norm_url(bad)
