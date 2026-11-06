"""Epic Games Store: installati dai manifest del launcher, posseduti tramite login all'account.

Il login usa lo stesso flusso dei launcher open source (Legendary/Heroic/Playnite): si accede
nella pagina ufficiale di Epic, che restituisce un "authorizationCode" monouso; lo si scambia
con un token. Il refresh token viene salvato nella cache locale.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from urllib.parse import quote

from .. import profilecfg as PC
from ..net import request
from .base import StoreGame, StoreProvider

CLIENT_ID = "34a02cf8f4414e29b15921876da36f9a"
CLIENT_SECRET = "daafbccc737745039dffe53d94fc76cf"
OAUTH = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token"
LIBRARY = "https://library-service.live.use1a.on.epicgames.com/library/api/public/items"
PLAYTIME = "https://library-service.live.use1a.on.epicgames.com/library/api/public/playtime/account/{acc}/all"
ASSETS = "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/public/assets/Windows"
CATALOG ="https://catalog-public-service-prod06.ol.epicgames.com/catalog/api/shared/namespace/{ns}/bulk/items"
LOGIN_URL = ("https://www.epicgames.com/id/login?redirectUrl=" +
             quote(f"https://www.epicgames.com/id/api/redirect?clientId={CLIENT_ID}&responseType=code", safe=""))
MANIFESTS = Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests")


def uri(ns: str, cid: str, app: str, action: str) -> str:
    return f"com.epicgames.launcher://apps/{ns}%3A{cid}%3A{app}?action={action}" + ("&silent=true" if action == "launch" else "")


class Epic(StoreProvider):
    id = "epic"
    name = "Epic Games"
    login = "oauth"
    login_url = LOGIN_URL

    def detected(self) -> bool:
        return MANIFESTS.exists() or bool(PC.get(self.cfg, "epic"))

    def account(self) -> dict:
        a = PC.get(self.cfg, "epic", {})
        return {"connected": bool(a.get("refresh_token")), "user": a.get("displayName", "")}

    @staticmethod
    def extract_code(text: str) -> str:
        """Accetta la pagina copiata (JSON grezzo o vista ad albero di Firefox) o il solo codice."""
        import re
        text = (text or "").strip()
        m = re.search(r'authorizationCode\W{0,6}([0-9a-fA-F]{32})', text)
        if m:
            return m.group(1)
        m = re.search(r'([0-9a-fA-F]{32})', text)
        return m.group(1) if m else text.strip('"')

    async def _token(self, data: dict) -> dict:
        auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        r = await request(self.client, "POST", OAUTH, data={**data, "token_type": "eg1"},
                          headers={"Authorization": f"Basic {auth}"}, ok404=False)
        if r is None or r.status_code != 200:
            msg = r.json().get("errorMessage", r.text[:200]) if r is not None else "nessuna risposta"
            raise RuntimeError(f"Epic: accesso non riuscito: {msg}")
        d = r.json()
        PC.set(self.cfg, "epic", {"refresh_token": d["refresh_token"], "account_id": d.get("account_id"),
                                  "displayName": d.get("displayName", ""),
                                  "refresh_expires": time.time() + d.get("refresh_expires", 0)})
        return d

    async def finish_login(self, code_or_page: str):
        code = self.extract_code(code_or_page)
        if not code:
            raise RuntimeError("Codice di autorizzazione Epic mancante")
        d = await self._token({"grant_type": "authorization_code", "code": code})
        return d.get("displayName", "")

    async def _access_token(self) -> str | None:
        a = PC.get(self.cfg, "epic", {})
        if not a.get("refresh_token"):
            return None
        try:
            return (await self._token({"grant_type": "refresh_token", "refresh_token": a["refresh_token"]}))["access_token"]
        except RuntimeError as e:
            self.log(f"{e} - ricollega l'account Epic dalle impostazioni")
            return None

    def installed(self) -> dict[str, dict]:
        out = {}
        # Durante un aggiornamento (o una verifica) il launcher sposta il manifest in Pending/ come "incompleto":
        # se esiste il manifest dell'installazione precedente il gioco e' comunque installato (es. Fortnite).
        # I manifest in Pending vengono letti per primi, cosi' quelli completi nella cartella principale vincono.
        for folder in (MANIFESTS / "Pending", MANIFESTS):
            if not folder.exists():
                continue
            for f in folder.glob("*.item"):
                try:
                    d = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
                except ValueError:
                    continue
                if d.get("CatalogNamespace") == "ue":
                    continue
                if d.get("bIsIncompleteInstall") and not Path(d.get("CompleteManifestPath") or "?").is_file():
                    continue
                out[d.get("CatalogItemId")] = d
        return out

    async def _played(self, h: dict, known: set) -> tuple[list[dict], dict[str, float]]:
        """Giochi free-to-play (Fortnite, Rocket League...) che non stanno nella libreria dell'account ma che
        l'account ha giocato: il tempo di gioco e' per artefatto, gli asset del launcher danno namespace e id."""
        acc = PC.get(self.cfg, "epic", {}).get("account_id")
        if not acc:
            return [], {}
        r = await request(self.client, "GET", PLAYTIME.format(acc=acc), headers=h)
        rows = r.json() if r is not None and r.status_code == 200 else []
        times = {x.get("artifactId"): float(x.get("totalTime") or 0) for x in rows if isinstance(x, dict) and x.get("artifactId")}
        if not times:
            return [], {}
        r = await request(self.client, "GET", ASSETS, params={"label": "Live"}, headers=h)
        assets = r.json() if r is not None and r.status_code == 200 else []
        extra = [{"namespace": a["namespace"], "catalogItemId": a["catalogItemId"], "appName": a["appName"]}
                 for a in assets if isinstance(a, dict) and a.get("appName") in times
                 and a.get("namespace") and a.get("catalogItemId") and a["catalogItemId"] not in known]
        return extra, times

    async def fetch(self) -> list[StoreGame]:
        inst = self.installed()
        games: dict[str, StoreGame] = {}
        for cid, d in inst.items():
            games[cid] = StoreGame(
                store=self.id, id=cid, title=d.get("DisplayName", d.get("AppName")), installed=True,
                install_dir=d.get("InstallLocation", ""), size=int(d.get("InstallSize") or 0),
                launch={"type": "uri", "target": uri(d["CatalogNamespace"], cid, d["AppName"], "launch")},
                install_uri=uri(d["CatalogNamespace"], cid, d["AppName"], "install"),
                page="https://store.epicgames.com/")
        token = await self._access_token()
        if not token:
            self.log(f"Epic: {len(games)} giochi installati (collega l'account per vedere anche quelli non installati)")
            return list(games.values())
        h = {"Authorization": f"Bearer {token}"}
        records, cursor = [], None
        for _ in range(50):  # paginazione
            params = {"includeMetadata": "true", "platform": "Windows"}
            if cursor:
                params["cursor"] = cursor
            r = await request(self.client, "GET", LIBRARY, params=params, headers=h)
            if r is None or r.status_code != 200:
                break
            d = r.json()
            records += d.get("records", [])
            cursor = (d.get("responseMetadata") or {}).get("nextCursor")
            if not cursor:
                break
        played = await self._played(h, {r["catalogItemId"] for r in records})
        records += played[0]
        # dettagli dal catalogo, raggruppati per namespace
        by_ns: dict[str, list[dict]] = {}
        for rec in records:
            if rec.get("namespace") in ("ue", None) or rec.get("sandboxType") == "PRIVATE":
                continue
            by_ns.setdefault(rec["namespace"], []).append(rec)
        for ns, recs in by_ns.items():
            ids = ",".join(r["catalogItemId"] for r in recs)
            r = await request(self.client, "GET", CATALOG.format(ns=ns),
                              params={"id": ids, "includeDLCDetails": "false", "includeMainGameDetails": "true",
                                      "country": "IT", "locale": "it"}, headers=h)
            items = r.json() if r is not None and r.status_code == 200 else {}
            for rec in recs:
                cid, app = rec["catalogItemId"], rec.get("appName", "")
                it = items.get(cid, {})
                if not it and cid not in inst:
                    continue  # senza scheda nel catalogo: DLC/contenuti aggiuntivi (il "titolo" sarebbe un codice)
                cats = {c.get("path") for c in it.get("categories", [])}
                dlc = bool(it) and ("addons" in cats or it.get("mainGameItem") or it.get("mainGameItemList"))
                if not dlc and it and "games" not in cats and "applications" not in cats and cid not in inst:
                    continue  # voce senza tipo (video, beta): il titolo non sarebbe affidabile
                imgs = {i.get("type"): i.get("url") for i in it.get("keyImages", [])}
                g = games.get(cid) or StoreGame(
                    store=self.id, id=cid, title=it.get("title") or app,
                    launch={"type": "uri", "target": uri(ns, cid, app, "launch")},
                    install_uri=uri(ns, cid, app, "install"), page="https://store.epicgames.com/")
                g.kind = "dlc" if dlc else "app" if "applications" in cats else "game"
                g.title = it.get("title") or g.title
                g.description = it.get("description", "") or g.description
                g.developer = it.get("developer", "") or g.developer
                g.images = {k: v for k, v in {
                    "cover": imgs.get("DieselGameBoxTall") or imgs.get("OfferImageTall"),
                    "hero": imgs.get("DieselGameBox") or imgs.get("OfferImageWide"),
                    "logo": imgs.get("DieselGameBoxLogo"), "icon": imgs.get("Thumbnail")}.items() if v}
                g.playtime = g.playtime or played[1].get(app, 0)
                games[cid] = g
        self.log(f"Epic: {len(games)} giochi posseduti, {sum(g.installed for g in games.values())} installati")
        return list(games.values())
