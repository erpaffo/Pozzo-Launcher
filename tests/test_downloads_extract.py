"""Estrazione archivi dei download: zip/7z/rar (anche a piu' volumi), sicurezza dei percorsi, annullo, spazio, password. Nessuna rete."""
import os
import shutil
import subprocess
import sys
import zipfile
from types import SimpleNamespace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.downloads import extract as E  # noqa: E402

py7zr = pytest.importorskip("py7zr", reason="py7zr non installato")
SZ = E._sevenzip()
need7z = pytest.mark.skipif(not SZ, reason="7-Zip non installato")


def mkzip(path: Path, files: dict, **kw) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, **kw) as z:
        for n, d in files.items():
            z.writestr(n, d)
    return path


def tree(p: Path) -> set:
    return {x.relative_to(p).as_posix() for x in p.rglob("*") if x.is_file()}


@pytest.fixture
def dest(tmp_path):
    return tmp_path / "out"


def test_zip_cartella_unica_senza_doppio_annidamento(tmp_path, dest):
    z = mkzip(tmp_path / "Gioco.zip", {"Gioco/a.iso": b"a" * 100, "Gioco/sub/b.txt": b"b"})
    out = E.extract(z, dest)
    assert out == [dest / "Gioco"] and tree(dest) == {"Gioco/a.iso", "Gioco/sub/b.txt"}
    assert [p.name for p in dest.iterdir()] == ["Gioco"]  # nessuna cartella temporanea


def test_zip_piu_file_in_cartella_col_nome_dell_archivio(tmp_path, dest):
    z = mkzip(tmp_path / "Mio Gioco.zip", {"a.iso": b"a", "b.cue": b"b"})
    assert E.extract(z, dest) == [dest / "Mio Gioco"]
    assert tree(dest) == {"Mio Gioco/a.iso", "Mio Gioco/b.cue"}


def test_zip_file_singolo_e_cartella_gia_esistente(tmp_path, dest):
    z = mkzip(tmp_path / "x.zip", {"x.iso": b"1"})
    a, b = E.extract(z, dest)[0], E.extract(z, dest)[0]
    assert a == dest / "x" and b == dest / "x (2)"


def test_zip_slip_e_percorsi_assoluti_ignorati(tmp_path, dest):
    z = mkzip(tmp_path / "evil.zip", {"../evil.txt": b"x", "/abs.txt": b"x", "C:/win.txt": b"x", "a/../../b.txt": b"x", "ok/f.txt": b"ok"})
    logs = []
    out = E.extract(z, dest, log=lambda m, l="info": logs.append((l, m)))
    assert out == [dest / "ok"] and tree(dest) == {"ok/f.txt"}
    assert not (tmp_path / "evil.txt").exists() and not (dest / "evil.txt").exists()
    assert sum(1 for l, _ in logs if l == "warn") == 4


def test_zip_progresso(tmp_path, dest):
    z = mkzip(tmp_path / "p.zip", {"a/a.bin": os.urandom(3 * E.CHUNK), "a/b.bin": b"x"})
    seen = []
    E.extract(z, dest, on_progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (3 * E.CHUNK + 1, 3 * E.CHUNK + 1) and [d for d, _ in seen] == sorted(d for d, _ in seen)


def test_zip_annullo_non_lascia_nulla(tmp_path, dest):
    z = mkzip(tmp_path / "c.zip", {"a/1.bin": b"1" * 10, "a/2.bin": b"2" * 10})
    n = []
    with pytest.raises(E.Cancelled):
        E.extract(z, dest, on_progress=lambda d, t: n.append(1), cancelled=lambda: bool(n))
    assert list(dest.iterdir()) == []


def test_zip_corrotto(tmp_path, dest):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"PK\x03\x04 non e' uno zip")
    with pytest.raises(E.ArchiveError):
        E.extract(bad, dest)
    assert list(dest.iterdir()) == []


def test_non_archivio_o_non_primo_volume(tmp_path, dest):
    f = tmp_path / "gioco.part2.rar"
    f.write_bytes(b"x")
    with pytest.raises(E.ArchiveError):
        E.extract(f, dest)
    with pytest.raises(E.ArchiveError):
        E.extract(tmp_path / "manca.zip", dest)


# --- riconoscimento dei set -------------------------------------------------

def touch(d: Path, *names) -> list:
    out = []
    for n in names:
        (d / n).write_bytes(b"x")
        out.append(d / n)
    return out


def test_gruppi_rar_part(tmp_path):
    v = touch(tmp_path, "g.part1.rar", "g.part2.rar", "g.part3.rar", "altro.part1.rar")
    assert E.archive_group(v[0]) == v[:3] and E.missing_volumes(v[0]) == []
    assert E.archive_group(v[1]) is None and E.archive_group(v[2]) is None
    assert E.is_archive(v[1])
    d = tmp_path / "w"
    d.mkdir()
    w = touch(d, "g.part01.rar", "g.part02.rar", "g.part04.rar")
    assert E.archive_group(w[0]) == w and E.missing_volumes(w[0]) == ["g.part03.rar"]


def test_gruppi_rar_vecchio_e_zip_spezzato(tmp_path):
    v = touch(tmp_path, "a.rar", "a.r00", "a.r01", "a.r03")
    assert E.archive_group(v[0]) == v and E.missing_volumes(v[0]) == ["a.r02"]
    assert E.archive_group(v[1]) is None and E.is_archive(v[1])
    z = touch(tmp_path, "b.zip", "b.z01", "b.z02")
    assert E.archive_group(z[0]) == z and E.missing_volumes(z[0]) == [] and E.archive_group(z[1]) is None


def test_gruppi_7z_numerato_e_singoli(tmp_path):
    v = touch(tmp_path, "s.7z.001", "s.7z.002", "s.7z.004")
    assert E.archive_group(v[0]) == v and E.missing_volumes(v[0]) == ["s.7z.003"]
    assert E.archive_group(v[1]) is None
    one = touch(tmp_path, "solo.7z", "solo.zip", "solo.rar", "note.txt")
    assert [E.archive_group(p) for p in one[:3]] == [[p] for p in one[:3]]
    assert E.archive_group(one[3]) is None and not E.is_archive(one[3])


def test_estrazione_rifiuta_volumi_mancanti(tmp_path, dest):
    v = touch(tmp_path, "g.part1.rar", "g.part3.rar")
    with pytest.raises(E.ArchiveError, match="g.part2.rar"):
        E.extract(v[0], dest)


# --- 7z con py7zr -----------------------------------------------------------

def mk7z(path: Path, files: dict, password=None) -> Path:
    with py7zr.SevenZipFile(path, "w", password=password) as z:
        for n, d in files.items():
            z.writestr(d, n)
    return path


def test_7z_estrazione_e_progresso(tmp_path, dest):
    a = mk7z(tmp_path / "Gioco.7z", {"Gioco/a.iso": b"a" * 5000, "Gioco/b.txt": b"b"})
    seen = []
    out = E.extract(a, dest, on_progress=lambda d, t: seen.append((d, t)))
    assert out == [dest / "Gioco"] and tree(dest) == {"Gioco/a.iso", "Gioco/b.txt"}
    assert seen and seen[-1][0] == seen[-1][1] == 5001


def test_7z_password(tmp_path, dest):
    a = mk7z(tmp_path / "p.7z", {"p/a.txt": b"segreto"}, password="giusta")
    with pytest.raises(E.PasswordRequired):
        E.extract(a, dest)
    with pytest.raises(E.BadPassword):
        E.extract(a, dest, password="sbagliata")
    assert list(dest.iterdir()) == []
    assert E.extract(a, dest, password="giusta") == [dest / "p"]


def test_7z_annullo_non_lascia_nulla(tmp_path, dest):
    a = mk7z(tmp_path / "c.7z", {"c/1": os.urandom(1000), "c/2": os.urandom(1000)})
    with pytest.raises(E.Cancelled):
        E.extract(a, dest, cancelled=lambda: True)
    assert list(dest.iterdir()) == []


def test_7z_senza_py7zr_ripiega_su_7zip(tmp_path, dest, monkeypatch):
    a = mk7z(tmp_path / "f.7z", {"f/a.txt": b"ciao"})

    def no(*x, **k):
        raise E._Skip("finto")
    monkeypatch.setattr(E, "_py7zr", no)
    if not SZ:
        with pytest.raises(E.NoBackend):
            E.extract(a, dest)
    else:
        assert E.extract(a, dest) == [dest / "f"]


# --- 7-Zip reale ------------------------------------------------------------

@need7z
def test_7zip_reale_volumi_7z_e_progresso(tmp_path, dest):
    src = tmp_path / "src" / "Big"
    src.mkdir(parents=True)
    (src / "a.bin").write_bytes(os.urandom(300_000))
    (src / "b.bin").write_bytes(os.urandom(100_000))
    subprocess.run([*SZ, "a", "-v150k", "-mx0", str(tmp_path / "Big.7z"), str(src)], check=True, capture_output=True)
    vols = sorted(tmp_path.glob("Big.7z.*"))
    assert len(vols) >= 3
    first = vols[0]
    assert E.archive_group(first) == vols and E.missing_volumes(first) == []
    seen = []
    assert E.extract(first, dest, on_progress=lambda d, t: seen.append((d, t))) == [dest / "Big"]
    assert (dest / "Big" / "a.bin").read_bytes() == (src / "a.bin").read_bytes()
    assert seen and seen[-1][1] == 400_000
    assert E.delete_archive_set(vols) == len(vols) and not list(tmp_path.glob("Big.7z.*"))


@need7z
def test_7zip_reale_zip_cifrato(tmp_path, dest):
    d = tmp_path / "src"
    d.mkdir()
    (d / "a.txt").write_text("ciao")
    subprocess.run([*SZ, "a", "-tzip", "-mem=ZipCrypto", "-pgiusta", str(tmp_path / "z.zip"), str(d / "a.txt")],
                   check=True, capture_output=True)
    with pytest.raises(E.PasswordRequired):
        E.extract(tmp_path / "z.zip", dest)
    with pytest.raises(E.BadPassword):
        E.extract(tmp_path / "z.zip", dest, password="no")
    assert list(dest.iterdir()) == []
    assert (E.extract(tmp_path / "z.zip", dest, password="giusta")[0] / "a.txt").read_text() == "ciao"


@need7z
def test_7zip_reale_zip_aes_ripiega(tmp_path, dest):
    d = tmp_path / "src"
    d.mkdir()
    (d / "a.txt").write_text("ciao")
    subprocess.run([*SZ, "a", "-tzip", "-mem=AES256", "-pgiusta", str(tmp_path / "z.zip"), str(d / "a.txt")],
                   check=True, capture_output=True)
    with pytest.raises(E.BadPassword):
        E.extract(tmp_path / "z.zip", dest, password="no")
    assert E.extract(tmp_path / "z.zip", dest, password="giusta")[0].joinpath("a.txt").read_text() == "ciao"


@need7z
def test_7zip_reale_rar_non_valido(tmp_path, dest):
    bad = tmp_path / "x.rar"
    bad.write_bytes(b"Rar!\x1a\x07\x00" + b"\0" * 40)
    with pytest.raises(E.ArchiveError):
        E.extract(bad, dest)
    assert list(dest.iterdir()) == []


# --- 7-Zip finto (logica senza il vero eseguibile) --------------------------

FAKE = r'''
import os, sys, time
a = sys.argv[1:]
if a[0] == "l":
    for i, n in enumerate(("Game/a.bin", "Game/b.cue")):
        print(f"Path = {n}\nSize = {(10, 5)[i]}\nFolder = -\nEncrypted = {os.environ.get('FAKE_ENC', '-')}\n")
    sys.exit(0)
out = [x[2:] for x in a if x.startswith("-o")][0]
os.makedirs(out + "/Game", exist_ok=True)
open(out + "/Game/a.bin", "wb").write(b"x" * 10)
sys.stdout.write("\x08\x08\x08 50%"); sys.stdout.flush()
if os.environ.get("FAKE_SLOW"):
    time.sleep(30)
open(out + "/Game/b.cue", "wb").write(b"y" * 5)
sys.stdout.write("\x08\x08\x08\x08100%"); sys.stdout.flush()
if os.environ.get("FAKE_FAIL"):
    print("ERROR: Wrong password"); sys.exit(2)
'''


@pytest.fixture
def fake7z(tmp_path, monkeypatch):
    s = tmp_path / "fake7z.py"
    s.write_text(FAKE)
    monkeypatch.setattr(E, "_sevenzip", lambda: [sys.executable, str(s)])
    return s


def rarfile_path(tmp_path, name="Game.part1.rar"):
    return touch(tmp_path, name, name.replace("part1", "part2"))[0]


def test_fake7z_rar_multivolume(tmp_path, dest, fake7z):
    seen = []
    out = E.extract(rarfile_path(tmp_path), dest, on_progress=lambda d, t: seen.append((d, t)))
    assert out == [dest / "Game"] and tree(dest) == {"Game/a.bin", "Game/b.cue"}
    assert seen[-1] == (15, 15) and (7, 15) in seen


def test_fake7z_annullo_termina_il_processo_e_pulisce(tmp_path, dest, fake7z, monkeypatch):
    monkeypatch.setenv("FAKE_SLOW", "1")
    import time
    t0 = time.time()
    with pytest.raises(E.Cancelled):
        E.extract(rarfile_path(tmp_path), dest, cancelled=lambda: time.time() - t0 > 1)
    assert time.time() - t0 < 15 and list(dest.iterdir()) == []


def test_fake7z_password_e_errore(tmp_path, dest, fake7z, monkeypatch):
    f = rarfile_path(tmp_path)
    monkeypatch.setenv("FAKE_ENC", "+")
    with pytest.raises(E.PasswordRequired):
        E.extract(f, dest)
    monkeypatch.setenv("FAKE_FAIL", "1")
    with pytest.raises(E.BadPassword):
        E.extract(f, dest, password="x")
    assert list(dest.iterdir()) == []


def test_spazio_insufficiente(tmp_path, dest, monkeypatch):
    z = mkzip(tmp_path / "s.zip", {"s/a": b"x" * 1000})
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(10_000, 9_500, 500))
    with pytest.raises(E.DiskSpace):
        E.extract(z, dest)
    assert list(dest.iterdir()) == []
    monkeypatch.setattr(shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(10_000, 8_000, 2_000))
    assert E.extract(z, dest)


def test_tetto_e_rapporto_di_compressione(tmp_path, dest, monkeypatch):
    z = mkzip(tmp_path / "b.zip", {"b/zeri": b"\0" * 1_000_000})
    with pytest.raises(E.ArchiveError, match="troppo grande"):
        E.extract(z, dest, max_bytes=999_999)
    monkeypatch.setattr(E, "RATIO_MIN", 1000)
    monkeypatch.setattr(E, "MAX_RATIO", 50)
    with pytest.raises(E.ArchiveError, match="sospetto"):
        E.extract(z, dest)
    assert list(dest.iterdir()) == []


def test_7z_tetto(tmp_path, dest):
    a = mk7z(tmp_path / "t.7z", {"t/a": b"x" * 1000})
    with pytest.raises(E.ArchiveError, match="troppo grande"):
        E.extract(a, dest, max_bytes=10)


# --- rarfile (finto) e nessun motore ---------------------------------------

def test_rar_senza_motori_errore_chiaro(tmp_path, dest, monkeypatch):
    import rarfile
    monkeypatch.setattr(E, "_sevenzip", lambda: None)

    def nope(*a, **k):
        raise rarfile.RarCannotExec("niente")
    monkeypatch.setattr(rarfile, "tool_setup", nope)
    f = touch(tmp_path, "g.rar")[0]
    with pytest.raises(E.NoBackend, match="7-zip.org"):
        E.extract(f, dest)
    assert list(dest.iterdir()) == []


def test_rar_con_rarfile_finto(tmp_path, dest, monkeypatch):
    import rarfile
    monkeypatch.setattr(E, "_sevenzip", lambda: None)
    monkeypatch.setattr(rarfile, "tool_setup", lambda *a, **k: None)

    class Info:
        def __init__(s, n, size): s.filename, s.file_size = n, size
        def is_dir(s): return False

    class RF:
        def __init__(s, p): s.p = p
        def __enter__(s): return s
        def __exit__(s, *a): pass
        def infolist(s): return [Info("Game/a.bin", 4), Info("../fuori.txt", 1)] if FAKE_EVIL[0] else [Info("Game/a.bin", 4)]
        def needs_password(s): return False
        def extract(s, i, path, pwd=None):
            p = Path(path) / i.filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x" * i.file_size)

    FAKE_EVIL[0] = False
    monkeypatch.setattr(rarfile, "RarFile", RF)
    f = touch(tmp_path, "g.rar")[0]
    assert E.extract(f, dest) == [dest / "Game"] and tree(dest) == {"Game/a.bin"}
    FAKE_EVIL[0] = True
    with pytest.raises(E.ArchiveError, match="non sicuro"):
        E.extract(f, dest)


FAKE_EVIL = [False]


# --- sicurezza, utilita' ----------------------------------------------------

def test_sanitize_toglie_link_simbolici(tmp_path):
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "ok.txt").write_text("ok")
    (tmp_path / "fuori.txt").write_text("fuori")
    try:
        os.symlink(tmp_path / "fuori.txt", tmp_path / "t" / "link.txt")
        os.symlink(tmp_path, tmp_path / "t" / "dirlink", target_is_directory=True)
    except OSError:
        pytest.skip("symlink non permessi su questo sistema")
    E._sanitize(tmp_path / "t", lambda *a: None)
    assert tree(tmp_path / "t") == {"ok.txt"} and (tmp_path / "fuori.txt").exists() and (tmp_path / "t" / "dirlink").exists() is False


def test_find_games(tmp_path):
    for n in ("a/Gioco.XCI", "a/b/disc.cue", "a/b/disc.bin", "a/readme.txt", "c.iso"):
        p = tmp_path / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    got = [p.relative_to(tmp_path).as_posix() for p in E.find_games(tmp_path, {".xci", ".iso", "cue"})]
    assert sorted(got) == ["a/Gioco.XCI", "a/b/disc.cue", "c.iso"]


def test_delete_archive_set_tocca_solo_il_set(tmp_path):
    v = touch(tmp_path, "g.part1.rar", "g.part2.rar", "h.part1.rar", "g.txt", "g.part1.rar.bak")
    assert E.delete_archive_set(E.archive_group(v[0])) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["g.part1.rar.bak", "g.txt", "h.part1.rar"]
    assert E.delete_archive_set([tmp_path / "gia_tolto.rar"]) == 0
    assert E.delete_archive_set(v[2]) == 1 and not v[2].exists()


def test_avanzamento_7z_con_nome_lungo(monkeypatch):
    """7-Zip scrive «NN% 1 nome» e la cancella con spazi: con un nome lungo la percentuale va trovata lo stesso."""
    name = "Super Long Game Name Collection (Europe) (En,Fr,De,Es,It) (Disc 1).iso"
    chunks = [f" 24% 1 {name}".encode(), b"\r" + b" " * 80 + b"\r", f" 61% 1 {name}".encode(), b"\r" + b" " * 80 + b"\r"]

    class Proc:
        returncode = 0
        stdout = SimpleNamespace(read1=lambda n: chunks.pop(0) if chunks else b"")

        def wait(self):
            pass

        def poll(self):
            return 0
    monkeypatch.setattr(E.subprocess, "Popen", lambda *a, **k: Proc())
    seen = []
    E._run7z(["7z"], lambda: False, lambda done, total: seen.append(done * 100 // total), 1000)
    assert seen == [24, 61]
