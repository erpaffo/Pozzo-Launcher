"""Mapping predefinito del controller (Xbox, PlayStation, Switch Pro) per gli emulatori.

- Alla prima installazione (`auto_apply`) si scrive solo se il file di config dell'emulatore NON esiste ancora.
- A mano (`apply(..., force=True)`, pannello Impostazioni › Controller): emulatore chiuso, copia .pozzo-<data>
  (come emusetup), poi si cambiano solo le chiavi del controller 1.
Posizione dei tasti uguale per tutti (sud = Croce/A): cambia solo l'origine dei dati (XInput o SDL) e il nome del pad.
shortcut: i nomi delle chiavi di RPCS3 e i nomi SDL di Dolphin sono scritti a memoria, non provati su un'installazione; Cemu non c'e'
(mappature numeriche non verificate).
"""

from __future__ import annotations

import sys
from pathlib import Path

from .remote import emusetup

TYPES = {"xbox": "Xbox", "ps": "PlayStation (DualSense)", "ps4": "PlayStation (DualShock 4)", "switch": "Switch Pro"}
# vendor USB -> tipo (0x054C Sony, 0x057E Nintendo, 0x045E Microsoft); PID DualShock 4 = 0x05C4/0x09CC
_VENDOR = {0x057E: "switch", 0x045E: "xbox"}
_DS4 = (0x05C4, 0x09CC)


def detect_type(layout: str | None = None) -> str:
    """Tipo del controller: aspetto scelto sul telefono (pozzo.remote.phone), altrimenti il primo pad collegato
    (Windows, winmm), altrimenti Xbox (anche i pad XInput sono Xbox)."""
    if layout in TYPES:
        return layout
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_string_buffer(728)  # JOYCAPSW
            for i in range(16):
                if ctypes.windll.winmm.joyGetDevCapsW(i, buf, 728) == 0:
                    mid, pid = int.from_bytes(buf[0:2], "little"), int.from_bytes(buf[2:4], "little")
                    if mid == 0x054C:
                        return "ps4" if pid in _DS4 else "ps"
                    if mid in _VENDOR:
                        return _VENDOR[mid]
        except Exception:  # noqa: BLE001 - nessun rilevamento: si resta su Xbox
            pass
    return "xbox"


def _src(t: str) -> str:
    return "XInput-0" if t == "xbox" else "SDL-0"


# ------------------------------------------------------------------ PS1/PS2 (PCSX2, DuckStation): stesse chiavi
def _ps_pad(t: str, pad_type: str) -> dict:
    s = _src(t)
    m = {"Up": "DPadUp", "Down": "DPadDown", "Left": "DPadLeft", "Right": "DPadRight",
         "Triangle": "Y", "Circle": "B", "Cross": "A", "Square": "X", "Select": "Back", "Start": "Start",
         "L1": "LeftShoulder", "R1": "RightShoulder", "L2": "+LeftTrigger", "R2": "+RightTrigger",
         "L3": "LeftStick", "R3": "RightStick", "Analog": "Guide",
         "LUp": "-LeftY", "LDown": "+LeftY", "LLeft": "-LeftX", "LRight": "+LeftX",
         "RUp": "-RightY", "RDown": "+RightY", "RLeft": "-RightX", "RRight": "+RightX"}
    return {"Type": pad_type, **{k: f"{s}/{v}" for k, v in m.items()}}


def _ps_changes(t: str, pad_type: str) -> dict:
    return {"InputSources": {"SDL": "true", "XInput": "true"}, "Pad1": _ps_pad(t, pad_type)}


# ------------------------------------------------------------------ Dolphin (GameCube pad 1)
_DOLPHIN_DEV = {"xbox": "XInput/0/Gamepad", "ps": "SDL/0/PS5 Controller", "ps4": "SDL/0/PS4 Controller",
                "switch": "SDL/0/Nintendo Switch Pro Controller"}


def _dolphin_changes(t: str) -> dict:
    x = t == "xbox"  # XInput: Button A/B/X/Y; SDL: Button S/E/W/N (sud, est, ovest, nord)
    a, b, xx, y = ("`Button A`", "`Button B`", "`Button X`", "`Button Y`") if x else \
        ("`Button S`", "`Button E`", "`Button W`", "`Button N`")
    return {"GCPad1": {
        "Device": _DOLPHIN_DEV[t],
        "Buttons/A": a, "Buttons/B": xx, "Buttons/X": b, "Buttons/Y": y,
        "Buttons/Z": "`Shoulder R`", "Buttons/Start": "Start",
        "Main Stick/Up": "`Left Y+`", "Main Stick/Down": "`Left Y-`",
        "Main Stick/Left": "`Left X-`", "Main Stick/Right": "`Left X+`",
        "C-Stick/Up": "`Right Y+`", "C-Stick/Down": "`Right Y-`",
        "C-Stick/Left": "`Right X-`", "C-Stick/Right": "`Right X+`",
        "Triggers/L": "`Trigger L`", "Triggers/R": "`Trigger R`",
        "Triggers/L-Analog": "`Trigger L`", "Triggers/R-Analog": "`Trigger R`",
        "D-Pad/Up": "`Pad N`", "D-Pad/Down": "`Pad S`", "D-Pad/Left": "`Pad W`", "D-Pad/Right": "`Pad E`",
    }}


# ------------------------------------------------------------------ RPCS3 (Player 1)
def _rpcs3_player(t: str) -> dict:
    if t == "xbox":
        handler, dev = "XInput", "XInput Pad #1"
        n = {"Square": "X", "Cross": "A", "Circle": "B", "Triangle": "Y", "L1": "LB", "R1": "RB", "L2": "LT",
             "R2": "RT", "L3": "LS", "R3": "RS", "Select": "Back", "PS Button": "Guide"}
    else:  # DualSense/DualShock 4 nativi; il Pro Controller passa da SDL con i nomi dei tasti Xbox
        handler, dev = {"ps": ("DualSense", "DualSense Pad #1"), "ps4": ("DualShock 4", "DS4 Pad #1"),
                        "switch": ("SDL", "SDL Pad #1")}[t]
        n = ({"Square": "Square", "Cross": "Cross", "Circle": "Circle", "Triangle": "Triangle", "L1": "L1", "R1": "R1",
              "L2": "L2", "R2": "R2", "L3": "L3", "R3": "R3", "Select": "Select", "PS Button": "PS Button"} if t != "switch" else
             {"Square": "X", "Cross": "A", "Circle": "B", "Triangle": "Y", "L1": "LB", "R1": "RB", "L2": "LT",
              "R2": "RT", "L3": "LS", "R3": "RS", "Select": "Back", "PS Button": "Guide"})
    cfg = {"Left Stick Left": "LS X-", "Left Stick Down": "LS Y-", "Left Stick Right": "LS X+", "Left Stick Up": "LS Y+",
           "Right Stick Left": "RS X-", "Right Stick Down": "RS Y-", "Right Stick Right": "RS X+", "Right Stick Up": "RS Y+",
           "Start": "Start", "Left": "Left", "Down": "Down", "Right": "Right", "Up": "Up", **n}
    return {"Handler": handler, "Device": dev, "Config": cfg}


# ------------------------------------------------------------------ RetroArch: l'autoconfig fa il resto
def _retroarch_changes(t: str) -> dict:
    return {"": {"input_joypad_driver": "xinput" if t == "xbox" else "sdl2", "input_autodetect_enable": "true",
                 "input_player1_joypad_index": "0"}}


# ------------------------------------------------------------------ percorsi e scrittura
def _config_file(emu: str, exe: str | None) -> Path | None:
    if emu == "pcsx2":
        return emusetup.pcsx2_ini(exe)
    if emu == "dolphin":
        return emusetup.dolphin_dir(exe) / "Config" / "GCPadNew.ini"
    if emu == "duckstation":
        from .emuadapters import duckstation
        return duckstation._data_root(exe) / "settings.ini"
    if emu == "rpcs3":
        from .emuadapters import rpcs3
        base = rpcs3._config_dir(exe)
        return None if base == Path() else base / "input_configs" / "global" / "Default.yml"
    if emu == "retroarch":
        return Path(exe).parent / "retroarch.cfg" if exe else None
    return None


SUPPORTED = ("dolphin", "pcsx2", "duckstation", "rpcs3", "retroarch")
_PROCS = {"dolphin": ("dolphin.exe",), "pcsx2": ("pcsx2-qt.exe", "pcsx2.exe"), "duckstation": ("duckstation-qt-x64-releaseltcg.exe", "duckstation-qt.exe"),
          "rpcs3": ("rpcs3.exe",), "retroarch": ("retroarch.exe",)}


def _render(emu: str, t: str, text: str) -> str:
    if emu == "pcsx2":
        out = emusetup.ini_update(text, _ps_changes(t, "DualShock2"))
    elif emu == "duckstation":
        out = emusetup.ini_update(text, _ps_changes(t, "AnalogController"))
    elif emu == "dolphin":
        out = emusetup.ini_update(text, _dolphin_changes(t))
    elif emu == "retroarch":
        from . import emucfg
        out = emucfg._patch(text, {k: f'"{v}"' for k, v in _retroarch_changes(t)[""].items()})
    else:  # rpcs3
        import yaml
        data = yaml.safe_load(text) if text.strip() else {}
        if not isinstance(data, dict):
            raise ValueError("Config RPCS3 non riconosciuta")
        new_p, old_p = _rpcs3_player(t), data.get("Player 1 Input")
        if isinstance(old_p, dict):  # tiene vibrazione, sensori e il resto: cambiano solo gestore, dispositivo e tasti
            old_p.update({k: v for k, v in new_p.items() if k != "Config"})
            old_p["Config"] = {**(old_p.get("Config") if isinstance(old_p.get("Config"), dict) else {}), **new_p["Config"]}
            new_p = old_p
        data["Player 1 Input"] = new_p
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    return out.replace("\n", "\r\n") if "\r\n" in text else out


def status(emulators: dict) -> list[dict]:
    out = []
    for emu in SUPPORTED:
        exe = emulators.get(emu)
        p = _config_file(emu, exe) if exe else None
        out.append({"id": emu, "exe": bool(exe), "config": str(p) if p else "", "exists": bool(p and p.exists())})
    return out


def apply(emu: str, t: str, emulators: dict, force: bool = False) -> dict:
    """Scrive il mapping. force=False: solo se la config non esiste (prima installazione). Ritorna {"file", "backup"}.
    ValueError: emulatore/tipo sconosciuto; RuntimeError: emulatore aperto o niente da fare."""
    if emu not in SUPPORTED or t not in TYPES:
        raise ValueError("Emulatore o controller sconosciuto")
    exe = emulators.get(emu)
    p = _config_file(emu, exe)
    if not exe or not p:
        raise RuntimeError("Emulatore non configurato")
    if p.exists() and not force:
        raise RuntimeError("Config gia' presente: non viene toccata")
    if emusetup._running(_PROCS[emu]):
        raise RuntimeError("Chiudi l'emulatore prima: all'uscita riscriverebbe le sue impostazioni")
    text = p.read_bytes().decode("utf-8-sig", errors="replace") if p.exists() else ""  # bytes: tiene i CRLF
    new = _render(emu, t, text)  # calcolato prima di aprire il file in scrittura
    b = emusetup.backup(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(new, encoding="utf-8", newline="")
    return {"file": str(p), "backup": str(b) if b else ""}


def auto_apply(emulators: dict, log=print, layout: str | None = None, only: str | None = None) -> list[str]:
    """Hook di fine installazione: per l'emulatore appena installato (`only`; tutti se None) la cui config non esiste ancora."""
    done, t = [], None
    for emu in SUPPORTED:
        if only and emu != only:
            continue
        exe = emulators.get(emu)
        p = _config_file(emu, exe) if exe else None
        if not p or p.exists():
            continue
        try:
            t = t or detect_type(layout)
            apply(emu, t, emulators)
            done.append(emu)
            log(f"Controller {TYPES[t]} configurato per {emu}")
        except Exception as e:  # noqa: BLE001 - mai bloccare l'installazione
            log(f"Controller non configurato per {emu}: {e}")
    return done
