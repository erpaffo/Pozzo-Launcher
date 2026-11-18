"""Click'n'Load 2 (come JDownloader): le pagine con il pulsante «Click'n'Load» mandano i link a 127.0.0.1:9666.

Qualunque pagina aperta nel browser puo' chiamare questa porta: e' cosi' che funziona il protocollo. Per questo i link
non entrano mai da soli nei download: finiscono in un elenco in attesa (solo in memoria, con un tetto) che la persona
rivede e conferma nell'app. Il server e' uno a se' (http.server della libreria standard) con quattro rotte e nient'altro:
nessuna API, nessun file dell'app. Il `jk` delle pagine e' JavaScript: non si esegue mai, se ne legge la chiave con
un'espressione rigida.

Protocollo (wiki di JDownloader, glossary/cnl2, e pyLoad cnl_blueprint):
  GET  /jdcheck.js          -> «jdownloader=true;»
  GET  /flash  (/flash/)    -> «JDownloader»
  POST /flash/add           urls (uno per riga), passwords, source
  POST /flash/addcrypted2   crypted = base64(AES-128-CBC, chiave = hex restituito da jk, IV = chiave, padding NUL), passwords, source
"""
from __future__ import annotations

import base64
import binascii
import itertools
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import linkcheck

PORT = 9666
HOST = "127.0.0.1"  # mai la rete: solo il browser di questo PC
MAX_BODY = 256 * 1024  # una pagina vera manda pochi KB anche con 50 link cifrati
MAX_PENDING = 20  # gruppi in attesa di conferma: oltre, i nuovi si rifiutano (una pagina insistente non riempie la memoria)
MAX_LINK = 4096
_JK = re.compile(r"\s*function\s+f\s*\(\s*\)\s*\{\s*return\s*(['\"])([0-9a-fA-F]{32})\1\s*;?\s*\}\s*;?\s*")


def key_from_jk(jk: str) -> bytes:
    """I 16 byte della chiave da `function f(){ return '<32 hex>';}`; ValueError per qualunque altra forma."""
    m = _JK.fullmatch(jk or "")
    if not m:
        raise ValueError("jk non riconosciuto")
    return bytes.fromhex(m[2])


def decrypt(crypted: str, key: bytes) -> str:
    """Testo in chiaro di `crypted` (base64 di AES-128-CBC con IV = chiave, riempito con NUL). ValueError se non torna."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    try:
        data = base64.b64decode(re.sub(r"\s+", "", crypted or ""), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("crypted non e' base64")
    if not data or len(data) % 16:
        raise ValueError("crypted di lunghezza non valida")
    d = Cipher(algorithms.AES(key), modes.CBC(key)).decryptor()
    return (d.update(data) + d.finalize()).replace(b"\0", b"").decode("utf-8", "replace")


def links(text: str) -> list[str]:
    """Solo link http(s)/magnet, con lo stesso filtro degli appunti (niente rete locale, al massimo 50)."""
    return [u for u in linkcheck.parse_links(text) if len(u) <= MAX_LINK]


class ClickNLoad:
    """Server Click'n'Load (acceso solo se l'impostazione e' attiva) ed elenco dei link in attesa di conferma."""

    def __init__(self, on_change=lambda: None, port: int | None = None):
        self.port, self.on_change = PORT if port is None else port, on_change
        self.lock = threading.Lock()
        self._pending: list[dict] = []
        self._ids = itertools.count(1)
        self.server: ThreadingHTTPServer | None = None
        self.error = ""  # "busy" = porta gia' occupata (JDownloader aperto?)

    # ---------------------------------------------------------------- elenco in attesa
    def pending(self) -> list[dict]:
        with self.lock:
            return [dict(p) for p in self._pending]

    def take(self, pid: int) -> dict | None:
        """Toglie un gruppo dall'elenco (confermato o scartato dalla persona) e lo restituisce."""
        with self.lock:
            p = next((x for x in self._pending if x["id"] == pid), None)
            if p:
                self._pending.remove(p)
        if p:
            self.on_change()
        return p

    def push(self, found: list[str], passwords: str, source: str) -> bool:
        if not found:
            return False
        src = str(source or "")[:500]
        entry = {"id": 0, "links": found, "source": src, "site": urlsplit(src).hostname or src[:80], "at": time.time(),
                 "passwords": [p for p in (x.strip() for x in str(passwords or "").splitlines()) if 0 < len(p) <= 128][:5]}
        with self.lock:
            if len(self._pending) >= MAX_PENDING:
                return False
            entry["id"] = next(self._ids)
            self._pending.append(entry)
        self.on_change()
        return True

    # ---------------------------------------------------------------- server
    def apply(self, on: bool):
        """Accende o spegne il server secondo l'impostazione. Porta occupata: error = "busy", nessuna eccezione."""
        if on and not self.server:
            try:
                srv = _Server((HOST, self.port), _Handler)
            except OSError:
                self.error = "busy"
                return
            srv.cnl, self.server, self.error = self, srv, ""
            threading.Thread(target=srv.serve_forever, daemon=True, name="clicknload").start()
        elif not on:
            self.error = ""
            if self.server:
                srv, self.server = self.server, None
                srv.shutdown()
                srv.server_close()
                with self.lock:  # spento: i link in attesa non servono piu'
                    self._pending.clear()
                self.on_change()


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows con SO_REUSEADDR legherebbe la porta anche se JDownloader la sta gia' usando
    allow_reuse_address = os.name != "nt"
    cnl: ClickNLoad


class _Handler(BaseHTTPRequestHandler):
    server_version, sys_version = "Pozzo", ""
    timeout = 10  # una connessione lasciata a meta' non tiene un thread per sempre
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code: int, text: str, ctype: str = "text/plain"):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/jdcheck.js":
            return self._send(200, "jdownloader=true;\r\n", "text/javascript")
        if path in ("/flash", "/flash/"):
            return self._send(200, "JDownloader\r\n")
        self._send(404, "")

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/flash/add", "/flash/addcrypted2"):
            return self._send(404, "")
        try:
            size = int(self.headers.get("Content-Length") or -1)
        except ValueError:
            size = -1
        if size < 0 or self.headers.get("Transfer-Encoding"):
            return self._send(411, "failed\r\n")
        if size > MAX_BODY:
            self._send(413, "failed\r\n")
            # chiudere con dati non letti manda un RST (Windows): il client vedrebbe "connessione interrotta" e non il 413
            left = min(size, 4 * MAX_BODY)
            while left > 0 and (chunk := self.rfile.read(min(left, 65536))):
                left -= len(chunk)
            return
        try:
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(size).decode("utf-8", "replace"), max_num_fields=20).items()}
            text = form.get("urls", "") if path == "/flash/add" else decrypt(form.get("crypted", ""), key_from_jk(form.get("jk", "")))
        except ValueError:  # jk sconosciuto, cifrato rotto, troppi campi: niente
            return self._send(400, "failed\r\n")
        ok = self.server.cnl.push(links(text), form.get("passwords", ""), form.get("source", ""))
        self._send(200 if ok else 400, "success\r\n" if ok else "failed\r\n")
