"""Tasti multimediali di sistema senza dipendenze aggiuntive."""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys

VK = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "volume_up": 0xAF,
      "volume_down": 0xAE, "mute": 0xAD}
LINUX_KEYS = {"play_pause": "XF86AudioPlay", "next": "XF86AudioNext", "previous": "XF86AudioPrev",
              "volume_up": "XF86AudioRaiseVolume", "volume_down": "XF86AudioLowerVolume", "mute": "XF86AudioMute"}


def _run(args, runner=subprocess.run):
    return runner(args, capture_output=True, text=True, timeout=5, check=False)


def send(action: str, *, platform: str | None = None, runner=subprocess.run, keybd_event=None,
         which=shutil.which) -> dict:
    platform = platform or sys.platform
    if action not in VK:
        return {"ok": False, "code": "invalid_action", "message": "Comando multimediale non valido."}
    try:
        if platform == "win32":
            event = keybd_event or ctypes.windll.user32.keybd_event
            event(VK[action], 0, 0, 0)
            event(VK[action], 0, 2, 0)
            return {"ok": True, "message": "Tasto multimediale inviato."}
        if platform == "darwin":
            app_command = {"play_pause": "playpause", "next": "next track", "previous": "previous track"}
            if action in app_command:
                for app in ("Spotify", "Music"):
                    result = _run(["osascript", "-e", f'tell application "{app}" to {app_command[action]}'], runner)
                    if result.returncode == 0:
                        return {"ok": True, "message": "Comando inviato al player."}
            if action.startswith("volume_"):
                op = "up" if action == "volume_up" else "down"
                script = f'tell application "System Events" to set volume output volume (output volume of (get volume settings) {"+" if op == "up" else "-"} 5)'
                result = _run(["osascript", "-e", script], runner)
                if result.returncode == 0:
                    return {"ok": True, "message": "Volume aggiornato."}
            return {"ok": False, "code": "unavailable", "message": "Nessun player compatibile trovato."}
        if platform.startswith("linux"):
            playerctl = which("playerctl")
            if playerctl:
                commands = {"play_pause": ["play-pause"], "next": ["next"], "previous": ["previous"],
                            "volume_up": ["volume", "0.05+"], "volume_down": ["volume", "0.05-"], "mute": ["volume", "0"]}
                result = _run([playerctl, *commands[action]], runner)
                if result.returncode == 0:
                    return {"ok": True, "message": "Comando inviato al player."}
            xdotool = which("xdotool")
            if xdotool:
                result = _run([xdotool, "key", "--clearmodifiers", LINUX_KEYS[action]], runner)
                if result.returncode == 0:
                    return {"ok": True, "message": "Tasto multimediale inviato."}
        return {"ok": False, "code": "unavailable", "message": "Tasti multimediali non disponibili su questo sistema."}
    except (OSError, subprocess.SubprocessError) as error:
        return {"ok": False, "code": "unavailable", "message": f"Controllo multimediale non riuscito: {error}"}
