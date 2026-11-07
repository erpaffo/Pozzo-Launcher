"""Gioca nel browser: ROM leggere con EmulatorJS (GPL-3) e Flash (.swf) con Ruffle (MIT/Apache).

Niente e' incluso nell'app ne' caricato da un CDN mentre si gioca: alla prima partita si scarica quello che serve
nella cartella dati (<impostazioni>/webplay) e da li' lo serve il server locale. Di EmulatorJS si prende solo la
parte comune e il core della console (dal sito ufficiale del progetto, versione fissata); di Ruffle l'ultima
build «web-selfhosted» delle release GitHub.
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

from . import bios as B
from . import config as C
from . import platforms as P
from . import ports as PT

EJS_VER = "4.2.3"
EJS_BASE = f"https://cdn.emulatorjs.org/{EJS_VER}/data/"
EJS_COMMON = ["loader.js", "emulator.min.js", "emulator.min.css", "compression/extract7z.js",
              "compression/extractzip.js", "compression/libunrar.js", "compression/libunrar.wasm"]
# id piattaforma di Pozzo -> (sistema di EmulatorJS, core). Solo sistemi leggeri.
# shortcut: nessun CD multi-file (cue+bin): serve un file solo (chd, iso, pbp, zip); le console pesanti restano fuori.
CORES: dict[str, tuple[str, str]] = {
    "nes": ("nes", "fceumm"), "snes": ("snes", "snes9x"), "gb": ("gb", "gambatte"), "gbc": ("gb", "gambatte"),
    "gba": ("gba", "mgba"), "n64": ("n64", "mupen64plus_next"), "nds": ("nds", "melonds"),
    "megadrive": ("segaMD", "genesis_plus_gx"), "mastersystem": ("segaMS", "smsplus"),
    "gamegear": ("segaGG", "genesis_plus_gx"), "pcengine": ("pce", "mednafen_pce"),
    "psx": ("psx", "pcsx_rearmed"), "atari2600": ("atari2600", "stella2014"),
    "arcade": ("arcade", "fbneo"), "fbneo": ("arcade", "fbneo"),
}
MAX_SAVE = 64 << 20
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def root(cfg) -> Path:
    return C.settings_path(cfg).parent / "webplay"


def rom_file(g: dict) -> Path | None:
    """File del gioco da dare al browser: scelto qui dalla libreria, mai da un percorso della richiesta."""
    if g.get("store") or not g.get("files"):
        return None
    p = P.PLATFORMS.get(g["platform"])
    ok = {"." + e for e in (p.all_exts if p else ())} | {".swf", ".chd", ".iso", ".pbp"}
    files = [Path(f) for f in g["files"]]
    return next((f for f in files if f.suffix.lower() in ok), files[0])


def plan(g: dict) -> dict | None:
    """{"kind": "ejs"|"ruffle", "system", "core"} se il gioco si puo' giocare nel browser, altrimenti None."""
    rom = rom_file(g)
    if not rom:
        return None
    if rom.suffix.lower() == ".swf":
        return {"kind": "ruffle", "system": "", "core": ""}
    c = CORES.get(g["platform"])
    return {"kind": "ejs", "system": c[0], "core": c[1]} if c else None


def bios_file(platform: str) -> Path | None:
    """BIOS dell'utente per la console (se ne serve uno e c'e'): lo stesso che cerca la verifica dei BIOS."""
    spec = B.REQUISITI.get(platform)
    if platform != "psx" or not spec:
        return None
    for nome, _, _ in spec["files"]:
        for d in B._cartelle(platform, None):
            if (d / nome).is_file():
                return d / nome
    return None


def _wanted(pl: dict) -> list[tuple[str, str]]:
    """[(url, file di destinazione relativo)] dei file di EmulatorJS per il core."""
    c = pl["core"]
    rel = EJS_COMMON + [f"cores/reports/{c}.json", f"cores/{c}-wasm.data", f"cores/{c}-legacy-wasm.data"]
    return [(EJS_BASE + r, "ejs/" + r) for r in rel]


def ready(cfg, pl: dict) -> bool:
    d = root(cfg)
    if pl["kind"] == "ruffle":
        return (d / "ruffle" / "ruffle.js").is_file()
    return all((d / r).is_file() for _, r in _wanted(pl))


def _fetch(cfg, url: str, dest: Path, job: dict, lo: float, hi: float):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    PT._download(url, tmp, lambda d, t: job.update(pct=lo + (hi - lo) * (d / t if t else 0)), PT._token(cfg))
    os.replace(tmp, dest)


def _install(cfg, pl: dict, job: dict):
    d = root(cfg)
    if pl["kind"] == "ruffle":
        rel = next((r for r in PT.releases("github", "ruffle-rs/ruffle", PT._token(cfg))
                    if any(a["name"].endswith("web-selfhosted.zip") for a in r["assets"])), None)
        if not rel:
            raise RuntimeError("nessuna build web-selfhosted di Ruffle nelle release")
        a = next(a for a in rel["assets"] if a["name"].endswith("web-selfhosted.zip"))
        zp = d / ".tmp" / a["name"]
        _fetch(cfg, a["url"], zp, job, 0, 0.9)
        if a.get("sum") and PT._sha256(zp) != a["sum"]:
            zp.unlink()
            raise RuntimeError("il file scaricato non corrisponde al checksum della release: download rifiutato")
        out = d / ".tmp" / "ruffle"
        shutil.rmtree(out, ignore_errors=True)
        PT._extract(zp, out, a["name"])
        zp.unlink()
        shutil.rmtree(d / "ruffle", ignore_errors=True)
        os.replace(out, d / "ruffle")
        return
    todo = [(u, r) for u, r in _wanted(pl) if not (d / r).is_file()]
    for i, (u, r) in enumerate(todo):
        try:
            _fetch(cfg, u, d / r, job, i / len(todo), (i + 1) / len(todo))
        except Exception:
            if "legacy" not in r:  # il core «legacy» (senza WebGL2) non esiste per tutti
                raise


def prepare(cfg, pl: dict) -> dict:
    """Avvia (una sola volta) il download di cio' che manca; ritorna lo stato {"status", "pct", "error"}."""
    key = pl["kind"] + ":" + pl["core"]
    with _LOCK:
        job = _JOBS.get(key)
        if ready(cfg, pl):
            return {"status": "ready", "pct": 1, "error": ""}
        if job and job["status"] == "running":
            return dict(job)
        job = _JOBS[key] = {"status": "running", "pct": 0.0, "error": ""}

    def run():
        try:
            _install(cfg, pl, job)
            job["status"] = "ready" if ready(cfg, pl) else "error"
            job["error"] = "" if job["status"] == "ready" else "file mancanti dopo il download"
        except Exception as e:  # rete assente, limite GitHub, disco: l'errore arriva alla pagina
            job.update(status="error", error=str(e) or e.__class__.__name__)

    threading.Thread(target=run, daemon=True).start()
    return dict(job)


def status(cfg, pl: dict) -> dict:
    job = _JOBS.get(pl["kind"] + ":" + pl["core"])
    if ready(cfg, pl):
        return {"status": "ready", "pct": 1, "error": ""}
    return dict(job) if job else {"status": "idle", "pct": 0, "error": ""}


def asset(cfg, rel: str) -> Path | None:
    """File scaricato da servire (ejs/..., ruffle/...): resta dentro la cartella webplay, altrimenti None."""
    base = root(cfg).resolve()
    p = (base / rel).resolve()
    top = rel.replace("\\", "/").split("/", 1)[0]
    return p if top in ("ejs", "ruffle") and p.is_file() and base in p.parents else None
