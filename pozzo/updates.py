"""Versione installata, changelog, controllo e installazione degli aggiornamenti (ultima release su GitHub).

Il controllo fa al massimo una richiesta ogni 12 ore (risposta in cache.db). install() scarica il file della
release adatto a come e' installata l'app (installer Windows, zip/tar.gz portatile, .app, .deb) e lo applica.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from . import __version__

log = logging.getLogger(__name__)

REPO = "erpaffo/Pozzo-Launcher"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
TTL = 2 * 3600


def parse(v: str) -> tuple[int, ...]:
    """'v0.2.1' -> (0, 2, 1); parti non numeriche (es. '-dev') ignorate."""
    return tuple(int(x) for x in re.findall(r"\d+", (v or "").split("-")[0])[:3]) or (0,)


def _newer(hit: dict | None) -> bool:
    latest = (hit or {}).get("latest")
    return bool(latest) and parse(latest) > parse(__version__)


def changelog() -> str:
    """changelog.md accanto al pacchetto (sorgenti) o dentro l'eseguibile (PyInstaller)."""
    bases = [Path(getattr(sys, "_MEIPASS", "")), Path(__file__).resolve().parent.parent]
    for b in bases:
        p = b / "changelog.md"
        if str(b) and p.is_file():
            return p.read_text(encoding="utf-8")
    return ""


def check(cache, force: bool = False) -> dict:
    hit = cache.kv_get("update_check")
    if not hit or force or time.time() - hit.get("time", 0) > TTL:
        try:
            r = httpx.get(LATEST, timeout=httpx.Timeout(10, connect=5), follow_redirects=True,
                          headers={"Accept": "application/vnd.github+json", "User-Agent": f"PozzoLauncher/{__version__}"})
            if r.status_code == 404:  # nessuna release pubblicata
                hit = {"time": time.time(), "latest": None}
            else:
                r.raise_for_status()
                j = r.json()
                hit = {"time": time.time(), "latest": j.get("tag_name"), "url": j.get("html_url"),
                       "published": j.get("published_at"), "notes": (j.get("body") or "")[:4000],
                       "assets": [{"name": a.get("name") or "", "url": a.get("browser_download_url") or "",
                                   "size": a.get("size") or 0, "digest": a.get("digest")} for a in j.get("assets") or []]}
            cache.kv_set("update_check", hit)
        except (httpx.HTTPError, ValueError) as e:
            return {"current": __version__, **(hit or {}), "error": f"{type(e).__name__}: {e}"[:200],
                    "newer": _newer(hit)}  # rete assente: vale comunque l'ultima versione nota in cache
    return {"current": __version__, **hit, "newer": _newer(hit)}


# ---------------------------------------------------------------- installazione dall'app
# file della release per ogni modo di installazione (nomi creati da .github/workflows/release.yml)
SUFFIX = {"setup": "-windows-x64-setup.exe", "win": "-windows-x64.zip", "mac": "-macos-arm64.zip",
          "linux": "-linux-x64.tar.gz", "deb": "_amd64.deb"}
STATE = {"status": "idle", "phase": "", "done": 0, "total": 0, "kind": None}
MANIFEST = ".pozzo-release-manifest.json"
PLATFORM = {"win": "windows-x64", "mac": "macos-arm64", "linux": "linux-x64"}
_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _unsafe_component(part: str) -> bool:
    return (part in ("", ".", "..") or "\\" in part or any(char in '<>:"|?*' for char in part)
            or part.endswith((" ", "."))
            or part.split(".")[0].upper() in _WIN_RESERVED)


def app_dir() -> Path:
    """Cartella dell'app da aggiornare: quella dell'eseguibile, su macOS il pacchetto PozzoLauncher.app."""
    exe = Path(sys.executable).resolve()
    return exe.parents[2] if sys.platform == "darwin" else exe.parent


def install_kind() -> str | None:
    """Come si aggiorna questa copia (chiave di SUFFIX); None se avviata dai sorgenti."""
    if not getattr(sys, "frozen", False):
        return None
    d = app_dir()
    if sys.platform == "win32":
        return "setup" if (d / "unins000.exe").exists() else "win"
    if sys.platform == "darwin":
        return "mac"
    return "linux" if os.access(d, os.W_OK) else "deb"  # /opt/PozzoLauncher del .deb non e' scrivibile


def _env() -> dict:
    """Ambiente pulito per i programmi lanciati: senza le librerie interne dell'eseguibile PyInstaller."""
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    if "LD_LIBRARY_PATH_ORIG" in env:
        env["LD_LIBRARY_PATH"] = env.pop("LD_LIBRARY_PATH_ORIG")
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


def _detach(cmd: list[str]):
    """Avvia un processo che sopravvive alla chiusura dell'app."""
    if sys.platform == "win32":
        subprocess.Popen(cmd, env=_env(), close_fds=True,
                         creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        subprocess.Popen(cmd, env=_env(), close_fds=True, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def swap_script(tmp: Path, src: Path, dst: Path, pid: int) -> list[str]:
    """Aspetta la chiusura dell'app e sostituisce la cartella con quella già pronta."""
    backup = dst.with_name(f".{dst.name}.old-{pid}")
    if sys.platform == "win32":
        s = tmp / "update.bat"
        s.write_text("@echo off\r\nchcp 65001 >nul\r\nset S=%SystemRoot%\\System32\r\n:wait\r\n"
                     f'"%S%\\tasklist.exe" /FI "PID eq {pid}" | "%S%\\find.exe" "{pid}" >nul'
                     ' && ("%S%\\timeout.exe" /t 1 /nobreak >nul & goto wait)\r\n'
                     f'move "{dst}" "{backup}" >nul\r\nif errorlevel 1 exit /b 1\r\n'
                     f'move "{src}" "{dst}" >nul\r\nif errorlevel 1 (move "{backup}" "{dst}" >nul & exit /b 1)\r\n'
                     f'rmdir /S /Q "{backup}"\r\n'
                     f'start "" "{dst / "PozzoLauncher.exe"}"\r\n', encoding="utf-8")
        return ["cmd", "/c", str(s)]
    run = f"open {shlex.quote(str(dst))}" if sys.platform == "darwin" else f"{shlex.quote(str(dst / 'PozzoLauncher'))} &"
    s = tmp / "update.sh"
    s.write_text(f"#!/bin/sh\nwhile kill -0 {pid} 2>/dev/null; do sleep 1; done\n"
                 f"mv {shlex.quote(str(dst))} {shlex.quote(str(backup))} || exit 1\n"
                 f"if ! mv {shlex.quote(str(src))} {shlex.quote(str(dst))}; then "
                 f"mv {shlex.quote(str(backup))} {shlex.quote(str(dst))}; exit 1; fi\n"
                 f"rm -rf {shlex.quote(str(backup))}\n{run}\n", encoding="utf-8")
    return ["/bin/sh", str(s)]


# Chiave pubblica Ed25519 (32 byte grezzi in base64) con cui e' firmato il manifest di aggiornamento.
# Vuota = firma non ancora attivata: la verifica e' saltata (e lo dice il log). Generala con tools/sign_manifest.py keygen.
PUBKEY = ""


class SignatureError(ValueError):
    """Firma del manifest assente o non valida: l'aggiornamento non deve partire (ne' ripiegare sul completo)."""


def verify_manifest_signature(raw: bytes, signature: bytes | str | None, pubkey: str | None = None) -> bool:
    """True se la firma e' valida, False se la verifica e' saltata (nessuna chiave); SignatureError altrimenti.

    La firma e' sui byte esatti del manifest scaricato, prima di leggerlo come JSON.
    """
    key = PUBKEY if pubkey is None else pubkey
    if not key.strip():
        log.warning("Aggiornamento: PUBKEY non impostata, firma del manifest non verificata")
        return False
    if not signature:
        raise SignatureError("Manifest senza firma")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(key.strip(), validate=True))
        sig = base64.b64decode(signature.strip() if isinstance(signature, (bytes, str)) else signature, validate=True)
        public.verify(sig, raw)
    except (InvalidSignature, binascii.Error, ValueError) as e:
        raise SignatureError("Firma del manifest non valida") from e
    return True


def _version(value) -> str:
    value = str(value or "")
    value = value[1:] if value.startswith("v") else value
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]*", value) or not re.search(r"\d", value):
        raise ValueError("Versione manifest non valida")
    return value


def _manifest(data, expected_version: str | None = None) -> dict:
    if not isinstance(data, dict) or set(data) != {"version", "file"} or not isinstance(data["file"], list):
        raise ValueError("Manifest non valido")
    version = _version(data["version"])
    if expected_version is not None and version != _version(expected_version):
        raise ValueError("Versione del manifest inattesa")
    files = {}
    for item in data["file"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
            raise ValueError("Voce manifest non valida")
        raw_path, digest, size = item["path"], item["sha256"], item["size"]
        if not isinstance(raw_path, str) or "\\" in raw_path:
            raise ValueError("Percorso manifest non valido")
        path = PurePosixPath(raw_path)
        if (path.is_absolute() or path.as_posix() != raw_path or len(path.parts) < 2
                or path.parts[0] not in PLATFORM.values()
                or any(_unsafe_component(part) for part in path.parts)
                or path.parts[1].casefold() == MANIFEST.casefold()):
            raise ValueError("Percorso manifest non sicuro")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("SHA-256 manifest non valido")
        if type(size) is not int or size < 0:
            raise ValueError("Dimensione manifest non valida")
        if raw_path in files:
            raise ValueError("Percorso duplicato nel manifest")
        files[raw_path] = {"path": raw_path, "sha256": digest, "size": size}
    return {"version": version, "file": files}


def _platform_files(manifest: dict, platform: str) -> dict:
    prefix = platform + "/"
    files = {path[len(prefix):]: item for path, item in manifest["file"].items() if path.startswith(prefix)}
    if not files:
        raise ValueError(f"Manifest senza file per {platform}")
    return files


def _relative(root: Path, value: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or "\\" in value or any(_unsafe_component(p) for p in path.parts):
        raise ValueError("Percorso non sicuro")
    return root.joinpath(*path.parts)


def _file_bytes(path: Path) -> bytes:
    return os.readlink(path).encode("utf-8") if path.is_symlink() else path.read_bytes()


def _verified(path: Path, item: dict, root: Path | None = None) -> bool:
    try:
        if path.is_symlink() and root is not None and not _inside(root, path.parent / os.readlink(path)):
            return False
        data = _file_bytes(path)
        return len(data) == item["size"] and hashlib.sha256(data).hexdigest() == item["sha256"]
    except (OSError, UnicodeError):
        return False


def _inside(root: Path, path: Path) -> bool:
    base, candidate = root.resolve(), path.resolve()
    return candidate == base or base in candidate.parents


def _remove(path: Path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _write_payload(archive_path: Path, stage: Path, relative: str, expected: dict):
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
        if len(members) != 1 or members[0].name != "payload":
            raise ValueError("Asset differenziale non valido")
        member = members[0]
        if member.isfile():
            stream = archive.extractfile(member)
            data = stream.read() if stream else b""
            link = None
        elif member.issym():
            link = member.linkname
            data = link.encode("utf-8")
        else:
            raise ValueError("Tipo di file differenziale non valido")
        if len(data) != expected["size"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"SHA-256 diverso: {relative}")
        target = _relative(stage, relative)
        if not _inside(stage, target.parent):
            raise ValueError(f"Percorso fuori dallo staging: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        _remove(target)
        if link is not None:
            if Path(link).is_absolute() or not _inside(stage, target.parent / link):
                raise ValueError(f"Link simbolico non sicuro: {relative}")
            target.symlink_to(link)
        else:
            target.write_bytes(data)
            if os.name != "nt":
                target.chmod(member.mode & 0o777)


def _verify_files(root: Path, files: dict):
    for relative, item in files.items():
        if not _verified(_relative(root, relative), item, root):
            raise ValueError(f"File mancante o hash diverso: {relative}")


def _extract_package(package: Path, unpacked: Path, kind: str):
    unpacked.mkdir(parents=True, exist_ok=True)

    def destination(name: str) -> Path:
        path = PurePosixPath(name)
        if (path.is_absolute() or len(path.parts) < 2
                or any(_unsafe_component(part) for part in path.parts)):
            raise ValueError("Archivio senza cartella principale")
        root = next((i for i, part in enumerate(path.parts[:-1])
                     if part in ("PozzoLauncher", "PozzoLauncher.app")), 0)
        return _relative(unpacked, PurePosixPath(*path.parts[root + 1:]).as_posix())

    if kind in ("win", "mac"):
        with zipfile.ZipFile(package) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                target = destination(info.filename)
                mode = info.external_attr >> 16
                data = archive.read(info)
                if not _inside(unpacked, target.parent):
                    raise ValueError("Percorso fuori dallo staging dell'archivio")
                target.parent.mkdir(parents=True, exist_ok=True)
                if stat.S_ISLNK(mode):
                    link = data.decode("utf-8")
                    if Path(link).is_absolute() or not _inside(unpacked, target.parent / link):
                        raise ValueError("Link simbolico non sicuro nel pacchetto")
                    target.symlink_to(link)
                else:
                    target.write_bytes(data)
                    if os.name != "nt":
                        target.chmod(mode & 0o777)
    else:
        with tarfile.open(package, "r:gz") as archive:
            for info in archive.getmembers():
                if info.isdir():
                    continue
                target = destination(info.name)
                if not _inside(unpacked, target.parent):
                    raise ValueError("Percorso fuori dallo staging dell'archivio")
                target.parent.mkdir(parents=True, exist_ok=True)
                if info.issym():
                    if Path(info.linkname).is_absolute() or not _inside(unpacked, target.parent / info.linkname):
                        raise ValueError("Link simbolico non sicuro nel pacchetto")
                    target.symlink_to(info.linkname)
                elif info.isfile() or info.islnk():
                    source = archive.extractfile(info)
                    target.write_bytes(source.read() if source else b"")
                    if os.name != "nt":
                        target.chmod(info.mode & 0o777)
                else:
                    raise ValueError("Tipo di file non supportato nel pacchetto")


def _overlay(source: Path, target: Path, root: Path):
    for item in source.iterdir():
        dest = target / item.name
        if not _inside(root, dest.parent):
            raise ValueError(f"Percorso fuori dallo staging: {dest}")
        if item.is_symlink():
            _remove(dest)
            dest.symlink_to(os.readlink(item), target_is_directory=item.is_dir())
        elif item.is_dir():
            if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
                _remove(dest)
            dest.mkdir(parents=True, exist_ok=True)
            _overlay(item, dest, root)
        else:
            if dest.is_dir() and not dest.is_symlink():
                _remove(dest)
            shutil.copy2(item, dest)


def _prune_removed(root: Path, old: dict | None, new: dict | None, platform: str):
    if not old or not new:
        return
    old_files, new_files = _platform_files(old, platform), _platform_files(new, platform)
    for relative in old_files.keys() - new_files.keys():
        target = _relative(root, relative)
        if not _inside(root, target.parent):
            raise ValueError(f"Percorso fuori dallo staging: {relative}")
        _remove(target)
        parent = target.parent
        while parent != root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def _stage_differential(installed: Path, stage: Path, old: dict, new: dict, platform: str, assets: dict,
                        download_payload) -> int:
    old_files, new_files = _platform_files(old, platform), _platform_files(new, platform)
    _verify_files(installed, old_files)
    stage.parent.mkdir(parents=True, exist_ok=True)
    _remove(stage)
    shutil.copytree(installed, stage, symlinks=True)
    _prune_removed(stage, old, new, platform)
    changed = {path: item for path, item in new_files.items()
               if path not in old_files or (item["sha256"], item["size"]) !=
               (old_files[path]["sha256"], old_files[path]["size"])}
    for relative, item in changed.items():
        remote_path = f"{platform}/{relative}"
        asset_name = (f"PozzoLauncher-{new['version']}-file-"
                      f"{hashlib.sha256(remote_path.encode('utf-8')).hexdigest()}.tar.gz")
        asset = assets.get(asset_name)
        if not asset:
            raise ValueError(f"Asset mancante: {asset_name}")
        payload = stage.parent / f".{stage.name}-{hashlib.sha256(remote_path.encode()).hexdigest()}.tar"
        try:
            download_payload(asset, payload)
            _write_payload(payload, stage, relative, item)
        finally:
            payload.unlink(missing_ok=True)
    _verify_files(stage, new_files)
    return sum(item["size"] for item in changed.values())


def _stage_with_fallback(stage: Path, differential, full):
    try:
        differential()
    except Exception as error:
        _remove(stage)
        full()
        return error
    return None


def _stage_full(installed: Path, stage: Path, package: Path, kind: str, old: dict | None,
                new: dict | None, platform: str):
    unpacked = stage.with_name(stage.name + "-unpacked")
    _remove(unpacked)
    try:
        _extract_package(package, unpacked, kind)
        _remove(stage)
        shutil.copytree(installed, stage, symlinks=True)
        trusted_old = old
        if old:
            try:
                _verify_files(installed, _platform_files(old, platform))
            except (OSError, ValueError):
                trusted_old = None
        _prune_removed(stage, trusted_old, new, platform)
        _overlay(unpacked, stage, stage)
        if new:
            _verify_files(stage, _platform_files(new, platform))
            (stage / MANIFEST).write_text(json.dumps(
                {"version": new["version"], "file": list(new["file"].values())},
                ensure_ascii=False, separators=(",", ":")
            ) + "\n", encoding="utf-8")
    except Exception:
        _remove(stage)
        raise
    finally:
        _remove(unpacked)


def _update_work_dir() -> Path:
    return Path.home() / ".cache" / "PozzoLauncher" / "updates"


def _download(url: str, dest: Path, *, digest: str | None = None, total: int | None = None,
              accumulate: bool = False):
    if not url.startswith("https://github.com/"):
        raise RuntimeError("Indirizzo di download inatteso: " + url[:120])
    if not accumulate:
        STATE.update(done=0, total=total or 0)
    h = hashlib.sha256()
    with httpx.stream("GET", url, follow_redirects=True, timeout=httpx.Timeout(60, connect=15),
                      headers={"User-Agent": f"PozzoLauncher/{__version__}"}) as response, dest.open("wb") as file:
        response.raise_for_status()
        for chunk in response.iter_bytes(1 << 20):
            file.write(chunk)
            h.update(chunk)
            STATE["done"] += len(chunk)
    if digest and digest != "sha256:" + h.hexdigest():
        raise RuntimeError("File scaricato danneggiato (checksum diverso): riprova")


def install(cache, quit) -> None:
    """Scarica e installa l'ultima versione; quit() chiude l'app perche' la nuova prenda il suo posto.
    Avanzamento ed errori in STATE (da eseguire in un thread)."""
    kind = install_kind()
    STATE.update(status="running", phase="Controllo della versione", done=0, total=0, kind=kind)
    work = stage = None
    launched = False
    try:
        if not kind:
            raise RuntimeError("Avviata dai sorgenti: aggiorna con git pull")
        info = check(cache, force=True)
        if not info.get("newer"):
            raise RuntimeError(info.get("error") or "Hai gia' l'ultima versione")
        a = next((x for x in info.get("assets") or [] if x["name"].endswith(SUFFIX[kind])), None)
        if not a:
            raise RuntimeError(f"La release {info['latest']} non contiene il file per questo sistema (*{SUFFIX[kind]})")
        if not a["url"].startswith("https://github.com/"):  # solo GitHub: il resto della release la decide il repo
            raise RuntimeError("Indirizzo di download inatteso: " + a["url"][:120])
        if kind not in ("setup", "deb") and not os.access(app_dir().parent, os.W_OK):
            raise RuntimeError(f"Cartella non scrivibile ({app_dir().parent}): scarica la nuova versione a mano")
        work = _update_work_dir() / uuid.uuid4().hex
        work.mkdir(parents=True, exist_ok=False)
        file = work / Path(a["name"]).name
        STATE.update(phase=f"Download di {file.name}", done=0, total=a["size"])
        if kind in ("setup", "deb"):
            _download(a["url"], file, digest=a.get("digest"), total=a["size"])
            if kind == "deb":
                _detach(["xdg-open", str(file)])
                STATE.update(status="done", phase=f"Aperto {file.name}: completa l'installazione e riavvia PozzoLauncher")
                return
            _detach([str(file), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"])
            STATE.update(status="done", phase="Installazione avviata")
            return

        target = app_dir()
        stage = target.with_name(f".{target.name}.stage-{uuid.uuid4().hex}")
        platform = PLATFORM[kind]
        release_version = _version(info["latest"])
        manifest_asset = next((x for x in info.get("assets", [])
                               if x["name"] == f"PozzoLauncher-{release_version}-manifest.json"), None)
        remote = None
        local = None
        full_attempted = False
        assets = {x["name"]: x for x in info.get("assets", [])}
        try:
            if manifest_asset:
                manifest_file = work / manifest_asset["name"]
                STATE.update(phase="Download manifest aggiornamento", done=0, total=manifest_asset["size"])
                _download(manifest_asset["url"], manifest_file, digest=manifest_asset.get("digest"),
                          total=manifest_asset["size"])
                sig_asset = assets.get(manifest_asset["name"] + ".sig")
                sig_data = None
                if sig_asset:
                    sig_file = work / sig_asset["name"]
                    _download(sig_asset["url"], sig_file, digest=sig_asset.get("digest"), total=sig_asset["size"])
                    sig_data = sig_file.read_bytes()
                verify_manifest_signature(manifest_file.read_bytes(), sig_data)
                remote = _manifest(json.loads(manifest_file.read_text(encoding="utf-8")), release_version)
                _platform_files(remote, platform)
            local_path = target / MANIFEST
            if local_path.is_file():
                local = _manifest(json.loads(local_path.read_text(encoding="utf-8")), __version__)
                _platform_files(local, platform)
            delta_size = 0
            if remote and local:
                old_files, new_files = _platform_files(local, platform), _platform_files(remote, platform)
                for relative, item in new_files.items():
                    if relative not in old_files or (item["sha256"], item["size"]) != (
                            old_files[relative]["sha256"], old_files[relative]["size"]):
                        remote_path = f"{platform}/{relative}"
                        asset_name = (f"PozzoLauncher-{remote['version']}-file-"
                                      f"{hashlib.sha256(remote_path.encode('utf-8')).hexdigest()}.tar.gz")
                        if asset_name not in assets:
                            raise ValueError(f"Asset differenziale mancante: {asset_name}")
                        delta_size += assets[asset_name]["size"]
                if delta_size < a["size"]:
                    STATE.update(phase=f"Aggiornamento differenziale: {delta_size / 1_000_000:.1f} MB "
                                       f"(pacchetto completo: {a['size'] / 1_000_000:.1f} MB)",
                                 done=0, total=delta_size)

                    def full_fallback():
                        nonlocal full_attempted
                        full_attempted = True
                        STATE.update(phase=f"Hash differenziale non valido; download completo: "
                                           f"{a['size'] / 1_000_000:.1f} MB", done=0, total=a["size"])
                        _download(a["url"], file, digest=a.get("digest"), total=a["size"])
                        _stage_full(target, stage, file, kind, local, remote, platform)

                    _stage_with_fallback(
                        stage,
                        lambda: _stage_differential(
                            target, stage, local, remote, platform, assets,
                            lambda asset, dest: _download(asset["url"], dest, digest=asset.get("digest"),
                                                          total=asset["size"], accumulate=True)
                        ),
                        full_fallback,
                    )
                else:
                    raise ValueError("Il differenziale non è più leggero del pacchetto completo")
            else:
                raise ValueError("Manifest locale o remoto non valido")
        except Exception as diff_error:
            if full_attempted or isinstance(diff_error, SignatureError):
                raise
            _remove(stage)
            STATE.update(phase=f"Differenziale non applicabile ({type(diff_error).__name__}); "
                               f"download completo: {a['size'] / 1_000_000:.1f} MB",
                         done=0, total=a["size"])
            _download(a["url"], file, digest=a.get("digest"), total=a["size"])
            _stage_full(target, stage, file, kind, local, remote, platform)
        else:
            (stage / MANIFEST).write_text(json.dumps(
                {"version": remote["version"], "file": list(remote["file"].values())},
                ensure_ascii=False, separators=(",", ":")
            ) + "\n", encoding="utf-8")

        STATE["phase"] = "Installazione atomica"
        command = swap_script(work, stage, target, os.getpid())
        script = Path(command[-1])
        for item in work.iterdir():
            if item != script:
                _remove(item)
        _detach(command)
        launched = True
        STATE.update(status="done", phase="Riavvio con la nuova versione…")
        quit()
    except Exception as e:
        if not launched:
            if stage is not None:
                _remove(stage)
            if work is not None:
                _remove(work)
        STATE.update(status="error", phase=f"{type(e).__name__}: {e}"[:300])
