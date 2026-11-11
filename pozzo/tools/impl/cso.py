"""PSP: iso -> .cso con maxcso (compressione senza perdita, i giochi si avviano uguale)."""
from pathlib import Path

from .. import binaries
from ..jobs import Tool, register


def _applies(pid: str, f: Path) -> bool:
    return pid == "psp" and f.suffix.lower() == ".iso" and f.is_file()


def _estimate(src: Path, o: dict) -> int:
    return src.stat().st_size


def command(exe, src: Path, out: Path) -> list:
    return [str(exe), str(src), "-o", str(out)]


def _run(src, dst, progress, cancel, o):
    exe = binaries.ensure(o.get("cfg"), "maxcso", progress, cancel)
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    final = dst / (Path(src).stem + ".cso")
    part = final.with_name(final.name + ".partial")
    return binaries.run_convert(command(exe, Path(src), part), part, final, progress, cancel, "maxcso")


register(Tool("cso", "Converti in CSO", _applies, _estimate, _run, binary="maxcso"))
