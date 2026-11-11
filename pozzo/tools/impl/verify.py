"""Verifica a richiesta dei dischi: CRC32/MD5/SHA1 di tutte le tracce confrontati con i DAT Redump di libretro.
Lo scanner salta l'hash dei dischi (troppo lento per una scansione); qui l'utente lo chiede per un gioco solo."""
import hashlib
import zlib
from pathlib import Path

from ... import platforms
from ..jobs import Tool, register

_EXTS = (".cue", ".gdi", ".iso", ".bin", ".img")
CHUNK = 4 * 2**20


def _applies(pid: str, f: Path) -> bool:
    return f.is_file() and f.suffix.lower() in _EXTS


def _tracks(src: Path) -> list[Path]:
    if src.suffix.lower() in (".cue", ".gdi"):
        from ...downloads.ingest import _refs  # stesso parsing di .cue/.gdi usato dall'importazione
        refs = _refs(src)
        if not refs:
            raise ValueError("il file non cita nessuna traccia presente")
        return refs
    return [src]


def _platform(src: Path, o: dict) -> str:
    if o.get("platform"):
        return o["platform"]
    for d in src.parents[:2]:
        p = platforms.detect(d.name)
        if p:
            return p.id
    return ""


def _load_index(cfg, pid: str):
    """Indice dai DAT in cache (di qualunque eta'); la rete solo se manca la cache. None se non c'e' nessun DAT."""
    from ...sources import libretro as L
    p = platforms.PLATFORMS.get(pid)
    if not p or not p.libretro:
        return None
    idx = L.Index()
    for system in p.libretro:
        for d in L.MAIN_DIRS:
            f = Path(cfg.cache) / "libretro" / d / f"{system}.dat"
            if f.exists():
                idx.add_main(f.read_text(encoding="utf-8", errors="ignore"))
        if not idx.has_dat:
            try:  # una volta sola, solo Redump; se fallisce restiamo "unknown"
                import urllib.request
                from urllib.parse import quote
                rel = f"metadat/redump/{system}.dat"
                with urllib.request.urlopen(L.RAW + quote(rel), timeout=15) as r:
                    data = r.read()
                f = Path(cfg.cache) / "libretro" / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(data)
                idx.add_main(data.decode("utf-8", "ignore"))
            except Exception:
                pass
    return idx if idx.has_dat else None


def _hash_files(files: list[Path], progress, cancel) -> list[dict]:
    total = sum(f.stat().st_size for f in files) or 1
    done, out = 0, []
    for f in files:
        crc, md5, sha1 = 0, hashlib.md5(), hashlib.sha1()
        with open(f, "rb") as fh:
            while chunk := fh.read(CHUNK):
                if cancel.is_set():
                    raise InterruptedError
                crc = zlib.crc32(chunk, crc)
                md5.update(chunk)
                sha1.update(chunk)
                done += len(chunk)
                progress(done * 100 // total)
        out.append({"file": f.name, "size": f.stat().st_size, "crc": f"{crc & 0xFFFFFFFF:08X}",
                    "md5": md5.hexdigest().upper(), "sha1": sha1.hexdigest().upper()})
    return out


def _match(idx, tracks: list[dict], stem: str) -> tuple[str, str]:
    """(stato, nome DAT): ok se un gioco del DAT contiene l'hash di tutte le tracce."""
    common = None
    for t in tracks:
        names = set()
        for kind in ("sha1", "md5", "crc"):
            names |= {n for n, sz in idx.by_hash.get((kind, t[kind]), ()) if not sz or sz == t["size"]}
        common = names if common is None else common & names
    if common:
        return "ok", sorted(common)[0]
    from ... import matching
    guess = idx.by_name.get(stem.lower()) or next(iter(idx.by_norm.get(matching.normalize(stem), [])), "")
    return ("mismatch", guess) if guess else ("unknown", "")


def _run(src, dst, progress, cancel, o):
    tracks = _hash_files(_tracks(Path(src)), progress, cancel)
    idx = _load_index(o.get("cfg"), _platform(Path(src), o))
    status, name = _match(idx, tracks, Path(src).stem) if idx else ("unknown", "")
    first = tracks[0]
    return {"status": status, "name": name,
            "hashes": {k: first[k] for k in ("crc", "md5", "sha1")} if len(tracks) == 1 else {},
            "tracks": tracks}


register(Tool("verify", "Verifica disco (Redump)", _applies, lambda s, o: 0, _run))
