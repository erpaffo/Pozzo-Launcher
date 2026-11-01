"""Installazione «un clic» dell'emulatore consigliato per una console.

recommend(console_id) dice quale emulatore Pozzo consiglia, se e' gia' installato e se Pozzo sa installarlo.
install_recommended(console_id, progress=None) lo installa con emuinstall.install e poi i core di RetroArch che
mancano alla console con emuinstall.install_cores. Il download e' quello di emuinstall: qui solo la scelta.

Convenzione errori: console sconosciuta -> ValueError. Console che Pozzo non sa installare, e qualunque errore
durante l'installazione (rete, permessi, file mancanti), -> dict con ok False e «message» in italiano, da mostrare
all'utente. progress(fase: str, frazione: float 0..1) e' chiamato in sincrono durante il lavoro.
"""

from __future__ import annotations

from . import config as C
from . import emuinstall as EI
from . import platforms as P
from .library import launcher as L

# console -> (emulatore, perche'). Solo emulatori che emuinstall.SOURCES sa installare; il resto passa da RetroArch.
CONSIGLIATI: dict[str, tuple[str, str]] = {
    "gc": ("dolphin", "Dolphin è l'emulatore più completo per GameCube"),
    "wii": ("dolphin", "Dolphin gestisce anche i giochi Wii, con lo stesso emulatore del GameCube"),
    "psx": ("duckstation", "DuckStation è preciso e semplice da usare per PlayStation"),
    "ps2": ("pcsx2", "PCSX2 è l'emulatore di riferimento per PlayStation 2"),
    "psp": ("ppsspp", "PPSSPP è l'emulatore PSP più usato e va bene anche su PC modesti"),
    "nds": ("melonds", "melonDS è accurato e gestisce bene le due schermate del Nintendo DS"),
    "3ds": ("azahar", "Azahar è il fork mantenuto di Citra per Nintendo 3DS"),
    "dreamcast": ("flycast", "Flycast emula il Dreamcast in modo fedele e veloce"),
    "wiiu": ("cemu", "Cemu è l'emulatore Wii U più usato"),
    "ps3": ("rpcs3", "RPCS3 è l'emulatore PlayStation 3 di riferimento"),
    "psvita": ("vita3k", "Vita3K è l'emulatore PlayStation Vita"),
    "ps4": ("shadps4", "shadPS4 è l'emulatore PlayStation 4 open source"),
    "xbox": ("xemu", "xemu emula la prima Xbox"),
    "xbox360": ("xenia", "Xenia è l'emulatore Xbox 360 più diffuso"),
}


def _cfg(cfg=None):
    return cfg if cfg is not None else C.load(None)


def _scelta(console_id: str) -> tuple[str, str, str | None]:
    """(emulatore o "" se non supportato, motivo, core di RetroArch o None)."""
    if console_id not in P.PLATFORMS:
        raise ValueError(f"console sconosciuta: {console_id}")
    if console_id in CONSIGLIATI:
        emu, why = CONSIGLIATI[console_id]
        return emu, why, None
    core = L.default_core(console_id, L.RA)
    if core:
        return L.RA, f"RetroArch con il core «{core}», il più adatto a questa console", core
    return "", "Pozzo non sa installare un emulatore per questa console: scegline uno a mano nelle impostazioni", None


def _supportato(emu: str) -> bool:
    return bool(emu) and (emu == L.RA or emu in EI.SOURCES)


def recommend(console_id: str, cfg=None) -> dict:
    """{"emulator", "reason", "installed", "supported"} per la console. ValueError se la console non esiste."""
    emu, why, _ = _scelta(console_id)
    return {"emulator": emu, "reason": why, "installed": emu in EI.installed(_cfg(cfg)),
            "supported": _supportato(emu)}


def _esito(ok: bool, emu: str, cores: list[str], msg: str) -> dict:
    return {"ok": ok, "emulator": emu, "core_installed": cores, "message": msg}


def install_recommended(console_id: str, progress=None, cfg=None) -> dict:
    """Installa l'emulatore consigliato (se non c'e' gia') e i core di RetroArch che mancano alla console.

    Ritorna {"ok", "emulator", "core_installed", "message"}. Non solleva per errori di installazione: li mette in
    message. Solleva ValueError solo per una console sconosciuta.
    """
    emu, _, _ = _scelta(console_id)
    cfg = _cfg(cfg)
    nome = P.PLATFORMS[console_id].name
    if not _supportato(emu):
        return _esito(False, "", [], f"Pozzo non sa installare un emulatore per {nome}: scegline uno a mano.")
    fase = [""]

    def say(msg: str):
        fase[0] = msg
        if progress:
            progress(msg, 0.0)

    def scarico(done: int, total: int):
        if progress and total:
            progress(fase[0], min(1.0, done / total))

    era_installato = emu in EI.installed(cfg)
    done: list[str] = []
    cores_mancanti: list[str] = []
    try:
        if not era_installato:
            EI.install(cfg, emu, progress=scarico, say=say)
        # dopo l'installazione: un emulatore dedicato ora c'e' e la console non chiede core di RetroArch
        cores_mancanti = EI.missing_cores(cfg, [console_id])
        if cores_mancanti:
            done = EI.install_cores(cfg, cores_mancanti, progress=scarico, say=say)
    except Exception as e:  # rete, permessi, release senza file per Windows...: un messaggio, niente crash
        return _esito(False, emu, done, f"Installazione di {emu} non riuscita: {type(e).__name__}: {e}")
    rimasti = [c for c in cores_mancanti if c not in done]
    parti = [f"{emu} " + ("già installato" if era_installato else "installato")]
    if done:
        parti.append("core installati: " + ", ".join(done))
    if rimasti:
        parti.append("core non scaricati: " + ", ".join(rimasti))
    if progress:
        progress("Fatto", 1.0)
    return _esito(not rimasti, emu, done, "; ".join(parti) + f" per {nome}.")
