"""Catena dei risolutori: motivi dei fallimenti debrid, chiave mai nei messaggi, tetti di tempo, pausa durante la
risoluzione, attesa di 1fichier. Nessuna rete."""

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import storelinks as SL  # noqa: E402
from pozzo.downloads import debrid as D, hosts, resolvers  # noqa: E402
from pozzo.downloads import task as T  # noqa: E402
from pozzo.downloads.engines import http as H  # noqa: E402
from pozzo.downloads.manager import Manager  # noqa: E402

URL = "https://1fichier.com/?abc"
KEY = "SEGRETO123"
REPLIES = {  # servizio -> risposta di errore vera (forma di ognuno)
    "realdebrid": (503, {"error": "hoster_unsupported", "error_code": 16}),
    "alldebrid": (200, {"status": "error", "error": {"code": "LINK_HOST_NOT_SUPPORTED", "message": "This host or link is not supported"}}),
    "premiumize": (200, {"status": "error", "message": "Unsupported host"}),
    "torbox": (200, {"success": False, "detail": "Quota giornaliera esaurita"}),
    "debridlink": (200, {"success": False, "error": "hoster_not_supported"}),
}


def _mock(monkeypatch, status, body):
    def handler(req):
        if req.url.path.endswith("/hosts/domains"):
            return httpx.Response(200, json={"status": "success", "data": {"hosts": ["1fichier.com"]}})
        if req.url.path.endswith("/downloader/hosts"):
            return httpx.Response(200, json={"success": True, "value": [
                {"domains": ["1fichier.com"], "status": 1}]})
        return httpx.Response(status, json=body)

    monkeypatch.setattr(D, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    D._cache.clear()
    D._hosts_cache.clear()


@pytest.mark.parametrize("svc,want", [("realdebrid", "host non supportato"), ("alldebrid", "host non supportato"),
                                      ("premiumize", "host non supportato"), ("torbox", "limite del servizio raggiunto"),
                                      ("debridlink", "host non supportato")])
def test_motivo_per_servizio(monkeypatch, svc, want):
    _mock(monkeypatch, *REPLIES[svc])
    link, why = D.attempt(svc, KEY, URL)
    assert link == "" and why == want
    assert D.unlock(svc, KEY, URL) == ""


def test_chiave_sbagliata_e_testo_sconosciuto(monkeypatch):
    _mock(monkeypatch, 401, {"success": False, "error": "badToken"})
    assert D.attempt("debridlink", KEY, URL)[1] == "chiave non valida"
    _mock(monkeypatch, 200, {"status": "error", "error": {"code": "XYZ", "message": "qualcosa di strano"}})
    assert D.attempt("alldebrid", KEY, URL)[1] == "XYZ qualcosa di strano"
    _mock(monkeypatch, 200, ["non", "un", "oggetto"])
    assert D.attempt("realdebrid", KEY, URL)[1] == "risposta non valida"


def test_chiave_coperta(monkeypatch):
    def boom(req):
        raise httpx.ConnectError(f"fallito {req.url}", request=req)
    monkeypatch.setattr(D, "_client", lambda: httpx.Client(transport=httpx.MockTransport(boom)))
    D._cache.clear()
    why = D.attempt("premiumize", KEY, URL)[1]
    assert why == "servizio non raggiungibile" and KEY not in why
    assert KEY not in D._why(D._Fail(f"errore con {KEY}"), KEY)
    assert KEY not in D._why(ValueError(f"?apikey={KEY}"), KEY)


def test_note_nel_resolve_e_nella_fase(monkeypatch):
    _mock(monkeypatch, *REPLIES["debridlink"])
    monkeypatch.setattr(resolvers, "_FNS", [])
    resolvers.register(D.resolver(lambda: {"debridlink": {"enabled": True, "key": KEY}}), "Sblocco")
    resolvers.register(lambda u: "", "Cerco il file")
    seen, notes = [], []
    assert resolvers.resolve(URL, seen.append, notes) == (URL, "")
    assert notes == ["Debrid-Link: host non supportato"]
    assert seen == ["Sblocco", "Debrid-Link: host non supportato", "Cerco il file — Debrid-Link: host non supportato"]


# ---------------------------------------------------------------- 1fichier
class _S:
    def __init__(self, text):
        self.text = text

    def post(self, url, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


@pytest.mark.parametrize("page,want", [
    ("You must wait 15 minutes before a new download", "1fichier: limite per IP, riprova tra 15 minuti"),
    ("you must wait 30 seconds", "1fichier: limite per IP, riprova tra 30 secondi"),
    ('<div class="g-recaptcha"></div>', "1fichier: chiede un captcha, scaricalo dal browser"),
])
def test_fichier_blocco_senza_browser(monkeypatch, page, want):
    monkeypatch.setattr(hosts.httpx, "Client", lambda **kw: _S(page))
    monkeypatch.setattr(SL, "with_browser", lambda u: pytest.fail("il browser non serve"))
    monkeypatch.setattr(resolvers, "_FNS", [])
    resolvers.register(hosts.resolve)
    seen, notes = [], []
    assert resolvers.resolve(URL, seen.append, notes) == (URL, "")
    assert notes == [want] and seen == [want]


# ---------------------------------------------------------------- browser nascosto
def test_browser_tetto_e_fase(monkeypatch):
    monkeypatch.setattr(SL, "_LOCK", threading.Lock())
    monkeypatch.setitem(SL.RESOLVER, "fn", lambda u: time.sleep(2) or "https://x/late")
    monkeypatch.setattr(resolvers, "_FNS", [])
    resolvers.register(lambda u: SL.with_browser(u, timeout=0.3) or "")
    seen, notes = [], []
    t0 = time.time()
    assert resolvers.resolve(URL, seen.append, notes) == (URL, "")
    assert time.time() - t0 < 1.5
    assert seen[0] == "Apro la pagina nel browser nascosto (fino a 0.3 s)…"
    assert notes == ["il browser nascosto non ha risposto entro 0.3 s"]
    monkeypatch.setitem(SL.RESOLVER, "fn", lambda u: "https://x/file.bin")
    assert SL.with_browser(URL, timeout=5) == "https://x/file.bin"
    monkeypatch.setitem(SL.RESOLVER, "fn", None)
    assert SL.with_browser(URL) == ""


# ---------------------------------------------------------------- manager
def _mgr(tmp):
    cfg = SimpleNamespace(cache=tmp / "cache", app={"downloads": {"dir": str(tmp / "out")}})
    return Manager(cfg, save=lambda new: None)


def _wait(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_scadenza_risoluzione_errore_chiaro(tmp, monkeypatch):
    monkeypatch.setattr(H, "RESOLVE_TIMEOUT", 0.4)
    gate = threading.Event()
    monkeypatch.setattr(resolvers, "_FNS", [])
    resolvers.register(lambda u: (resolvers.note("Debrid-Link: host non supportato"), gate.wait(5), "https://x/late.bin")[2], "Lento")
    m = _mgr(tmp)
    m.start()
    t = m.add(URL, name="r.bin")
    assert _wait(lambda: t.status == T.ERROR)
    assert t.error.startswith("Non sono riuscito a ottenere il link in 0.4 s") and t.error.endswith("(Debrid-Link: host non supportato)")
    gate.set()  # il thread tardivo finisce: non deve toccare il task
    time.sleep(0.4)
    assert t.status == T.ERROR and "resolved_by" not in t.options and t.id not in m._jobs
    m.stop()


def test_pausa_durante_la_risoluzione(tmp, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(resolvers, "_FNS", [])
    resolvers.register(lambda u: (gate.wait(5), "https://x/late.bin")[1], "Lento")
    m = _mgr(tmp)
    m.start()
    t = m.add(URL, name="p.bin")
    assert _wait(lambda: t.phase == "Lento")
    t0 = time.time()
    m.pause(t.id)
    assert _wait(lambda: t.id not in m._jobs, 2) and time.time() - t0 < 2 and t.status == T.PAUSED
    resolvers._FNS.append((lambda u: "", "Altro"))
    phase = t.phase
    gate.set()  # il thread tardivo finisce: ne' fase ne' resolved_by cambiano
    time.sleep(0.4)
    assert t.status == T.PAUSED and t.phase == phase and "resolved_by" not in t.options
    m.stop()
