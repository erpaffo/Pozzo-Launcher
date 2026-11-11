"""Programmi esterni degli strumenti (chdman, maxcso, redumper): scaricati una volta, dalle release ufficiali
(solo gli URL di SOURCES, mai da input dell'utente), in <cartella dati>/tools/<nome>/. Solo Windows x64 per il download;
altrove si usa quello gia' nel PATH. Come emuinstall: .tmp, checksum, rename."""
from __future__ import annotations

import os
import re
import shutil
import threading
from pathlib import Path

from .. import config as C
from .. import ports as PT
from . import space

# repo GitHub, regex (fullmatch) dell'asset Windows x64 della release piu' recente, "kind" dell'archivio e file da tenere.
# Nomi asset verificati sull'API il 2026-11-11 (redumper b772, maxcso v1.13.0, mame0289). Se un progetto li cambia
# l'errore lo dice. Il checksum e' il "digest" sha256 che GitHub calcola per ogni asset.
SOURCES: dict[str, dict] = {
    # chdman: nessun download a parte, sta nell'eseguibile autoestraente 7z di MAME (~85 MB): si estrae solo chdman.exe.
    # Licenza: BSD-3-Clause per chdman/OSD (MAME e' GPL-2+/BSD-3 per parti); il binario e' distribuito da MAME.
    "chdman": {"repo": "mamedev/mame", "asset": r"mame\d+b?_x64\.exe", "kind": "sfx7z", "exe": "chdman.exe",
               "license": "BSD-3-Clause", "home": "https://www.mamedev.org"},
    # maxcso: archivio 7z con il solo maxcso.exe. Licenza ISC.
    "maxcso": {"repo": "unknownbrackets/maxcso", "asset": r"maxcso_v[\d.]+_windows\.7z", "kind": "7z", "exe": "maxcso.exe",
               "license": "ISC", "home": "https://github.com/unknownbrackets/maxcso"},
    # redumper: zip con <cartella>/bin/redumper.exe. Licenza GPL-3.0.
    "redumper": {"repo": "superg/redumper", "asset": r"redumper-[\w.]+-windows-x64\.zip", "kind": "zip", "exe": "redumper.exe",
                 "license": "GPL-3.0", "home": "https://github.com/superg/redumper"},
}
_SIG7Z = b"7z\xbc\xaf\x27\x1c"
_LOCK = threading.Lock()


def tools_dir(cfg) -> Path:
    return C.settings_path(cfg).parent / "tools"


def _exe(name: str) -> str:
    return name + (".exe" if os.name == "nt" else "")


def path(cfg, name: str) -> Path | None:
    """Percorso del programma se c'e' gia' (installato da qui, accanto a Dolphin, o nel PATH); altrimenti None."""
    if name == "dolphin-tool":
        d = (getattr(cfg, "emulators", None) or {}).get("dolphin")
        p = Path(d).parent / _exe(name) if d else None
        return p if p and p.is_file() else None
    src = SOURCES.get(name)
    if src:
        p = tools_dir(cfg) / name / src["exe"]
        if p.is_file():
            return p
    w = shutil.which(name)
    return Path(w) if w else None


def _latest(cfg, src: dict) -> dict:
    """{"name","url","sum","size"} dell'asset giusto nell'ultima release."""
    rel = PT._get(f"https://api.github.com/repos/{src['repo']}/releases/latest", None, PT._token(cfg))
    for a in rel.get("assets") or []:
        if re.fullmatch(src["asset"], a["name"]):
            url = a["browser_download_url"]
            if not url.startswith("https://"):
                break
            return {"name": a["name"], "url": url, "size": a.get("size") or 0,
                    "sum": (a.get("digest") or "").removeprefix("sha256:").lower()}
    raise RuntimeError(f"nessun file adatto nelle release di {src['repo']}: il progetto potrebbe aver cambiato i nomi")


def _pick(names: list[str], exe: str) -> str | None:
    """Il membro dell'archivio che si chiama come il programma, a qualunque profondita'; mai percorsi anomali."""
    for n in names:
        parts = n.replace("\\", "/").split("/")
        if parts[-1].lower() == exe.lower() and ".." not in parts and not n.startswith(("/", "\\")) and ":" not in parts[0]:
            return n
    return None


def _extract(src: dict, arc: Path, out: Path):
    """Scrive in `out` solo il programma voluto, con un nome deciso da noi (niente path traversal possibile)."""
    exe = src["exe"]
    if src["kind"] == "zip":
        import zipfile
        with zipfile.ZipFile(arc) as z:
            m = _pick(z.namelist(), exe)
            if not m:
                raise RuntimeError(f"{exe} non e' nell'archivio scaricato")
            with z.open(m) as i, open(out, "wb") as o:
                shutil.copyfileobj(i, o)
        return
    import py7zr
    if src["kind"] == "sfx7z":  # eseguibile autoestraente: il 7z comincia alla firma, la parte prima e' il programma
        seven = arc.with_suffix(".7z")
        with open(arc, "rb") as f:
            head = f.read(2 * 2**20)
            off = head.find(_SIG7Z)
            if off < 0:
                raise RuntimeError("archivio di MAME in un formato inatteso")
            f.seek(off)
            with open(seven, "wb") as o:
                shutil.copyfileobj(f, o, 1 << 20)
        arc.unlink()
        arc = seven
    with py7zr.SevenZipFile(arc) as z:
        m = _pick(z.getnames(), exe)
        if not m:
            raise RuntimeError(f"{exe} non e' nell'archivio scaricato")
        tmp = arc.parent / "x"
        z.extract(path=tmp, targets=[m])
    shutil.move(str(tmp / m), out)


def ensure(cfg, name: str, progress=lambda d: None, cancel: threading.Event | None = None) -> Path:
    """Il programma pronto all'uso: lo scarica se manca. Errori in italiano; InterruptedError se annullato."""
    if (p := path(cfg, name)):
        return p
    src = SOURCES.get(name)
    if not src:
        raise RuntimeError(f"{name} non e' installato e non posso scaricarlo da qui")
    if os.name != "nt":
        raise RuntimeError(f"{name} non e' installato: installalo col gestore pacchetti del sistema (serve nel PATH)")
    import httpx
    with _LOCK:  # due lavori non scaricano lo stesso programma insieme
        if (p := path(cfg, name)):
            return p
        dest = tools_dir(cfg) / name
        work = tools_dir(cfg) / ".tmp" / name
        try:
            asset = _latest(cfg, src)
            space.check(asset["size"] * 2 + 64 * 2**20, tools_dir(cfg))
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir(parents=True)
            arc = work / ("download" + Path(asset["name"]).suffix)

            def prog(done, total):
                if cancel is not None and cancel.is_set():
                    raise InterruptedError
                progress(int(done * 100 / total) if total else 0)
            PT._download(asset["url"], arc, prog)
            if asset["sum"] and PT._sha256(arc) != asset["sum"]:
                raise RuntimeError("il file scaricato non corrisponde al checksum della release: download rifiutato")
            _extract(src, arc, work / src["exe"])
            dest.mkdir(parents=True, exist_ok=True)
            os.replace(work / src["exe"], dest / src["exe"])
        except (httpx.HTTPError, OSError) as e:
            if isinstance(e, (space.NoSpace, InterruptedError)):  # sono OSError, ma non sono errori di rete
                raise
            raise RuntimeError(f"Non riesco a scaricare {name}: controlla la connessione a internet e riprova ({e})") from e
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return dest / src["exe"]


_PCT = re.compile(rb"(\d{1,3}(?:[.,]\d+)?)\s*%")


def run_convert(cmd: list, partial: Path, final: Path, progress, cancel: threading.Event, label: str) -> Path:
    """Esegue `cmd` (che scrive in `partial`), legge la percentuale dall'output, poi rinomina in `final`.
    Il .partial sparisce sempre (annullo, errore, successo); `final` non viene mai sovrascritto."""
    import subprocess
    import sys
    if final.exists():
        raise FileExistsError(f"{final.name} esiste gia': non lo sovrascrivo")
    partial.unlink(missing_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    tail: list[bytes] = []
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)

    def read():  # chdman riscrive la stessa riga con \r: si spezza su \r e \n
        buf = b""
        while (c := proc.stdout.read(1)):
            if c not in b"\r\n":
                buf += c
                continue
            if (m := _PCT.search(buf)):
                progress(min(99, int(float(m[1].replace(b",", b".")))))
            elif buf.strip():
                tail.append(buf.strip())
                del tail[:-5]
            buf = b""
    t = threading.Thread(target=read, daemon=True)
    t.start()
    try:
        while proc.poll() is None:
            if cancel.wait(0.2):
                proc.kill()
                proc.wait()
                raise InterruptedError
        t.join(5)
        if proc.returncode != 0 or not partial.exists():
            why = b" ".join(tail[-2:]).decode("utf-8", "replace")[:300]
            raise RuntimeError(f"{label} non e' riuscito (codice {proc.returncode}){': ' + why if why else ''}")
        if final.exists():  # comparso nel frattempo
            raise FileExistsError(f"{final.name} esiste gia': non lo sovrascrivo")
        os.replace(partial, final)
        return final
    finally:
        if proc.poll() is None:
            proc.kill()
        partial.unlink(missing_ok=True)
