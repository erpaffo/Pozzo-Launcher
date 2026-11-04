"""Protocollo pozzo://: comando, registro (finto), parsing e inoltro su server locale."""
import socket
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

from pozzo import protocol as P


class _Key:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_winreg():
    # Registro finto in memoria: chiave completa -> valori. Le chiavi intermedie vengono create.
    keys = {}

    def create(_root, path):
        parts = path.split("\\")
        for i in range(1, len(parts) + 1):
            keys.setdefault("\\".join(parts[:i]), {})
        return _Key(path)

    def open_key(_root, path, *_a):
        if path not in keys:
            raise FileNotFoundError(path)
        return _Key(path)

    def set_value(k, name, _res, _typ, value):
        keys[k.path][name] = value

    def enum_key(k, i):
        kids = sorted({p[len(k.path) + 1:].split("\\")[0] for p in keys if p.startswith(k.path + "\\")})
        if i >= len(kids):
            raise OSError("fine")
        return kids[i]

    def delete_key(_root, path):
        if path not in keys:
            raise FileNotFoundError(path)
        if any(p.startswith(path + "\\") for p in keys):
            raise OSError("chiave non vuota")
        del keys[path]

    wr = types.SimpleNamespace(
        HKEY_CURRENT_USER="HKCU", REG_SZ=1, KEY_ALL_ACCESS=0xF003F, CreateKey=create,
        OpenKey=open_key, SetValueEx=set_value, EnumKey=enum_key, DeleteKey=delete_key,
    )
    return wr, keys


def test_command_per_sorgente_e_frozen(monkeypatch):
    c = P.command_for_current()
    assert c.endswith('"%1"') and sys.executable in c
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    c = P.command_for_current()
    assert c == f'"{sys.executable}" "%1"'


def test_register_scrive_chiavi_corrette(monkeypatch):
    wr, keys = _fake_winreg()
    monkeypatch.setitem(sys.modules, "winreg", wr)
    assert P.register(_force=True) is True
    assert keys[r"Software\Classes\pozzo"] == {"": "URL:Pozzo", "URL Protocol": ""}
    assert keys[r"Software\Classes\pozzo\shell\open\command"][""] == P.command_for_current()


def test_unregister_rimuove_la_chiave(monkeypatch):
    wr, keys = _fake_winreg()
    monkeypatch.setitem(sys.modules, "winreg", wr)
    assert P.register(_force=True) is True
    assert P.unregister(_force=True) is True
    assert not [k for k in keys if "pozzo" in k]  # le chiavi padre restano, come nel registro vero


def test_unregister_senza_chiave_e_ok(monkeypatch):
    wr, keys = _fake_winreg()
    monkeypatch.setitem(sys.modules, "winreg", wr)
    assert P.unregister(_force=True) is True


def test_fuori_windows_o_sotto_pytest_non_scrive(monkeypatch):
    wr, keys = _fake_winreg()
    monkeypatch.setitem(sys.modules, "winreg", wr)
    monkeypatch.setattr(sys, "platform", "linux")
    assert P.register() is False and P.unregister() is False
    monkeypatch.setattr(sys, "platform", "win32")
    assert P.register() is False and P.unregister() is False  # pytest in sys.modules
    assert keys == {}


def test_parse_url():
    assert P.parse_url("pozzo://join/ABC123") == "ABC123"
    assert P.parse_url("POZZO://JOIN/X") == "X"
    assert P.parse_url("pozzo://altro/X") is None
    assert P.parse_url("pozzo://join/") is None
    assert P.parse_url("pozzo://join/X/") is None
    assert P.parse_url("pozzo://join/X?a=1") is None
    assert P.parse_url("https://join/X") is None


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        self.rfile.read(n)
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_forward_con_server_locale():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        assert P.forward("pozzo://join/XYZ", port=srv.server_address[1]) is True
        assert P.forward("https://x/y", port=srv.server_address[1]) is False
    finally:
        srv.shutdown()
        srv.server_close()


def test_forward_porta_chiusa():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert P.forward("pozzo://join/XYZ", port=port) is False
