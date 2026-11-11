"""Test della conversione Switch 2 (cartella / NSP / NUP): giro completo su un gioco finto, rifiuto degli NSP
retail o cifrati, annullamento, e supported() con le versioni di Eglantine. Nessun gioco vero, nessuna rete.

Esegui: python tests/test_switch2pack.py
"""
import json
import os
import struct
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pozzo import config  # noqa: E402
from pozzo import switch2pack as S  # noqa: E402

TID = 0x0400ABCD00012000  # il primo byte 04 e' quello dei titoli Switch 2
DLC = "0400ABCD00013001"


def _npdm(tid: int) -> bytes:
    d = bytearray(0xA0)
    d[:4] = b"META"
    struct.pack_into("<II", d, 0x70, 0x80, 0x20)
    d[0x80:0x84] = b"ACI0"
    struct.pack_into("<Q", d, 0x90, tid)
    return bytes(d)


def _game(root: Path) -> dict[str, bytes]:
    """Cartella exefs/romfs minima che il packager accetta; ritorna {percorso: contenuto} per i confronti."""
    files = {"exefs/main": b"NSO0" + os.urandom(300), "exefs/main.npdm": _npdm(TID),
             "romfs/a.txt": b"ciao " * 5000, "romfs/sub/b.bin": os.urandom(70000), "romfs/sub/vuoto": b""}
    for rel, data in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(data)
    return files


def _same(folder: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        assert (folder / rel).read_bytes() == data, rel


def _pfs0(entries: list[tuple[str, bytes]]) -> bytes:
    names = b"".join(n.encode() + b"\0" for n, _ in entries)
    head, body, noff = struct.pack("<4sIII", b"PFS0", len(entries), len(names), 0), b"", 0
    for n, data in entries:
        head += struct.pack("<QQII", len(body), len(data), noff, 0)
        noff += len(n.encode()) + 1
        body += data
    return head + names + body


def test_giro_completo(tmp: Path):
    files = _game(tmp / "Gioco")
    assert S.detect_format(tmp / "Gioco") == "folder" and S.detect_format(tmp / "Gioco" / "romfs") == "folder"
    seen = []
    nsp = S.convert(tmp / "Gioco", "nsp", tmp / "out", progress=lambda d, t: seen.append((d, t)))
    assert nsp == (tmp / "out" / "Gioco.nsp").resolve() and S.detect_format(nsp) == "nsp"
    assert seen and seen[-1] == (100, 100) and all(0 <= d <= 100 and t == 100 for d, t in seen)
    nup = S.convert(nsp, "nup", tmp / "out")
    assert nup.name == "Gioco.nup" and S.detect_format(nup) == "nup"
    back = S.convert(nup, "folder", tmp / "out")  # disposizione di NSP-Box: base/ + nup-manifest.json
    _same(back / "base", files)
    assert S.detect_format(back) == "folder"
    # l'altro verso: cartella -> NUP -> NSP -> cartella
    nup2 = S.convert(tmp / "Gioco", "nup", tmp / "out2")
    nsp2 = S.convert(nup2, "nsp", tmp / "out2")
    assert nsp2.is_file() and nsp2.read_bytes() == nsp.read_bytes()  # stesso contenuto, stesso NSP
    back2 = S.convert(nsp2, "folder", tmp / "out2")
    _same(back2 / "base", files)
    man = json.loads((back2 / "nup-manifest.json").read_text("utf-8"))
    assert man["packages"][0]["title_id"] == f"{TID:016X}"
    # la cartella estratta si rimpacchetta (manifest)
    assert S.convert(back2, "nup", tmp / "out3").is_file()
    assert not [p for p in tmp.rglob("*") if ".partial" in p.name or p.name.startswith(".nup-")]  # nessun avanzo


def test_gioco_piu_dlc(tmp: Path):
    files = _game(tmp / "Bundle" / "base")
    d = tmp / "Bundle" / "dlc" / DLC / "romfs"
    d.mkdir(parents=True)
    (d / "extra.bin").write_bytes(b"dlc" * 1000)
    out = S.convert(tmp / "Bundle", "nsp", tmp / "out")
    assert out.is_dir() and sorted(p.name for p in out.iterdir()) == [f"DLC [{DLC}] v0.nsp", f"Game [{TID:016X}] v0.nsp"]
    nup = S.convert(tmp / "Bundle", "nup", tmp / "out")
    out2 = S.convert(nup, "nsp", tmp / "out2")
    assert out2.is_dir() and len(list(out2.glob("*.nsp"))) == 2
    back = S.convert(out / f"DLC [{DLC}] v0.nsp", "folder", tmp / "out3")
    assert (back / "dlc" / DLC / "0" / "romfs" / "extra.bin").read_bytes() == b"dlc" * 1000
    _same(S.convert(nup, "folder", tmp / "out4") / "base", files)


def _err(fn, *words):
    try:
        fn()
    except S.SwitchPackError as e:
        assert all(w in str(e) for w in words), str(e)
        return
    raise AssertionError("doveva fallire")


def test_rifiuti(tmp: Path):
    _game(tmp / "Gioco")
    nsp = S.convert(tmp / "Gioco", "nsp", tmp / "out")
    nca = bytearray(0xC00)
    nca[0x200:0x204] = b"NCA3"
    retail = tmp / "retail.nsp"
    retail.write_bytes(_pfs0([("a" * 32 + ".nca", bytes(nca)), ("a" * 32 + ".tik", b"x" * 0x2C0)]))
    _err(lambda: S.convert(retail, "nup", tmp / "o"), "retail", "ticket")
    cifrato = tmp / "cifrato.nsp"
    cifrato.write_bytes(_pfs0([("b" * 32 + ".nca", os.urandom(0xC00))]))  # intestazione cifrata: niente «NCA3»
    _err(lambda: S.convert(cifrato, "folder", tmp / "o"), "cifrato")
    # intestazione in chiaro ma tipo di distribuzione «cartuccia» (byte 0x204 != 0): lo rifiuta NSP-Box
    nca[0x204] = 1
    carta = tmp / "carta.nsp"
    carta.write_bytes(_pfs0([("c" * 32 + ".nca", bytes(nca))]))
    _err(lambda: S.convert(carta, "nup", tmp / "o"), "non si può convertire")
    (tmp / "nsz.nsp").write_bytes(_pfs0([("d" * 32 + ".ncz", b"x" * 64)]))
    _err(lambda: S.convert(tmp / "nsz.nsp", "nup", tmp / "o"), "NSZ")
    (tmp / "troncato.nsp").write_bytes(b"PFS0" + struct.pack("<III", 5, 100, 0))
    _err(lambda: S.convert(tmp / "troncato.nsp", "nup", tmp / "o"), "troncato")
    assert not (tmp / "o").exists() or not list((tmp / "o").iterdir())  # nessun file scritto dai rifiuti

    (tmp / "gioco.xci").write_bytes(b"HEAD" + bytes(100))
    assert S.detect_format(tmp / "gioco.xci") is None and S.detect_format(tmp / "manca") is None
    (tmp / "vuota").mkdir()
    assert S.detect_format(tmp / "vuota") is None
    _err(lambda: S.convert(tmp / "gioco.xci", "nsp", tmp / "o"), "formato non supportato")
    _err(lambda: S.convert(tmp / "manca.nsp", "nup", tmp / "o"), "non trovo")
    _err(lambda: S.convert(nsp, "zip", tmp / "o"), "destinazione non supportato")
    _err(lambda: S.convert(nsp, "nsp", tmp / "o"), "già in formato")
    _err(lambda: S.convert(tmp / "Gioco", "nsp", tmp / "out"), "esiste già")  # mai sovrascrivere
    _err(lambda: S.convert(tmp / "Gioco", "nup", tmp / "Gioco" / "dentro"), "fuori dalla cartella")
    # cartella senza main.npdm ne' ID nel nome: per NSP-Box e' un DLC senza title ID
    (tmp / "solo" / "romfs").mkdir(parents=True)
    (tmp / "solo" / "romfs" / "x").write_bytes(b"x")
    _err(lambda: S.convert(tmp / "solo", "nup", tmp / "o"), "conversione non riuscita")
    # NUP rovinato: l'hash della tabella non torna
    nup = S.convert(nsp, "nup", tmp / "out")
    rotto = bytearray(nup.read_bytes())
    rotto[140] ^= 0xFF
    (tmp / "rotto.nup").write_bytes(bytes(rotto))
    _err(lambda: S.convert(tmp / "rotto.nup", "folder", tmp / "o"), "conversione non riuscita")


def test_annulla(tmp: Path):
    _game(tmp / "Gioco")
    ev = threading.Event()
    ev.set()
    for cancel in (ev, lambda: True):  # sia l'Event sia la funzione usata dal resto di Pozzo
        try:
            S.convert(tmp / "Gioco", "nup", tmp / "out", cancel=cancel)
            raise AssertionError("doveva annullare")
        except InterruptedError:
            pass
    assert not list((tmp / "out").glob("*")) if (tmp / "out").exists() else True
    assert S.convert(tmp / "Gioco", "nup", tmp / "out", cancel=lambda: False).is_file()


def test_supported(tmp: Path):
    (tmp / "config.toml").write_text('[paths]\nroms = "roms"\ncache = "cache"\n', encoding="utf-8")
    cfg = config.load(tmp / "config.toml")
    cfg.app["emulators_dir"] = str(tmp / "Emulatori")
    cfg.emulators.pop("eglantine", None)
    cfg.app.pop("emu_installed", None)
    assert S.supported(cfg) == (False, "Eglantine non è installato")
    exe = tmp / "eglantine.exe"
    cfg.emulators["eglantine"] = str(exe)
    assert S.supported(cfg)[0] is False  # configurato ma il file non c'e'
    exe.write_bytes(b"MZ")
    ok, why = S.supported(cfg)  # c'e', ma non l'ha installato Pozzo: versione ignota
    assert not ok and "sconosciuta" in why
    for tag, want in (("2.7.7", True), ("2.5.0", True), ("v2.5.0a", True), ("2.10", True), ("3.0.0", True),
                      ("2.4.9", False), ("2.1.0a", False), ("nx2-98", False), ("", False)):
        cfg.app["emu_installed"] = {"eglantine": {"version": tag, "dir": str(tmp)}}
        ok, why = S.supported(cfg)
        assert ok is want and bool(why) is not want, (tag, ok, why)
    # ripiego su versions.json (sola lettura) quando le impostazioni non hanno la versione
    cfg.app["emu_installed"] = {}
    (tmp / "Emulatori").mkdir()
    vfile = tmp / "Emulatori" / "versions.json"
    vfile.write_text(json.dumps({"installed": {"eglantine": "2.6.1"}}), "utf-8")
    before = vfile.read_bytes()
    assert S.supported(cfg) == (True, "")
    vfile.write_text(json.dumps({"installed": {"eglantine": "2.0.0"}}), "utf-8")
    ok, why = S.supported(cfg)
    assert not ok and "2.0.0" in why and "2.5.0" in why
    vfile.write_bytes(before)
    assert S.supported(cfg) == (True, "") and vfile.read_bytes() == before


def test_zstandard_mancante():
    """Senza zstandard l'errore dice che cosa installare (import pigro: il resto di Pozzo parte lo stesso)."""
    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] == "zstandard" or "vendor.nspbox" in k}
    sys.modules["zstandard"] = None  # fa fallire «import zstandard» come se non fosse installato
    try:
        S._tools()
        raise AssertionError("doveva fallire")
    except S.SwitchPackError as e:
        assert "zstandard" in str(e) and "requirements.txt" in str(e)
    finally:
        del sys.modules["zstandard"]
        for k in [k for k in sys.modules if "vendor.nspbox" in k]:
            del sys.modules[k]
        sys.modules.update(saved)


if __name__ == "__main__":
    for t in (test_giro_completo, test_gioco_piu_dlc, test_rifiuti, test_annulla, test_supported):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            t(Path(d))
    test_zstandard_mancante()
    print("TUTTI I TEST OK")
