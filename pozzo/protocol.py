"""Protocollo pozzo://: registrazione schema in Windows e inoltro del codice party."""
import json
import sys
import urllib.parse
import urllib.request

_KEY = r"Software\Classes\pozzo"
_CMD = _KEY + r"\shell\open\command"


def command_for_current() -> str:
    # Comando che Windows lancia col link; %1 e' l'URL cliccato.
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    return f'"{sys.executable}" -m pozzo "%1"'


def _allowed(_force: bool) -> bool:
    # Fuori da Windows e sotto pytest non si tocca il registro.
    return _force or (sys.platform == "win32" and "pytest" not in sys.modules)


def register(_force: bool = False) -> bool:
    if not _allowed(_force):
        return False
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Pozzo")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _CMD) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, command_for_current())
        return True
    except Exception:
        return False


def _rm_tree(wr, path: str) -> None:
    # DeleteKey non cancella chiavi con figli: prima svuota ricorsivamente.
    try:
        k = wr.OpenKey(wr.HKEY_CURRENT_USER, path, 0, wr.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return
    with k:
        subs = []
        while True:
            try:
                subs.append(wr.EnumKey(k, len(subs)))
            except OSError:
                break
    for s in subs:
        _rm_tree(wr, path + "\\" + s)
    wr.DeleteKey(wr.HKEY_CURRENT_USER, path)


def unregister(_force: bool = False) -> bool:
    if not _allowed(_force):
        return False
    try:
        import winreg
        _rm_tree(winreg, _KEY)
        return True
    except Exception:
        return False


def parse_url(url: str) -> str | None:
    # Accetta solo pozzo://join/<codice>, schema e host senza distinzione di maiuscole.
    p = urllib.parse.urlsplit(url)
    if p.scheme.lower() != "pozzo" or p.netloc.lower() != "join":
        return None
    code = p.path[1:]
    if not code or "/" in code or p.query or p.fragment:
        return None
    return code


def forward(url: str, port: int = 8765) -> bool:
    code = parse_url(url)
    if code is None:
        return False
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/party/incoming",
            data=json.dumps({"code": code}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read().decode("utf-8")).get("ok") is True
    except Exception:
        return False
