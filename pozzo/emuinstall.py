"""Installazione degli emulatori (e dei core di RetroArch) dalle loro release ufficiali, dalle impostazioni.

Gli emulatori sono dei rispettivi sviluppatori: Pozzo scarica le build che pubblicano loro, cosi' come sono, e
mostra il link al progetto. La versione si legge dalle release GitHub del progetto; chi non pubblica i file su
GitHub (RetroArch, Dolphin, PPSSPP) ha l'indirizzo del download costruito dalla versione, sul sito ufficiale.

Ogni emulatore va in <cartella>\\<id>. Un aggiornamento copia i file nuovi sopra quelli vecchi: la configurazione
e i dati dell'utente nella cartella (modalita' portatile) restano. Prima dell'aggiornamento la cartella viene
copiata in <id>.bak (una sola copia): se l'installazione fallisce o manca l'eseguibile viene rimessa a posto, e
rollback() la ripristina a mano. Le versioni installate e l'ultima nota (cache 12 ore) stanno in versions.json.
Windows, macOS (il bundle .app, da .dmg/.zip/.tar.xz/.7z) e Linux (AppImage), ciascuno su x64 e su ARM64: si
scarica solo la build per il processore della macchina (ARCH); un emulatore senza quella build resta bloccato.
"""

from __future__ import annotations

import json
import os
import re
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

from . import config as C
from . import platforms as P
from . import ports as PT
from .library import launcher as L

# id di launcher.py -> repository GitHub e filtro sul nome del file della release, oppure "url" costruito dalla
# versione ({ver} = tag senza «v», {ver_} = con i punti cambiati in «_»); "tags": versione dai tag, non dalle release.
# shortcut: nomi dei file scritti a mano, da correggere se un progetto li cambia (l'errore lo dice).
_WINDOWS: dict[str, dict] = {
    "retroarch": {"repo": "libretro/RetroArch", "home": "https://www.retroarch.com",
                  "url": "https://buildbot.libretro.com/stable/{ver}/windows/x86_64/RetroArch.7z"},
    "dolphin": {"repo": "dolphin-emu/dolphin", "home": "https://dolphin-emu.org", "tags": r"\d{4}[a-z]?",
                "url": "https://dl.dolphin-emu.org/releases/{ver}/dolphin-{ver}-x64.7z"},
    "ppsspp": {"repo": "hrydgard/ppsspp", "home": "https://www.ppsspp.org",
               "url": "https://www.ppsspp.org/files/{ver_}/ppsspp_win.zip"},
    "duckstation": {"repo": "stenzek/duckstation", "filter": "windows-x64-release"},
    "pcsx2": {"repo": "PCSX2/pcsx2", "filter": "windows-x64-qt"},
    "rpcs3": {"repo": "RPCS3/rpcs3-binaries-win", "home": "https://rpcs3.net", "filter": "win64"},
    "vita3k": {"repo": "Vita3K/Vita3K", "filter": "windows"},
    "melonds": {"repo": "melonDS-emu/melonDS", "filter": "windows"},
    "azahar": {"repo": "azahar-emu/azahar", "filter": "windows-msvc"},
    "cemu": {"repo": "cemu-project/Cemu", "filter": "windows-x64"},
    "xenia": {"repo": "xenia-canary/xenia-canary-releases", "home": "https://xenia.jp"},
    "xemu": {"repo": "xemu-project/xemu", "filter": "release"},
    "flycast": {"repo": "flyinghead/flycast", "filter": "win64"},
    "shadps4": {"repo": "shadps4-emu/shadPS4", "filter": "win64"},
    "mgba": {"repo": "mgba-emu/mgba", "home": "https://mgba.io", "filter": "win64"},
    "mesen": {"repo": "SourMesen/Mesen2", "home": "https://www.mesen.ca", "filter": "windows"},
    "dosbox-staging": {"repo": "dosbox-staging/dosbox-staging", "home": "https://www.dosbox-staging.org", "filter": "windows-x64"},
    "rmg": {"repo": "Rosalie241/RMG", "home": "https://github.com/Rosalie241/RMG", "filter": "portable-windows64"},
    # Switch: Eden e Ryujinx (fork Ryubing) pubblicano su Forgejo, non su GitHub
    "eden": {"repo": "eden-emu/eden", "api": "https://git.eden-emu.dev/api/v1", "home": "https://eden-emu.dev",
             "filter": "msvc-standard"},
    "ryujinx": {"repo": "ryubing/ryujinx", "api": "https://git.ryujinx.app/api/v1", "home": "https://ryujinx.app",
                "filter": "win_x64"},
    # Switch 2: fork di Eden su Forgejo, pubblica solo pre-release (lo zip non dice «windows» nel nome)
    "eglantine": {"repo": "Franseven/PokeDinner-a-Eglantine-Fork", "api": "https://git.eden-emu.dev/api/v1",
                  "home": "https://git.eden-emu.dev/Franseven/PokeDinner-a-Eglantine-Fork", "prerelease": True},
}
# macOS e Linux: cosa cambia rispetto a Windows. "asset" = regex sul nome del file della release (debug, core
# libretro e .zsync gia' esclusi), "url": None = file dalle release GitHub invece del sito. Chi manca qui non ha una
# build per quel sistema: non compare nel catalogo e il consiglio «un clic» lo dice non installabile.
# shortcut: nomi verificati a mano (novembre 2026), da correggere se un progetto li cambia (l'errore lo dice).


def _native_arch() -> str:
    """"x64" o "arm64" della macchina, non del processo: Pozzo x64 sotto Rosetta o sotto l'emulazione di Windows
    ARM deve comunque scegliere gli emulatori nativi (girano come programmi a parte)."""
    m = platform.machine().lower()
    if sys.platform == "darwin" and m == "x86_64":
        try:
            r = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"], capture_output=True, text=True, timeout=3)
            return "arm64" if r.stdout.strip() == "1" else "x64"
        except Exception:  # noqa: BLE001 - sysctl assente: vale il processo
            return "x64"
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            proc, native = ctypes.c_ushort(), ctypes.c_ushort()
            if k.IsWow64Process2(k.GetCurrentProcess(), ctypes.byref(proc), ctypes.byref(native)):
                return "arm64" if native.value == 0xAA64 else "x64"  # IMAGE_FILE_MACHINE_ARM64
        except Exception:  # noqa: BLE001 - Windows 10 prima della 1709: niente IsWow64Process2
            pass
    return "arm64" if m in ("arm64", "aarch64") else "x64"


ARCH = _native_arch()
_MAC_ARCH = "x86_64" if ARCH == "x64" else "arm64"
_POSIX: dict[str, dict[str, dict]] = {
    "darwin": {
        "retroarch": {"url": "https://buildbot.libretro.com/stable/{ver}/apple/osx/universal/RetroArch_Metal.dmg"},
        "dolphin": {"url": "https://dl.dolphin-emu.org/releases/{ver}/dolphin-{ver}-universal.dmg"},
        "ppsspp": {"url": None, "asset": r"-macos-.*\.zip$"},
        "duckstation": {"asset": r"-mac-release\.zip$"},
        "pcsx2": {"asset": r"-macos-qt\.tar\.xz$"},
        # i repo rpcs3-binaries elencano le release fuori ordine: solo /releases/latest e' affidabile
        "rpcs3": {"repo": "RPCS3/rpcs3-binaries-mac-arm64", "asset": r"_macos_(arm64|aarch64)\.7z$", "latest": True},
        "vita3k": {"asset": r"^macos-arm64-latest\.dmg$"},
        "melonds": {"asset": r"-macos-universal\.zip$"},
        "azahar": {"asset": r"^azahar-macos-universal-.*\.zip$"},
        "cemu": {"asset": r"-macos-.*\.dmg$"},  # solo x64: gira con Rosetta
        "xemu": {"asset": r"-macos-universal(-unsigned)?\.zip$"},
        "flycast": {"asset": r"-macos-.*\.zip$"},
        "shadps4": {"asset": r"-macos-sdl-.*\.zip$"},
        "eglantine": {"asset": r"-macos-arm64-.*\.zip$"},
        "eden": {"asset": r"-macos-.*\.dmg$"},
        # OpenEmu: frontend con i suoi core (NES, SNES, Mega Drive, Saturn, PS1, PSP...); solo macOS
        "openemu": {"repo": "OpenEmu/OpenEmu", "home": "https://openemu.org", "asset": r"^OpenEmu_[\d.]+\.zip$"},
        "mgba": {"asset": r"-macos\.dmg$"},
        "mesen": {"asset": r"_macos_" + ("x64_intel" if _MAC_ARCH == "x86_64" else "arm64_applesilicon") + r"\.zip$"},
        "dosbox-staging": {"asset": r"-macos-v[\d.]+\.dmg$"},
        "ryujinx": {"asset": r"-macos_universal\.app\.tar\.gz$"},
    },
    "linux": {  # Dolphin e Xenia non pubblicano build Linux pronte
        "retroarch": {"url": "https://buildbot.libretro.com/stable/{ver}/linux/x86_64/RetroArch.7z"},
        "ppsspp": {"url": None, "asset": r"-anylinux-x86_64\.appimage$"},
        "duckstation": {"asset": r"^duckstation-x64\.appimage$"},
        "pcsx2": {"asset": r"-linux-appimage-x64-qt\.appimage$"},
        "rpcs3": {"repo": "RPCS3/rpcs3-binaries-linux", "asset": r"_linux64\.appimage$", "latest": True},
        "vita3k": {"asset": r"^vita3k-x86_64\.appimage$"},
        "melonds": {"asset": r"-appimage-x86_64\.zip$"},
        "azahar": {"asset": r"^azahar.*\.appimage$"},
        "cemu": {"asset": r"-x86_64\.appimage$"},
        "xemu": {"asset": r"-x86_64\.appimage$"},
        "flycast": {"asset": r"-x86_64.*\.appimage$"},
        "shadps4": {"asset": r"-linux-sdl-.*\.zip$"},  # dentro c'e' l'AppImage
        "eglantine": {"asset": r"-linux-x86_64\.appimage$"},
        "eden": {"asset": r"-amd64-gcc-standard\.appimage$"},
        "mgba": {"asset": r"-appimage-x64\.appimage$"},
        "mesen": {"asset": r"_linux_x64\.zip$"},
        "dosbox-staging": {"asset": r"-linux-x86_64-v[\d.]+\.tar\.xz$"},
        "rmg": {"asset": r"portable-linux64.*\.appimage$"},
        "ryujinx": {"asset": r"-x64\.appimage$"},
    },
}
# Le tabelle sopra sono Windows x64, macOS Apple Silicon (con le build universali) e Linux x86_64. Qui cosa cambia
# per l'altro processore: None = nessuna build, emulatore bloccato. Windows e Linux ARM64 non ereditano nulla (una
# build x86_64 li' non parte o va emulata): ci sono solo gli emulatori elencati. macOS Intel eredita (quasi tutte
# universali). Cemu e shadPS4 su Apple Silicon restano x64: girano con Rosetta, che macOS installa da solo.
# shortcut: nomi verificati sulle release di novembre 2026, da correggere se un progetto li cambia (l'errore lo dice).
_ARCH_DIFF: dict[tuple[str, str], dict[str, dict | None]] = {
    ("win32", "arm64"): {  # niente build ARM64: RetroArch, PCSX2, RPCS3, Cemu, Xenia, Azahar, Flycast, shadPS4, mGBA...
        "dolphin": {"url": "https://dl.dolphin-emu.org/releases/{ver}/dolphin-{ver}-arm64.7z"},
        "ppsspp": {"url": None, "asset": r"-windows-arm64\.zip$"},
        "duckstation": {"asset": r"^duckstation-windows-arm64-release\.zip$"},
        "vita3k": {"asset": r"^windows-arm64-latest\.zip$"},
        "melonds": {"asset": r"-windows-aarch64\.zip$"},
        "xemu": {"asset": r"^xemu-win-aarch64-release\.zip$"},
        "eden": {"asset": r"-arm64-clang-standard\.zip$"},
    },
    ("linux", "arm64"): {  # RetroArch: il buildbot non ha build stabili ARM64 (si installa dalla distribuzione)
        "ppsspp": {"url": None, "asset": r"-anylinux-aarch64\.appimage$"},
        "duckstation": {"asset": r"^duckstation-arm64\.appimage$"},
        "rpcs3": {"repo": "RPCS3/rpcs3-binaries-linux-arm64", "asset": r"_linux_aarch64\.appimage$", "latest": True},
        "vita3k": {"asset": r"^vita3k-aarch64\.appimage$"},
        "melonds": {"asset": r"-appimage-aarch64\.zip$"},
        "xemu": {"asset": r"-aarch64\.appimage$"},
        "eden": {"asset": r"-aarch64-gcc-standard\.appimage$"},
        "mgba": {"asset": r"-appimage-arm64\.appimage$"},
        "mesen": {"asset": r"_linux_arm64\.zip$"},
        "ryujinx": {"asset": r"-arm64\.appimage$"},
    },
    ("darwin", "x64"): {
        "rpcs3": {"repo": "RPCS3/rpcs3-binaries-mac", "asset": r"_macos\.7z$", "latest": True},
        "vita3k": {"asset": r"^macos-latest\.dmg$"},
        "eden": None,  # solo Apple Silicon
        "eglantine": None,
    },
}
_NO_INHERIT = {("win32", "arm64"), ("linux", "arm64")}
_NOT_APP = re.compile(r"dbg|debug|libretro|\.zsync$|\.sha256$", re.I)


def _merge(e: str, o: dict) -> dict:
    """Voce di Windows con le differenze o (None toglie la chiave; "filter" vale solo per i nomi di Windows)."""
    return {k: v for k, v in {**_WINDOWS.get(e, {}), "filter": None, **o}.items() if v is not None}


def _for_os(plat: str, arch: str | None = None) -> dict[str, dict]:
    """SOURCES per un sistema: Windows cosi' com'e', gli altri = Windows + le differenze di _POSIX; con arch, solo
    gli emulatori che hanno una build per quel processore (vedi _ARCH_DIFF)."""
    base = _WINDOWS if plat == "win32" else {e: _merge(e, o) for e, o in _POSIX.get(plat, {}).items()}
    diff = _ARCH_DIFF.get((plat, arch))
    if diff is None:
        return base
    out = {} if (plat, arch) in _NO_INHERIT else dict(base)
    for e, o in diff.items():
        if o is None:
            out.pop(e, None)
        else:
            out[e] = _merge(e, o)
    return out


SOURCES = _for_os(sys.platform, ARCH)
KNOWN = _for_os(sys.platform)  # tutti gli emulatori del sistema, anche quelli senza build per questo processore
CHECK_TTL = 12 * 3600
# core di RetroArch per (sistema, processore); manca = il buildbot non li ha (Windows ARM64)
CORES_URL = {("win32", "x64"): "https://buildbot.libretro.com/nightly/windows/x86_64/latest/{core}_libretro.dll.zip",
             ("darwin", "x64"): "https://buildbot.libretro.com/nightly/apple/osx/x86_64/latest/{core}_libretro.dylib.zip",
             ("darwin", "arm64"): "https://buildbot.libretro.com/nightly/apple/osx/arm64/latest/{core}_libretro.dylib.zip",
             ("linux", "x64"): "https://buildbot.libretro.com/nightly/linux/x86_64/latest/{core}_libretro.so.zip",
             ("linux", "arm64"): "https://buildbot.libretro.com/nightly/linux/aarch64/latest/{core}_libretro.so.zip"}
_OS = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
ARCH_NAME = {"x64": "x64", "arm64": "ARM64"}


def arch_blocked(emu: str) -> bool:
    """L'emulatore esiste per questo sistema ma non per questo processore."""
    return emu in KNOWN and emu not in SOURCES
_run = subprocess.run  # sostituibile nei test (hdiutil, ditto, xattr)


class EmulatorRunning(RuntimeError):
    """L'emulatore e' aperto: non si aggiorna ne' si ripristina (si riprova piu' tardi)."""


def emus_dir(cfg) -> Path:
    return Path(cfg.app.get("emulators_dir") or C.settings_path(cfg).parent / "Emulatori")


def installed(cfg) -> dict[str, dict]:
    """{emulatore: {"version", "dir"}} installati da qui (finche' l'eseguibile configurato esiste)."""
    return {e: v for e, v in (cfg.app.get("emu_installed") or {}).items()
            if cfg.emulators.get(e) and Path(cfg.emulators[e]).exists()}


def catalog(cfg) -> list[dict]:
    names = {p.id: p.name for p in P.PLATFORMS.values()}
    inst = installed(cfg)
    # anche gli emulatori senza build per questo processore: compaiono, ma con arch_ok False (pulsante bloccato)
    return [{"id": e, "repo": s["repo"], "home": s.get("home") or f"https://github.com/{s['repo']}",
             "consoles": [names.get(pid, pid) for pid, c in L.PRESETS.items() if any(x == e for x, _ in c)],
             "version": (inst.get(e) or {}).get("version") or "", "configured": bool(cfg.emulators.get(e)),
             "arch_ok": e in SOURCES}
            for e, s in {**KNOWN, **SOURCES}.items()]


def _latest(cfg, src: dict) -> tuple[str, dict]:
    """(versione, file da scaricare {"name", "url", "sum"?}) dell'ultima release per questo sistema."""
    tok = PT._token(cfg)
    if src.get("latest"):
        j = PT._get(f"https://api.github.com/repos/{src['repo']}/releases/latest", None, tok)
        a = _pick_asset([{"name": x.get("name") or "", "url": x.get("browser_download_url"),
                          "sum": (x.get("digest") or "").removeprefix("sha256:").lower()} for x in j.get("assets") or []], src)
        if not a:
            raise RuntimeError(f"nessun file per {_OS} nell'ultima release di {src['repo']}")
        return j.get("tag_name") or "", a
    if src.get("tags"):
        tags = [t["name"] for t in PT._get(f"https://api.github.com/repos/{src['repo']}/tags", {"per_page": 100}, tok)
                if re.fullmatch(src["tags"], t.get("name") or "")]
        if not tags:
            raise RuntimeError(f"nessuna versione trovata nei tag di {src['repo']}")
        tag = max(tags)
    else:
        rels = PT.releases(src.get("api") or "github", src["repo"], tok)
        if src.get("prerelease"):  # voluto: l'ultima pre-release, non l'ultima stabile
            rels = [r for r in rels if r["prerelease"]] or rels
            for r in rels:
                a = _pick_asset(r["assets"], src)
                if a:
                    return r["tag"], a
            raise RuntimeError(f"nessun file per {_OS} nelle release di {src['repo']}")
        if src.get("url"):
            tag = next((r["tag"] for r in rels if not r["prerelease"]), "")
            if not tag:
                raise RuntimeError(f"nessuna release stabile di {src['repo']}")
        else:
            got = _pick_release(rels, src)
            if not got:
                raise RuntimeError(f"nessun file per {_OS} nelle release di {src['repo']}")
            return got[0]["tag"], got[1]
    ver = tag.lstrip("vV")
    url = src["url"].format(ver=ver, ver_=ver.replace(".", "_"))
    return tag, {"name": url.rsplit("/", 1)[-1], "url": url}


def _pick_asset(assets: list[dict], src: dict) -> dict | None:
    if "asset" not in src:
        return PT.pick_asset(assets, src.get("filter") or "")
    c = [a for a in assets if re.search(src["asset"], a["name"], re.I) and not _NOT_APP.search(a["name"])]
    return min(c, key=lambda a: len(a["name"])) if c else None  # il nome piu' corto e' la variante «normale»


def _pick_release(rels: list[dict], src: dict) -> tuple[dict, dict] | None:
    """Come PT.pick_release (prima l'ultima stabile), con la scelta del file di questo sistema."""
    if "asset" not in src:
        return PT.pick_release(rels, src.get("filter") or "")
    for stable in (True, False):
        for r in rels:
            if not (stable and r["prerelease"]) and (a := _pick_asset(r["assets"], src)):
                return r, a
    return None


def _unpack(arc: Path, out: Path, name: str) -> None:
    """macOS/Linux: estrae tenendo link simbolici e permessi (un .app senza i suoi link non parte)."""
    n = name.lower()
    out.mkdir(parents=True)
    if n.endswith(".dmg"):
        mnt = out.with_name("mnt")
        mnt.mkdir()
        _run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mnt), str(arc)], check=True,
             capture_output=True)
        try:
            apps = [a for a in mnt.iterdir() if a.suffix == ".app" and not a.is_symlink()]
            if not apps:
                raise RuntimeError(f"nessuna app dentro {name}")
            for a in apps:
                _run(["ditto", str(a), str(out / a.name)], check=True, capture_output=True)
        finally:
            if _run(["hdiutil", "detach", str(mnt)], capture_output=True).returncode:
                _run(["hdiutil", "detach", "-force", str(mnt)], capture_output=True)
    elif n.endswith(".zip") and sys.platform == "darwin":
        _run(["ditto", "-x", "-k", str(arc), str(out)], check=True, capture_output=True)
    elif n.endswith(".7z"):
        import py7zr
        with py7zr.SevenZipFile(arc) as z:
            z.extractall(out)
    elif re.search(r"\.tar(\.\w+)?$|\.tgz$", n):
        with tarfile.open(arc) as t:
            t.extractall(out, filter="data")
    elif n.endswith(".zip"):  # Linux: dentro c'e' l'AppImage, i permessi si rimettono sotto
        with zipfile.ZipFile(arc) as z:
            z.extractall(out)
    else:  # AppImage
        shutil.copy2(arc, out / Path(name).name)
    root = out.resolve()
    for f in out.rglob("*"):
        if f.is_symlink() and not f.resolve().is_relative_to(root):
            raise RuntimeError(f"collegamento fuori dalla cartella in {name}: {f.name}")
        if f.suffix.lower() == ".appimage" and f.is_file():
            f.chmod(0o755)


def _find_exe(dest: Path, emu: str) -> str | None:
    """Eseguibile da avviare: quello noto, altrimenti il binario del primo .app (macOS) o la prima AppImage."""
    exe = L.detect_emulators(dest).get(emu)
    if exe or sys.platform == "win32":
        return exe
    for app in sorted(dest.glob("*.app")) + sorted(dest.glob("*/*.app")):
        if b := L.app_binary(app):
            return str(b)
    return next((str(f) for f in sorted(dest.glob("*.AppImage")) + sorted(dest.glob("*/*.AppImage"))), None)


def _stage(cfg, asset: dict, name: str, progress=None) -> Path:
    """Scarica ed estrae in una cartella temporanea (rifiuta il file se il checksum della release non torna)."""
    # GitHub calcola il digest di ogni asset: se manca qualcosa non torna. Le altre fonti (sito del progetto,
    # GitLab, Codeberg) non lo pubblicano: si installa lo stesso e install() lo dice nel log.
    if not asset.get("sum") and "sum" in asset and asset["url"].startswith("https://github.com/"):
        raise RuntimeError("la release GitHub non ha il checksum del file: download rifiutato")
    work = emus_dir(cfg) / ".tmp" / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    arc = work / ("download" + "".join(Path(asset["name"]).suffixes[-1:]))
    try:
        PT._download(asset["url"], arc, progress, PT._token(cfg))
        if asset.get("sum") and PT._sha256(arc) != asset["sum"]:
            raise RuntimeError("il file scaricato non corrisponde al checksum della release: download rifiutato")
        if sys.platform == "win32":
            PT._extract(arc, work / "files", asset["name"])
        else:
            _unpack(arc, work / "files", asset["name"])
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    arc.unlink()
    return work / "files"


def _bak(dest: Path) -> Path:
    return dest.with_name(dest.name + ".bak")


def _vfile(cfg) -> Path:
    return emus_dir(cfg) / "versions.json"


def _vload(cfg) -> dict:
    try:
        d = json.loads(_vfile(cfg).read_text("utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _vsave(cfg, change) -> None:
    """{"installed": {emu: tag}, "latest": {emu: {"tag", "t"}}} in <emulatori>/versions.json."""
    d = _vload(cfg)
    change(d)
    f = _vfile(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d), "utf-8")


def rollback(emu_id: str, cfg) -> str:
    """Rimette la versione precedente (cartella .bak lasciata dall'ultimo aggiornamento); ritorna l'eseguibile."""
    prev = installed(cfg).get(emu_id) or {}
    if not prev.get("dir"):
        raise RuntimeError(f"{emu_id} non e' installato da Pozzo")
    dest = Path(prev["dir"])
    bak = _bak(dest)
    if not bak.is_dir():
        raise RuntimeError(f"nessuna versione precedente di {emu_id} da ripristinare")
    if dest.exists() and PT._running(dest):
        raise EmulatorRunning(f"chiudi {emu_id} prima del ripristino")
    shutil.rmtree(dest, ignore_errors=True)
    bak.rename(dest)
    exe = _find_exe(dest, emu_id)
    if not exe:
        raise RuntimeError(f"ripristinato in {dest}, ma non trovo l'eseguibile di {emu_id}")
    _vsave(cfg, lambda d: d.setdefault("installed", {}).pop(emu_id, None))  # versione ora ignota
    C.save_settings(cfg, emulators={emu_id: exe},
                    app={"emu_installed": {**(cfg.app.get("emu_installed") or {}), emu_id: {"version": "", "dir": str(dest)}}})
    return exe


# Dati dell'utente: voci dentro la cartella dell'emulatore (modalita' portatile) e cartella in %APPDATA%
# (su macOS/Linux la cartella che usa l'emulatore, vedi _appdata).
_USER_ENTRIES = {"portable", "portable.txt", "portable.ini", "user", "config", "saves", "sstates", "states",
                 "memcards", "dev_hdd0", "cache", "shaders", "gameprofiles", "games", "sys", "bis", "profiles",
                 "memstick", "savestates", "system", "bios", "inis"}
APPDATA_DIRS = {"ryujinx": "Ryujinx", "eden": "eden", "eglantine": "eden", "cemu": "Cemu", "dolphin": "Dolphin Emulator",
                "duckstation": "DuckStation", "pcsx2": "PCSX2", "ppsspp": "PPSSPP", "melonds": "melonDS"}
# file/cartella che fa leggere i dati accanto all'eseguibile: (nome, e' cartella)
PORTABLE = {"dolphin": ("portable.txt", False), "duckstation": ("portable.txt", False), "pcsx2": ("portable.ini", False),
            "ryujinx": ("portable", True), "cemu": ("portable", True), "eden": ("user", True), "eglantine": ("user", True),
            "ppsspp": ("memstick", True), "melonds": ("portable.txt", False)}
_USER_ENTRIES |= {n.lower() for n, _ in PORTABLE.values()}  # i marcatori della modalita' portatile sono dati dell'utente


def _appdata(emu_id: str) -> Path | None:
    """Cartella dei dati dell'utente fuori dalla cartella dell'emulatore (None = non nota)."""
    name = APPDATA_DIRS.get(emu_id)
    if not name:
        return None
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / name if os.environ.get("APPDATA") else None
    from .emuadapters import cemu, dolphin, duckstation, eden, pcsx2
    known = {"dolphin": lambda: dolphin._user_dir(None), "duckstation": lambda: duckstation._data_root(None),
             "pcsx2": lambda: pcsx2._data_root(None), "cemu": lambda: cemu._base(None),
             "eden": lambda: eden._base(None), "eglantine": lambda: eden._base(None)}
    if emu_id in known:
        return known[emu_id]()
    if sys.platform == "darwin":  # shortcut: PPSSPP/melonDS/Ryujinx su macOS non verificati dai sorgenti
        return Path.home() / "Library" / "Application Support" / name
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    return (Path(xdg) if os.path.isabs(xdg) else Path.home() / ".config") / (name.lower() if emu_id == "ppsspp" else name)


def uninstall(cfg, emu_id: str, keep_data: bool = True) -> None:
    """Toglie un emulatore installato da Pozzo. keep_data=True lascia config, salvataggi e shader cache
    (dentro la cartella o in %APPDATA%); False cancella anche quelli."""
    prev = installed(cfg).get(emu_id) or {}
    if not prev.get("dir"):
        raise RuntimeError(f"{emu_id} non e' installato da Pozzo")
    dest = Path(prev["dir"])
    if dest.exists() and PT._running(dest):
        raise EmulatorRunning(f"chiudi {emu_id} prima di disinstallarlo")
    shutil.rmtree(_bak(dest), ignore_errors=True)
    if keep_data and dest.is_dir():  # via tutto tranne i dati dell'utente
        for f in dest.iterdir():
            if f.name.lower() not in _USER_ENTRIES:
                shutil.rmtree(f, ignore_errors=True) if f.is_dir() else f.unlink(missing_ok=True)
        if not any(dest.iterdir()):
            dest.rmdir()
    else:
        shutil.rmtree(dest, ignore_errors=True)
        if APPDATA_DIRS.get(emu_id):
            appdata = _appdata(emu_id)
            # cartella condivisa con un altro emulatore installato (eden/eglantine): resta
            shared = any(APPDATA_DIRS.get(o) == APPDATA_DIRS[emu_id] for o in installed(cfg) if o != emu_id)
            if appdata and not shared:
                shutil.rmtree(appdata, ignore_errors=True)
    # emu_installed si riscrive intero (save_settings non unisce i dict annidati): gli altri emulatori restano
    rest = {k: v for k, v in (cfg.app.get("emu_installed") or {}).items() if k != emu_id}
    C.save_settings(cfg, emulators={emu_id: None}, app={"emu_installed": rest or None})  # None = rimuovi
    _vsave(cfg, lambda d: d.setdefault("installed", {}).pop(emu_id, None))


def make_portable(cfg, emu_id: str) -> Path:
    """Dati accanto all'eseguibile (backup e spostamento facili): crea il marcatore che l'emulatore riconosce.
    I dati gia' in %APPDATA% si copiano (non si spostano) nella nuova cartella. Ritorna il marcatore."""
    exe, spec = cfg.emulators.get(emu_id), PORTABLE.get(emu_id)
    if not spec or sys.platform == "darwin":  # macOS: il marcatore finirebbe dentro il .app e ne romperebbe la firma
        raise ValueError(f"{emu_id} non ha una modalita' portatile")
    if not exe or not Path(exe).exists():
        raise RuntimeError(f"{emu_id} non e' installato")
    if PT._running(Path(exe).parent):
        raise EmulatorRunning(f"chiudi {emu_id} prima di renderlo portatile")
    name, is_dir = spec
    mark = Path(exe).parent / name
    old = _appdata(emu_id)
    if is_dir:
        if old and old.is_dir() and not mark.exists():
            shutil.copytree(old, mark)
        mark.mkdir(exist_ok=True)
    else:
        mark.touch()
    return mark


def check_updates(cfg) -> list[dict]:
    """[{"id","name","current","latest","update"}] per gli emulatori installati da qui; "current" vuoto = ignota.
    Errori di rete: emulatore saltato. L'ultima versione e' in cache 12 ore (anti rate limit di GitHub)."""
    now, out = time.time(), []
    for emu, info in installed(cfg).items():
        src = SOURCES.get(emu)
        if not src:
            continue
        hit = (_vload(cfg).get("latest") or {}).get(emu) or {}
        if now - hit.get("t", 0) < CHECK_TTL and hit.get("tag"):
            latest = hit["tag"]
        else:
            try:
                latest = _latest(cfg, src)[0]
            except Exception:  # noqa: BLE001 - rete/rate limit: salta
                continue
            _vsave(cfg, lambda d: d.setdefault("latest", {}).__setitem__(emu, {"tag": latest, "t": now}))
        cur = (_vload(cfg).get("installed") or {}).get(emu) or info.get("version") or ""
        out.append({"id": emu, "name": emu, "current": cur, "latest": latest, "update": bool(cur) and cur != latest})
    return out


def install(cfg, emu: str, folder: str = "", progress=None, say=print) -> str:
    """Installa (o aggiorna) un emulatore all'ultima versione e lo imposta; ritorna il percorso dell'eseguibile."""
    src = SOURCES.get(emu)
    prev = installed(cfg).get(emu) or {}
    cur = cfg.emulators.get(emu)
    if not prev and cur and Path(cur).is_file():  # gia' presente (anche installato altrove, o senza build per questo OS)
        say(f"{emu} e' gia' installato: {cur}")
        return cur
    if not src:
        if arch_blocked(emu):
            raise ValueError(f"{emu} non ha una build per {_OS} {ARCH_NAME[ARCH]}: installane una versione a mano, se esiste")
        raise ValueError(f"emulatore sconosciuto: {emu}")
    say(f"Cerco l'ultima versione di {emu} ({src['repo']})…")
    tag, asset = _latest(cfg, src)
    if prev.get("version") == tag:
        say(f"{emu} e' gia' all'ultima versione ({tag})")
        return cfg.emulators[emu]
    dest = Path(prev.get("dir") or Path(folder or emus_dir(cfg)) / emu)
    if dest.exists() and PT._running(dest):
        raise EmulatorRunning(f"chiudi {emu} prima di aggiornarlo")
    say(f"Scarico {asset['name']}…")
    if not asset.get("sum"):
        say(f"Attenzione: la fonte non pubblica un checksum di {asset['name']}, file non verificato")
    staged = _stage(cfg, asset, emu, progress)  # se fallisce, la cartella vecchia non e' stata toccata
    bak = _bak(dest)
    had, backed = dest.exists(), False
    links = sys.platform != "win32"  # i .app hanno link simbolici: si copiano come link
    try:
        if had:  # copia (non sposta): la cartella ha configurazione e salvataggi dell'utente
            shutil.rmtree(bak, ignore_errors=True)
            shutil.copytree(dest, bak, symlinks=links)
            backed = True  # solo una copia completa puo' sostituire la cartella in caso di errore
            if links:  # .app/AppImage vecchi via interi: file misti di due versioni rompono la firma del bundle
                for f in [*dest.glob("*.app"), *dest.glob("*.AppImage")]:
                    shutil.rmtree(f) if f.is_dir() and not f.is_symlink() else f.unlink()
        shutil.copytree(staged, dest, dirs_exist_ok=True, symlinks=links)  # sopra la versione vecchia: i file dell'utente restano
        if sys.platform == "darwin":  # niente avviso «scaricata da Internet» al primo avvio
            _run(["xattr", "-dr", "com.apple.quarantine", str(dest)], capture_output=True)
        exe = _find_exe(dest, emu)
        if not exe and had:
            raise RuntimeError(f"installato in {dest}, ma non trovo l'eseguibile di {emu}")
    except Exception:
        if backed:
            shutil.rmtree(dest, ignore_errors=True)
            bak.rename(dest)
        raise
    finally:
        shutil.rmtree(staged.parent, ignore_errors=True)
    if not exe:
        raise RuntimeError(f"installato in {dest}, ma non trovo l'eseguibile di {emu}: impostalo a mano")
    C.save_settings(cfg, emulators={emu: exe},
                    app={"emu_installed": {**(cfg.app.get("emu_installed") or {}), emu: {"version": tag, "dir": str(dest)}}})
    _vsave(cfg, lambda d: d.setdefault("installed", {}).__setitem__(emu, tag))
    if emu == "eglantine":  # dati separati da quelli di Eden
        L.isolate_eglantine(exe)
    say(f"Installato {emu} {tag} in {dest}")
    try:  # mapping del controller solo se l'emulatore non ha ancora impostazioni (mai quelle dell'utente)
        from . import controllerprofiles
        controllerprofiles.auto_apply(cfg.emulators, say, only=emu)
    except Exception:  # noqa: BLE001 - non deve rovinare un'installazione riuscita
        pass
    return exe


def missing_cores(cfg, pids) -> list[str]:
    """Core di RetroArch da scaricare perche' le console della libreria abbiano un emulatore pronto."""
    out = []
    for pid in pids:
        p, over = P.PLATFORMS.get(pid), cfg.launch.get(pid, {})
        cores = [c for e, c in L.PRESETS.get(pid, []) if e == L.RA and c]
        if over.get("emulator") == L.RA and over.get("core"):
            cores = [over["core"]]
        elif over.get("emulator"):  # console legata a un altro emulatore: niente core
            continue
        if p and cores and not L.plan(cfg, p) and cores[0] not in out:
            out.append(cores[0])
    return out


def install_cores(cfg, cores: list[str], progress=None, say=print) -> list[str]:
    """Scarica i core dal buildbot di libretro nella cartella dei core di RetroArch."""
    if not (cfg.emulators.get(L.RA) and Path(cfg.emulators[L.RA]).exists()):
        raise RuntimeError("installa prima RetroArch")
    url = CORES_URL.get((sys.platform, ARCH))
    if not url:  # core di un altro processore: RetroArch non li caricherebbe
        raise RuntimeError(f"il buildbot di libretro non ha core per {_OS} {ARCH_NAME[ARCH]}")
    if sys.platform != "win32" and not cfg.emulators.get("retroarch_cores"):
        # i core non stanno accanto al .app/AppImage: cartella di RetroArch dell'utente, che e' anche quella letta all'avvio
        base = (Path.home() / "Library" / "Application Support" / "RetroArch" if sys.platform == "darwin"
                else Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "retroarch")
        C.save_settings(cfg, emulators={"retroarch_cores": str(base / "cores")})
    done = []
    for n, core in enumerate(cores, 1):
        if not re.fullmatch(r"\w+", core):
            raise ValueError(f"core non valido: {core}")
        dll = L._core_path(cfg, core)
        dll.parent.mkdir(parents=True, exist_ok=True)
        say(f"Core {n}/{len(cores)}: {core}…")
        arc = dll.parent / f"{core}.download.zip"
        try:
            PT._download(url.format(core=core), arc, progress)
            with zipfile.ZipFile(arc) as z:
                z.extract(dll.name, dll.parent)
            done.append(core)
        except Exception as e:  # un core che manca sul buildbot non ferma gli altri
            say(f"{core}: non scaricato ({type(e).__name__}: {e})")
        finally:
            arc.unlink(missing_ok=True)
    say(f"Core installati: {', '.join(done) or 'nessuno'}")
    return done
