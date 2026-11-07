"""Obiettivi dei giochi Steam, GOG ed Epic in una forma sola (come RetroAchievements, ma per i giochi PC).

Ogni provider riceve un httpx.Client (in prova con MockTransport) e ritorna
{source, game_id, total, unlocked, items:[{id, name, description, icon, unlocked, unlocked_at, rarity_pct}]}.
Timeout brevi e messaggi di errore chiari (AchError), come pozzo/retroachievements.py.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

UA = {"User-Agent": "PozzoLauncher/1.0"}
STEAM = "https://api.steampowered.com"
GOG_API = "https://gameplay.gog.com/clients/{cid}/users/{uid}/achievements"
EPIC_GQL = "https://graphql.epicgames.com/graphql"


class AchError(Exception):
    """Errore di credenziali, rete o dati con le API degli obiettivi."""


def http(transport: httpx.BaseTransport | None = None, timeout: float = 12.0) -> httpx.Client:
    return httpx.Client(headers=UA, timeout=httpx.Timeout(timeout, connect=8.0), transport=transport, follow_redirects=True)


def _json(r_fn, who: str):
    try:
        r = r_fn()
    except httpx.HTTPError as e:
        raise AchError(f"Errore di rete verso {who}: {e}") from e
    if r.status_code in (401, 403):
        raise AchError(f"Accesso a {who} negato (HTTP {r.status_code}): controlla le credenziali"
                       + (" e che il profilo Steam abbia i dettagli del gioco pubblici" if who == "Steam" else ""))
    if r.status_code == 429:
        raise AchError(f"Limite di richieste di {who} superato (HTTP 429): riprova piu' tardi")
    if r.status_code == 400 and who == "Steam":
        return {}  # Steam risponde 400 se il gioco non ha statistiche/obiettivi
    if r.status_code != 200:
        raise AchError(f"{who} ha risposto HTTP {r.status_code}: {r.text[:120]}")
    try:
        return r.json()
    except ValueError as e:
        raise AchError(f"Risposta non valida da {who}") from e


def _out(source, game_id, items):
    items.sort(key=lambda i: (not i["unlocked"], -(i["unlocked_at"] or 0), i["name"]))
    return {"source": source, "game_id": str(game_id), "total": len(items),
            "unlocked": sum(1 for i in items if i["unlocked"]), "items": items}


def _pct(v):
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ Steam
def steam_check(c: httpx.Client, key: str, steamid: str) -> None:
    """Prova la chiave API con una richiesta leggera (alza AchError se rifiutata)."""
    _json(lambda: c.get(f"{STEAM}/ISteamUser/GetPlayerSummaries/v0002/", params={"key": key, "steamids": steamid}), "Steam")


def steam(c: httpx.Client, key: str, steamid: str, appid: str, lang: str = "english") -> dict:
    if not key or not steamid:
        raise AchError("Servono la chiave API Steam e lo SteamID (impostazioni > Store)")
    p = {"key": key, "appid": appid, "l": lang}
    mine = _json(lambda: c.get(f"{STEAM}/ISteamUserStats/GetPlayerAchievements/v0001/", params={**p, "steamid": steamid}), "Steam")
    ps = mine.get("playerstats") or {}
    if ps.get("success") is False or not ps.get("achievements"):
        err = str(ps.get("error") or "")
        if "not public" in err.lower():
            raise AchError("Il profilo Steam non e' pubblico: rendi pubblici i dettagli del gioco")
        return _out("steam", appid, [])  # gioco senza obiettivi
    schema = _json(lambda: c.get(f"{STEAM}/ISteamUserStats/GetSchemaForGame/v2/", params=p), "Steam")
    sch = {a["name"]: a for a in ((schema.get("game") or {}).get("availableGameStats") or {}).get("achievements") or []}
    glob = _json(lambda: c.get(f"{STEAM}/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v0002/", params={"gameid": appid}), "Steam")
    rar = {a["name"]: a.get("percent") for a in (glob.get("achievementpercentages") or {}).get("achievements") or []}
    items = []
    for a in ps["achievements"]:
        n, s = a.get("apiname"), sch.get(a.get("apiname"), {})
        done = bool(a.get("achieved"))
        items.append({"id": n, "name": s.get("displayName") or a.get("name") or n,
                      "description": s.get("description") or a.get("description") or "",
                      "icon": s.get("icon" if done else "icongray") or s.get("icon"), "unlocked": done,
                      "unlocked_at": a.get("unlocktime") or None, "rarity_pct": _pct(rar.get(n))})
    return _out("steam", appid, items)


# ------------------------------------------------------------------ GOG
def gog_client_id(install_dir: str, product_id: str) -> str | None:
    """Il clientId sta nel goggame-<id>.info accanto al gioco installato.
    # shortcut: solo giochi GOG installati; per gli altri servirebbe il manifest della build (content-system), da fare se serve"""
    f = Path(install_dir or "") / f"goggame-{product_id}.info"
    try:
        return str(json.loads(f.read_text(encoding="utf-8-sig")).get("clientId") or "") or None
    except (OSError, ValueError):
        return None


def gog(c: httpx.Client, token: str, client_id: str, user_id: str, product_id: str) -> dict:
    d = _json(lambda: c.get(GOG_API.format(cid=client_id, uid=user_id), headers={"Authorization": f"Bearer {token}"}), "GOG")
    items = []
    for a in d.get("items") or []:
        ts = a.get("date_unlocked")
        items.append({"id": a.get("achievement_key") or a.get("achievement_id"), "name": a.get("name") or "",
                      "description": a.get("description") or "",
                      "icon": a.get("image_url_unlocked" if ts else "image_url_locked") or a.get("image_url_unlocked"),
                      "unlocked": bool(ts), "unlocked_at": _ts(ts), "rarity_pct": _pct(a.get("rarity"))})
    return _out("gog", product_id, items)


def _ts(iso):
    if not iso:
        return None
    from datetime import datetime
    try:
        return int(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


# ------------------------------------------------------------------ Epic
_Q_MINE = """query PlayerAchievement($epicAccountId: String!, $sandboxId: String!) { PlayerAchievement {
 playerAchievementGameRecordsBySandbox(epicAccountId: $epicAccountId, sandboxId: $sandboxId) { records {
 playerAchievements { playerAchievement { unlocked progress unlockDate achievementName } } } } } }"""
_Q_DEFS = """query Achievement($sandboxId: String!, $locale: String!) { Achievement {
 productAchievementsRecordBySandbox(sandboxId: $sandboxId, locale: $locale) { achievements { achievement {
 name hidden unlockedDisplayName lockedDisplayName unlockedDescription lockedDescription
 unlockedIconLink lockedIconLink rarity { percent } } } } } }"""


def _gql(c, token, query, variables):
    d = _json(lambda: c.post(EPIC_GQL, json={"query": query, "variables": variables},
                             headers={"Authorization": f"Bearer {token}"}), "Epic")
    if d.get("errors") and not d.get("data"):
        raise AchError("Epic: " + str((d["errors"][0] or {}).get("message", "richiesta rifiutata"))[:120])
    return d.get("data") or {}


def epic(c: httpx.Client, token: str, account_id: str, sandbox: str, item_id: str, locale: str = "en-US") -> dict:
    # shortcut: query GraphQL non documentate (Epic le puo' cambiare/chiudere); sandbox = CatalogNamespace del gioco installato
    defs = _gql(c, token, _Q_DEFS, {"sandboxId": sandbox, "locale": locale})
    defs = (((defs.get("Achievement") or {}).get("productAchievementsRecordBySandbox")) or {}).get("achievements") or []
    mine = _gql(c, token, _Q_MINE, {"epicAccountId": account_id, "sandboxId": sandbox})
    recs = ((((mine.get("PlayerAchievement") or {}).get("playerAchievementGameRecordsBySandbox")) or {}).get("records")) or []
    got = {}
    for r in recs:
        for x in r.get("playerAchievements") or []:
            pa = (x or {}).get("playerAchievement") or {}
            got[pa.get("achievementName")] = pa
    items = []
    for x in defs:
        a = (x or {}).get("achievement") or {}
        pa = got.get(a.get("name")) or {}
        done = bool(pa.get("unlocked"))
        hidden = bool(a.get("hidden")) and not done
        items.append({"id": a.get("name"),
                      "name": (a.get("unlockedDisplayName") if done else a.get("lockedDisplayName")) or a.get("unlockedDisplayName") or "",
                      "description": "" if hidden else (a.get("unlockedDescription") if done else a.get("lockedDescription")) or "",
                      "icon": a.get("unlockedIconLink" if done else "lockedIconLink"), "unlocked": done,
                      "unlocked_at": _ts(pa.get("unlockDate")), "rarity_pct": _pct((a.get("rarity") or {}).get("percent"))})
    return _out("epic", item_id, items)


# ------------------------------------------------------------------ token (GOG/Epic): rinnovo dal refresh token salvato
def gog_token(c: httpx.Client, refresh: str) -> dict:
    from .stores.gog import CLIENT_ID, CLIENT_SECRET
    d = _json(lambda: c.get("https://auth.gog.com/token", params={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                                                                  "grant_type": "refresh_token", "refresh_token": refresh}), "GOG")
    if not d.get("access_token"):
        raise AchError("GOG: accesso scaduto, ricollega l'account dalle impostazioni")
    return d


def epic_token(c: httpx.Client, refresh: str) -> dict:
    from .stores.epic import CLIENT_ID, CLIENT_SECRET, OAUTH
    auth = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    d = _json(lambda: c.post(OAUTH, data={"grant_type": "refresh_token", "refresh_token": refresh, "token_type": "eg1"},
                             headers={"Authorization": f"Basic {auth}"}), "Epic")
    if not d.get("access_token"):
        raise AchError("Epic: accesso scaduto, ricollega l'account dalle impostazioni")
    return d


def epic_namespace(item_id: str) -> str | None:
    """CatalogNamespace del gioco Epic installato (manifest del launcher)."""
    from .stores.epic import MANIFESTS
    for f in MANIFESTS.glob("*.item") if MANIFESTS.exists() else []:
        try:
            d = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
        except ValueError:
            continue
        if d.get("CatalogItemId") == item_id:
            return d.get("CatalogNamespace")
    return None
