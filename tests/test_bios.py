"""Test della verifica BIOS e firmware (pozzo/bios.py): file con hash noto, hash non noto, file mancante, cartella
vuota, file illeggibile, console senza BIOS, console sconosciuta. Usa file finti e nessun file BIOS reale.

Esegui: python tests/test_bios.py
"""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import bios as B  # noqa: E402


def _item(res: dict, nome: str) -> dict:
    return next(i for i in res["items"] if i["file"] == nome)


def test_hash_noto(tmp: Path):
    f = tmp / "scph5500.bin"
    f.write_bytes(b"file finto, non e' un BIOS")
    sha = hashlib.sha1(f.read_bytes()).hexdigest()
    md5_ = hashlib.md5(f.read_bytes()).hexdigest()
    vecchi = (B.SHA1_NOTI, B.MD5_NOTI)
    B.SHA1_NOTI = {"scph5500.bin": {sha}}  # hash aggiunto solo per il test
    try:
        res = B.check("psx", str(tmp))
        assert _item(res, "scph5500.bin") == {"file": "scph5500.bin", "required": True, "found": True, "ok": True,
                                              "sha1": sha, "help_url": B.REQUISITI["psx"]["help"]}
        assert res["ok"] is True, "un file del gruppo PS1 ok basta"
        assert res["console"] == "psx" and res["emulator"] == "duckstation"
    finally:
        B.SHA1_NOTI = vecchi[0]
    B.MD5_NOTI = {"scph5501.bin": {md5_}}  # stesso file, ma con il nome del gruppo che MD5 riconosce
    try:
        (tmp / "scph5501.bin").write_bytes(f.read_bytes())
        assert _item(B.check("psx", str(tmp)), "scph5501.bin")["ok"] is True, "il controllo MD5 funziona"
    finally:
        B.MD5_NOTI = vecchi[1]


def test_hash_non_noto(tmp: Path):
    (tmp / "bios7.bin").write_bytes(b"qualcosa")
    (tmp / "bios9.bin").write_bytes(b"qualcosa")
    (tmp / "firmware.bin").write_bytes(b"qualcosa")
    res = B.check("nds", str(tmp))
    assert res["ok"] is False
    assert all(i["found"] and not i["ok"] and i["sha1"] for i in res["items"]), "presenti ma hash non noti"


def test_file_mancante_e_cartella_vuota(tmp: Path):
    res = B.check("saturn", str(tmp))  # cartella vuota
    assert res["ok"] is False and len(res["items"]) == 2
    assert all(not i["found"] and not i["ok"] and i["sha1"] is None for i in res["items"])
    assert all(i["required"] for i in res["items"]), "i file del gruppo risultano required"
    (tmp / "3ds").mkdir()
    res = B.check("3ds", str(tmp / "3ds"))
    assert res["ok"] is False and _item(res, "aes_keys.txt")["found"] is False


def test_file_illeggibile(tmp: Path):
    (tmp / "aes_keys.txt").mkdir()  # una cartella con quel nome non si legge come file
    res = B.check("3ds", str(tmp))
    it = _item(res, "aes_keys.txt")
    assert it["found"] is True and it["ok"] is False and it["sha1"] is None, "niente crash, presente ma non verificabile"
    assert res["ok"] is False


def test_firmware_cartella_e_blocchi(tmp: Path):
    (tmp / "prod.keys").write_bytes(b"a" * (3 << 20))  # piu' blocchi da 1 MiB
    (tmp / "title.keys").write_bytes(b"b")
    (tmp / "firmware").mkdir()  # firmware Switch e' una cartella: senza hash noto resta ok False
    res = B.check("switch", str(tmp))
    assert _item(res, "prod.keys")["sha1"] == hashlib.sha1(b"a" * (3 << 20)).hexdigest()
    assert _item(res, "firmware")["found"] is True and _item(res, "firmware")["ok"] is False
    assert res["ok"] is False


def test_console_senza_bios(tmp: Path):
    res = B.check("nes", str(tmp))
    assert res == {"console": "nes", "emulator": "retroarch", "items": [], "ok": True}
    res = B.check("gba", str(tmp))  # il BIOS del GBA e' facoltativo: ok anche se manca
    assert res["ok"] is True and res["items"][0]["required"] is False and res["items"][0]["found"] is False


def test_console_sconosciuta():
    try:
        B.check("console-che-non-esiste", "")
    except ValueError as e:
        assert "console sconosciuta" in str(e)
    else:
        raise AssertionError("ci si aspetta ValueError")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        test_hash_noto(Path(t))
    for fn in (test_hash_non_noto, test_file_mancante_e_cartella_vuota, test_file_illeggibile,
               test_firmware_cartella_e_blocchi, test_console_senza_bios):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            fn(Path(t))
    test_console_sconosciuta()
    print("TUTTI I TEST OK")
