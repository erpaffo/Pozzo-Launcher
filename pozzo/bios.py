"""Verifica dei BIOS e dei firmware che alcuni emulatori richiedono.

Pozzo non include e non scarica nessun file BIOS: qui ci sono solo i nomi dei file attesi, gli hash noti e il link
a una guida. check(console_id, folder) dice per ogni file se e' presente e se il suo hash corrisponde a uno noto.

Gli hash non si scrivono a mano: arrivano da pozzo/data/bios_hashes.json, generato da tools/update_bios_hashes.py
dal dat/System.dat di libretro (dimensione, crc, md5 e sha1 ufficiali). Un file che non e' li' resta «hash non noto»,
mai dato per buono. Le chiavi della Switch (prod.keys, title.keys) e la cartella firmware sono personali e non hanno
hash pubblico: si controlla solo che ci siano e che abbiano la forma giusta.

Gruppi: i file con lo stesso gruppo sono alternativi (per esempio una regione di PlayStation): ne basta uno
presente e ok. Nell'elenco degli item sono tutti required=True; il campo ok di primo livello tiene conto dei gruppi.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import config as C
from . import platforms as P
from .library import launcher as L

# Hash ufficiali per nome file in minuscolo (da libretro dat/System.dat), letti una volta all'avvio.
BIOS_HASHES = Path(__file__).parent / "data" / "bios_hashes.json"
KEYS = {"prod.keys", "title.keys"}  # chiavi della Switch: personali, nessun hash pubblico


def load_hashes(path: Path | str = BIOS_HASHES) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """(sha1, md5) attesi per nome file. JSON mancante o illeggibile: nessun hash noto, si controlla la presenza."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}
    sha1: dict[str, set[str]] = {}
    md5: dict[str, set[str]] = {}
    for nome, rec in (data.get("files") or {}).items():
        if rec.get("sha1"):
            sha1[nome.lower()] = {str(rec["sha1"]).lower()}
        if rec.get("md5"):
            md5[nome.lower()] = {str(rec["md5"]).lower()}
    return sha1, md5


SHA1_NOTI, MD5_NOTI = load_hashes()

# console -> file attesi: (nome, obbligatorio, gruppo) e guida ufficiale dell'emulatore (help).
# Il primo emulatore dei preset della console (launcher.PRESETS) dice dove si cercano i file.
REQUISITI: dict[str, dict] = {
    "psx": {"files": [("scph5500.bin", True, "ps1"), ("scph5501.bin", True, "ps1"), ("scph5502.bin", True, "ps1")],
            "help": "https://github.com/stenzek/duckstation"},
    "ps2": {"files": [("scph39001.bin", True, "ps2"), ("scph10000.bin", True, "ps2"), ("scph70012.bin", True, "ps2")],
            "help": "https://github.com/PCSX2/pcsx2"},
    "saturn": {"files": [("sega_101.bin", True, "saturn"), ("mpr-17933.bin", True, "saturn")],
               "help": "https://docs.libretro.com/"},
    "dreamcast": {"files": [("dc_boot.bin", True, None), ("dc_flash.bin", False, None)],
                  "help": "https://github.com/flyinghead/flycast"},
    "gba": {"files": [("gba_bios.bin", False, None)], "help": "https://github.com/mgba-emu/mgba"},
    "nds": {"files": [("bios7.bin", True, None), ("bios9.bin", True, None), ("firmware.bin", True, None)],
            "help": "https://github.com/melonDS-emu/melonDS"},
    "3ds": {"files": [("aes_keys.txt", True, None)], "help": "https://github.com/azahar-emu/azahar"},
    # prod.keys e title.keys sono file; «firmware» e' una cartella di file .nca (senza hash: ok resta False)
    "switch": {"files": [("prod.keys", True, None), ("title.keys", True, None), ("firmware", True, None)],
               "help": "https://github.com/Ryujinx/Ryujinx"},
    "segacd": {"files": [("bios_CD_U.bin", True, "segacd"), ("bios_CD_E.bin", True, "segacd"),
                         ("bios_CD_J.bin", True, "segacd")],
               "help": "https://docs.libretro.com/"},
}


def _cartelle(console_id: str, folder: str | None) -> list[Path]:
    """Dove cercare: la cartella passata (con system/ e bios/), altrimenti quelle degli emulatori configurati."""
    if folder:
        base = Path(folder)
        return [base, base / "system", base / "bios"]
    try:
        cfg = C.load(None)
    except Exception:  # config illeggibile: si segnala come file mancante, senza crash
        return []
    out: list[Path] = []
    for emu in {e for e, _ in L.PRESETS.get(console_id, [])} | {L.RA}:
        exe = cfg.emulators.get(emu)
        if exe:
            d = Path(exe).parent
            out += [d, d / "system", d / "bios"]
    return list(dict.fromkeys(out))


def _hash(path: Path) -> tuple[str, str]:
    """(sha1, md5) del file, letto a blocchi da 1 MiB. Solleva OSError se non si legge."""
    s1, m5 = hashlib.sha1(), hashlib.md5()
    with open(path, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            s1.update(blocco)
            m5.update(blocco)
    return s1.hexdigest(), m5.hexdigest()


def _chiavi_ok(path: Path) -> bool:
    """Chiavi della Switch: righe «nome = esadecimale», nient'altro. Il contenuto non si usa per altro."""
    try:
        testo = path.read_text(encoding="utf-8", errors="replace")[:64 * 1024]
    except OSError:
        return False
    righe = [r.strip() for r in testo.splitlines() if r.strip()]
    return bool(righe) and all(re.fullmatch(r"[A-Za-z0-9_]+\s*=\s*[0-9A-Fa-f]+", r) for r in righe)


def _cartella_piena(path: Path) -> bool:
    try:
        return any(f.is_file() for f in path.iterdir())
    except OSError:
        return False


def _giudica(nome: str, trovato: Path | None, sha1: str | None, md5: str | None) -> tuple[bool, str]:
    """(ok, motivo in italiano) di un file atteso: hash noto che corrisponde, formato per i file personali, o niente."""
    if trovato is None:
        return False, "manca"
    if trovato.is_dir():  # la cartella «firmware» della Switch
        piena = _cartella_piena(trovato)
        return piena, "cartella firmware presente" if piena else "cartella vuota"
    if nome.lower() in KEYS:
        return ((True, "formato valido (hash non pubblico)") if _chiavi_ok(trovato) else
                (False, "formato non valido: righe «nome = esadecimale»"))
    if sha1 is None:
        return False, "file non leggibile"
    if sha1 in SHA1_NOTI.get(nome.lower(), set()) or md5 in MD5_NOTI.get(nome.lower(), set()):
        return True, "ok"
    if nome.lower() in SHA1_NOTI or nome.lower() in MD5_NOTI:
        return False, "hash diverso"
    return False, "hash non noto"


def check(console_id: str, folder: str | None = None) -> dict:
    """Stato dei BIOS e firmware di una console.

    Ritorna {"console", "emulator", "items": [{"file", "required", "found", "ok", "sha1", "help_url"}], "ok"}.
    ok di primo livello: ogni file required non di gruppo e' presente e corrisponde a un hash noto, e per ogni gruppo
    c'e' almeno un file presente e ok. Console senza BIOS: items vuoto e ok True. Console sconosciuta: ValueError.
    """
    if console_id not in P.PLATFORMS:
        raise ValueError(f"console sconosciuta: {console_id}")
    preset = L.PRESETS.get(console_id) or [("", None)]
    spec = REQUISITI.get(console_id)
    if not spec:
        return {"console": console_id, "emulator": preset[0][0], "items": [], "ok": True}

    cartelle = _cartelle(console_id, folder)
    items, gruppi, singoli = [], {}, []
    for nome, obbligatorio, gruppo in spec["files"]:
        trovato = next((c / nome for c in cartelle if (c / nome).exists()), None)
        sha1 = md5 = None
        if trovato is not None and trovato.is_file():
            try:
                sha1, md5 = _hash(trovato)
            except OSError:  # file illeggibile: presente ma non verificabile
                sha1 = None
        ok, motivo = _giudica(nome, trovato, sha1, md5)
        item = {"file": nome, "required": obbligatorio or gruppo is not None, "found": trovato is not None,
                "ok": ok, "sha1": sha1, "motivo": motivo, "help_url": spec["help"]}
        items.append(item)
        if gruppo:
            gruppi[gruppo] = gruppi.get(gruppo, False) or ok
        else:
            singoli.append(ok or not obbligatorio)
    ok_generale = all(singoli) and all(gruppi.values())
    return {"console": console_id, "emulator": preset[0][0], "items": items, "ok": ok_generale}
