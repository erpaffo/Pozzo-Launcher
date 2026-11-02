"""Crea gli asset per l'aggiornamento differenziale a partire dai pacchetti portatili.

shortcut: un asset per file supera il limite di 1000 asset per release di GitHub con i pacchetti PyInstaller,
quindi release.yml NON lo usa e l'updater ripiega sull'archivio completo; da riattivare con un contenitore unico
(es. archivio per file letto con richieste Range) prima di metterlo nel workflow.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def _safe_path(value: str) -> str:
    path = PurePosixPath(value)
    invalid = set('<>:"|?*')
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if (not value or path.is_absolute() or path.as_posix() != value or "\\" in value
            or any(part in ("", ".", "..") or any(char in invalid for char in part)
                   or part.endswith((" ", ".")) or part.split(".")[0].upper() in reserved for part in path.parts)):
        raise ValueError(f"Percorso non valido nell'archivio: {value!r}")
    return path.as_posix()


def _asset_name(version: str, path: str) -> str:
    key = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return f"PozzoLauncher-{version}-file-{key}.tar.gz"


def _relative_to_app(name: str) -> str:
    parts = PurePosixPath(_safe_path(name)).parts
    for index, part in enumerate(parts[:-1]):
        if part in ("PozzoLauncher", "PozzoLauncher.app"):
            return PurePosixPath(*parts[index + 1:]).as_posix()
    if len(parts) < 2:
        raise ValueError(f"Pacchetto senza cartella principale: {name}")
    return PurePosixPath(*parts[1:]).as_posix()


def _payload(path: str, data: bytes, mode: int, link: str | None = None) -> bytes:
    info = tarfile.TarInfo("payload")
    info.mode = mode & 0o777
    info.mtime = 0
    if link is not None:
        info.type = tarfile.SYMTYPE
        info.linkname = link
        info.size = 0
        content = b""
    else:
        info.size = len(data)
        content = data
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        archive.addfile(info, io.BytesIO(content))
    return out.getvalue()


def _zip_files(archive: zipfile.ZipFile):
    for info in archive.infolist():
        if info.is_dir():
            continue
        relative = _relative_to_app(info.filename)
        mode = info.external_attr >> 16
        data = archive.read(info)
        if stat.S_ISLNK(mode):
            link = data.decode("utf-8")
            yield relative, link.encode("utf-8"), mode, link
        else:
            yield relative, data, mode, None


def _tar_files(archive: tarfile.TarFile):
    for info in archive.getmembers():
        if info.isdir():
            continue
        relative = _relative_to_app(info.name)
        if info.issym():
            link = info.linkname
            yield relative, link.encode("utf-8"), info.mode, link
        elif info.isfile():
            source = archive.extractfile(info)
            if source is None:
                raise ValueError(f"File mancante nel pacchetto: {info.name}")
            yield relative, source.read(), info.mode, None
        else:
            raise ValueError(f"Tipo di file non supportato nel pacchetto: {info.name}")


def create(release: Path, version: str) -> Path:
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+-]*", version):
        raise ValueError(f"Versione non valida: {version}")
    manifest = {"version": version, "file": []}
    platforms = (
        ("windows-x64", release / f"PozzoLauncher-{version}-windows-x64.zip"),
        ("macos-arm64", release / f"PozzoLauncher-{version}-macos-arm64.zip"),
        ("linux-x64", release / f"PozzoLauncher-{version}-linux-x64.tar.gz"),
    )
    seen: set[str] = set()
    for platform, package in platforms:
        if not package.is_file():
            continue
        if package.suffix == ".zip":
            with zipfile.ZipFile(package) as archive:
                files = list(_zip_files(archive))
        else:
            with tarfile.open(package, "r:gz") as archive:
                files = list(_tar_files(archive))
        for relative, data, mode, link in files:
            path = _safe_path(f"{platform}/{relative}")
            if path in seen:
                raise ValueError(f"Percorso duplicato: {path}")
            seen.add(path)
            (release / _asset_name(version, path)).write_bytes(_payload(path, data, mode, link))
            manifest["file"].append({"path": path, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    if not manifest["file"]:
        raise ValueError("Nessun pacchetto portatile trovato")
    result = release / f"PozzoLauncher-{version}-manifest.json"
    result.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    import sys

    version = sys.argv[1].removeprefix("v")
    print(create(Path(sys.argv[2]), version))
