"""Patch IPS/BPS (ROM hack, traduzioni): scrive una COPIA "<nome> (patched).<ext>", la ROM originale non si tocca."""
from pathlib import Path

from ... import platforms, ports
from ..jobs import Tool, register

MAX_PATCH = 64 * 2**20  # una patch reale e' al massimo qualche MB; oltre e' un file sbagliato


def _applies(pid: str, f: Path) -> bool:
    p = platforms.PLATFORMS.get(pid)
    return f.is_file() and not (p and p.cd) and f.suffix.lower().lstrip(".") not in platforms.ARCHIVES


def _estimate(src: Path, o: dict) -> int:
    return src.stat().st_size


def _check_patch(raw) -> Path:
    """La patch la sceglie l'utente: deve essere un file normale .ips/.bps di dimensione sensata."""
    if not raw:
        raise ValueError("patch non indicata")
    p = Path(str(raw))
    if p.suffix.lower() not in (".ips", ".bps"):
        raise ValueError("la patch deve essere un file .ips o .bps")
    if p.is_symlink() or not p.is_file():
        raise ValueError("file di patch non trovato")
    if not 0 < p.stat().st_size <= MAX_PATCH:
        raise ValueError("dimensione della patch non valida")
    if p.suffix.lower() == ".ips" and not _ips_ok(p.read_bytes()):
        raise ValueError("patch IPS danneggiata")
    return p


def _ips_ok(p: bytes) -> bool:
    """apply_patch_copy cicla all'infinito su un IPS senza "EOF" (troncato): lo scartiamo prima."""
    i = 5
    while p[i:i + 3] != b"EOF":
        if i + 5 > len(p):
            return False
        size = int.from_bytes(p[i + 3:i + 5], "big")
        i += 5 + (size or 3)
        if i > len(p):
            return False
    return True


def _run(src, dst, progress, cancel, o):
    patch = _check_patch(o.get("patch"))
    out = Path(dst) / f"{src.stem} (patched){src.suffix}"
    if out.exists():
        raise FileExistsError(f"esiste gia': {out.name}")
    if cancel.is_set():
        raise InterruptedError
    progress(5)
    try:
        ports.apply_patch_copy(src, out, patch)
    except (IndexError, ValueError) as e:  # patch troncata/incoerente: messaggio leggibile per la UI
        out.unlink(missing_ok=True)
        raise ValueError(str(e) or "patch non valida") from e
    except BaseException:
        out.unlink(missing_ok=True)
        out.with_name(out.name + ".tmp").unlink(missing_ok=True)
        raise
    return out


register(Tool("patch", "Applica patch IPS/BPS", _applies, _estimate, _run))
