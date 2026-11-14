"""Minecraft: Java Edition (tramite Minecraft Launcher) e Bedrock (Minecraft per Windows).

Se non sono installati, "Installa" apre il Microsoft Store sulla pagina giusta.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .base import StoreGame, StoreProvider, is_windows, powershell_json

LAUNCHER_PFN = "Microsoft.4297127D64EC6_8wekyb3d8bbwe"
LAUNCHER_STORE = "9PGW18NPBZV5"  # Minecraft Launcher
BEDROCK_STORE = "9NBLGGH2JHXJ"  # Minecraft per Windows


def java_dir() -> str:
    """Cartella di Minecraft Java (il launcher ufficiale la crea qui)."""
    if is_windows():
        return os.path.expandvars(r"%APPDATA%\.minecraft")
    if sys.platform == "darwin":
        return str(Path.home() / "Library/Application Support/minecraft")
    return str(Path.home() / ".minecraft")


class Minecraft(StoreProvider):
    id = "minecraft"
    name = "Minecraft"

    def _packages(self) -> dict[str, dict]:
        rows = powershell_json(
            "@(Get-AppxPackage -Name 'Microsoft.4297127D64EC6') + @(Get-AppxPackage -Name 'Microsoft.MinecraftUWP') | "
            "Select-Object Name, PackageFamilyName, InstallLocation | ConvertTo-Json -Compress") or []
        return {r["Name"]: r for r in rows if r.get("Name")}

    def detected(self) -> bool:
        # fuori da Windows c'e' solo la Java edition: visibile se la sua cartella esiste
        return is_windows() or Path(java_dir()).is_dir()

    def account(self) -> dict:
        return {"connected": True, "note": "Java tramite Minecraft Launcher, Bedrock dal Microsoft Store"}

    async def fetch(self) -> list[StoreGame]:
        pk = self._packages()
        launcher = pk.get("Microsoft.4297127D64EC6")
        jd = java_dir()
        java_used = Path(jd).exists()
        java = StoreGame(
            store=self.id, id="java", title="Minecraft: Java Edition", installed=bool(launcher),
            install_dir=jd if java_used else "",
            launch={"type": "exe", "target": "explorer.exe", "args": [f"shell:AppsFolder\\{LAUNCHER_PFN}!Minecraft"]},
            install_uri=f"ms-windows-store://pdp/?ProductId={LAUNCHER_STORE}",
            page="https://www.minecraft.net/", developer="Mojang Studios", publisher="Microsoft",
            genres=["Sandbox", "Survival"], release_date="2011-11-18")
        bedrock_pkg = pk.get("Microsoft.MinecraftUWP")
        bedrock = StoreGame(
            store=self.id, id="bedrock", title="Minecraft for Windows (Bedrock)", installed=bool(bedrock_pkg),
            install_dir=(bedrock_pkg or {}).get("InstallLocation", ""),
            launch={"type": "uri", "target": "minecraft:"},
            install_uri=f"ms-windows-store://pdp/?ProductId={BEDROCK_STORE}",
            page="https://www.minecraft.net/", developer="Mojang Studios", publisher="Microsoft",
            genres=["Sandbox", "Survival"], release_date="2017-09-20")
        self.log(f"Minecraft: Java {'installato' if java.installed else 'non installato'}, "
                 f"Bedrock {'installato' if bedrock.installed else 'non installato'}")
        return [java, bedrock]
