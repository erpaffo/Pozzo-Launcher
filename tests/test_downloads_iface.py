"""Download legati a un'interfaccia di rete (VPN) con kill switch: interfacce finte per gli stati, loopback vera per
il traffico. Server HTTP e sciame torrent locali, nessuna rete esterna."""

import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import iface as IFACE, linkcheck, rss  # noqa: E402
from pozzo.downloads import manager as M  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.engines import torrent as TOR  # noqa: E402

DATA = os.urandom(3 * 1024 * 1024)
HITS = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        HITS.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", str(len(DATA)))
        self.send_header("Content-Disposition", 'attachment; filename="gioco.bin"')
        self.end_headers()
        try:
            for i in range(0, len(DATA), 64 * 1024):
                self.wfile.write(DATA[i:i + 64 * 1024])
        except OSError:
            pass


@pytest.fixture(scope="module")
def server():
    s = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()
    s.server_close()


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(M.hosts, "assert_public", lambda u: None)  # i server di prova stanno su 127.0.0.1
    monkeypatch.setattr(M, "IFACE_EVERY", 0.1)
    yield
    IFACE.BIND = None  # stato di modulo: il test dopo parte senza vincoli


def _fake(monkeypatch, box):
    monkeypatch.setattr(IFACE, "interfaces", lambda: [dict(i) for i in box])


def _mgr(tmp, **dl):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out"), "segments": 1, **dl,
                                                       "discovery": {"dht": False, "pex": False, "lsd": False, "upnp": False}}})
    return M.Manager(cfg, client_factory=net.make_client, save=lambda new: None)


def _wait(cond, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def _local(client):
    return client._transport._pool._local_address


def _start(m):
    m.start()
    assert _wait(lambda: hasattr(m, "_client"), 10)  # lo crea il ciclo appena parte
    return m


def _loopback() -> str:
    return next(i["name"] for i in IFACE.interfaces() if "127.0.0.1" in i["addrs"])


def test_addrs_ipv4_prima_e_interfacce_spente(monkeypatch):
    _fake(monkeypatch, [{"name": "vpn0", "up": True, "addrs": ["fd00::2", "10.8.0.2"]},
                        {"name": "eth0", "up": False, "addrs": ["192.168.1.5"]}])
    assert IFACE.addrs("vpn0") == ("10.8.0.2", "fd00::2")
    assert IFACE.addrs("eth0") == () and IFACE.addrs("nope") == ()


def test_client_kw_e_kill_switch_delle_richieste_sincrone(server):
    assert IFACE.client_kw() == {}
    IFACE.BIND = ("127.0.0.1", "::1")
    kw = IFACE.client_kw()
    assert kw["trust_env"] is False and kw["transport"]._pool._local_address == "127.0.0.1"
    assert linkcheck.check(server + "/ok")["status"] == "online"  # legato alla loopback: arriva
    IFACE.BIND = ()  # interfaccia scelta ma assente: niente esce, nemmeno dai moduli dei risolutori
    HITS.clear()
    assert linkcheck.check(server + "/ko")["status"] == "unknown"
    with pytest.raises(httpx.ConnectError):
        rss.fetch(server + "/feed")
    with pytest.raises(ValueError):
        IFACE.source()
    assert not HITS


def test_impostazione_valida_solo_interfacce_esistenti(tmp, monkeypatch):
    box = [{"name": "vpn0", "up": True, "addrs": ["10.8.0.2"]}]
    _fake(monkeypatch, box)
    m = _mgr(tmp)
    assert m.settings()["interface"] == "" and m.settings()["iface_down"] is False  # predefinita: qualunque
    with pytest.raises(ValueError):
        m.update_settings({"interface": "nope0"})
    assert m.update_settings({"interface": "vpn0"})["interface"] == "vpn0"
    box.clear()  # la VPN spenta: quella gia' salvata resta valida (non torna mai a «qualunque» da sola)
    assert m.update_settings({"interface": "vpn0", "max_active": 2})["interface"] == "vpn0"
    assert m.update_settings({"interface": ""})["interface"] == ""


def test_kill_switch_presente_assente_di_nuovo(server, tmp, monkeypatch):
    box = [{"name": "vpn0", "up": True, "addrs": ["127.0.0.1"]}]
    _fake(monkeypatch, box)
    m = _mgr(tmp, interface="vpn0", limit_down=300)
    _start(m)
    try:
        assert IFACE.BIND == ("127.0.0.1",) and _local(m._client) == "127.0.0.1"  # client creato gia' legato
        t = m.add(server + "/a")
        assert _wait(lambda: t.status == T.RUNNING and t.done > 0), (t.status, t.error)
        box.clear()  # VPN caduta
        assert _wait(lambda: t.status == T.PAUSED and t.phase == M.IFACE_PHASE), (t.status, t.phase)
        assert m.settings()["iface_down"] is True and IFACE.BIND == ()
        assert isinstance(m._client._transport, IFACE._Off)
        t2 = m.add(server + "/b")
        done = t.done
        time.sleep(1)
        assert t.done == done and t2.status == T.QUEUED  # niente scarica e niente parte
        box.append({"name": "vpn0", "up": True, "addrs": ["127.0.0.1", "::1"]})  # torna, con un indirizzo in piu'
        m.update_settings({"limit_down": 0})
        assert _wait(lambda: t.status == T.COMPLETED and t2.status == T.COMPLETED), (t.status, t.error, t2.status, t2.error)
        assert IFACE.BIND == ("127.0.0.1", "::1") and _local(m._client) == "127.0.0.1"
        assert (tmp / "out" / "gioco.bin").read_bytes() == DATA and t.phase == ""
    finally:
        m.stop()


def test_loopback_vera_e_interfaccia_inesistente(server, tmp):
    lo = _loopback()  # lo0 su macOS, lo su Linux, «Loopback Pseudo-Interface 1» su Windows
    m = _mgr(tmp, interface=lo)
    _start(m)
    try:
        assert "127.0.0.1" in IFACE.BIND and _local(m._client) == "127.0.0.1"
        t = m.add(server + "/lo")
        assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
    finally:
        m.stop()
    m2 = _mgr(tmp / "2", interface="nessuna-interfaccia-cosi")
    _start(m2)
    try:
        HITS.clear()
        t = m2.add(server + "/mai")
        time.sleep(1.5)
        assert t.status == T.QUEUED and not HITS and m2.settings()["iface_down"] is True
    finally:
        m2.stop()


def test_impostazioni_libtorrent():
    if not TOR.available():
        pytest.skip("libtorrent assente")
    e = TOR.Engine(Path("."))
    e.configure({"port": 6881})
    assert e._pack["listen_interfaces"] == "0.0.0.0:6881,[::]:6881" and e._pack["outgoing_interfaces"] == ""
    e.configure({"port": 6881, "bind": ("10.8.0.2", "fd00::2")})
    assert e._pack["listen_interfaces"] == "10.8.0.2:6881,[fd00::2]:6881"
    assert e._pack["outgoing_interfaces"] == "10.8.0.2,fd00::2"
    e.configure({"port": 6881, "bind": ()})  # interfaccia assente: solo loopback
    assert e._pack["listen_interfaces"] == "127.0.0.1:6881" and e._pack["outgoing_interfaces"] == "127.0.0.1"


@pytest.fixture
def swarm(tmp):
    lt = pytest.importorskip("libtorrent")
    src = tmp / "src" / "set"
    src.mkdir(parents=True)
    (src / "a.bin").write_bytes(os.urandom(16384 * 8))
    ct = lt.create_torrent(lt.list_files(str(src)), 16384)
    lt.set_piece_hashes(ct, str(src.parent))
    (tmp / "set.torrent").write_bytes(lt.bencode(ct.generate()))
    seed = lt.session({"listen_interfaces": "127.0.0.1:0", "enable_dht": False, "enable_lsd": False,
                       "enable_upnp": False, "enable_natpmp": False})
    p = lt.add_torrent_params()
    p.ti, p.save_path = lt.torrent_info(str(tmp / "set.torrent")), str(src.parent)
    p.flags |= lt.torrent_flags.seed_mode
    h = seed.add_torrent(p)
    yield SimpleNamespace(torrent=tmp / "set.torrent", peer=f"127.0.0.1:{seed.listen_port()}")
    seed.remove_torrent(h)


def test_torrent_legato_alla_loopback(swarm, tmp):
    m = _mgr(tmp, interface=_loopback())
    _start(m)
    try:
        t = m.add(str(swarm.torrent), connect=[swarm.peer])
        assert _wait(lambda: t.status == T.COMPLETED), (t.status, t.error)
        assert "127.0.0.1" in m._torrent.ses.get_settings()["outgoing_interfaces"]
    finally:
        m.stop()


def test_torrent_solo_ipv6_non_raggiunge_il_peer_ipv4(swarm, tmp, monkeypatch):
    """Interfaccia con il solo ::1: il seeder su 127.0.0.1 non si raggiunge, quindi le connessioni escono davvero da lì."""
    _fake(monkeypatch, [{"name": "vpn6", "up": True, "addrs": ["::1"]}])
    m = _mgr(tmp, interface="vpn6")
    _start(m)
    try:
        t = m.add(str(swarm.torrent), connect=[swarm.peer])
        assert _wait(lambda: t.status == T.RUNNING and t.options.get("metadata"), 30)
        time.sleep(3)
        assert t.done == 0 and not t.options.get("peers"), (t.done, t.options.get("peers"))
        assert m._torrent.ses.get_settings()["listen_interfaces"].startswith("[::1]:")
    finally:
        m.stop()
