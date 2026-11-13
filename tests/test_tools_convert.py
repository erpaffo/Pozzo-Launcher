"""Strumenti di conversione (chd/rvz/cso) e binaries: nessuna rete, nessun vero chdman (finto programma python)."""
import hashlib
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pozzo.tools import binaries, jobs
from pozzo.tools.impl import chd, cso, rvz

tmp = Path(tempfile.mkdtemp())
try:
    # --- applies
    (tmp / "a.cue").write_text('FILE "a.bin" BINARY\n  TRACK 01 MODE2/2352\n')
    (tmp / "a.bin").write_bytes(b"x" * 1000)
    (tmp / "g.iso").write_bytes(b"y" * 500)
    (tmp / "g.txt").write_text("z")
    assert chd._applies("psx", tmp / "a.cue") and chd._applies("ps2", tmp / "g.iso")
    assert not chd._applies("snes", tmp / "g.iso") and not chd._applies("psx", tmp / "g.txt")
    assert rvz._applies("gc", tmp / "g.iso") and rvz._applies("wii", tmp / "g.iso") and not rvz._applies("psx", tmp / "g.iso")
    assert cso._applies("psp", tmp / "g.iso") and not cso._applies("psp", tmp / "a.cue")
    # --- estimate: segue le tracce del cue e del gdi
    assert chd._estimate(tmp / "a.cue", {}) == 1000 and chd._estimate(tmp / "g.iso", {}) == 500
    (tmp / "t.gdi").write_text('2\n1 0 4 2352 "t1.bin" 0\n2 450 0 2352 t2.raw 0\n')
    (tmp / "t1.bin").write_bytes(b"1" * 10)
    (tmp / "t2.raw").write_bytes(b"2" * 20)
    assert chd._estimate(tmp / "t.gdi", {}) == 30
    # --- righe di comando
    assert chd.command("c", "ps2", tmp / "g.iso", Path("o"))[1] == "createdvd"
    assert chd.command("c", "psx", tmp / "a.cue", Path("o"))[1] == "createcd"
    assert chd.command("c", "ps2", tmp / "a.cue", Path("o"))[1] == "createcd"
    assert rvz.command("d", Path("i"), Path("o"))[1:] == ["convert", "-i", "i", "-o", "o", "-f", "rvz", "-c", "zstd", "-l", "5", "-b", "131072"]
    assert cso.command("m", Path("i"), Path("o")) == ["m", "i", "-o", "o"]

    # --- run_convert con un finto programma
    fake = tmp / "fake.py"
    fake.write_text(
        "import sys,time\nout=sys.argv[-1]\nmode=sys.argv[1]\n"
        "if mode=='fail':\n open(out,'wb').write(b'p'); print('Errore: disco rotto'); sys.exit(2)\n"
        "if mode=='slow':\n open(out,'wb').write(b'p')\n time.sleep(30)\n"
        "open(out,'wb').write(b'ok')\n"
        "for i in (10,55.5,100): sys.stdout.write('Compressing, %s%% complete... (ratio=50%%)\\r'%i); sys.stdout.flush()\n")

    def go(mode, name="o.chd", cancel=None, seen=None):
        final = tmp / name
        part = final.with_name(name + ".partial")
        cb = seen.append if seen is not None else (lambda d: None)
        return final, part, (lambda: binaries.run_convert([sys.executable, str(fake), mode, str(part)], part, final,
                                                          cb, cancel or threading.Event(), "chdman"))
    seen = []
    final, part, f = go("ok", seen=seen)
    assert f() == final and final.read_bytes() == b"ok" and not part.exists()
    assert 10 in seen and 55 in seen and max(seen) <= 99, seen
    # rifiuto di sovrascrittura: il file resta intatto
    _, _, f = go("ok")
    try:
        f()
        raise SystemExit("doveva rifiutare")
    except FileExistsError:
        pass
    assert final.read_bytes() == b"ok"
    # errore: .partial ripulito, messaggio con l'output del programma
    final, part, f = go("fail", "e.chd")
    try:
        f()
        raise SystemExit("doveva fallire")
    except RuntimeError as e:
        assert "disco rotto" in str(e)
    assert not part.exists() and not final.exists()
    # annullo: processo terminato, .partial cancellato
    ev = threading.Event()
    final, part, f = go("slow", "s.chd", ev)
    threading.Timer(1.0, ev.set).start()
    t0 = time.time()
    try:
        f()
        raise SystemExit("doveva annullare")
    except InterruptedError:
        pass
    assert time.time() - t0 < 10 and not part.exists() and not final.exists()

    # --- binaries.path / ensure
    cfg = SimpleNamespace(emulators={}, config_path=tmp / "cfg" / "config.toml", app={})
    with mock.patch("shutil.which", return_value=None):
        assert binaries.path(cfg, "chdman") is None and binaries.path(cfg, "dolphin-tool") is None
        dol = tmp / "dol"
        dol.mkdir()
        cfg.emulators["dolphin"] = str(dol / "Dolphin.exe")
        assert binaries.path(cfg, "dolphin-tool") is None
        (dol / binaries._exe("dolphin-tool")).write_bytes(b"x")
        assert binaries.path(cfg, "dolphin-tool") == dol / binaries._exe("dolphin-tool")
        # rvz senza dolphin-tool: errore chiaro
        try:
            rvz._run(tmp / "g.iso", tmp, lambda d: 0, threading.Event(), {"cfg": SimpleNamespace(emulators={})})
            raise SystemExit("doveva fallire")
        except RuntimeError as e:
            assert "Dolphin" in str(e)

        # download mockato: zip con redumper.exe annidato + un membro con path traversal
        z = tmp / "r.zip"
        with zipfile.ZipFile(z, "w") as w:
            w.writestr("../evil.txt", "no")
            w.writestr("redumper-x/bin/redumper.exe", "BIN")
        data = z.read_bytes()
        asset = {"name": "redumper-b1-windows-x64.zip", "url": "https://example.invalid/r.zip", "size": len(data),
                 "sum": hashlib.sha256(data).hexdigest()}

        def dl(url, dest, progress=None, token=""):
            assert url.startswith("https://")
            Path(dest).write_bytes(data)
            progress(len(data), len(data))
        with mock.patch.object(binaries, "_win", return_value=True), mock.patch.object(binaries, "_latest", return_value=asset), \
                mock.patch.object(binaries.PT, "_download", dl), mock.patch.object(binaries.PT, "_token", return_value=""):
            prog = []
            p = binaries.ensure(cfg, "redumper", prog.append)
            assert p.read_bytes() == b"BIN" and p.parent.name == "redumper" and 100 in prog
            assert not (binaries.tools_dir(cfg) / ".tmp" / "redumper").exists()
            assert not (tmp / "cfg" / "evil.txt").exists() and not (binaries.tools_dir(cfg) / "evil.txt").exists()
            assert binaries.ensure(cfg, "redumper") == p  # gia' presente: niente download
            # checksum sbagliato: rifiutato, niente installato
            shutil.rmtree(p.parent)
            asset["sum"] = "0" * 64
            try:
                binaries.ensure(cfg, "redumper")
                raise SystemExit("doveva rifiutare il checksum")
            except RuntimeError as e:
                assert "checksum" in str(e)
            assert binaries.path(cfg, "redumper") is None
            # offline: messaggio italiano
            with mock.patch.object(binaries.PT, "_download", side_effect=httpx.ConnectError("no")):
                try:
                    binaries.ensure(cfg, "redumper")
                    raise SystemExit("doveva fallire offline")
                except RuntimeError as e:
                    assert "connessione" in str(e)
            # annullo durante il download: nessun residuo
            ev = threading.Event()
            ev.set()
            asset["sum"] = ""
            try:
                binaries.ensure(cfg, "redumper", cancel=ev)
                raise SystemExit("doveva annullare")
            except InterruptedError:
                pass
            assert not (binaries.tools_dir(cfg) / ".tmp" / "redumper").exists()
        # membri pericolosi mai scelti
        assert binaries._pick(["../redumper.exe", "/x/redumper.exe", "a/redumper.exe"], "redumper.exe") == "a/redumper.exe"
    assert {"chd", "rvz", "cso"} <= set(jobs.TOOLS)
    print("ok")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
