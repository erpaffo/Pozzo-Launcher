"""Motore delle mod, indipendente da cosa si modda: un port oggi, un gioco della libreria poi.

Il punto di variazione e' la `Dest`: dove applicare i file e dove tenere archivi/backup/stato.
Le mod si scaricano solo dagli host in allow-list, si verificano (sha256), si estraggono senza
uscire dalla cartella di destinazione e si possono disattivare ripristinando i file originali."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from . import __version__
from .matching import normalize

MOD_MAX_DOWNLOAD = 512 << 20  # 512 MB: una mod piu' grande e' quasi sempre un pacchetto sbagliato
LIST_TTL = 12 * 3600  # elenchi delle fonti in cache 12 ore
UA = {"User-Agent": f"PozzoLauncher/{__version__} (+https://github.com/erpaffo/Pozzo-Launcher)"}
MOD_META = {"manifest.json", "icon.png", "readme.md", "changelog.md", "license", "license.md", "license.txt"}
# host da cui si accettano download e pagine; Nexus non c'e': senza chiave API dell'utente niente scraping
MOD_HOSTS = {"thunderstore": "thunderstore.io", "gamebanana": "gamebanana.com", "moddb": "moddb.com"}
_LINK = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_ARC = "pozzo-mod-archive"  # nome temporaneo dell'archivio: distingue «cartella unica» da «contenuto» dopo extract()


@dataclass
class Dest:
    root: Path        # cartella del port/gioco; i percorsi dei file registrati sono relativi a questa
    path: str         # sottocartella di root in cui si applicano le mod
    store_dir: Path   # base degli archivi: <store_dir>/<mod_id>/{mod.zip,backup.zip}
    store_base: Path  # il backup si registra nello stato relativo a questa cartella
    load_state: Callable[[], dict]        # installed_mods: {id: record}
    save_state: Callable[[dict], object]  # salva installed_mods; il ritorno passa ai chiamanti
    # (mod_id, file dell'archivio) -> percorso sotto path, o None per saltarlo: i loader (BepInEx) vogliono
    # i file in cartelle precise; senza, il contenuto dell'archivio va in path cosi' com'e'
    layout: Callable[[str, str], str | None] | None = None


def _inside(root: Path, rel: str) -> Path:
    """root/rel, rifiutando percorsi che escono da root (dati dalla fonte o dall'utente)."""
    p = (root / rel).resolve()
    if p != root.resolve() and root.resolve() not in p.parents:
        raise ValueError(f"percorso non valido: {rel}")
    return p


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().lower()


def host_ok(url: str, provider: str) -> bool:
    m = re.match(r"https://([^/:]+)", url or "")
    host = MOD_HOSTS.get(provider)
    return bool(m and host) and (m.group(1) == host or m.group(1).endswith("." + host))


# ---------------------------------------------------------------- fonti

def parse_thunderstore(raw: list) -> list[dict]:
    return [{"provider": "thunderstore", "id": p["full_name"], "name": p["name"].replace("_", " "),
             "owner": p.get("owner") or "", "description": v.get("description") or "", "icon": v.get("icon") or "",
             "version": v.get("version_number") or "", "url": v.get("download_url") or "",
             "sha256": (v.get("sha256") or "").lower(), "page": p.get("package_url") or "",
             "downloads": sum(x.get("downloads") or 0 for x in p["versions"]), "nsfw": p.get("has_nsfw_content"),
             # "Owner-Name-1.2.3" -> "Owner-Name", lo stesso id del pacchetto
             "deps": [d.rsplit("-", 1)[0] for d in v.get("dependencies") or [] if isinstance(d, str)]}
            for p in raw or [] if p.get("versions") and not p.get("is_deprecated") for v in [p["versions"][0]]]


def parse_mod_page(url: str, provider: str, html: str) -> list[dict]:
    """Mod elencate in una pagina pubblica di GameBanana o ModDB: solo link alla pagina (il download si fa da li')."""
    out: dict[str, dict] = {}
    for href, text in _LINK.findall(html or ""):
        if not host_ok(href, provider):
            continue
        name = re.sub(r"<[^>]+>|\s+", " ", text).strip()
        if provider == "gamebanana":
            m = re.search(r"/(?:mods|dl)/(\d+)", href)
            mid = m and f"gamebanana-{m.group(1)}"
        elif provider == "moddb":
            m = re.search(r"/mods/([^/]+)/downloads", href)
            mid = m and f"moddb-{m.group(1)}"
        else:
            mid = None
        if mid and mid not in out:
            out[mid] = {"provider": provider, "id": mid, "name": name or mid, "page": href, "url": "",
                        "version": "", "description": "", "downloads": 0, "source": url}
    return list(out.values())


def mod_matches(item: dict, games: list[str], consoles: list[str], norm_platform=lambda c: c) -> bool:
    """Prudente: la mod vale solo se il gioco coincide (titolo normalizzato) e la piattaforma, se dichiarata, e' tra
    quelle del bersaglio. `norm_platform` porta gli id di piattaforma alla stessa forma (i port hanno alias propri)."""
    plat = item.get("platform")
    if plat and norm_platform(plat) not in {norm_platform(c) for c in consoles or []}:
        return False
    return bool(item.get("game")) and normalize(item["game"]) in {normalize(g) for g in games or [] if g}


def _get(url: str):
    r = httpx.get(url, headers=UA, timeout=httpx.Timeout(20, connect=8), follow_redirects=True)
    r.raise_for_status()
    return r


def mod_list(cache, mods: dict, games: list[str] = (), consoles: list[str] = (), norm_platform=lambda c: c) -> list[dict]:
    """Mod da Thunderstore (con download) e dalle pagine di GameBanana/ModDB (solo link); elenchi in cache 12 ore."""
    out = []
    for s in mods.get("sources") or []:
        src, provider = s.get("sourceUrl") or "", s.get("provider")
        m = re.search(r"thunderstore\.io/c/([^/]+)", src)
        if provider == "thunderstore" and m:
            key, url, parse = "mods:ts:" + m.group(1), f"https://thunderstore.io/c/{m.group(1)}/api/v1/package/", parse_thunderstore
        elif provider in ("gamebanana", "moddb") and host_ok(src, provider):
            key, url, parse = f"ports:{provider}:{src}", src, None
        else:
            continue
        pk = cache.kv_get(key, max_age=LIST_TTL)
        if pk is None:
            try:
                pk = parse(_get(url).json()) if parse else parse_mod_page(src, provider, _get(url).text[:2_000_000])
                cache.kv_set(key, pk)
            except (httpx.HTTPError, ValueError, RuntimeError):
                pk = cache.kv_get(key) or []
        out += [x for x in pk if "game" not in x or mod_matches(x, games, consoles, norm_platform)]
    return sorted(out, key=lambda x: -(x.get("downloads") or 0))


# ---------------------------------------------------------------- download ed estrazione

def download(url: str, dest: Path, provider: str, max_bytes: int = MOD_MAX_DOWNLOAD):
    """Download di una mod: solo https dall'host della fonte (ricontrollato dopo i redirect), interrotto oltre max_bytes."""
    if not host_ok(url, provider):
        raise ValueError("indirizzo della mod non consentito")
    with httpx.stream("GET", url, headers=UA, timeout=httpx.Timeout(60, connect=10), follow_redirects=True) as r:
        r.raise_for_status()
        if not host_ok(str(r.url), provider):
            raise ValueError("la mod rimanda a un altro sito: download rifiutato")
        done = 0
        with open(dest, "wb") as f:
            for b in r.iter_bytes(1 << 20):
                done += len(b)
                if done > max_bytes:
                    raise ValueError("mod troppo grande")
                f.write(b)


def extract_files(archive: Path, out: Path) -> list[str]:
    """Estrae la mod (zip, 7z, rar) in out senza i file di metadati; rifiuta percorsi che escono dalla cartella.
    Ritorna i file (relativi, con /). Il contenuto resta com'e' nell'archivio, anche con una cartella unica."""
    from .downloads import extract as X  # import qui: serve solo a chi installa
    archive, out = Path(archive), Path(out)
    if archive.suffix.lower() == ".zip":  # extract() scarta in silenzio i percorsi non sicuri: qui la mod si rifiuta intera
        with zipfile.ZipFile(archive) as z:
            for i in z.infolist():
                if not i.is_dir():
                    _inside(out, i.filename)
    work = out.with_name(out.name + ".estrazione")
    shutil.rmtree(work, ignore_errors=True)
    tmp = archive.with_name(_ARC + archive.suffix.lower())
    archive.rename(tmp)
    try:
        got = X.extract(tmp, work)[0]
    except X.ArchiveError as e:
        raise ValueError(f"estrazione della mod non riuscita: {e}") from e
    finally:
        tmp.rename(archive)
    try:
        root = got if got.name == _ARC else work  # cartella unica nell'archivio: extract() la porta su, qui si tiene
        files = []
        for f in sorted(p for p in root.rglob("*") if p.is_file() and p.name.lower() not in MOD_META):
            rel = f.relative_to(root).as_posix()
            dst = _inside(out, rel)
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(f, dst)
            files.append(dst.relative_to(out.resolve()).as_posix())
        return files
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- installazione

def _store(dest: Dest, mod_id: str) -> Path:
    """Cartella con l'archivio della mod e il backup dei file originali che sostituisce."""
    return dest.store_dir / re.sub(r"[^\w.-]+", "_", mod_id)


def _targets(dest: Dest, mod_id: str, files: list[str]) -> list[tuple[str, Path]]:
    """(file dell'archivio, destinazione) secondo il layout della Dest, sempre dentro la cartella delle mod."""
    target = _inside(dest.root, dest.path)
    out = []
    for f in files:
        rel = dest.layout(mod_id, f) if dest.layout else f
        if rel:
            out.append((f, _inside(target, rel)))
    return out


def would_replace(dest: Dest, mod_id: str, archive: Path) -> list[str]:
    """File gia' presenti (relativi a root) che l'archivio sostituirebbe: anteprima prima di installare."""
    with zipfile.ZipFile(archive) as z:
        names = [i.filename for i in z.infolist() if not i.is_dir() and i.filename.rsplit("/", 1)[-1].lower() not in MOD_META]
    root = dest.root.resolve()
    return [d.relative_to(root).as_posix() for _, d in _targets(dest, mod_id, names) if d.is_file()]


def _apply(dest: Dest, store: Path, mod_id: str, backup: bool = False) -> list[str]:
    """Estrae mod.zip nella cartella della mod; con `backup` salva prima i file che sostituira'.
    Ritorna i file relativi a dest.root."""
    root = dest.root.resolve()
    stage = store / "stage"
    shutil.rmtree(stage, ignore_errors=True)
    try:
        pairs = _targets(dest, mod_id, extract_files(store / "mod.zip", stage))
        files, dsts = [f for f, _ in pairs], [d for _, d in pairs]
        replaced = [d for d in dsts if backup and d.is_file()]
        if replaced:
            with zipfile.ZipFile(store / "backup.zip", "w", zipfile.ZIP_DEFLATED) as z:
                for p in replaced:
                    z.write(p, p.relative_to(root).as_posix())
        for f, d in zip(files, dsts):
            d.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / f, d)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return [d.relative_to(root).as_posix() for d in dsts]


def _unapply(dest: Dest, record: dict, store: Path):
    """Toglie i file della mod e rimette quelli originali salvati nel backup."""
    for f in record.get("files") or []:
        _inside(dest.root, f).unlink(missing_ok=True)
    backup = store / "backup.zip"
    if backup.is_file():
        with zipfile.ZipFile(backup) as z:
            for i in z.infolist():
                dst = _inside(dest.root, i.filename)
                dst.parent.mkdir(parents=True, exist_ok=True)
                with z.open(i) as f, open(dst, "wb") as w:
                    shutil.copyfileobj(f, w)


def install(dest: Dest, mod: dict, download=download):
    """Scarica, verifica e applica la mod; registra il record nello stato. `download` e' sostituibile (test)."""
    provider, url = mod.get("provider") or "thunderstore", str(mod.get("url") or "")
    if not host_ok(url, provider):
        raise ValueError("mod non valida")
    _inside(dest.root, dest.path)
    store = _store(dest, mod["id"])
    shutil.rmtree(store, ignore_errors=True)
    store.mkdir(parents=True)
    try:
        archive = store / "mod.zip"
        download(url, archive, provider)
        want = (mod.get("sha256") or "").lower()
        if want and _sha256(archive) != want:
            raise RuntimeError("la mod scaricata non corrisponde al checksum: download rifiutato")
        files = _apply(dest, store, mod["id"], backup=True)
    except Exception:
        shutil.rmtree(store, ignore_errors=True)
        raise
    mods = dict(dest.load_state() or {})
    mods[mod["id"]] = {"name": mod.get("name") or mod["id"], "version": mod.get("version") or "", "files": files,
                       "enabled": True, "provider": provider, "download_url": url,
                       "backup": (store / "backup.zip").relative_to(dest.store_base).as_posix()}
    return dest.save_state(mods)


def set_enabled(dest: Dest, mod_id: str, enabled: bool):
    """Attiva/disattiva; ritorna il risultato di save_state, o None se lo stato era gia' quello."""
    mods = dict(dest.load_state() or {})
    record = dict(mods[mod_id])  # KeyError: mod non installata
    if record.get("enabled", True) == enabled:
        return None
    store = _store(dest, mod_id)
    if enabled:
        if not (store / "mod.zip").is_file():
            raise ValueError("archivio della mod mancante: reinstallala")
        record["files"] = _apply(dest, store, mod_id)
    else:
        _unapply(dest, record, store)
    record["enabled"] = enabled
    mods[mod_id] = record
    return dest.save_state(mods)


def remove(dest: Dest, mod_id: str):
    mods = dict(dest.load_state() or {})
    record = mods.pop(mod_id, None) or {}
    store = _store(dest, mod_id)
    if record.get("enabled", True):
        _unapply(dest, record, store)
    shutil.rmtree(store, ignore_errors=True)
    return dest.save_state(mods)
