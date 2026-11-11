"""Switch 2: NSP in chiaro / cartella -> NUP (o NSP). Usa switch2pack, che non sovrascrive mai e pulisce i .partial."""
from pathlib import Path

from ... import switch2pack as S
from ..jobs import Tool, register


def _applies(pid: str, f: Path) -> bool:
    return pid == "switch2" and f.exists() and S.detect_format(f) in ("nsp", "folder")


def _estimate(src: Path, o: dict) -> int:
    from ..space import tree_size
    return int(tree_size(src) * 2.1) + 64 * 2**20  # stessa regola del vendor: il doppio più i temporanei


def _run(src, dst, progress, cancel, o):
    cfg = o.get("cfg")
    ok, why = S.supported(cfg)
    if not ok:
        raise S.SwitchPackError(why)
    fmt = o.get("format") or "nup"
    return S.convert(src, fmt, dst, lambda d, n: progress(d), cancel)


register(Tool("nup", "Switch 2 → NUP", _applies, _estimate, _run))
