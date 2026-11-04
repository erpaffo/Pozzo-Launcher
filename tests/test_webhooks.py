"""Webhook in uscita: firma, corpo, hook saltati (evento sconosciuto, URL non valido, disattivato)."""
import hashlib
import hmac
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pozzo import webhooks as WH  # noqa: E402
from pozzo.app.extensions import Events  # noqa: E402

received = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers["Content-Length"])
        received.append((self.path, self.headers.get("X-Pozzo-Signature"), self.rfile.read(n)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def test_webhook_signed_body_and_skipped_hooks():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    cfg = SimpleNamespace(app={"webhooks": [
        {"url": base + "/ok", "events": ["gioco_avviato"], "secret": "s3"},
        {"url": "ftp://127.0.0.1/x", "events": ["gioco_avviato"]},  # URL non valido
        {"url": base + "/sconosciuto", "events": ["evento_inventato"]},  # evento non esistente
        {"url": base + "/off", "events": ["gioco_avviato"], "enabled": False},
    ]})
    bus = Events()
    WH.register(bus, cfg)
    bus.emit("game_started", {"title": "Doom"})
    bus.emit("game_stopped", {"title": "Doom"})  # nessun hook ascolta questo evento
    deadline = time.time() + 5
    while not received and time.time() < deadline:
        time.sleep(0.05)
    time.sleep(0.3)  # tempo per eventuali invii sbagliati
    try:
        assert len(received) == 1
        path, sig, body = received[0]
        assert path == "/ok"
        assert sig == "sha256=" + hmac.new(b"s3", body, hashlib.sha256).hexdigest()
        msg = json.loads(body)
        assert msg["event"] == "gioco_avviato"
        assert msg["data"] == {"title": "Doom"}
        assert msg["time"]

        assert WH.send_test("ftp://127.0.0.1/x")[0] is False
        assert WH.send_test(base + "/ok", "s3") == (True, "200")
        assert json.loads(received[-1][2])["event"] == "test"
    finally:
        srv.shutdown()


def test_retry_only_on_5xx_or_network(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        code = {"/4xx": 404, "/5xx": 503}.get(url[-4:])
        if code is None:
            raise OSError("rete giu'")
        return SimpleNamespace(status_code=code)

    monkeypatch.setattr(WH.httpx, "post", fake_post)
    for u, n in (("http://h/4xx", 1), ("http://h/5xx", 2), ("http://h/rete", 2)):
        calls.clear()
        WH._post(u, b"{}", None)
        assert len(calls) == n, u
    assert not WH._valid_url("http://") and not WH._valid_url("javascript:alert(1)")
