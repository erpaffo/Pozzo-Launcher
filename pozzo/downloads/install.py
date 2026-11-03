"""Installazione di un repack: avvia il setup scaricato e, quando la finestra si chiude, mette il gioco in libreria.

L'avanzamento del setup non e' leggibile da fuori: l'attivita' mostra il tempo trascorso e la barra indeterminata,
poi il passaggio «riconosco il gioco». Il gioco installato si trova dall'elenco delle app («App e funzionalita'»)
oppure, se il repack non si registra, dalle cartelle nuove in Program Files e nella radice dei dischi fissi.
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from pathlib import Path

_SETUP = re.compile(r"^setup.*\.exe$", re.I)  # setup.exe, Setup (1).exe, setup_dodi.exe
_SKIP = re.compile(r"unins|redist|vcredist|dxsetup|directx|install|crash|update", re.I)
_UNINSTALL = ((r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 1),
              (r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", 1),
              (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", 0))  # (chiave, 1 = macchina, 0 = utente)
_RUNS: dict[str, dict] = {}  # id del task -> installazione in corso o appena finita
_LOCK = threading.Lock()


def find_setup(files) -> Path | None:
    """Il setup di un repack tra i file scaricati o estratti (quello piu' in alto nell'albero)."""
    cands = [Path(f) for f in files if f.suffix.lower() == ".exe" and _SETUP.match(f.name) and not _SKIP.search(f.name)]
    return min(cands, key=lambda f: (len(f.parts), str(f).lower()), default=None)


def rows() -> list[dict]:
    """Installazioni in corso o appena finite, per il pannello Attivita'."""
    with _LOCK:
        return [dict(r) for r in _RUNS.values()]


def start(t, mgr, ctx) -> None:
    """Avvia il setup del repack in un thread (ValueError se non c'e' niente da avviare)."""
    setup = Path((t.options.get("setup") or {}).get("exe") or "")
    if not setup.is_file():
        raise ValueError("Nessun setup da avviare: il repack non e' stato estratto o i file sono stati spostati")
    with _LOCK:
        if (_RUNS.get(t.id) or {}).get("status") == "running":
            raise ValueError("L'installazione e' gia' in corso")
        _RUNS[t.id] = {"id": t.id, "name": _title(t, ctx) or setup.stem, "status": "running", "progress": None,
                       "started": time.time(), "finished": 0.0, "phase": "Avvio del setup…", "last": str(setup)}
    threading.Thread(target=_run, args=(t, mgr, ctx, setup), daemon=True, name="repack-install").start()


def _title(t, ctx) -> str:
    """Titolo del gioco: quello della scheda del catalogo, che e' anche quello con cui la voce online sparisce."""
    gid = t.options.get("game_id")
    if gid is not None:
        try:
            return ctx.lib.get(gid)["title"]
        except Exception:  # noqa: BLE001 - gioco non piu' in libreria: si usa il nome del file
            pass
    return t.name


def _state(tid: str, **kw) -> None:
    with _LOCK:
        if tid in _RUNS:
            _RUNS[tid].update(kw)


def _run(t, mgr, ctx, setup: Path) -> None:
    try:
        before = _snapshot()
        t.log(f"Installazione: avvio di {setup.name} (si apre la finestra del setup)")
        mgr._poke()
        code = _launch(setup)
        _state(t.id, phase="Riconosco il gioco installato…")
        t.log(f"Setup chiuso (codice {code}): cerco il gioco appena installato…")
        found = detect(before)
        if not found:
            _state(t.id, status="error", finished=time.time(),
                   phase="Installazione finita, ma non ho riconosciuto il gioco")
            t.log("Non trovo il gioco installato: aggiungilo con «＋ Aggiungi» o con la cartella PC in Impostazioni", "warn")
            return
        title = _title(t, ctx) or found["title"]
        exe = found["exe"]
        mid = ctx.user.add_manual(title, str(exe), [], str(exe.parent))
        refresh = getattr(ctx, "_refresh_manual", None)
        if refresh:
            refresh(mid)  # libreria aggiornata subito: il gioco compare senza aspettare una scansione
        t.options["setup"]["installed"] = True
        _state(t.id, status="done", finished=time.time(), phase=f"In libreria: {title}")
        t.log(f"Repack installato: {title} → {exe}")
    except Exception as e:  # noqa: BLE001 - l'errore si vede nell'attivita' e nel registro del download
        _state(t.id, status="error", finished=time.time(), phase=f"{type(e).__name__}: {e}")
        t.log(f"Installazione non riuscita: {type(e).__name__}: {e}", "error")
    finally:
        mgr._poke()


def _launch(exe: Path) -> int:
    """Avvia il setup come farebbe Esplora file (anche con la richiesta di amministratore) e aspetta che finisca."""
    if sys.platform != "win32":
        return subprocess.run([str(exe)], cwd=str(exe.parent)).returncode
    import ctypes
    from ctypes import wintypes

    class ShellExecuteInfoW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

    info = ShellExecuteInfoW(cbSize=ctypes.sizeof(ShellExecuteInfoW), fMask=0x00000040,  # SEE_MASK_NOCLOSEPROCESS
                             lpVerb="open", lpFile=str(exe), lpDirectory=str(exe.parent), nShow=1)
    if not ctypes.WinDLL("shell32", use_last_error=True).ShellExecuteExW(ctypes.byref(info)):
        raise OSError(f"Il setup non si e' avviato (errore {ctypes.get_last_error()})")
    if not info.hProcess:
        return 0
    try:
        ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        code = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return int(code.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(info.hProcess)


# ---------------------------------------------------------------- riconoscere il gioco installato
def _snapshot() -> dict:
    """Cosa c'e' prima dell'installazione: app registrate e cartelle di primo livello dove finiscono i giochi."""
    return {"apps": _registry_apps(), "dirs": sorted(_listing())}


def detect(before: dict) -> dict | None:
    """Il gioco appena installato: {"title", "exe"} dall'elenco delle app o dalle cartelle nuove, None se niente."""
    for name, vals in _registry_apps().items():
        if name not in before.get("apps", {}):
            exe = _install_exe(vals)
            if exe:
                return {"title": name, "exe": exe}
    for folder in sorted(_listing() - set(before.get("dirs") or ())):
        exe = _exe_in(Path(folder))
        if exe:
            return {"title": Path(folder).name, "exe": exe}
    return None


def _registry_apps() -> dict[str, dict]:
    """Nome visibile -> cartella e icona delle app in «App e funzionalita'» (vuoto fuori da Windows)."""
    if sys.platform != "win32":
        return {}
    import winreg
    out = {}
    for path, machine in _UNINSTALL:
        hive = winreg.HKEY_LOCAL_MACHINE if machine else winreg.HKEY_CURRENT_USER
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:  # chiave assente (utente o Windows vecchio)
            continue
        with root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                vals = {}
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i)) as sub:
                        for field in ("DisplayName", "InstallLocation", "DisplayIcon"):
                            try:
                                vals[field] = str(winreg.QueryValueEx(sub, field)[0])
                            except OSError:
                                pass
                except OSError:  # voce illeggibile: si passa alla prossima
                    continue
                if vals.get("DisplayName"):
                    out[vals["DisplayName"]] = vals
    return out


def _install_exe(vals: dict) -> Path | None:
    """L'eseguibile di un'app installata: l'icona mostrata in «App e funzionalita'» o il piu' grande della cartella."""
    icon = (vals.get("DisplayIcon") or "").split(",")[0].strip().strip('"')
    if icon.lower().endswith(".exe") and Path(icon).is_file() and not _SKIP.search(Path(icon).name):
        return Path(icon)
    loc = (vals.get("InstallLocation") or "").strip().strip('"')
    return _exe_in(Path(loc)) if loc else None


def _drives() -> list[Path]:
    """I dischi fissi (niente lettori ottici, USB o unita' di rete)."""
    if sys.platform != "win32":
        return []
    import ctypes
    import string
    out = []
    for letter in string.ascii_uppercase:
        d = Path(f"{letter}:\\")
        try:
            if ctypes.windll.kernel32.GetDriveTypeW(str(d)) == 3:  # DRIVE_FIXED
                out.append(d)
        except OSError:
            continue
    return out


def _roots() -> list[Path]:
    return [r for d in _drives() for r in (d / "Program Files", d / "Program Files (x86)", d) if r.is_dir()]


def _listing() -> set[str]:
    """Cartelle di primo livello dove un repack puo' finire (una per gioco)."""
    out = set()
    for root in _roots():
        try:
            out.update(str(p) for p in root.iterdir() if p.is_dir())
        except OSError:  # disco scollegato o cartella non leggibile
            continue
    return out


def _exe_in(folder: Path) -> Path | None:
    """L'eseguibile del gioco: il più grande, esclusi disinstallatori, redistributable e launcher di setup.
    shortcut: scansione ricorsiva senza limite di profondità, qualche secondo sulle cartelle enormi; da fermare
    prima (profondità massima) se diventa fastidiosa."""
    if not folder.is_dir():
        return None
    best = None
    try:
        for f in folder.rglob("*.exe"):
            if _SKIP.search(f.name):
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            if best is None or size > best[0]:
                best = (size, f)
    except OSError:  # cartella che sparisce mentre la si legge
        return best[1] if best else None
    return best[1] if best else None
