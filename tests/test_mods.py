"""Fixture offline per fonti mod, archivi sicuri, backup e gestione installazioni port."""

import hashlib
import io
import json
import os
import shutil
import sys
import types
import zipfile
import zlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import ports as PT  # noqa: E402

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures" / "mod_sources"
WORK = ROOT / "fixtures" / ".mods-work"


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return buf.getvalue()


def _bps_number(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value == 0:
            out.append(byte | 0x80)
            return bytes(out)
        out.append(byte)
        value -= 1


def test_source_parsers():
    raw = json.loads((FIXTURES / "thunderstore.json").read_text(encoding="utf-8"))
    ts = PT.parse_thunderstore(raw)
    assert len(ts) == 1 and ts[0]["id"] == "FixtureOwner/FixtureMod"
    assert ts[0]["version"] == "1.2.3" and ts[0]["provider"] == "thunderstore"
    gb = PT.parse_mod_page("https://gamebanana.com/mods/games/1", "gamebanana",
                           (FIXTURES / "gamebanana.html").read_text(encoding="utf-8"))
    assert {x["id"] for x in gb} == {"gamebanana-12345", "gamebanana-67890"}
    md = PT.parse_mod_page("https://www.moddb.com/mods/fixture", "moddb",
                           (FIXTURES / "moddb.html").read_text(encoding="utf-8"))
    assert len(md) == 1 and md[0]["page"].endswith("/downloads")
    assert not PT.parse_mod_page("https://www.nexusmods.com/game/mods/1", "nexus", "<a>blocked</a>")
    assert PT.mod_matches({"game": "The Legend of Zelda: Ocarina of Time", "platform": "n64"},
                          ["The Legend of Zelda: Ocarina of Time"], ["n64"])
    assert not PT.mod_matches({"game": "Other Game", "platform": "n64"},
                              ["The Legend of Zelda: Ocarina of Time"], ["n64"])
    assert not PT.mod_matches({"platform": "psx"}, ["Fixture"], ["n64"])
    print("ok  parser Thunderstore/GameBanana/ModDB, Nexus escluso, corrispondenza titolo/piattaforma prudente")


def test_archive_and_patches():
    WORK.mkdir(parents=True, exist_ok=True)
    archive_path, output = WORK / "safe.zip", WORK / "extract"
    archive_path.write_bytes(_zip({"mod/file.txt": b"safe"}))
    assert PT._extract_mod_zip(archive_path, output) == ["mod/file.txt"]
    assert (output / "mod" / "file.txt").read_bytes() == b"safe"
    shutil.rmtree(output)
    archive_path.write_bytes(_zip({"../escape.txt": b"no"}))
    try:
        PT._extract_mod_zip(archive_path, output)
        raise AssertionError("ZIP traversal non rifiutato")
    except ValueError:
        pass

    source, patch, destination = WORK / "source.rom", WORK / "update.ips", WORK / "patched.rom"
    source.write_bytes(b"abc")
    patch.write_bytes(b"PATCH" + b"\x00\x00\x01" + b"\x00\x01" + b"Z" + b"EOF")
    PT.apply_patch_copy(source, destination, patch)
    assert source.read_bytes() == b"abc" and destination.read_bytes() == b"aZc"

    source.write_bytes(b"A")
    command = _bps_number(((1 - 1) << 2) | 1) + b"B"  # TargetRead un byte
    header = b"BPS1" + _bps_number(1) + _bps_number(1) + _bps_number(0) + command
    bps = header + (zlib.crc32(b"A") & 0xFFFFFFFF).to_bytes(4, "little")
    bps += (zlib.crc32(b"B") & 0xFFFFFFFF).to_bytes(4, "little")
    bps += (zlib.crc32(bps) & 0xFFFFFFFF).to_bytes(4, "little")
    bps_path = patch.with_suffix(".bps")
    bps_path.write_bytes(bps)
    PT.apply_patch_copy(source, destination, bps_path)
    assert source.read_bytes() == b"A" and destination.read_bytes() == b"B"
    shutil.rmtree(WORK)
    print("ok  estrazione ZIP traversal-safe, patch IPS/BPS scritte solo su una copia")


def test_install_backup_toggle_remove():
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        cfg = types.SimpleNamespace(app={"ports_dir": str(WORK / "Ports")})
        ports = PT.ports_dir(cfg)
        folder = ports / "FixturePort"
        folder.mkdir(parents=True)
        PT.write_manifest(folder, {"slug": "fixture-port", "name": "Fixture Port",
                                   "mods": {"path": "mods"}, "installed_mods": {}})
        old = folder / "mods" / "replace.txt"
        old.parent.mkdir(parents=True)
        old.write_text("before", encoding="utf-8")
        payload = _zip({"replace.txt": b"after", "new.txt": b"new"})
        original_download = PT._mod_download
        PT._mod_download = lambda url, dest, provider, max_bytes=PT.MOD_MAX_DOWNLOAD: dest.write_bytes(payload)
        try:
            installed = PT.install_mod(cfg, "fixture-port", {
                "provider": "thunderstore", "id": "Owner/Package", "name": "Fixture",
                "url": "https://thunderstore.io/package/download/Owner/Package/1.0/"
            })
        finally:
            PT._mod_download = original_download
        record = installed["installed_mods"]["Owner/Package"]
        assert record["enabled"] and record["download_url"].startswith("https://")
        assert (folder / "mods" / "replace.txt").read_text(encoding="utf-8") == "after"
        backup = PT.ports_dir(cfg) / Path(record["backup"])
        with zipfile.ZipFile(backup) as z:
            assert z.read("mods/replace.txt") == b"before"
        PT.set_mod_enabled(cfg, "fixture-port", "Owner/Package", False)
        assert not (folder / "mods" / "new.txt").exists()
        PT.set_mod_enabled(cfg, "fixture-port", "Owner/Package", True)
        assert (folder / "mods" / "new.txt").read_bytes() == b"new"
        PT.remove_mod(cfg, "fixture-port", "Owner/Package")
        assert not (folder / "mods" / "new.txt").exists()
        assert not PT.all_installed(cfg)["fixture-port"].get("installed_mods")
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
    print("ok  installazione, link persistito, backup dei file sostituiti, enable/disable e rimozione sicuri")


if __name__ == "__main__":
    test_source_parsers()
    test_archive_and_patches()
    test_install_backup_toggle_remove()
