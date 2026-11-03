"""Estrazione degli archivi scaricati (.zip/.7z/.rar, anche a piu' volumi). Funzioni bloccanti: il gestore le lancia in un thread.

Tutto si estrae prima in una cartella temporanea nascosta dentro `dest`, la si controlla (niente uscite dalla cartella,
niente link simbolici) e solo allora la si rinomina: un annullamento o un errore non lasciano mai mezze cartelle."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

MAX_BYTES = 200 * 2**30  # tetto al decompresso (anti zip-bomb), cambiabile per chiamata con max_bytes
MAX_RATIO = 2000  # decompresso/compresso oltre questo (e oltre RATIO_MIN) = bomba
RATIO_MIN = 2**30
CHUNK = 1 << 20
SEVENZIP_PATHS = (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe")
NO_RAR = "Per i .rar serve 7-Zip o UnRAR: installalo da 7-zip.org"
NO_BACKEND = "Non riesco ad aprire questo archivio: installa 7-Zip da 7-zip.org"
_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ArchiveError(Exception):
    """Archivio illeggibile, incompleto o rifiutato (il messaggio e' gia' in italiano)."""


class NoBackend(ArchiveError):
    pass


class DiskSpace(ArchiveError):
    pass


class PasswordRequired(ArchiveError):
    pass


class BadPassword(ArchiveError):
    pass


class Cancelled(ArchiveError):
    pass


class _Skip(Exception):
    """Questo motore non puo' aprire l'archivio: si passa al successivo."""


@dataclass
class Group:
    kind: str  # zip | 7z | rar
    name: str  # nome senza estensioni/numero di volume
    volumes: list = field(default_factory=list)  # il primo e' il file da passare a extract()
    missing: list = field(default_factory=list)


def _num(p: Path, rx: re.Pattern) -> int | None:
    m = rx.fullmatch(p.name)
    return int(m.group(1)) if m else None


def _siblings(p: Path, pattern: str) -> dict:
    rx = re.compile(pattern, re.I)
    out = {}
    try:
        for f in p.parent.iterdir():
            n = _num(f, rx)
            if n is not None and f.is_file():
                out[n] = f
    except OSError:
        pass
    return out


def _gaps(found: dict, start: int, fmt) -> list:
    return [fmt(i) for i in range(start, max(found, default=start - 1) + 1) if i not in found]


def _scan(path) -> Group | None:
    """Group se `path` e' il primo volume (o un archivio singolo); None se non e' un archivio o e' un volume successivo."""
    p = Path(path)
    n = p.name
    esc = lambda s: re.escape(s)  # noqa: E731
    if m := re.fullmatch(r"(.+)\.part(\d+)\.rar", n, re.I):
        if int(m[2]) != 1:
            return None
        w = len(m[2])
        found = _siblings(p, esc(m[1]) + r"\.part(\d+)\.rar")
        vols = [found[i] for i in sorted(found)]
        return Group("rar", m[1], vols, _gaps(found, 1, lambda i: f"{m[1]}.part{i:0{w}d}.rar"))
    if re.fullmatch(r".+\.r\d{2,}", n, re.I) or re.fullmatch(r".+\.z\d{2,}", n, re.I):
        return None  # volumi intermedi dei vecchi rar/zip: li apre il volume principale
    if m := re.fullmatch(r"(.+)\.(7z|zip|rar)\.(\d{3,})", n, re.I):
        if int(m[3]) != 1:
            return None
        w = len(m[3])
        found = _siblings(p, esc(m[1]) + r"\." + m[2] + r"\.(\d+)")
        return Group(m[2].lower(), m[1], [found[i] for i in sorted(found)],
                     _gaps(found, 1, lambda i: f"{m[1]}.{m[2]}.{i:0{w}d}"))
    if m := re.fullmatch(r"(.+)\.(\d{3,})", n):  # file spezzato generico: lo apre 7-Zip
        if int(m[2]) != 1:
            return None
        found = _siblings(p, esc(m[1]) + r"\.(\d+)")
        return Group("7z", m[1], [found[i] for i in sorted(found)], _gaps(found, 1, lambda i: f"{m[1]}.{i:03d}"))
    if m := re.fullmatch(r"(.+)\.rar", n, re.I):
        found = _siblings(p, esc(m[1]) + r"\.r(\d{2,})")  # .r00 e' il secondo volume
        return Group("rar", m[1], [p, *(found[i] for i in sorted(found))], _gaps(found, 0, lambda i: f"{m[1]}.r{i:02d}"))
    if m := re.fullmatch(r"(.+)\.zip", n, re.I):
        found = _siblings(p, esc(m[1]) + r"\.z(\d{2,})")
        return Group("zip", m[1], [p, *(found[i] for i in sorted(found))], _gaps(found, 1, lambda i: f"{m[1]}.z{i:02d}"))
    if m := re.fullmatch(r"(.+)\.7z", n, re.I):
        return Group("7z", m[1], [p])
    return None


def is_archive(path) -> bool:
    """True per qualunque file di un set (anche i volumi non iniziali)."""
    n = Path(path).name.lower()
    return bool(re.search(r"\.(zip|7z|rar|\d{3,}|[rz]\d{2,})$", n))


def archive_group(path) -> list[Path] | None:
    """Volumi del set se `path` e' il primo (o un archivio singolo), altrimenti None. Il primo elemento e' quello da estrarre."""
    g = _scan(path)
    return g.volumes if g else None


def missing_volumes(path) -> list[str]:
    """Nomi dei volumi mancanti nella numerazione del set (vuota se completo o se non e' un primo volume)."""
    g = _scan(path)
    return g.missing if g else []


def _sevenzip() -> list | None:
    for n in ("7z", "7zz"):
        if w := shutil.which(n):
            return [w]
    for p in SEVENZIP_PATHS:
        if os.path.isfile(p):
            return [p]
    return None


def _safe_rel(name: str) -> str | None:
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"[A-Za-z]:", n):
        return None
    parts = [x for x in PurePosixPath(n).parts if x != "."]
    return None if ".." in parts or not parts else "/".join(parts)


def _gb(n: int) -> str:
    return f"{n / 2**30:.1f} GB"


def _precheck(g: Group, total: int, dest: Path, max_bytes: int | None):
    cap = MAX_BYTES if max_bytes is None else max_bytes
    if total > cap:
        raise ArchiveError(f"Archivio troppo grande: {_gb(total)} da estrarre (limite {_gb(cap)})")
    packed = sum(v.stat().st_size for v in g.volumes if v.exists())
    if total > RATIO_MIN and packed and total / packed > MAX_RATIO:
        raise ArchiveError("Archivio sospetto (rapporto di compressione assurdo): estrazione rifiutata")
    free = shutil.disk_usage(dest).free
    if free < total:
        raise DiskSpace(f"Spazio insufficiente: servono {_gb(total)}, liberi {_gb(free)}")


def _unique(p: Path) -> Path:
    q, i = p, 2
    while q.exists():
        q = p.with_name(f"{p.name} ({i})")
        i += 1
    return q


def _clear(d: Path):
    for x in d.iterdir():
        shutil.rmtree(x, ignore_errors=True) if x.is_dir() and not x.is_symlink() else x.unlink(missing_ok=True)


def _sanitize(tmp: Path, log):
    """Toglie link simbolici/giunzioni e controlla che ogni percorso resti dentro la cartella temporanea."""
    root = tmp.resolve()
    for cur, dirs, files in os.walk(tmp):
        for n in [*dirs, *files]:
            p = Path(cur) / n
            if p.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(p)):
                log(f"Collegamento ignorato: {p.relative_to(tmp)}", "warn")
                if p.is_dir() and not p.is_symlink():
                    os.rmdir(p)
                else:
                    p.unlink()
                if n in dirs:
                    dirs.remove(n)
            elif not p.resolve().is_relative_to(root):
                raise ArchiveError(f"Percorso non sicuro nell'archivio: {n}")


def _place(tmp: Path, dest: Path, name: str) -> list[Path]:
    items = list(tmp.iterdir())
    if not items:
        raise ArchiveError("L'archivio e' vuoto")
    if len(items) == 1 and items[0].is_dir():  # niente "Gioco/Gioco/"
        out = _unique(dest / items[0].name)
        os.replace(items[0], out)
    else:
        out = _unique(dest / (name or "estratto"))
        os.replace(tmp, out)
    return [out]


def _copy_members(infos, tmp: Path, total: int, on_progress, cancelled, cap: int):
    """infos: [(nome_sicuro, apri())]; copia a blocchi controllando annullo e tetto reale (la dimensione dichiarata puo' mentire)."""
    done = 0
    for rel, open_ in infos:
        if cancelled():
            raise Cancelled("Estrazione annullata")
        out = tmp / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        with open_() as src, open(out, "wb") as dst:
            while b := src.read(CHUNK):
                done += len(b)
                if done > cap:
                    raise ArchiveError("L'archivio contiene piu' dati del dichiarato: estrazione interrotta")
                dst.write(b)
                if on_progress:
                    on_progress(done, total)
                if cancelled():
                    raise Cancelled("Estrazione annullata")


def _zip(g, tmp, dest, password, on_progress, cancelled, log, max_bytes):
    if len(g.volumes) > 1:
        raise _Skip("zip a piu' volumi")
    try:
        z = zipfile.ZipFile(g.volumes[0])
    except zipfile.BadZipFile as e:
        raise ArchiveError(f"ZIP danneggiato: {e}") from e
    with z:
        infos = []
        for i in z.infolist():
            if i.is_dir():
                continue
            if i.compress_type == 99:  # cifratura AES: zipfile non la legge
                raise _Skip("zip AES")
            rel = _safe_rel(i.filename)
            if rel is None:
                log(f"Percorso non sicuro ignorato: {i.filename}", "warn")
                continue
            infos.append((rel, i))
        total = sum(i.file_size for _, i in infos)
        _precheck(g, total, dest, max_bytes)
        pw = password.encode() if password else None
        enc = any(i.flag_bits & 1 for _, i in infos)
        if enc and not pw:
            raise PasswordRequired("L'archivio e' protetto da password")
        try:
            _copy_members([(r, lambda i=i: z.open(i, pwd=pw)) for r, i in infos], tmp, total, on_progress,
                          cancelled, MAX_BYTES if max_bytes is None else max_bytes)
        except RuntimeError as e:
            raise BadPassword("Password errata") from e
        except zipfile.BadZipFile as e:
            if enc:
                raise BadPassword("Password errata") from e
            raise ArchiveError(f"ZIP danneggiato: {e}") from e
        except NotImplementedError as e:
            raise _Skip(str(e)) from e


def _py7zr(g, tmp, dest, password, on_progress, cancelled, log, max_bytes):
    if len(g.volumes) > 1:
        raise _Skip("7z a piu' volumi")
    try:
        import py7zr
        from py7zr import exceptions as px
        from py7zr.io import Py7zIO, WriterFactory
    except ImportError as e:
        raise _Skip("py7zr mancante") from e

    class Out(Py7zIO):  # scrive a blocchi nel thread chiamante: da qui si puo' annullare
        def __init__(self, out):
            out.parent.mkdir(parents=True, exist_ok=True)
            self.f = open(out, "wb")
            opened.append(self.f)

        def write(self, s):
            st["done"] += len(s)
            if cancelled():
                raise Cancelled("Estrazione annullata")
            if st["done"] > cap:
                raise ArchiveError("L'archivio contiene piu' dati del dichiarato: estrazione interrotta")
            self.f.write(s)
            if on_progress:
                on_progress(st["done"], st["total"])
            return len(s)

        def read(self, size=None): return b""
        def seek(self, offset, whence=0): return self.f.seek(offset, whence)
        def flush(self): self.f.flush()
        def size(self): return self.f.tell()
        def close(self): self.f.close()

    class Factory(WriterFactory):
        def create(self, filename):
            out = Path(filename).resolve()  # py7zr passa il percorso gia' sotto tmp e ripulito
            if not out.is_relative_to(tmp.resolve()):
                raise ArchiveError(f"Percorso non sicuro nell'archivio: {filename}")
            return Out(out)

    cap = MAX_BYTES if max_bytes is None else max_bytes
    st = {"done": 0, "total": 0}
    opened = []
    try:
        with py7zr.SevenZipFile(g.volumes[0], password=password or None) as z:
            if z.needs_password() and not password:
                raise PasswordRequired("L'archivio e' protetto da password")
            files = [f for f in z.list() if not f.is_directory]
            for f in files:
                if _safe_rel(f.filename) is None:
                    raise ArchiveError(f"Percorso non sicuro nell'archivio: {f.filename}")
            st["total"] = sum(f.uncompressed or 0 for f in files)
            _precheck(g, st["total"], dest, max_bytes)
            try:
                z.extract(path=tmp, factory=Factory())
            finally:
                for f in opened:
                    f.close()
    except (ArchiveError, MemoryError):
        raise
    except px.PasswordRequired as e:
        raise PasswordRequired("L'archivio e' protetto da password") from e
    except Exception as e:
        if password:  # CRC/lzma sbagliati con password data = quasi sempre password errata
            raise BadPassword("Password errata (o archivio danneggiato)") from e
        raise _Skip(f"py7zr: {e}") from e


def _run7z(cmd: list, cancelled, on_progress=None, total=0) -> tuple[int, str]:
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=_NOWIN)
    stop = threading.Event()

    def watch():  # la lettura dell'output blocca: l'annullo lo controlla un thread a parte
        while not stop.wait(0.3):
            if cancelled():
                proc.terminate()
                return

    t = threading.Thread(target=watch, daemon=True)
    t.start()
    tail, last = "", -1
    try:
        while b := proc.stdout.read1(4096):
            tail = (tail + b.decode("utf-8", "replace"))[-4000:]
            # la riga e' «NN% n nome-del-file» e poi viene cancellata con spazi: con un nome lungo la percentuale
            # e' molto prima della fine, quindi si cerca l'ultima in tutto il pezzo letto
            if on_progress and total and (m := re.findall(r"(\d{1,3})%", tail)):
                pct = min(int(m[-1]), 100)
                if pct != last:
                    last = pct
                    on_progress(total * pct // 100, total)
        proc.wait()
    finally:
        stop.set()
        if proc.poll() is None:
            proc.kill()
    return proc.returncode, tail


def _errtext(out: str) -> str:
    lines = [re.sub(r"[\x08\r]", "", ln).strip() for ln in out.splitlines()]
    errs = [ln for ln in lines if re.search(r"error|cannot|can not|wrong|unsupported|headers", ln, re.I)]
    return " | ".join((errs or [ln for ln in lines if ln])[-3:])[:300]


def _via7z(g, tmp, dest, password, on_progress, cancelled, log, max_bytes):
    exe = _sevenzip()
    if not exe:
        raise _Skip("7-Zip non trovato")
    pw = [f"-p{password}"] if password else []
    arch = str(g.volumes[0])
    rc, out = _run7z([*exe, "l", "-slt", "-ba", "-sccUTF-8", *pw, "--", arch], cancelled)
    low = out.lower()
    if rc not in (0, 1):
        if "password" in low or "encrypted" in low:
            raise BadPassword("Password errata") if password else PasswordRequired("L'archivio e' protetto da password")
        raise ArchiveError(f"7-Zip non riesce a leggere l'archivio: {_errtext(out)}")
    entries = []  # (path, size, cartella, cifrato)
    for blk in re.split(r"\r?\n\r?\n", out.strip()):
        kv = dict(ln.split(" = ", 1) for ln in blk.splitlines() if " = " in ln)
        if "Path" in kv:
            entries.append((kv["Path"], int(kv.get("Size") or 0), kv.get("Folder") == "+", kv.get("Encrypted") == "+"))
    files = [e for e in entries if not e[2]]
    for p, *_ in files:
        if _safe_rel(p) is None:
            raise ArchiveError(f"Percorso non sicuro nell'archivio: {p}")
    if any(e[3] for e in files) and not password:
        raise PasswordRequired("L'archivio e' protetto da password")
    total = sum(e[1] for e in files)
    _precheck(g, total, dest, max_bytes)
    rc, out = _run7z([*exe, "x", "-y", "-bsp1", "-sccUTF-8", f"-o{tmp}", *pw, "--", arch], cancelled, on_progress, total)
    if cancelled():
        raise Cancelled("Estrazione annullata")
    if rc not in (0, 1):
        if "wrong password" in out.lower():
            raise BadPassword("Password errata")
        raise ArchiveError(f"Estrazione fallita: {_errtext(out)}")
    if rc == 1:
        log(f"7-Zip: avvisi durante l'estrazione ({_errtext(out)})", "warn")


def _rarfile(g, tmp, dest, password, on_progress, cancelled, log, max_bytes):
    try:
        import rarfile
        rarfile.tool_setup()
    except (ImportError, rarfile.RarCannotExec) as e:
        raise _Skip("nessun motore rar") from e
    try:
        rf = rarfile.RarFile(str(g.volumes[0]))
    except rarfile.PasswordRequired as e:
        raise PasswordRequired("L'archivio e' protetto da password") from e
    except rarfile.Error as e:
        raise ArchiveError(f"RAR illeggibile: {e}") from e
    with rf:
        infos = []
        for i in rf.infolist():
            if i.is_dir():
                continue
            if _safe_rel(i.filename) is None:
                raise ArchiveError(f"Percorso non sicuro nell'archivio: {i.filename}")
            infos.append(i)
        total = sum(i.file_size for i in infos)
        _precheck(g, total, dest, max_bytes)
        if rf.needs_password() and not password:
            raise PasswordRequired("L'archivio e' protetto da password")
        done = 0
        try:
            for i in infos:
                if cancelled():
                    raise Cancelled("Estrazione annullata")
                rf.extract(i, str(tmp), pwd=password or None)
                done += i.file_size
                if on_progress:
                    on_progress(done, total)
        except rarfile.RarWrongPassword as e:
            raise BadPassword("Password errata") from e
        except rarfile.RarCannotExec as e:
            raise _Skip("nessun motore rar") from e
        except rarfile.Error as e:
            raise ArchiveError(f"Estrazione RAR fallita: {e}") from e


def extract(archive, dest, *, password: str | None = None, on_progress=None, cancelled=lambda: False,
            log=lambda msg, level="info": None, max_bytes: int | None = None) -> list[Path]:
    """Estrae in `dest` e ritorna [cartella del gioco]: `dest/<nome archivio>`, o la cartella unica che l'archivio contiene.
    Errori: ArchiveError e sottoclassi (NoBackend, DiskSpace, PasswordRequired, BadPassword, Cancelled)."""
    dest = Path(dest)
    g = _scan(archive)
    if not g or not Path(archive).is_file():
        raise ArchiveError("Non e' un archivio supportato (o non e' il primo volume)")
    if g.missing:
        raise ArchiveError("Mancano dei volumi: " + ", ".join(g.missing))
    dest.mkdir(parents=True, exist_ok=True)
    multi = len(g.volumes) > 1
    order = {"zip": [_zip, _via7z], "7z": [_py7zr, _via7z], "rar": [_via7z, _rarfile]}[g.kind]
    tmp = Path(tempfile.mkdtemp(prefix=".estrazione-", dir=dest))
    try:
        for backend in order:
            try:
                log(f"Estrazione con {backend.__name__.strip('_')}" + (f" ({len(g.volumes)} volumi)" if multi else ""))
                backend(g, tmp, dest, password, on_progress, cancelled, log, max_bytes)
                break
            except _Skip as e:
                log(f"{backend.__name__.strip('_')} non disponibile: {e}", "warn")
                _clear(tmp)
        else:
            raise NoBackend(NO_RAR if g.kind == "rar" else NO_BACKEND)
        _sanitize(tmp, log)
        return _place(tmp, dest, g.name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def find_games(root, exts: set[str]) -> list[Path]:
    """File dell'albero estratto con estensione in `exts` (con il punto, es. {".iso", ".chd"}), in ordine."""
    ex = {e.lower() if e.startswith(".") else "." + e.lower() for e in exts}
    return sorted(p for p in Path(root).rglob("*") if p.is_file() and p.suffix.lower() in ex)


def delete_archive_set(group) -> int:
    """Cancella i soli file del set (lista di volumi, o un percorso da cui ricavarla); ritorna quanti ne ha tolti."""
    if isinstance(group, (str, os.PathLike)):
        group = archive_group(group) or []
    n = 0
    for v in group:
        v = Path(v)
        if v.is_file() or v.is_symlink():
            v.unlink()
            n += 1
    return n
