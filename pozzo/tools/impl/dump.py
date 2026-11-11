"""Dump di un disco dell'utente da lettore ottico con redumper (superg/redumper). Output: immagine .cue/.bin."""
import glob
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from ..jobs import Tool, register

DEFAULT_SIZE = 8_500_000_000  # DVD a doppio strato: se non leggiamo la capacita' meglio sovrastimare
_PCT = re.compile(r"(\d{1,3})\s*%")


def drives() -> list[dict]:
    """[{"id": "D:", "label": "D: (VOLUME)"}]; vuoto se non ci sono lettori (mai un errore)."""
    if sys.platform == "win32":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            mask, out = k.GetLogicalDrives(), []
            for i in range(26):
                if not mask >> i & 1:
                    continue
                root = f"{chr(65 + i)}:\\"
                if k.GetDriveTypeW(root) != 5:  # DRIVE_CDROM
                    continue
                buf = ctypes.create_unicode_buffer(261)
                ok = k.GetVolumeInformationW(root, buf, 261, None, None, None, None, 0)
                vol = buf.value if ok else ""
                out.append({"id": root[:2], "label": f"{root[:2]} ({vol})" if vol else root[:2]})
            return out
        except Exception:
            return []
    return [{"id": d, "label": d} for d in sorted(glob.glob("/dev/sr*"))]


def _volume(drive: str) -> str:
    if sys.platform == "win32":
        for d in drives():
            if d["id"] == drive and "(" in d["label"]:
                return d["label"].split("(", 1)[1].rstrip(")")
    return ""


def _check_drive(o: dict) -> str:
    d = o.get("drive")
    if not isinstance(d, str) or d not in {x["id"] for x in drives()}:
        raise ValueError("lettore non valido")
    return d


def _estimate(src: Path, o: dict) -> int:
    try:
        d = o.get("drive")
        if sys.platform == "win32" and d in {x["id"] for x in drives()}:
            total = shutil.disk_usage(d + "\\").total
            if total > 0:
                return int(total * 1.2)  # il dump grezzo (settori da 2352 byte) e' piu' grande del filesystem
    except OSError:
        pass
    return DEFAULT_SIZE


def _spawn(args: list[str]):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", creationflags=flags)


def _ensure(cfg, progress, cancel) -> Path:
    from .. import binaries
    return binaries.ensure(cfg, "redumper", progress, cancel)


def _mkdir_unique(base: Path) -> Path:
    n = 1
    while True:
        d = base if n == 1 else base.with_name(f"{base.name} ({n})")
        try:
            d.mkdir()
            return d
        except FileExistsError:
            n += 1


def _run(src, dst, progress, cancel, o):
    drive = _check_drive(o)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", _volume(drive)).strip(" .") or "Disc"
    exe = _ensure(o.get("cfg"), lambda d: None, cancel)
    out = _mkdir_unique(Path(dst) / name)
    # solo argomenti fissi + il drive validato: niente shell, niente testo libero
    proc = _spawn([str(exe), "disc", f"--drive={drive}", f"--image-path={out}", f"--image-name={out.name}"])
    stop = threading.Event()

    def watch():  # annullo: il readline sotto puo' bloccarsi, quindi si ferma il processo da fuori
        while not stop.is_set():
            if cancel.wait(0.3):
                proc.terminate()
                return

    threading.Thread(target=watch, daemon=True).start()
    tail, best = [], 0
    try:
        for line in proc.stdout:
            tail = (tail + [line.strip()])[-5:]
            m = _PCT.findall(line)
            if m:
                best = max(best, min(int(m[-1]), 99))
                progress(best)
        rc = proc.wait()
    except BaseException:
        proc.terminate()
        shutil.rmtree(out, ignore_errors=True)
        raise
    finally:
        stop.set()
    if cancel.is_set():
        shutil.rmtree(out, ignore_errors=True)
        raise InterruptedError
    cue = out / f"{out.name}.cue"
    if rc != 0 or not cue.is_file():
        shutil.rmtree(out, ignore_errors=True)
        raise RuntimeError(f"dump non riuscito (codice {rc}): {' | '.join(x for x in tail if x)}")
    return cue


register(Tool("dump", "Dump da lettore ottico", lambda pid, f: False, _estimate, _run, binary="redumper", needs_game=False))
