"""Rileva gli emulatori gia' installati fuori dalla cartella degli emulatori: Program Files, Scoop, Winget,
librerie Steam, registro di Windows. Non modifica nulla: restituisce {emulatore: {path, source}}."""

from __future__ import annotations

import fnmatch
import os
import sys
import time
from pathlib import Path

from .library.launcher import KNOWN_EXES, detect_emulators

try:
    if sys.platform != "win32":
        raise ImportError
    import winreg
except ImportError:  # non-Windows
    winreg = None

_UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
_APPPATHS = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"


def _match(emu: str, name: str) -> bool:
    return any(fnmatch.fnmatch(name.lower(), p) for p in KNOWN_EXES[emu])


def _roots() -> list[tuple[Path, str, int]]:
    """(cartella, origine, profondita'). Le sottocartelle di Program Files sono una per programma: bastano 3 livelli."""
    env, home = os.environ.get, Path.home()
    out = [(Path(p), "program-files", 3) for p in (env("ProgramFiles"), env("ProgramFiles(x86)")) if p]
    if env("LOCALAPPDATA"):
        la = Path(env("LOCALAPPDATA"))
        out += [(la / "Programs", "localappdata", 3), (la / "Microsoft" / "WinGet" / "Packages", "winget", 3)]
    scoop = Path(env("SCOOP") or home / "scoop")
    try:
        out += [(a / "current", "scoop", 2) for a in (scoop / "apps").iterdir()]
    except OSError:
        pass
    out.append((scoop / "shims", "scoop", 1))
    return out


def _steam_roots(cfg, libs: list[Path] | None) -> list[tuple[Path, str, int]]:
    if libs is None:
        try:
            from .stores.steam import Steam  # noqa: PLC0415
            libs = Steam(cfg, None, None, None).libraries() if cfg is not None else []
        except Exception:  # noqa: BLE001 - Steam assente o config incompleta
            libs = []
    return [(lib / "steamapps" / "common", "steam", 3) for lib in libs]


def _registry() -> list[tuple[str, str]]:
    """(cartella o eseguibile, origine) dalle chiavi Uninstall e App Paths."""
    if winreg is None:
        return []
    out = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for base, fields in ((_UNINSTALL, ("InstallLocation", "DisplayIcon")), (_APPPATHS, ("", "Path"))):
            for view in (0, getattr(winreg, "KEY_WOW64_32KEY", 0)):
                try:
                    with winreg.OpenKey(hive, base, 0, winreg.KEY_READ | view) as k:
                        subs = [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
                        for s in subs:
                            try:
                                with winreg.OpenKey(k, s) as sk:
                                    for f in fields:
                                        try:
                                            v = str(winreg.QueryValueEx(sk, f)[0]).split(",")[0].strip('" ')
                                        except OSError:
                                            continue
                                        if v:
                                            out.append((v, "registry"))
                            except OSError:
                                pass
                except OSError:
                    pass
    return out


def detect_all(cfg=None, extra_roots=None, steam_libs: list[Path] | None = None, registry=None, budget: float = 20.0) -> dict[str, dict]:
    """{emulatore: {path, source}}: il primo trovato vince. `budget` = secondi massimi di scansione."""
    found: dict[str, dict] = {}
    end = time.monotonic() + budget

    def add(emu: str, path: str, source: str):
        if emu not in found and Path(path).is_file():
            found[emu] = {"path": str(path), "source": source}

    for root, source, depth in [*_roots(), *_steam_roots(cfg, steam_libs), *(extra_roots or [])]:
        if time.monotonic() > end:
            break
        try:
            for emu, p in detect_emulators(root, max_depth=depth).items():
                add(emu, p, source)
        except OSError:
            continue
    for v, source in (registry() if registry else _registry()):
        p = Path(v)
        try:
            if p.is_file():
                for emu in KNOWN_EXES:
                    if _match(emu, p.name):
                        add(emu, str(p), source)
            elif p.is_dir() and any(emu in str(p).lower() for emu in KNOWN_EXES):  # senza filtro: centinaia di programmi
                for emu, e in detect_emulators(p, max_depth=2).items():
                    add(emu, e, source)
        except OSError:
            continue
        if time.monotonic() > end:
            break
    return found
