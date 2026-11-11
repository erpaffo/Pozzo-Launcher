"""GameCube/Wii: iso/gcm/wbfs -> .rvz con dolphin-tool (zstd, come consiglia Dolphin). Dolphin non si scarica da qui."""
from pathlib import Path

from .. import binaries
from ..jobs import Tool, register


def _applies(pid: str, f: Path) -> bool:
    return pid in ("gc", "wii") and f.suffix.lower() in (".iso", ".gcm", ".wbfs") and f.is_file()


def _estimate(src: Path, o: dict) -> int:
    return src.stat().st_size  # tetto: lo zstd non allarga


def command(exe, src: Path, out: Path) -> list:
    return [str(exe), "convert", "-i", str(src), "-o", str(out), "-f", "rvz", "-c", "zstd", "-l", "5", "-b", "131072"]


def _run(src, dst, progress, cancel, o):
    exe = binaries.path(o.get("cfg"), "dolphin-tool")
    if not exe:
        raise RuntimeError("Serve Dolphin: installalo dalle impostazioni degli emulatori (dolphin-tool sta nella sua cartella)")
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    final = dst / (Path(src).stem + ".rvz")
    part = final.with_name(final.name + ".partial")
    return binaries.run_convert(command(exe, Path(src), part), part, final, progress, cancel, "dolphin-tool")


register(Tool("rvz", "Converti in RVZ", _applies, _estimate, _run, binary="dolphin-tool"))
