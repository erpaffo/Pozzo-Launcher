"""Installazione degli emulatori (e dei core di RetroArch) dalle loro release ufficiali, dalle impostazioni.

Gli emulatori sono dei rispettivi sviluppatori: Pozzo scarica le build che pubblicano loro, cosi' come sono, e
mostra il link al progetto. La versione si legge dalle release GitHub del progetto; chi non pubblica i file su
GitHub (RetroArch, Dolphin, PPSSPP) ha l'indirizzo del download costruito dalla versione, sul sito ufficiale.

Ogni emulatore va in <cartella>\\<id>. Un aggiornamento copia i file nuovi sopra quelli vecchi: la configurazione
e i dati dell'utente nella cartella (modalita' portatile) restano. Solo Windows x64.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

from . import config as C
from . import platforms as P
from . import ports as PT
from .library import launcher as L

# id di launcher.py -> repository GitHub e filtro sul nome del file della release, oppure "url" costruito dalla
# versione ({ver} = tag senza «v», {ver_} = con i punti cambiati in «_»); "tags": versione dai tag, non dalle release.
# shortcut: nomi dei file scritti a mano, da correggere se un progetto li cambia (l'errore lo dice).
SOURCES: dict[str, dict] = {
    "retroarch": {"repo": "libretro/RetroArch", "home": "https://www.retroarch.com",
                  "url": "https://buildbot.libretro.com/stable/{ver}/windows/x86_64/RetroArch.7z"},
    "dolphin": {"repo": "dolphin-emu/dolphin", "home": "https://dolphin-emu.org", "tags": r"\d{4}[a-z]?",
                "url": "https://dl.dolphin-emu.org/releases/{ver}/dolphin-{ver}-x64.7z"},
    "ppsspp": {"repo": "hrydgard/ppsspp", "home": "https://www.ppsspp.org",
               "url": "https://www.ppsspp.org/files/{ver_}/ppsspp_win.zip"},
    "duckstation": {"repo": "stenzek/duckstation", "filter": "windows-x64-release"},
    "pcsx2": {"repo": "PCSX2/pcsx2", "filter": "windows-x64-qt"},
    "rpcs3": {"repo": "RPCS3/rpcs3-binaries-win", "home": "https://rpcs3.net", "filter": "win64"},
    "vita3k": {"repo": "Vita3K/Vita3K", "filter": "windows"},
    "melonds": {"repo": "melonDS-emu/melonDS", "filter": "windows"},
    "azahar": {"repo": "azahar-emu/azahar", "filter": "windows-msvc"},
    "cemu": {"repo": "cemu-project/Cemu", "filter": "windows-x64"},
    "xenia": {"repo": "xenia-canary/xenia-canary-releases", "home": "https://xenia.jp"},
    "xemu": {"repo": "xemu-project/xemu", "filter": "release"},
    "flycast": {"repo": "flyinghead/flycast", "filter": "win64"},
    "shadps4": {"repo": "shadps4-emu/shadPS4", "filter": "win64"},
}
CORES_URL = "https://buildbot.libretro.com/nightly/windows/x86_64/latest/{core}_libretro.dll.zip"


def emus_dir(cfg) -> Path:
    return Path(cfg.app.get("emulators_dir") or C.settings_path(cfg).parent / "Emulatori")


def installed(cfg) -> dict[str, dict]:
    """{emulatore: {"version", "dir"}} installati da qui (finche' l'eseguibile configurato esiste)."""
    return {e: v for e, v in (cfg.app.get("emu_installed") or {}).items()
            if cfg.emulators.get(e) and Path(cfg.emulators[e]).exists()}


def catalog(cfg) -> list[dict]:
    names = {p.id: p.name for p in P.PLATFORMS.values()}
    inst = installed(cfg)
    return [{"id": e, "repo": s["repo"], "home": s.get("home") or f"https://github.com/{s['repo']}",
             "consoles": [names.get(pid, pid) for pid, c in L.PRESETS.items() if any(x == e for x, _ in c)],
             "version": (inst.get(e) or {}).get("version") or "", "configured": bool(cfg.emulators.get(e))}
            for e, s in SOURCES.items()]


def _latest(cfg, src: dict) -> tuple[str, dict]:
    """(versione, file da scaricare {"name", "url", "sum"?}) dell'ultima release Windows."""
    tok = PT._token(cfg)
    if src.get("tags"):
        tags = [t["name"] for t in PT._get(f"https://api.github.com/repos/{src['repo']}/tags", {"per_page": 100}, tok)
                if re.fullmatch(src["tags"], t.get("name") or "")]
        if not tags:
            raise RuntimeError(f"nessuna versione trovata nei tag di {src['repo']}")
        tag = max(tags)
    else:
        rels = PT.releases("github", src["repo"], tok)
        if src.get("url"):
            tag = next((r["tag"] for r in rels if not r["prerelease"]), "")
            if not tag:
                raise RuntimeError(f"nessuna release stabile di {src['repo']}")
        else:
            got = PT.pick_release(rels, src.get("filter") or "")
            if not got:
                raise RuntimeError(f"nessun file per Windows nelle release di {src['repo']}")
            return got[0]["tag"], got[1]
    ver = tag.lstrip("vV")
    url = src["url"].format(ver=ver, ver_=ver.replace(".", "_"))
    return tag, {"name": url.rsplit("/", 1)[-1], "url": url}


def _stage(cfg, asset: dict, name: str, progress=None) -> Path:
    """Scarica ed estrae in una cartella temporanea (rifiuta il file se il checksum della release non torna)."""
    work = emus_dir(cfg) / ".tmp" / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    arc = work / ("download" + "".join(Path(asset["name"]).suffixes[-1:]))
    try:
        PT._download(asset["url"], arc, progress, PT._token(cfg))
        if asset.get("sum") and PT._sha256(arc) != asset["sum"]:
            raise RuntimeError("il file scaricato non corrisponde al checksum della release: download rifiutato")
        PT._extract(arc, work / "files", asset["name"])
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    arc.unlink()
    return work / "files"


def install(cfg, emu: str, folder: str = "", progress=None, say=print) -> str:
    """Installa (o aggiorna) un emulatore all'ultima versione e lo imposta; ritorna il percorso dell'eseguibile."""
    src = SOURCES.get(emu)
    if not src:
        raise ValueError(f"emulatore sconosciuto: {emu}")
    prev = installed(cfg).get(emu) or {}
    cur = cfg.emulators.get(emu)
    if not prev and cur and Path(cur).is_file():  # gia' presente (anche installato altrove): non scaricare
        say(f"{emu} e' gia' installato: {cur}")
        return cur
    say(f"Cerco l'ultima versione di {emu} ({src['repo']})…")
    tag, asset = _latest(cfg, src)
    if prev.get("version") == tag:
        say(f"{emu} e' gia' all'ultima versione ({tag})")
        return cfg.emulators[emu]
    dest = Path(prev.get("dir") or Path(folder or emus_dir(cfg)) / emu)
    if dest.exists() and PT._running(dest):
        raise RuntimeError(f"chiudi {emu} prima di aggiornarlo")
    say(f"Scarico {asset['name']}…")
    staged = _stage(cfg, asset, emu, progress)
    try:
        shutil.copytree(staged, dest, dirs_exist_ok=True)  # sopra la versione vecchia: i file dell'utente restano
    finally:
        shutil.rmtree(staged.parent, ignore_errors=True)
    exe = L.detect_emulators(dest).get(emu)
    if not exe:
        raise RuntimeError(f"installato in {dest}, ma non trovo l'eseguibile di {emu}: impostalo a mano")
    C.save_settings(cfg, emulators={emu: exe},
                    app={"emu_installed": {**(cfg.app.get("emu_installed") or {}), emu: {"version": tag, "dir": str(dest)}}})
    say(f"Installato {emu} {tag} in {dest}")
    try:  # mapping del controller solo se l'emulatore non ha ancora impostazioni (mai quelle dell'utente)
        from . import controllerprofiles
        controllerprofiles.auto_apply(cfg.emulators, say, only=emu)
    except Exception:  # noqa: BLE001 - non deve rovinare un'installazione riuscita
        pass
    return exe


def missing_cores(cfg, pids) -> list[str]:
    """Core di RetroArch da scaricare perche' le console della libreria abbiano un emulatore pronto."""
    out = []
    for pid in pids:
        p, over = P.PLATFORMS.get(pid), cfg.launch.get(pid, {})
        cores = [c for e, c in L.PRESETS.get(pid, []) if e == L.RA and c]
        if over.get("emulator") == L.RA and over.get("core"):
            cores = [over["core"]]
        elif over.get("emulator"):  # console legata a un altro emulatore: niente core
            continue
        if p and cores and not L.plan(cfg, p) and cores[0] not in out:
            out.append(cores[0])
    return out


def install_cores(cfg, cores: list[str], progress=None, say=print) -> list[str]:
    """Scarica i core dal buildbot di libretro nella cartella dei core di RetroArch."""
    if not (cfg.emulators.get(L.RA) and Path(cfg.emulators[L.RA]).exists()):
        raise RuntimeError("installa prima RetroArch")
    done = []
    for n, core in enumerate(cores, 1):
        if not re.fullmatch(r"\w+", core):
            raise ValueError(f"core non valido: {core}")
        dll = L._core_path(cfg, core)
        dll.parent.mkdir(parents=True, exist_ok=True)
        say(f"Core {n}/{len(cores)}: {core}…")
        arc = dll.parent / f"{core}.download.zip"
        try:
            PT._download(CORES_URL.format(core=core), arc, progress)
            with zipfile.ZipFile(arc) as z:
                z.extract(dll.name, dll.parent)
            done.append(core)
        except Exception as e:  # un core che manca sul buildbot non ferma gli altri
            say(f"{core}: non scaricato ({type(e).__name__}: {e})")
        finally:
            arc.unlink(missing_ok=True)
    say(f"Core installati: {', '.join(done) or 'nessuno'}")
    return done
