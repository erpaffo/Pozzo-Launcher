"""Strumenti patch / verify / m3u / dump: nessuna rete, nessun redumper vero."""
import hashlib
import sys
import tempfile
import threading
import zlib
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo.sources import libretro as L
from pozzo.tools import jobs
from pozzo.tools.impl import dump, m3u, patch, verify

T = jobs.TOOLS
for k in ("patch", "verify", "m3u", "dump"):
    assert k in T, k
nocancel = threading.Event()


def raises(exc, f, *a):
    try:
        f(*a)
    except exc:
        return
    raise AssertionError(f"{exc.__name__} atteso")


tmp = Path(tempfile.mkdtemp())

# ---- patch
rom = tmp / "g.nes"
rom.write_bytes(b"A" * 16)
ips = tmp / "p.ips"
ips.write_bytes(b"PATCH" + (2).to_bytes(3, "big") + (2).to_bytes(2, "big") + b"ZZ" + b"EOF")
t = T["patch"]
assert t.applies("nes", rom) and not t.applies("nes", tmp / "x.nes")
assert not t.applies("nes", tmp / "a.zip") and not t.applies("psx", rom)
assert t.estimate(rom, {}) == 16
out = t.run(rom, tmp, lambda d: None, nocancel, {"patch": str(ips)})
assert out.name == "g (patched).nes" and out.read_bytes() == b"AAZZ" + b"A" * 12
assert rom.read_bytes() == b"A" * 16
raises(FileExistsError, t.run, rom, tmp, lambda d: None, nocancel, {"patch": str(ips)})
for bad in (None, "", str(tmp / "nope.ips"), str(rom), str(tmp)):
    raises(ValueError, t.run, rom, tmp, lambda d: None, nocancel, {"patch": bad})
big = tmp / "big.ips"
big.write_bytes(b"")
raises(ValueError, t.run, rom, tmp, lambda d: None, nocancel, {"patch": str(big)})
trunc = tmp / "t.ips"
trunc.write_bytes(b"PATCH\x00\x00\x00\x00\x09ab")  # troncata
r3 = tmp / "k.nes"; r3.write_bytes(b"C" * 4)
raises(ValueError, t.run, r3, tmp, lambda d: None, nocancel, {"patch": str(trunc)})
assert not (tmp / "k (patched).nes").exists() and not (tmp / "k (patched).nes.tmp").exists()
ev = threading.Event(); ev.set()
r2 = tmp / "h.nes"; r2.write_bytes(b"B" * 4)
raises(InterruptedError, t.run, r2, tmp, lambda d: None, ev, {"patch": str(ips)})
assert not (tmp / "h (patched).nes").exists()

# ---- m3u
d = tmp / "m"
d.mkdir()
for n in ("Game (Disc 2) (USA).cue", "Game (Disc 1) (USA).cue", "Game (Disc 3) (USA).cue", "Other (Disc 1).cue", "Single.cue"):
    (d / n).write_text("x")
t = T["m3u"]
assert t.applies("psx", d / "Game (Disc 2) (USA).cue")
assert not t.applies("psx", d / "Other (Disc 1).cue") and not t.applies("psx", d / "Single.cue")
res = t.run(d / "Game (Disc 2) (USA).cue", d, lambda x: None, nocancel, {})
assert res["discs"] == ["Game (Disc 1) (USA).cue", "Game (Disc 2) (USA).cue", "Game (Disc 3) (USA).cue"]
assert Path(res["m3u"]).name == "Game (USA).m3u"
assert Path(res["m3u"]).read_text("utf-8").splitlines() == res["discs"]
raises(FileExistsError, t.run, d / "Game (Disc 1) (USA).cue", d, lambda x: None, nocancel, {})
assert (d / "x").mkdir() is None
sub = d / "x"
(d / "Z (CD1).iso").write_text("1"); (d / "Z (CD2).iso").write_text("2")
res = t.run(d / "Z (CD1).iso", sub, lambda x: None, nocancel, {})
assert res["discs"] == ["../Z (CD1).iso", "../Z (CD2).iso"] and t.estimate(d, {}) < 10000

# ---- verify
v = d / "v"
v.mkdir()
b1, b2 = b"track one data" * 10, b"second track" * 7
(v / "Disc (Track 1).bin").write_bytes(b1)
(v / "Disc (Track 2).bin").write_bytes(b2)
(v / "Disc.cue").write_text('FILE "Disc (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\nFILE "Disc (Track 2).bin" BINARY\n')


def rom_line(n, b):
    return (f'\trom ( name "{n}" size {len(b)} crc {zlib.crc32(b):08x} '
            f'md5 {hashlib.md5(b).hexdigest()} sha1 {hashlib.sha1(b).hexdigest()} )\n')


def mkidx(tracks):
    i = L.Index()
    i.add_main('game (\n\tname "Disc Real"\n' + "".join(rom_line(*x) for x in tracks) + ")\n")
    return i


t = T["verify"]
assert t.applies("psx", v / "Disc.cue") and not t.applies("psx", v / "a.zip") and t.estimate(v, {}) == 0
assert t.needs_game
good = mkidx([("Disc (Track 1).bin", b1), ("Disc (Track 2).bin", b2)])
verify._load_index = lambda cfg, pid: good
seen = []
res = t.run(v / "Disc.cue", tmp, seen.append, nocancel, {"platform": "psx"})
assert res["status"] == "ok" and res["name"] == "Disc Real" and len(res["tracks"]) == 2 and seen[-1] == 100
assert res["tracks"][0]["crc"] == f"{zlib.crc32(b1):08X}"
res = t.run(v / "Disc (Track 1).bin", tmp, lambda x: None, nocancel, {})
assert res["hashes"]["sha1"] == hashlib.sha1(b1).hexdigest().upper()
assert res["status"] == "ok"  # limite noto: una traccia singola combacia con il gioco del DAT
# disco con nome nel DAT ma hash diversi
verify._load_index = lambda cfg, pid: mkidx([("Disc.bin", b"altro")])
(v / "Disc Real.iso").write_bytes(b1)
res = t.run(v / "Disc Real.iso", tmp, lambda x: None, nocancel, {})
assert res["status"] == "mismatch" and res["name"] == "Disc Real"
# offline senza DAT: unknown ma hash calcolati
verify._load_index = lambda cfg, pid: None
res = t.run(v / "Disc.cue", tmp, lambda x: None, nocancel, {})
assert res["status"] == "unknown" and res["name"] == "" and res["tracks"][1]["md5"] == hashlib.md5(b2).hexdigest().upper()
raises(InterruptedError, t.run, v / "Disc.cue", tmp, lambda x: None, ev, {})
(tmp / "e.cue").write_text("TRACK 1\n")
raises(ValueError, t.run, tmp / "e.cue", tmp, lambda x: None, nocancel, {})
# cache DAT su disco, senza rete
cfg = SimpleNamespace(cache=tmp / "cache")
verify._load_index = lambda cfg, pid: (_ for _ in ()).throw(AssertionError)  # sostituito sotto
import importlib
importlib.reload(verify)
dd = cfg.cache / "libretro" / "metadat" / "redump"
dd.mkdir(parents=True)
(dd / "Sony - PlayStation.dat").write_text('game (\n\tname "X"\n' + rom_line("x.bin", b1) + ")\n")
ix = verify._load_index(cfg, "psx")
assert ix is not None and verify._match(ix, [{"size": len(b1), "crc": f"{zlib.crc32(b1):08X}", "md5": hashlib.md5(b1).hexdigest().upper(), "sha1": hashlib.sha1(b1).hexdigest().upper()}], "q") == ("ok", "X")

# ---- dump
t = T["dump"]
assert t.binary == "redumper" and not t.needs_game and not t.applies("psx", tmp)
dump.drives = lambda: [{"id": "D:", "label": "D: (MY DISC)"}]
dump._volume = lambda drv: "MY: DISC?"
assert t.estimate(Path(), {"drive": "Z:"}) == dump.DEFAULT_SIZE
for bad in (None, "", "E:", "D: --x", ["D:"], "D:\\ & calc"):
    raises(ValueError, t.run, Path(), tmp, lambda x: None, nocancel, {"drive": bad})
dump._ensure = lambda cfg, p, c: Path("redumper.exe")


class FakeProc:
    def __init__(self, args, lines, rc, make):
        self.args, self.rc, self.stdout = args, rc, iter(lines)
        if make:
            out = Path(args[3].split("=", 1)[1])
            (out / f"{out.name}.cue").write_text("x")
            (out / "partial.bin").write_text("x")

    def wait(self):
        return self.rc

    def terminate(self):
        pass


calls = []


def spawn(lines, rc, make):
    def f(args):
        calls.append(args)
        return FakeProc(args, lines, rc, make)
    return f


dest = tmp / "dumps"
dest.mkdir()
prog = []
dump._spawn = spawn(["reading...  12%\n", "dumping 55% x\n", "refine 100%\n", "done\n"], 0, True)
cue = t.run(Path(), dest, prog.append, nocancel, {"drive": "D:"})
assert cue.name == "MY DISC.cue" and cue.parent.name == "MY DISC" and prog == [12, 55, 99]
a = calls[-1]
assert isinstance(a, list) and a[:3] == ["redumper.exe", "disc", "--drive=D:"]
cue2 = t.run(Path(), dest, lambda x: None, nocancel, {"drive": "D:"})
assert cue2.parent.name == "MY DISC (2)"  # non sovrascrive
# errore: cartella rimossa
dump._spawn = spawn(["boom\n"], 1, False)
before = set(dest.iterdir())
raises(RuntimeError, t.run, Path(), dest, lambda x: None, nocancel, {"drive": "D:"})
assert set(dest.iterdir()) == before
# annullo: file parziali rimossi
dump._spawn = spawn(["10%\n"], 0, True)
raises(InterruptedError, t.run, Path(), dest, lambda x: None, ev, {"drive": "D:"})
assert set(dest.iterdir()) == before

print("test_tools_extra OK")
