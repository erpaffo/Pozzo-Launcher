"""Dischi (cue/bin, gdi, iso, img) -> .chd con chdman: stesso contenuto, molto meno spazio. Scrive su .partial."""
import re
from pathlib import Path

from .. import binaries
from ..jobs import Tool, register

PLATFORMS = {"psx", "ps2", "saturn", "segacd", "dreamcast", "pcenginecd", "neogeocd", "3do", "amigacd32", "pcfx"}
EXTS = {".cue", ".iso", ".gdi", ".img"}


def _applies(pid: str, f: Path) -> bool:
    return pid in PLATFORMS and f.suffix.lower() in EXTS and f.is_file()


def _refs(f: Path) -> list[Path]:
    """File citati da un .cue/.gdi (come downloads/ingest._refs)."""
    try:
        txt = f.read_text("utf-8", "replace")
    except OSError:
        return []
    if f.suffix.lower() == ".cue":
        names = [a or b for a, b in re.findall(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', txt, re.I | re.M)]
    else:
        names = [a or b for a, b in re.findall(r'^[ \t]*\d+[ \t]+\d+[ \t]+\d+[ \t]+\d+[ \t]+(?:"([^"]+)"|(\S+))', txt, re.M)]
    return [f.parent / n for n in names if (f.parent / n).is_file()]


def _estimate(src: Path, o: dict) -> int:
    # il CHD e' piu' piccolo dell'originale: la dimensione delle tracce e' un tetto sicuro
    files = _refs(src) if src.suffix.lower() in (".cue", ".gdi") else []
    return sum(f.stat().st_size for f in files) or src.stat().st_size


def command(exe, pid: str, src: Path, out: Path) -> list:
    # DVD (PS2) -> createdvd; il resto e' su CD. Niente -f: chdman non sovrascrive.
    # senza piattaforma nelle opzioni, un'iso oltre gli 800 MiB non puo' essere un CD
    dvd = pid == "ps2" or (not pid and src.stat().st_size > 800 * 2**20)
    verb = "createdvd" if dvd and src.suffix.lower() == ".iso" else "createcd"
    return [str(exe), verb, "-i", str(src), "-o", str(out)]


def _run(src, dst, progress, cancel, o):
    exe = binaries.ensure(o.get("cfg"), "chdman", progress, cancel)
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    final = dst / (Path(src).stem + ".chd")
    return binaries.run_convert(command(exe, o.get("platform", ""), Path(src), final.with_name(final.name + ".partial")),
                                final.with_name(final.name + ".partial"), final, progress, cancel, "chdman")


register(Tool("chd", "Converti in CHD", _applies, _estimate, _run, binary="chdman"))
