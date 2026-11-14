"""Protocollo pozzo://: registrazione schema in Windows e inoltro del codice party."""
import json
import shutil
import subprocess
import sys
from pathlib import Path
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
    # Sotto pytest non si tocca ne' il registro ne' la home, salvo _force.
    return _force or (sys.platform in ("win32", "linux") and "pytest" not in sys.modules)


def _desktop_file() -> Path:
    return Path.home() / ".local" / "share" / "applications" / "pozzo-url.desktop"


def _register_linux() -> bool:
    exe = command_for_current().replace('"%1"', "%u")
    f = _desktop_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("[Desktop Entry]\nType=Application\nName=Pozzo Launcher\n"
                     f"Exec={exe}\nNoDisplay=true\nTerminal=false\nMimeType=x-scheme-handler/pozzo;\n", encoding="utf-8")
        if shutil.which("xdg-mime"):
            subprocess.run(["xdg-mime", "default", f.name, "x-scheme-handler/pozzo"], timeout=10, check=False)
        return True
    except Exception:
        return False


def register(_force: bool = False) -> bool:
    if sys.platform == "darwin":
        return True  # statico: lo schema sta nell'Info.plist del .app (packaging/pozzo.spec)
    if not _allowed(_force):
        return False
    if sys.platform.startswith("linux"):
        return _register_linux()
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
    if sys.platform == "darwin":
        return False  # non si puo' togliere senza modificare il .app
    if not _allowed(_force):
        return False
    if sys.platform.startswith("linux"):
        try:
            _desktop_file().unlink(missing_ok=True)
            return True
        except Exception:
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
