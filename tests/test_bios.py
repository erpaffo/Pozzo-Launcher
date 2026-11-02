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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep + "tools")

import json  # noqa: E402

import update_bios_hashes as U  # noqa: E402
from pozzo import bios as B  # noqa: E402

DAT = """clrmamepro (
\tversion v1.19.0
)

game (
\tname "System"
\tcomment "System"

\tcomment "Dreamcast"
\trom ( name "dc/dc_boot.bin" size 2097152 crc 89F2B1A1 md5 E10C53C2F8B90BAB96EAD2D368858623 sha1 8951D1BB219AB2FF8583033D2119C899CC81F18C )

\tcomment "Sony - PlayStation"
\trom ( name scph5501.bin size 524288 crc 8D8CB7E4 md5 490f666e1afb15b7362b406ed1cea246 sha1 0555c6fae8906f3f09baf5988f00e55f88e9f30b )
)
"""


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
                                              "sha1": sha, "motivo": "ok",
                                              "help_url": B.REQUISITI["psx"]["help"]}
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
    assert all(i["found"] and not i["ok"] and i["sha1"] for i in res["items"]), "presenti ma con l'hash sbagliato"
    assert {i["motivo"] for i in res["items"]} == {"hash diverso"}, res["items"]
    print("ok  file con hash ufficiale diverso: rosso, con il motivo")


def test_hash_non_noto_per_davvero(tmp: Path):
    """Un file che nel JSON ufficiale non c'e' resta «hash non noto», non verde."""
    (tmp / "aes_keys.txt").write_text("slot0x2CKeyX=00112233445566778899AABBCCDDEEFF\n", encoding="utf-8")
    res = B.check("3ds", str(tmp))
    assert res["ok"] is False and _item(res, "aes_keys.txt")["motivo"] == "hash non noto", res
    print("ok  file fuori dal DAT ufficiale: «hash non noto» (mai dato per buono)")


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


def test_json_ufficiale():
    """Il JSON nel repo viene dal DAT di libretro: i BIOS standard hanno uno sha1 vero, non scritto a mano."""
    assert B.SHA1_NOTI, "pozzo/data/bios_hashes.json vuoto: rilancia tools/update_bios_hashes.py"
    for nome in ("scph5501.bin", "mpr-17933.bin", "dc_boot.bin", "bios7.bin", "bios_cd_e.bin"):
        assert len(B.SHA1_NOTI.get(nome, ())) == 1, nome
        assert all(len(h) == 40 for h in B.SHA1_NOTI[nome]), nome
    assert "prod.keys" not in B.SHA1_NOTI, "le chiavi della Switch non hanno hash pubblico"
    print(f"ok  JSON ufficiale: {len(B.SHA1_NOTI)} file con sha1 (DAT libretro)")


def test_json_fixture(tmp: Path):
    """load_hashes legge anche un JSON suo, senza toccare quello vero."""
    (tmp / "scph5502.bin").write_bytes(b"abc")
    sha = hashlib.sha1(b"abc").hexdigest()
    mio = tmp / "hashes.json"
    mio.write_text(json.dumps({"files": {"scph5502.bin": {"size": 3, "crc": "",
                                                          "md5": hashlib.md5(b"abc").hexdigest(), "sha1": sha}}}),
                   encoding="utf-8")
    sha1, md5 = B.load_hashes(mio)
    assert sha1 == {"scph5502.bin": {sha}}, sha1
    vecchi = (B.SHA1_NOTI, B.MD5_NOTI)
    B.SHA1_NOTI, B.MD5_NOTI = sha1, md5
    try:
        assert B.check("psx", str(tmp))["ok"] is True
    finally:
        B.SHA1_NOTI, B.MD5_NOTI = vecchi
    assert B.load_hashes(tmp / "non-esiste.json") == ({}, {})
    (tmp / "rotto.json").write_text("{non e' json", encoding="utf-8")
    assert B.load_hashes(tmp / "rotto.json") == ({}, {})
    print("ok  JSON di prova caricato; mancante o rotto: nessun hash noto, niente crash")


def test_parser_dat():
    """Il parser di tools/update_bios_hashes.py: gruppi, prefisso di cartella, hash normalizzati."""
    assert U.version_of(DAT) == "v1.19.0"
    assert [(r["group"], r["name"]) for r in U.parse_dat(DAT)] == [("Dreamcast", "dc_boot.bin"),
                                                                   ("Sony - PlayStation", "scph5501.bin")]
    files, doppioni = U.build(DAT, ["dc_boot.bin", "assente.bin"])
    assert doppioni == 0 and list(files) == ["dc_boot.bin"], files
    assert files["dc_boot.bin"] == {"size": 2097152, "crc": "89F2B1A1", "md5": "e10c53c2f8b90bab96ead2d368858623",
                                    "sha1": "8951d1bb219ab2ff8583033d2119c899cc81f18c"}, files
    print("ok  parser del DAT: gruppi, prefisso di cartella, hash del formato giusto")


def test_switch_personali(tmp: Path):
    """Chiavi e firmware della Switch: personali, si controlla il formato, non un hash."""
    (tmp / "prod.keys").write_text("master_key_00 = 00112233445566778899AABBCCDDEEFF\nheader_key = 00112233\n",
                                   encoding="utf-8")
    (tmp / "title.keys").write_text("0100000000010000 = 00112233445566778899AABBCCDDEEFF\n", encoding="utf-8")
    (tmp / "firmware").mkdir()
    (tmp / "firmware" / "0100000000000808.nca").write_bytes(b"nca")
    res = B.check("switch", str(tmp))
    assert res["ok"] is True, res["items"]
    assert {i["motivo"] for i in res["items"]} == {"formato valido (hash non pubblico)",
                                                   "cartella firmware presente"}, res["items"]
    (tmp / "title.keys").write_text("questo non e' un file di chiavi\n", encoding="utf-8")
    res = B.check("switch", str(tmp))
    assert res["ok"] is False and _item(res, "title.keys")["motivo"].startswith("formato non valido"), res
    print("ok  Switch: chiavi per formato (hash non pubblico), firmware come cartella con dentro qualcosa")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
        test_hash_noto(Path(t))
    for fn in (test_hash_non_noto, test_hash_non_noto_per_davvero, test_file_mancante_e_cartella_vuota,
               test_file_illeggibile, test_firmware_cartella_e_blocchi, test_console_senza_bios, test_json_fixture,
               test_switch_personali):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as t:
            fn(Path(t))
    test_console_sconosciuta()
    test_json_ufficiale()
    test_parser_dat()
    print("TUTTI I TEST OK")
