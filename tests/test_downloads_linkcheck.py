import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pozzo import net  # noqa: E402
from pozzo.downloads import hosts, linkcheck as LC, manager as M  # noqa: E402


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def _pub(monkeypatch):
    monkeypatch.setattr(hosts, "assert_public", lambda u: None)


def test_check_online_offline_sconosciuto(monkeypatch):
    _pub(monkeypatch)

    def h(req):
        p = req.url.path
        if p == "/ok":
            return httpx.Response(206, headers={"content-range": "bytes 0-0/1234", "content-disposition": 'attachment; filename="g.zip"'})
        if p == "/gone":
            return httpx.Response(404)
        if p == "/redir":
            return httpx.Response(302, headers={"location": "/ok"})
        return httpx.Response(503)
    c = _client(h)
    r = LC.check("https://x.test/ok", c)
    assert (r["status"], r["size"], r["name"]) == ("online", 1234, "g.zip")
    assert LC.check("https://x.test/gone", c)["status"] == "offline"
    assert LC.check("https://x.test/redir", c)["status"] == "online"
    assert LC.check("https://x.test/boh", c)["status"] == "unknown"
    assert LC.check("magnet:?xt=urn:btih:abc", c)["status"] == "unknown"


def test_check_redirect_verso_lan_non_seguito(monkeypatch):
    def pub(u):
        if "lan.test" in u:
            raise ValueError("lan")
    monkeypatch.setattr(hosts, "assert_public", pub)
    seen = []

    def h(req):
        seen.append(req.url.host)
        return httpx.Response(302, headers={"location": "http://lan.test/x"})
    assert LC.check("https://x.test/a", _client(h))["status"] == "unknown"
    assert seen == ["x.test"]


def test_parse_links():
    def pub(u):
        if "192.168." in u:
            raise ValueError("lan")
    t = ("Guarda https://a.test/f.zip, e (https://a.test/f.zip) poi http://192.168.1.2/x "
         "magnet:?xt=urn:btih:abc&dn=x e magnet:?dn=senza_hash. Fine https://b.test/p?q=1.")
    assert LC.parse_links(t, pub) == ["https://a.test/f.zip", "magnet:?xt=urn:btih:abc&dn=x", "https://b.test/p?q=1"]
    assert len(LC.parse_links(" ".join(f"https://a.test/{i}" for i in range(80)), pub)) == LC.MAX_LINKS
    assert LC.parse_links("http://127.0.0.1/x http://[::1]/y") == []


def test_host_free():
    lim = {"datanodes.to": 2}
    assert M.host_free("s1.datanodes.to", ["s2.datanodes.to"], lim)
    assert not M.host_free("datanodes.to", ["s2.datanodes.to", "datanodes.to"], lim)
    assert M.host_free("altro.test", ["datanodes.to"] * 5, lim) and M.host_free("", [], lim)
    assert M.host_free("notdatanodes.to", ["datanodes.to"] * 5, lim)


def test_impostazioni_e_add_con_check(tmp_path):
    cfg = SimpleNamespace(cache=tmp_path / "cache", app={"downloads": {"dir": str(tmp_path / "out")}})
    m = M.Manager(cfg, client_factory=net.make_client, save=lambda new: None)
    s = m.update_settings({"host_limits": {"WWW.Datanodes.to": 2}, "check_links": True})
    assert s["host_limits"] == {"datanodes.to": 2} and s["check_links"] is True
    for bad in ({"x": 1}, {"a.test": 0}, {"a.test": 11}, {"a.test": True}, {"a/b.test": 1}, [1]):
        with pytest.raises(ValueError):
            m.update_settings({"host_limits": bad})
    m._check = lambda u: {"status": "offline" if "morto" in u else "unknown"}
    with pytest.raises(ValueError):
        m.add("https://x.test/morto.zip")
    assert m.add("https://x.test/vivo.zip").status
    assert M.DEFAULTS["check_links"] is False and M.DEFAULTS["host_limits"] == {}
