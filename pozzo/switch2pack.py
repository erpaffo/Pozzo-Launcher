"""Conversione dei giochi Switch 2 gia' in chiaro tra cartella (exefs/romfs), NSP e NUP.

Il lavoro vero lo fanno i moduli di NSP-Box copiati in pozzo/vendor/nspbox (MIT): qui ci sono solo la scelta
dell'operazione, i controlli prima di partire e gli errori in italiano. Niente chiavi (prod.keys) e niente
decifratura: un NSP retail o cifrato viene rifiutato. Il NUP e' il formato compresso (zstd) di NSP-Box, letto da
Eglantine dalla 2.5.0.

    convert(src, fmt, dst_dir, progress=None, cancel=None) -> Path
        progress(fatto, 100); cancel e' una funzione che ritorna True oppure un threading.Event.
        Annullando esce InterruptedError; ogni altro problema e' SwitchPackError. Non sovrascrive mai.
        Ritorna il file creato, o una cartella («folder», e «nsp» quando escono piu' NSP: gioco + DLC).
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import struct
import threading
from pathlib import Path

FORMATS = ("nsp", "nup", "folder")
MIN_EGLANTINE = (2, 5, 0)
_LOCK = threading.Lock()  # NSP-Box tiene l'annullamento in variabili di modulo: una conversione alla volta


class SwitchPackError(Exception):
    """Conversione impossibile: il testo e' gia' per la persona."""


def supported(cfg) -> tuple[bool, str]:
    """(True, "") solo con Eglantine installato da Pozzo in versione >= 2.5.0 (la prima che legge questi file)."""
    from . import emuinstall

    exe = cfg.emulators.get("eglantine")
    if not exe or not Path(exe).exists():
        return False, "Eglantine non è installato"
    tag = ((emuinstall.installed(cfg).get("eglantine") or {}).get("version")
           or (emuinstall._vload(cfg).get("installed") or {}).get("eglantine") or "")
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", str(tag))
    if not m:
        return False, "versione di Eglantine sconosciuta: installalo o aggiornalo da Pozzo (serve la 2.5.0 o successiva)"
    if tuple(int(x or 0) for x in m.groups()) < MIN_EGLANTINE:
        return False, f"Eglantine {tag} è troppo vecchio: serve la 2.5.0 o successiva"
    return True, ""


def _folder(p: Path) -> Path:
    return p.parent if p.name.lower() in ("exefs", "romfs") else p


def detect_format(path) -> str | None:
    """«nsp», «nup» o «folder» guardando il contenuto (non l'estensione); None se non e' nessuno dei tre."""
    p = Path(path)
    if p.is_dir():
        p = _folder(p)
        ok = (p / "nup-manifest.json").is_file() or any((p / d).is_dir() for d in ("exefs", "romfs", "base", "updates", "dlc"))
        return "folder" if ok else None
    try:
        with p.open("rb") as f:
            magic = f.read(4)
    except OSError:
        return None
    return {b"PFS0": "nsp", b"NUP\x01": "nup"}.get(magic)


def _check_plain(path: Path) -> None:
    """Rifiuta subito, con un motivo chiaro, gli NSP retail (ticket) o con NCA cifrati: non si possono convertire."""
    with path.open("rb") as f:
        magic, n, strsize, _ = struct.unpack("<4sIII", f.read(16).ljust(16, b"\0"))
        if magic != b"PFS0" or n > 65536 or strsize > 1 << 24:
            raise SwitchPackError("NSP non valido")
        table, names = f.read(n * 0x18), f.read(strsize)
        if len(table) != n * 0x18 or len(names) != strsize:
            raise SwitchPackError("NSP troncato")
        for i in range(n):
            off, _size, noff, _ = struct.unpack_from("<QQII", table, i * 0x18)
            name = names[noff:].split(b"\0")[0].decode("utf-8", "replace").lower()
            if name.endswith((".tik", ".cert")):
                raise SwitchPackError("NSP retail (contiene un ticket): si convertono solo i giochi già in chiaro")
            if name.endswith(".ncz"):
                raise SwitchPackError("NSZ compresso: formato non supportato")
            if name.endswith(".nca"):
                f.seek(16 + len(table) + strsize + off + 0x200)
                if f.read(4) != b"NCA3":  # con l'intestazione cifrata la firma non si legge
                    raise SwitchPackError("NSP cifrato (retail): si convertono solo i giochi già in chiaro, "
                                          "Pozzo non usa chiavi e non decifra")


def _tools():
    try:
        from .vendor.nspbox import nup_format, nup_tools
    except ModuleNotFoundError as e:
        if e.name != "zstandard":
            raise
        raise SwitchPackError('manca il modulo Python "zstandard": installa le dipendenze '
                              "(pip install -r requirements.txt)") from e
    return nup_tools, nup_format


class _Cancel:
    """NSP-Box vuole .is_set(); nel resto di Pozzo l'annullamento e' una funzione."""

    def __init__(self, c):
        self.c = c

    def is_set(self) -> bool:
        return bool(self.c.is_set() if hasattr(self.c, "is_set") else self.c())


def _italian(e: Exception) -> str:
    s = str(e) or type(e).__name__
    if "encrypted" in s or "plaintext" in s:
        return f"NSP cifrato, retail o non creato da NSP-Box: non si può convertire ({s})"
    return f"conversione non riuscita: {s}"


def _write_nsps(tools, packages, out: Path, notify, cancel) -> Path:
    """Un NSP per il gioco (base + ultimo aggiornamento fusi) e uno per ogni DLC, come fa NSP-Box dal NUP."""
    todo = ([tools.merge_game(packages)] if any(p.kind in (0, 1) for p in packages) else []) + [p for p in packages if p.kind == 2]
    if not todo:
        raise SwitchPackError("nessun gioco o DLC convertibile nella cartella")
    # shortcut: build_snapshot_nsp copia prima i file in una cartella temporanea (serve il doppio dello spazio),
    # per i giochi molto grandi passare a engine.build che legge direttamente dalla sorgente
    if len(todo) == 1:
        tools.build_snapshot_nsp(todo[0], out, True, notify, cancel)
        return out
    out = out.with_name(out.name[:-4])  # piu' NSP: in una cartella col nome del gioco (senza «.nsp»)
    if out.exists():
        raise SwitchPackError(f"esiste già: {out}")
    out.mkdir()
    try:
        for p in todo:
            tools.build_snapshot_nsp(p, out / f'{"DLC" if p.kind == 2 else "Game"} [{p.title_id:016X}] v{p.version}.nsp',
                                     True, notify, cancel)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)  # creata qui e incompleta: dentro non c'e' niente dell'utente
        raise
    return out


def _nsp_to_folder(tools, nf, src: Path, out: Path, notify, cancel) -> None:
    """Stessa disposizione dell'estrazione di un NUP (base/, dlc/<id>/<v>/ + nup-manifest.json): si puo' rimpacchettare."""
    stage = out.with_name(out.name + ".partial")
    if stage.exists():
        raise SwitchPackError(f"esiste già: {stage}")
    try:
        with tools.nsp_packages(src, cancel, notify) as packages:
            total = sum(s.size for p in packages for s in p.files.values()) or 1
            done, manifest = 0, []
            for p in packages:
                rel = nf.package_path(p)
                base = stage / rel
                for d in p.directories:
                    base.joinpath(*nf.path_parts(d)).mkdir(parents=True, exist_ok=True)
                for name, source in p.files.items():
                    target = base.joinpath(*[nf.safe_name(x, windows=True) for x in nf.path_parts(name)])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.opener() as f, target.open("xb") as o:
                        while b := f.read(1024 * 1024):
                            nf.check(cancel)
                            o.write(b)
                            done += len(b)
                            notify("", 5 + 94 * done / total)
                manifest.append({"path": rel, "title_id": f"{p.title_id:016X}", "version": p.version, "kind": p.kind,
                                 "flags": p.flags, "metadata": [[t, base64.b64encode(d).decode("ascii")] for t, d in p.metadata]})
            (stage / "nup-manifest.json").write_text(
                json.dumps({"format": "NSP Box NUP extraction v1", "packages": manifest}, indent=2), encoding="utf-8")
        stage.rename(out)
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def convert(src, fmt: str, dst_dir, progress=None, cancel=None) -> Path:
    src, dst_dir = Path(src).resolve(), Path(dst_dir).resolve()
    if fmt not in FORMATS:
        raise SwitchPackError(f"formato di destinazione non supportato: {fmt}")
    if not src.exists():
        raise SwitchPackError(f"non trovo {src}")
    kind = detect_format(src)
    if kind is None:
        raise SwitchPackError("formato non supportato: servono un NSP in chiaro, un NUP o una cartella con exefs/romfs")
    if kind == fmt:
        raise SwitchPackError(f"è già in formato {fmt}")
    if kind == "folder":
        src = _folder(src)
        if dst_dir == src or src in dst_dir.parents:
            raise SwitchPackError("scegli una destinazione fuori dalla cartella del gioco")
    elif kind == "nsp":
        _check_plain(src)
    name = src.name if kind == "folder" else src.stem
    out = dst_dir / (name if fmt == "folder" else f"{name}.{fmt}")
    if out.exists():
        raise SwitchPackError(f"esiste già: {out}")
    tools, nf = _tools()
    cancel = _Cancel(cancel) if cancel is not None else None

    def notify(_text="", value=0, *_):
        if progress:
            progress(max(0, min(100, int(value))), 100)

    opts = {"notify": notify, "cancel": cancel}
    with _LOCK:
        try:
            dst_dir.mkdir(parents=True, exist_ok=True)
            if fmt == "nup":
                (tools.pack_folder if kind == "folder" else tools.nsp_to_nup)(src, out, **opts)
            elif kind == "nup" and fmt == "folder":
                tools.extract(src, out, **opts)
            elif kind == "nup":
                kinds = [p["kind"] for p in tools.inspect(src, cancel=cancel)["packages_info"]]
                if any(k in ("base", "update") for k in kinds) + kinds.count("addon") > 1:
                    out = dst_dir / name  # gioco + DLC: piu' NSP in una cartella
                    if out.exists():
                        raise SwitchPackError(f"esiste già: {out}")
                tools.nup_to_nsp(src, out, **opts)
            elif fmt == "nsp":
                out = _write_nsps(tools, tools.select_packages(tools.discover(src, cancel, None, notify)), out, notify, cancel)
            else:
                _nsp_to_folder(tools, nf, src, out, notify, cancel)
        except (SwitchPackError, InterruptedError):
            raise
        except (ValueError, OSError, AssertionError, struct.error, LookupError, StopIteration) as e:
            raise SwitchPackError(_italian(e)) from e
    notify("", 100)
    return out
