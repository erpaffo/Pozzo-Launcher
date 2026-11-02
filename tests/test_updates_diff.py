"""Test offline dell'aggiornamento differenziale con installazioni e asset simulati."""

import hashlib
import io
import json
import tarfile
import zipfile
from pozzo import updates
from tools.release_manifest import create


PLATFORM = "windows-x64"


def _item(path, data):
    return {"path": f"{PLATFORM}/{path}", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def _manifest(version, **files):
    return updates._manifest({"version": version, "file": [_item(path, data) for path, data in files.items()]})


def _payload(data):
    stream = io.BytesIO()
    info = tarfile.TarInfo("payload")
    info.size = len(data)
    with tarfile.open(fileobj=stream, mode="w") as archive:
        archive.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def _assets(version, files):
    return {
        f"PozzoLauncher-{version}-file-{hashlib.sha256(f'{PLATFORM}/{path}'.encode()).hexdigest()}.tar.gz": _payload(data)
        for path, data in files.items()
    }


def _apply(installed, stage, old, new, payloads):
    def download(asset, destination):
        destination.write_bytes(payloads[asset["name"]])

    return updates._stage_differential(installed, stage, old, new, PLATFORM,
                                       {name: {"name": name} for name in payloads}, download)


def test_differential_with_no_changes_copies_without_downloading(tmp_path):
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "same.txt").write_bytes(b"same")
    old, new = _manifest("0.12.0", **{"same.txt": b"same"}), _manifest("0.12.1", **{"same.txt": b"same"})
    stage = tmp_path / "stage"

    _apply(installed, stage, old, new, {})

    assert (stage / "same.txt").read_bytes() == b"same"


def test_differential_downloads_only_changed_files(tmp_path):
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "changed.txt").write_bytes(b"old")
    (installed / "same.txt").write_bytes(b"same")
    old = _manifest("0.12.0", **{"changed.txt": b"old", "same.txt": b"same"})
    new = _manifest("0.12.1", **{"changed.txt": b"new", "same.txt": b"same"})
    payloads = _assets("0.12.1", {"changed.txt": b"new"})
    stage = tmp_path / "stage"

    _apply(installed, stage, old, new, payloads)

    assert (stage / "changed.txt").read_bytes() == b"new"
    assert (stage / "same.txt").read_bytes() == b"same"


def test_differential_removes_files_missing_from_new_manifest(tmp_path):
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "keep.txt").write_bytes(b"keep")
    (installed / "remove.txt").write_bytes(b"remove")
    old = _manifest("0.12.0", **{"keep.txt": b"keep", "remove.txt": b"remove"})
    new = _manifest("0.12.1", **{"keep.txt": b"keep"})
    stage = tmp_path / "stage"

    _apply(installed, stage, old, new, {})

    assert (stage / "keep.txt").read_bytes() == b"keep"
    assert not (stage / "remove.txt").exists()


def test_bad_delta_hash_falls_back_to_complete_staging(tmp_path):
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "game.bin").write_bytes(b"old")
    (installed / "obsolete.bin").write_bytes(b"obsolete")
    old = _manifest("0.12.0", **{"game.bin": b"old", "obsolete.bin": b"obsolete"})
    new = _manifest("0.12.1", **{"game.bin": b"new"})
    payloads = _assets("0.12.1", {"game.bin": b"corrupt"})
    stage = tmp_path / "stage"
    full_package = tmp_path / "PozzoLauncher-0.12.1-windows-x64.zip"
    with zipfile.ZipFile(full_package, "w") as archive:
        archive.writestr("dist/PozzoLauncher/game.bin", b"new")

    def full_fallback():
        updates._stage_full(installed, stage, full_package, "win", old, new, PLATFORM)

    error = updates._stage_with_fallback(
        stage,
        lambda: _apply(installed, stage, old, new, payloads),
        full_fallback,
    )

    assert isinstance(error, ValueError)
    assert (stage / "game.bin").read_bytes() == b"new"
    assert not (stage / "obsolete.bin").exists()
    assert (stage / updates.MANIFEST).is_file()
    assert (installed / "game.bin").read_bytes() == b"old"


def test_release_manifest_and_file_assets_are_built_from_portable_archive(tmp_path):
    release = tmp_path / "release"
    release.mkdir()
    package = release / "PozzoLauncher-0.12.1-windows-x64.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("dist/PozzoLauncher/PozzoLauncher.exe", b"launcher")
        archive.writestr("dist/PozzoLauncher/_internal/runtime.dll", b"runtime")

    manifest_path = create(release, "0.12.1")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["version"] == "0.12.1"
    entries = {item["path"]: item for item in manifest["file"]}
    assert set(entries) == {"windows-x64/PozzoLauncher.exe", "windows-x64/_internal/runtime.dll"}
    for path, data in (("PozzoLauncher.exe", b"launcher"), ("_internal/runtime.dll", b"runtime")):
        remote_path = f"windows-x64/{path}"
        asset_name = f"PozzoLauncher-0.12.1-file-{hashlib.sha256(remote_path.encode()).hexdigest()}.tar.gz"
        assert (release / asset_name).is_file()
        assert entries[remote_path]["sha256"] == hashlib.sha256(data).hexdigest()
        assert entries[remote_path]["size"] == len(data)
