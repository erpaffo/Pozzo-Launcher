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
# SHA-256 dei file di EJS_VER: girano con l'origine dell'app (e quindi con tutta la sua API), un file del CDN
# diverso viene rifiutato. Si ricalcolano quando si cambia EJS_VER o si aggiunge un core a CORES.
EJS_SHA256 = {
    "loader.js": "69e0903bf1e2f62ced78895e7e511fa26e11316f7eb734925c35e919ba1287b2",
    "emulator.min.js": "6aec3fd7bb2721255801b0a6af02e47e78b05e28a1822b1f213aacbd348abaee",
    "emulator.min.css": "16406c60b2dc3b04ae9b115e308613e6f567a0cc7068e21d9d0c1e5030fb395e",
    "compression/extract7z.js": "4ac9933b995a516cb6b3ca4027db860278372a20c21c405d93ceb1998498853a",
    "compression/extractzip.js": "3cc825428724213acd43d30552a78008e0869b2326de17dee240dbff9ee2f629",
    "compression/libunrar.js": "bc35b98ec95020ec047f4762de3e66629741eee3826022195498d2a1e0fc102c",
    "compression/libunrar.wasm": "e4ea9bd0b13a9767916b424469e30205f47f267ecd9125ed56fb9ff0b9bc1b58",
    "cores/reports/fbneo.json": "d2c5e07c2afc2b53937f14b721d7d025ad599d111e9627fc77e9b3fd17450e70",
    "cores/fbneo-wasm.data": "315a25e0bcd61d58ee0d9e8b1dbf3740b9e0ca4b7d0726f848ce1068de73437c",
    "cores/fbneo-legacy-wasm.data": "9dbb6242c028f4179549f324688b654353881beb552292f939bc6171a0828b5f",
    "cores/reports/fceumm.json": "13dbbfba0ea1bea087c97c38f47dd49c3fb8f16c3f5ed5678dd75d352b737132",
    "cores/fceumm-wasm.data": "8c449fd5c36646fb0769423ed6ffa9efbdfc21fbfdc9bac7952b559d34d5b493",
    "cores/fceumm-legacy-wasm.data": "f1054b094e7149fd6278485bc1b2e51ff75c5259048ddb1134171e53d651f239",
    "cores/reports/gambatte.json": "a240a47bd6b2a38a6c46ee63c80bdcd24befbd50474453df4898d49282bd5f57",
    "cores/gambatte-wasm.data": "ad67c7bf57f8f8b62606048e6ea498afac5b5abc76ad8de5f9dfc2a6719374bb",
    "cores/gambatte-legacy-wasm.data": "940a7381d51223c0be0c0f98d1a988d42cc98d03c27b392cbd29cb9f357b5f62",
    "cores/reports/genesis_plus_gx.json": "5936a8ce8d7f010d5bfdd8c3bba2b2414f103b3a703121e56f2724b24dbe7ff3",
    "cores/genesis_plus_gx-wasm.data": "190297a6f86757405090f1a2266f67dfe1a570a528c583434ed3641a5664f768",
    "cores/genesis_plus_gx-legacy-wasm.data": "2a1edeb68d7ec882149ed3cd5d3aa95a6ac231ebabaf82cdb56175a8b62967cc",
    "cores/reports/mednafen_pce.json": "3c82092f1433cc2cf0d9265e137f44c5a80f5a7dfbfcb712ef659797299a67ca",
    "cores/mednafen_pce-wasm.data": "29cebda0c7a93bbcb5e67e97fe28a1886bd030715d5a25224e7d9175d1d985c3",
    "cores/mednafen_pce-legacy-wasm.data": "c3d6e52680175b5528964b2c506a462bfd330d856661f28c5a54f7114b9b9a4c",
    "cores/reports/melonds.json": "568f4ca9e4fb6ca8220d48047ae5ee3a7a1452c820b6718ef8b3888efed05a6a",
    "cores/melonds-wasm.data": "f3ad9e42bb3ccd5c9bece23445b56e2d10d2cae8cc33a2c0591529d0a83cdfeb",
    "cores/melonds-legacy-wasm.data": "9707c56d903daa699dbc725b065e63bc09834a94b143ee0f3b3c1520c6e3b54f",
    "cores/reports/mgba.json": "08219f6c855a9d996f04ed21169bb0c5ac64d469a8a536468b9876205b5c268d",
    "cores/mgba-wasm.data": "01fcaf6d4296ef1db6676e0c69400c4474e24572d0b2b99cc097e4ae885e02d7",
    "cores/mgba-legacy-wasm.data": "e300d2f368c82bf61d77c972c36e367cf16408ec3d50beede080337519a3d696",
    "cores/reports/mupen64plus_next.json": "270105553cec57fd1058c50e0541b8b89dbd30b2323fd70682036f6919b805cc",
    "cores/mupen64plus_next-wasm.data": "2da1cbce9fda395e3ae83ca5787353baa159142d45ef3ea90f108b92524f76cc",
    "cores/mupen64plus_next-legacy-wasm.data": "425072f4bf94eec02633cbe9b84f47d6803dc0ec1b3c3b8de3ebbd2eb5617c3f",
    "cores/reports/pcsx_rearmed.json": "93b99266955ab16e9aa0faa0d6338f4a29b50c197764dd48be945573a5b449c1",
    "cores/pcsx_rearmed-wasm.data": "fe5515f6c29f093f0e8c01824b213804f1f76eb9cb4c97c72fe2cc17606bfbc2",
    "cores/pcsx_rearmed-legacy-wasm.data": "88faee73d06c597a68a8b78e5621d97feefca134c64b623e65f0a900037456da",
    "cores/reports/smsplus.json": "1a3fc4e4ead90eb7f394b2498e63833ee5c35b7c8fa8e45445057b8bd9b81590",
    "cores/smsplus-wasm.data": "0f197c5e0000f17b2d072122a72b3f8fc1693514c4014fcd9694eec78584aa08",
    "cores/smsplus-legacy-wasm.data": "9fcc16b3e4ad662c395542bc96a0142cded1d17cbd8e43f0d5b3205cf4f7d340",
    "cores/reports/snes9x.json": "dc7ac963eb7935a7ac78956235ac0b8912ec785c57026336825aa2ed8031b3ad",
    "cores/snes9x-wasm.data": "eaa0bcfce67673809886e50387a80a616b719502175db64c090d04c9d75958ee",
    "cores/snes9x-legacy-wasm.data": "7d427a575cefad98ff400493fa1d7e892da63fe7bab68979babd9cea0bfaaf3b",
    "cores/reports/stella2014.json": "c9920b95db48f678294daa72a289c19846e74ba69ca6d6094a76fb9f560fb39a",
    "cores/stella2014-wasm.data": "6c96c6b1746f3f05ca599066abe131a36c77ca61fc20a9e2a7560540457c487d",
    "cores/stella2014-legacy-wasm.data": "6dc81bb0c3c5833af69aa750491a6ecd547ec9b91c21bd55ed9a77d5b0a8dd08",
}
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


def _fetch(cfg, url: str, dest: Path, job: dict, lo: float, hi: float, sha256: str | None):
    """Scarica in dest solo se lo SHA-256 corrisponde: senza impronta nota non si scarica."""
    if not sha256:
        raise RuntimeError(f"impronta SHA-256 sconosciuta per {url}: download rifiutato")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    PT._download(url, tmp, lambda d, t: job.update(pct=lo + (hi - lo) * (d / t if t else 0)), PT._token(cfg))
    if PT._sha256(tmp) != sha256.lower():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name}: il file scaricato non corrisponde al checksum atteso, download rifiutato")
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
        _fetch(cfg, a["url"], zp, job, 0, 0.9, a.get("sum"))  # sum = digest dell'asset GitHub
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
            _fetch(cfg, u, d / r, job, i / len(todo), (i + 1) / len(todo), EJS_SHA256.get(r[4:]))
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
