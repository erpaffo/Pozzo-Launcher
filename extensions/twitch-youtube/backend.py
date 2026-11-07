"""Dirette Twitch e video YouTube per il dettaglio di un gioco. Le chiavi sono quelle dell'utente (nessuna inclusa).

GET  /plugin-api/twitch-youtube/stato                  -> {"twitch": bool, "youtube": bool}
GET  /plugin-api/twitch-youtube/live/{titolo}          -> {"streams": [{user, title, viewers, thumbnail, url}]}
GET  /plugin-api/twitch-youtube/videos/{titolo}        -> {"videos": [{title, channel, thumb, videoId}]}
POST /plugin-api/twitch-youtube/impostazioni {"twitch_client_id", "twitch_client_secret", "youtube_key"} (vuoti = non cambiano)

Chiavi mancanti: 400 con il messaggio da mostrare. Errori di rete o delle API: 502. Risposte in cache 10 minuti (in memoria).
Il token Twitch (client_credentials) si riusa finche' non scade.
"""

import html
import time

import httpx
from fastapi import Body, HTTPException

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX = "https://api.twitch.tv/helix"
YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
TTL = 600
TIMEOUT = 10
_token: dict = {}  # {"creds": (id, segreto), "token": str, "exp": secondi}
_cache: dict = {}  # chiave -> (momento, dati)


def _client():
    return httpx.Client(timeout=TIMEOUT)


def _send(method: str, url: str, nome: str, **kw) -> dict:
    try:
        with _client() as c:
            r = c.request(method, url, **kw)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"{nome}: rete non disponibile ({type(e).__name__})")
    if r.status_code in (400, 401, 403):
        raise HTTPException(502, f"{nome}: chiave o credenziali non valide, oppure quota esaurita")
    if r.status_code >= 400:
        raise HTTPException(502, f"{nome}: errore {r.status_code}")
    return r.json()


def cached(chiave, fn):
    hit = _cache.get(chiave)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    data = fn()  # un errore non entra in cache
    _cache[chiave] = (time.time(), data)
    return data


def twitch_token(cid: str, segreto: str) -> str:
    if _token.get("creds") == (cid, segreto) and time.time() < _token.get("exp", 0):
        return _token["token"]
    j = _send("POST", TOKEN_URL, "Twitch", data={"client_id": cid, "client_secret": segreto, "grant_type": "client_credentials"})
    _token.update(creds=(cid, segreto), token=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)) - 60)
    return _token["token"]


def parse_streams(j: dict) -> list[dict]:
    return [{"user": s.get("user_name", ""), "title": s.get("title", ""), "viewers": int(s.get("viewer_count") or 0),
             "thumbnail": (s.get("thumbnail_url") or "").replace("{width}", "440").replace("{height}", "248"),
             "url": "https://www.twitch.tv/" + (s.get("user_login") or s.get("user_name") or "")}
            for s in j.get("data", [])]


def twitch_live(titolo: str, cid: str, segreto: str) -> list[dict]:
    h = {"Client-Id": cid, "Authorization": f"Bearer {twitch_token(cid, segreto)}"}
    games = _send("GET", f"{HELIX}/games", "Twitch", params={"name": titolo}, headers=h)
    if not games.get("data"):  # nessuna categoria con questo nome: nessuna diretta da mostrare
        return []
    gid = games["data"][0]["id"]
    return parse_streams(_send("GET", f"{HELIX}/streams", "Twitch", params={"game_id": gid, "first": 6}, headers=h))


def parse_videos(j: dict) -> list[dict]:
    out = []
    for it in j.get("items", []):
        vid = (it.get("id") or {}).get("videoId")
        if not vid:
            continue
        sn = it.get("snippet") or {}
        th = sn.get("thumbnails") or {}
        out.append({"title": html.unescape(sn.get("title", "")), "channel": html.unescape(sn.get("channelTitle", "")),
                    "thumb": (th.get("medium") or th.get("high") or th.get("default") or {}).get("url", ""),
                    "videoId": vid})
    return out


def youtube_videos(titolo: str, key: str) -> list[dict]:
    visti, out = set(), []
    for q in (f"{titolo} trailer", f"{titolo} guida"):
        params = {"part": "snippet", "type": "video", "q": q, "maxResults": 6, "key": key}
        for v in parse_videos(_send("GET", YT_SEARCH, "YouTube", params=params)):
            if v["videoId"] not in visti:
                visti.add(v["videoId"])
                out.append(v)
    return out


def register(gs):
    def chiavi() -> tuple[str, str, str]:
        s = gs.settings
        return (str(s.get("twitch_client_id") or "").strip(), str(s.get("twitch_client_secret") or "").strip(),
                str(s.get("youtube_key") or "").strip())

    @gs.route("stato")
    def stato():
        cid, segreto, yt = chiavi()
        return {"twitch": bool(cid and segreto), "youtube": bool(yt)}

    @gs.route("live/{titolo:path}")
    def live(titolo: str):
        cid, segreto, _ = chiavi()
        if not (cid and segreto):
            raise HTTPException(400, "Dirette Twitch: inserisci Client ID e Client Secret in Impostazioni › Streaming "
                                     "(app gratuita su dev.twitch.tv).")
        return {"streams": cached(("live", titolo.lower(), cid, segreto), lambda: twitch_live(titolo, cid, segreto))}

    @gs.route("videos/{titolo:path}")
    def videos(titolo: str):
        yt = chiavi()[2]
        if not yt:
            raise HTTPException(400, "Video YouTube: inserisci la chiave YouTube Data API in Impostazioni › Streaming.")
        return {"videos": cached(("videos", titolo.lower(), yt), lambda: youtube_videos(titolo, yt))}

    @gs.route("impostazioni", methods=("POST",))
    def impostazioni(body: dict = Body(...)):
        nuovi = {k: str(body[k]).strip()[:200] for k in ("twitch_client_id", "twitch_client_secret", "youtube_key") if body.get(k)}
        gs.save_settings(nuovi)
        return stato()
