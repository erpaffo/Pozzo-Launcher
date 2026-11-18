"""GOG.com: installati dal registro di Windows, posseduti tramite login all'account GOG.

Senza GOG Galaxy, "Installa" apre la pagina dei download dell'account GOG (i giochi GOG
si installano con gli installer offline); con Galaxy apre direttamente il gioco in Galaxy.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import quote

from .. import noclient as NC
from .. import profilecfg as PC
from ..net import request
from .base import StoreGame, StoreProvider, reg_get, reg_subkeys

CLIENT_ID = "46899977096215655"
CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
REDIRECT = "https://embed.gog.com/on_login_success?origin=client"
LOGIN_URL = (f"https://auth.gog.com/auth?client_id={CLIENT_ID}&redirect_uri={quote(REDIRECT, safe='')}"
             "&response_type=code&layout=client2")
REG = r"SOFTWARE\WOW6432Node\GOG.com\Games"
MAC = sys.platform == "darwin"
MAC_GALAXY = Path("/Applications/GOG Galaxy.app")
MAC_DB = Path("/Users/Shared/GOG.com/Galaxy/Storage/galaxy-2.0.db")


class Gog(StoreProvider):
    id = "gog"
    name = "GOG.com"
    login = "oauth"
    login_url = LOGIN_URL

    def galaxy(self) -> str | None:
        if MAC:
            return str(MAC_GALAXY) if MAC_GALAXY.exists() else None
        return reg_get("HKLM", r"SOFTWARE\WOW6432Node\GOG.com\GalaxyClient\paths", "client")

    def official(self) -> bool:
        """GOG Galaxy installato (altrimenti si installa con gogdl)."""
        return bool(self.galaxy())

    def detected(self) -> bool:
        return (bool(reg_subkeys("HKLM", REG)) or bool(self.galaxy()) or bool(PC.get(self.cfg, "gog"))
                or (MAC and bool(self._mac_installed())))

    def account(self) -> dict:
        a = PC.get(self.cfg, "gog", {})
        return {"connected": bool(a.get("refresh_token")), "user": a.get("user", ""), "galaxy": bool(self.galaxy())}

    @staticmethod
    def extract_code(text: str) -> str:
        """Accetta l'indirizzo finale del login (con code=...) o il solo codice."""
        import re
        text = (text or "").strip()
        m = re.search(r"[?&]code=([^&\s#]+)", text)
        return m.group(1) if m else text

    async def _token(self, params: dict) -> dict:
        r = await request(self.client, "GET", "https://auth.gog.com/token", ok404=False,
                          params={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, **params})
        if r is None or r.status_code != 200:
            raise RuntimeError(f"GOG: accesso non riuscito ({r.text[:150] if r is not None else 'nessuna risposta'})")
        d = r.json()
        prev = PC.get(self.cfg, "gog", {})
        PC.set(self.cfg, "gog", {"refresh_token": d["refresh_token"], "user_id": d.get("user_id"),
                                 "user": prev.get("user", ""), "time": time.time()})
        return d

    async def finish_login(self, code_or_url: str):
        code = self.extract_code(code_or_url)
        if not code:
            raise RuntimeError("Codice di autorizzazione GOG mancante")
        d = await self._token({"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT})
        r = await request(self.client, "GET", "https://embed.gog.com/userData.json",
                          headers={"Authorization": f"Bearer {d['access_token']}"})
        name = r.json().get("username", "") if r is not None and r.status_code == 200 else ""
        a = PC.get(self.cfg, "gog", {})
        a["user"] = name
        PC.set(self.cfg, "gog", a)
        return name

    @staticmethod
    def _mac_installed() -> dict[str, tuple[str, str]]:
        """id -> (titolo, cartella/app): dal db di Galaxy e dai .app standalone con goggame-<id>.info."""
        found: dict[str, tuple[str, str]] = {}
        try:
            if MAC_DB.exists():
                with sqlite3.connect(f"file:{MAC_DB}?mode=ro", uri=True) as db:
                    for pid, path, title in db.execute(
                            "SELECT i.productId, i.installationPath, l.title FROM InstalledBaseProducts i "
                            "LEFT JOIN LimitedDetails l ON l.productId = i.productId"):
                        if title and path and os.path.exists(path):
                            found[str(pid)] = (title, path)
        except sqlite3.Error:
            pass
        for info in Path("/Applications").glob("*.app/Contents/Resources/goggame-*.info"):
            try:
                d = json.loads(info.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            gid = str(d.get("gameId") or info.stem.split("-", 1)[1])
            if d.get("name"):
                found.setdefault(gid, (d["name"], str(info.parents[2])))
        return found

    def installed(self) -> dict[str, StoreGame]:
        out = {}
        for gid, (name, path) in self._mac_installed().items() if MAC else ():
            app = path if path.endswith(".app") else next(iter(sorted(Path(path).glob("*.app"))), None)
            launch = ({"type": "exe", "target": "/usr/bin/open", "args": [str(app)]} if app
                      else {"type": "uri", "target": f"goggalaxy://openGameView/{gid}"})
            out[gid] = StoreGame(store=self.id, id=gid, title=name, installed=True, install_dir=path,
                                 launch=launch, install_uri=self._install_uri(gid, ""),
                                 page="https://www.gog.com/account")
        for gid in reg_subkeys("HKLM", REG):
            v = reg_get("HKLM", REG + "\\" + gid) or {}
            name = v.get("gameName") or v.get("GAMENAME")
            exe = v.get("exe") or v.get("EXE")
            if not name or not os.path.isdir(v.get("path") or ""):  # voce di registro rimasta senza il gioco
                continue
            launch ={"type": "exe", "target": exe, "args": (v.get("launchParam") or "").split(), "cwd": v.get("workingDir") or v.get("path", "")}
            out[gid] = StoreGame(store=self.id, id=gid, title=name, installed=True, install_dir=v.get("path", ""),
                                 launch=launch, install_uri=self._install_uri(gid, ""),
                                 page="https://www.gog.com/account")
        return out

    def _install_uri(self, gid: str, slug: str) -> str:
        if self.galaxy():
            return f"goggalaxy://openGameView/{gid}"
        return "https://www.gog.com/account"  # download degli installer dalla libreria GOG

    async def fetch(self) -> list[StoreGame]:
        games = self.installed()
        a = PC.get(self.cfg, "gog", {})
        if not a.get("refresh_token"):
            self.log(f"GOG: {len(games)} giochi installati (collega l'account per vedere anche quelli non installati)")
            return list(games.values())
        try:
            token = (await self._token({"grant_type": "refresh_token", "refresh_token": a["refresh_token"]}))["access_token"]
        except RuntimeError as e:
            self.log(f"{e} - ricollega l'account GOG dalle impostazioni")
            return list(games.values())
        h = {"Authorization": f"Bearer {token}"}
        products, page, pages = [], 1, 1
        while page <= pages and page <= 100:
            r = await request(self.client, "GET", "https://embed.gog.com/account/getFilteredProducts",
                              params={"mediaType": 1, "page": page}, headers=h)
            if r is None or r.status_code != 200:
                break
            d = r.json()
            products += d.get("products", [])
            pages = d.get("totalPages", 1)
            page += 1
        cli = NC.installed(self.cfg, "gog")  # installati con gogdl da Pozzo
        sem = asyncio.Semaphore(8)

        async def boxart(pid):
            async with sem:
                r = await request(self.client, "GET", f"https://api.gog.com/v2/games/{pid}", params={"locale": "it-IT"})
                if r is None or r.status_code != 200:
                    return {}
                links = r.json().get("_links", {})
                return {"cover": (links.get("boxArtImage") or {}).get("href"),
                        "hero": (links.get("backgroundImage") or {}).get("href"),
                        "logo": (links.get("logo") or {}).get("href"),
                        "icon": (links.get("iconSquare") or {}).get("href")}

        arts = await asyncio.gather(*(boxart(p["id"]) for p in products))
        for p, art in zip(products, arts):
            gid = str(p["id"])
            g = games.get(gid) or StoreGame(store=self.id, id=gid, title=p.get("title", ""),
                                            install_uri=self._install_uri(gid, p.get("slug", "")),
                                            launch={"type": "uri", "target": f"goggalaxy://openGameView/{gid}"} if self.galaxy() else {})
            g.title = p.get("title") or g.title
            if gid in cli and not g.installed:
                g.installed, g.install_dir = True, cli[gid]["path"]
                g.launch = NC.launch_cmd(self.cfg, "gog", gid, cli[gid])
            # 1 = gioco, 3 = pack (DLC, artbook, contenuti extra): lo dice GOG
            g.kind = "game" if p.get("type") in (None, 1) else "dlc"
            g.page = "https://www.gog.com" + p.get("url", "") if p.get("url") else g.page
            img = {k: v for k, v in art.items() if v}
            if not img.get("cover") and p.get("image"):
                img["header"] = "https:" + p["image"] + "_product_tile_extended_432x243.jpg"
            g.images = img
            games[gid] = g
        self.log(f"GOG: {len(products)} giochi posseduti, {sum(g.installed for g in games.values())} installati")
        return list(games.values())
