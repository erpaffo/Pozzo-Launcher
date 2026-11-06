"""Media server: le librerie di Jellyfin e Plex dentro Pozzo, con lo stesso contratto di media-locale.

Contratto «fonte di media» (vedi media-locale):
    list(kind, query) -> [MediaItem]
    detail(id) -> MediaItem
    play_target(id) -> {url, resume_pos}
    set_progress(id, pos, seen) -> {"ok": true}
Il server resta la fonte di verità: posizione e «visto» si sincronizzano con lui (Sessions/Playing per Jellyfin,
/:/progress e /:/scrobble per Plex). Le credenziali restano in locale, in settings.json; la password serve solo
al primo accesso (poi si usa il token) e non viene mai salvata né restituita.

Rotte (/plugin-api/media-server/...):
    GET  list?kind=&query=&source= -> [MediaItem]
    GET  detail?id=&source=        -> MediaItem
    GET  play_target?id=&source=   -> {"url", "resume_pos", "external", "mime"}
    POST set_progress              <- {"id", "pos", "seen", "source"}
    GET  artwork?src=&source=      -> immagine del server (il token non arriva al frontend)
    GET  config                    -> server configurati, senza token né password
    POST config                    <- {"source", "base_url", "api_key"|"token", "username", "password"}
    GET  test?source=              -> {"ok", "items"?, "error"?}

Se `source` è omesso si usa il primo server configurato. Nessun HLS, nessuna transcodifica: si chiede al server
lo stream diretto e lo si passa al player (integrato o esterno).
"""

from __future__ import annotations

import re
from urllib.parse import quote, urlencode

import httpx
from fastapi import Body, HTTPException
from fastapi.responses import Response

TICKS = 10_000_000  # Jellyfin: 1 tick = 100 ns
BROWSER = {"mp4", "m4v", "webm", "ogv", "mp3", "flac", "m4a", "ogg", "opus", "wav"}
MIME = {"mp4": "video/mp4", "m4v": "video/mp4", "webm": "video/webm", "ogv": "video/ogg", "mkv": "video/x-matroska",
        "avi": "video/x-msvideo", "mov": "video/quicktime", "mp3": "audio/mpeg", "flac": "audio/flac",
        "m4a": "audio/mp4", "ogg": "audio/ogg", "opus": "audio/ogg", "wav": "audio/wav"}
KINDS = ("film", "episodio", "brano")
MAX_IMAGE = 8 * 1024 * 1024


class Http:
    """Client HTTP minimo e sostituibile nei test: basta un oggetto con request(method, url, **kw)."""

    def __init__(self, timeout: float = 20.0):
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)

    def request(self, method: str, url: str, **kw):
        try:
            return self._client.request(method, url, **kw)
        except httpx.HTTPError as e:  # server spento, DNS, timeout: 502 invece di un 500 con lo stack
            # solo il tipo di errore: l'URL (per Plex e Jellyfin) contiene il token e non deve finire nei messaggi
            raise HTTPException(502, f"server non raggiungibile ({type(e).__name__})")

    def close(self):
        self._client.close()


def _json(resp, what: str) -> dict:
    status = getattr(resp, "status_code", 200)
    if status == 404:
        raise HTTPException(404, f"{what}: contenuto non trovato")
    if status in (401, 403):
        raise HTTPException(401, f"{what}: credenziali rifiutate dal server (token scaduto?)")
    if status >= 400:
        raise HTTPException(502, f"{what}: il server ha risposto {status}")
    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(502, f"{what}: risposta non leggibile")
    return data if isinstance(data, dict) else {}


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------- Jellyfin
class Jellyfin:
    """Adattatore Jellyfin: /Items per la lista, /Videos|/Audio/{id}/stream per lo stream diretto."""

    id = "jellyfin"
    _TYPE = {"Movie": "film", "Episode": "episodio", "Audio": "brano"}

    def __init__(self, base: str, http, token: str = "", user_id: str = ""):
        self.base, self.http, self.token, self.user_id = base.rstrip("/"), http, token, user_id

    def _headers(self) -> dict:
        out = {"Accept": "application/json"}
        if self.token:
            out["X-Emby-Token"] = self.token
        return out

    def _get(self, path: str, params: dict | None = None) -> dict:
        return _json(self.http.request("GET", self.base + path, params=params or {}, headers=self._headers()),
                     "Jellyfin")

    def _post(self, path: str, body: dict | None = None) -> dict:
        return _json(self.http.request("POST", self.base + path, json=body or {}, headers=self._headers()), "Jellyfin")

    def item(self, raw: dict) -> dict | None:
        kind = self._TYPE.get(raw.get("Type") or "")
        if not kind or not raw.get("Id"):
            return None
        out = {"id": str(raw["Id"]), "kind": kind, "title": raw.get("Name") or "", "source": "jellyfin"}
        if raw.get("SeriesName"):
            out["series"] = raw["SeriesName"]
        for key, field in (("season", "ParentIndexNumber"), ("episode", "IndexNumber"), ("year", "ProductionYear")):
            if raw.get(field) is not None:
                out[key] = raw[field]
        if raw.get("RunTimeTicks"):
            out["duration"] = round(_num(raw["RunTimeTicks"]) / TICKS, 1)
        if raw.get("Overview"):
            out["overview"] = str(raw["Overview"])[:600]
        if (raw.get("ImageTags") or {}).get("Primary"):
            out["poster"] = self.artwork_url(str(raw["Id"]))
        data = raw.get("UserData") or {}
        if data.get("PlaybackPositionTicks"):
            out["resume_pos"] = round(_num(data["PlaybackPositionTicks"]) / TICKS, 1)
        out["seen"] = bool(data.get("Played"))
        return out

    def artwork_url(self, item_id: str) -> str:
        return f"/plugin-api/media-server/artwork?source=jellyfin&src={quote(f'/Items/{item_id}/Images/Primary')}"

    def list(self, kind: str = "", query: str = "", limit: int = 200) -> list[dict]:
        types = {"film": "Movie", "episodio": "Episode", "brano": "Audio"}.get(kind, "Movie,Episode,Audio")
        params = {"Recursive": "true", "IncludeItemTypes": types, "SearchTerm": query or "",
                  "Limit": str(max(1, min(limit, 1000))), "SortBy": "SortName", "ImageTypeLimit": "1",
                  "Fields": "Overview,RunTimeTicks,SeriesName,ParentIndexNumber,IndexNumber,ProductionYear"}
        if self.user_id:
            params["UserId"] = self.user_id
        data = self._get("/Items", params)
        return [x for x in (self.item(i) for i in data.get("Items") or []) if x]

    def _raw(self, item_id: str) -> dict:
        path = f"/Users/{self.user_id}/Items/{quote(item_id)}" if self.user_id else f"/Items/{quote(item_id)}"
        return self._get(path)

    def detail(self, item_id: str) -> dict:
        out = self.item(self._raw(item_id))
        if out is None:
            raise HTTPException(404, "contenuto non trovato")
        return out

    def play_target(self, item_id: str) -> dict:
        raw = self._raw(item_id)
        out = self.item(raw)
        if out is None:
            raise HTTPException(404, "contenuto non trovato")
        container = str(raw.get("Container") or "").lower()
        path = f"/Audio/{quote(item_id)}/stream" if out["kind"] == "brano" else f"/Videos/{quote(item_id)}/stream"
        params = {"static": "true", "api_key": self.token}
        sources = raw.get("MediaSources") or []
        if sources and sources[0].get("Id"):
            params["mediaSourceId"] = str(sources[0]["Id"])
        return {"url": f"{self.base}{path}?{urlencode(params)}", "resume_pos": out.get("resume_pos", 0.0),
                "external": container not in BROWSER, "mime": MIME.get(container, "application/octet-stream")}

    def set_progress(self, item_id: str, pos: float = 0.0, seen: bool = False) -> dict:
        ticks = int(max(0.0, _num(pos)) * TICKS)
        body = {"ItemId": item_id, "PositionTicks": ticks, "CanSeek": True, "PlayMethod": "DirectPlay"}
        self._post("/Sessions/Playing/Progress", body)
        if seen:
            if not self.user_id:
                raise HTTPException(400, "per segnare «visto» su Jellyfin serve l'accesso con utente e password")
            self._post(f"/Users/{self.user_id}/PlayedItems/{quote(item_id)}")
            self._post("/Sessions/Playing/Stopped", body)
        elif ticks == 0 and self.user_id:
            self.http.request("DELETE", f"{self.base}/Users/{self.user_id}/PlayedItems/{quote(item_id)}",
                              headers=self._headers())
        return {"ok": True}


def jellyfin_login(base: str, username: str, password: str, http) -> dict:
    """Utente e password -> {"token", "user_id"}. La password non viene salvata da nessuna parte."""
    head = {'Authorization': 'MediaBrowser Client="Pozzo Launcher", Device="PC", DeviceId="pozzo-launcher", '
                             'Version="1.0"', "Content-Type": "application/json"}
    data = _json(http.request("POST", base.rstrip("/") + "/Users/AuthenticateByName", json={"Username": username,
                                                                                           "Pw": password},
                             headers=head), "Jellyfin")
    token = data.get("AccessToken")
    if not token:
        raise HTTPException(400, "Jellyfin non ha restituito un token: utente o password errati")
    return {"token": str(token), "user_id": str((data.get("User") or {}).get("Id") or "")}


# ---------------------------------------------------------------- Plex
class Plex:
    """Adattatore Plex: /library/sections per le librerie, /:/progress e /:/scrobble per lo stato."""

    id = "plex"
    _TYPE = {"movie": "film", "episode": "episodio", "track": "brano"}
    _SECTION = {"film": ("movie", None), "episodio": ("show", "4"), "brano": ("artist", "10")}
    _IDENTIFIER = "com.plexapp.plugins.library"

    def __init__(self, base: str, http, token: str):
        self.base, self.http, self.token = base.rstrip("/"), http, token

    def _get(self, path: str, params: dict | None = None) -> dict:
        query = {**(params or {}), "X-Plex-Token": self.token}
        resp = self.http.request("GET", self.base + path, params=query, headers={"Accept": "application/json"})
        return _json(resp, "Plex")

    def _post(self, path: str, params: dict | None = None) -> dict:
        query = {**(params or {}), "X-Plex-Token": self.token}
        return _json(self.http.request("POST", self.base + path, params=query), "Plex")

    def artwork_url(self, thumb: str) -> str:
        return f"/plugin-api/media-server/artwork?source=plex&src={quote(thumb)}"

    def item(self, raw: dict) -> dict | None:
        kind = self._TYPE.get(raw.get("type") or "")
        if not kind or not raw.get("ratingKey"):
            return None
        out = {"id": str(raw["ratingKey"]), "kind": kind, "title": raw.get("title") or "", "source": "plex"}
        series = raw.get("grandparentTitle") or (raw.get("parentTitle") if kind == "brano" else "")
        if series:
            out["series"] = series
        for key, field in (("season", "parentIndex"), ("episode", "index"), ("year", "year")):
            if raw.get(field) is not None:
                out[key] = raw[field]
        if raw.get("duration"):
            out["duration"] = round(_num(raw["duration"]) / 1000, 1)
        if raw.get("summary"):
            out["overview"] = str(raw["summary"])[:600]
        if raw.get("thumb"):
            out["poster"] = self.artwork_url(raw["thumb"])
        if raw.get("viewOffset"):
            out["resume_pos"] = round(_num(raw["viewOffset"]) / 1000, 1)
        out["seen"] = bool(raw.get("viewCount"))
        return out

    def sections(self) -> list[dict]:
        data = self._get("/library/sections")
        return (data.get("MediaContainer") or {}).get("Directory") or []

    def list(self, kind: str = "", query: str = "", limit: int = 200) -> list[dict]:
        limit = max(1, min(limit, 1000))
        if query:
            data = self._get("/search", {"query": query, "limit": limit})
            raws = [m for hub in (data.get("MediaContainer") or {}).get("Hub") or [] for m in hub.get("Metadata") or []]
        else:
            raws = []
            wanted = self._SECTION.get(kind)
            for section in self.sections():
                stype = section.get("type")
                if wanted and stype != wanted[0]:
                    continue
                if not wanted and stype not in ("movie", "show", "artist"):
                    continue
                sub = wanted[1] if wanted else {"movie": None, "show": "4", "artist": "10"}[stype]
                params = {"X-Plex-Container-Start": "0", "X-Plex-Container-Size": str(limit)}
                if sub:
                    params["type"] = sub
                data = self._get(f"/library/sections/{quote(str(section.get('key')))}/all", params)
                raws += (data.get("MediaContainer") or {}).get("Metadata") or []
        return [x for x in (self.item(raw) for raw in raws) if x and (not kind or x["kind"] == kind)][:limit]

    def _raw(self, item_id: str) -> dict:
        data = self._get(f"/library/metadata/{quote(item_id)}")
        found = (data.get("MediaContainer") or {}).get("Metadata") or []
        if not found:
            raise HTTPException(404, "contenuto non trovato")
        return found[0]

    def detail(self, item_id: str) -> dict:
        out = self.item(self._raw(item_id))
        if out is None:
            raise HTTPException(404, "contenuto non trovato")
        return out

    def play_target(self, item_id: str) -> dict:
        raw = self._raw(item_id)
        out = self.item(raw)
        if out is None:
            raise HTTPException(404, "contenuto non trovato")
        part = ((raw.get("Media") or [{}])[0].get("Part") or [{}])[0]
        key = part.get("key")
        if not key:
            raise HTTPException(502, "Plex non ha indicato un file da riprodurre")
        container = str(part.get("container") or "").lower()
        url = f"{self.base}{key}?{urlencode({'X-Plex-Token': self.token})}"
        return {"url": url, "resume_pos": out.get("resume_pos", 0.0),
                "external": container not in BROWSER, "mime": MIME.get(container, "application/octet-stream")}

    def set_progress(self, item_id: str, pos: float = 0.0, seen: bool = False) -> dict:
        ms = int(max(0.0, _num(pos)) * 1000)
        self._post("/:/progress", {"key": item_id, "identifier": self._IDENTIFIER, "time": str(ms),
                                   "state": "stopped" if seen else "playing"})
        if seen:
            self._post("/:/scrobble", {"key": item_id, "identifier": self._IDENTIFIER})
        elif ms == 0:
            self._post("/:/unscrobble", {"key": item_id, "identifier": self._IDENTIFIER})
        return {"ok": True}


# ---------------------------------------------------------------- rotte
def _base_url(raw) -> str:
    url = str(raw or "").strip().rstrip("/")
    if not re.match(r"^https?://[^\s/]+", url) or len(url) > 300:
        raise HTTPException(400, "serve un indirizzo http:// o https:// del server")
    return url


def _bare(conf: dict) -> dict:
    """Configurazione senza segreti: token e password non escono mai dal PC tramite l'API."""
    return {"base_url": conf.get("base_url", ""), "user_id": conf.get("user_id", ""),
            "configured": bool(conf.get("base_url") and conf.get("token"))}


def register(gs):
    http = Http()

    def configured() -> dict[str, dict]:
        servers = gs.settings.get("servers") or {}
        return {k: v for k, v in servers.items() if isinstance(v, dict)}

    def adapter(source: str = ""):
        servers = configured()
        if source:
            conf = servers.get(source)
            if not conf or not conf.get("base_url"):
                raise HTTPException(400, f"server «{source}» non configurato")
        else:
            source, conf = next(((k, v) for k, v in servers.items() if v.get("base_url")), ("", None))
            if not conf:
                raise HTTPException(400, "nessun server configurato: imposta indirizzo e credenziali")
        if source == "jellyfin":
            return Jellyfin(conf["base_url"], http, conf.get("token") or "", conf.get("user_id") or "")
        return Plex(conf["base_url"], http, conf.get("token") or "")

    gs.add_player({"id": "integrato", "label": "Lettore integrato", "mode": "integrato"})
    gs.add_player({"id": "esterno", "label": "Lettore esterno (mpv, VLC o sistema)", "mode": "esterno"})

    @gs.route("list")
    def media_list(kind: str = "", query: str = "", q: str = "", source: str = "", limit: int = 200):
        return adapter(source).list(kind if kind in KINDS else "", (query or q or "").strip()[:200], limit)

    @gs.route("detail")
    def media_detail(id: str = "", source: str = ""):
        return adapter(source).detail(str(id or ""))

    @gs.route("play_target")
    def media_play_target(id: str = "", source: str = ""):
        return adapter(source).play_target(str(id or ""))

    @gs.route("set_progress", methods=("POST",))
    def media_set_progress(body: dict | None = Body(None), id: str = "", pos: float | None = None,
                           seen: bool | None = None, source: str = ""):
        data = body if isinstance(body, dict) else {}
        item_id = str(data.get("id") or id or "").strip()
        if not item_id:
            raise HTTPException(400, "id mancante")
        return adapter(str(data.get("source") or source or "")).set_progress(
            item_id, _num(data.get("pos", pos)), bool(data.get("seen", seen)))

    @gs.route("artwork")
    def media_artwork(src: str = "", source: str = ""):
        server = adapter(source)
        path = str(src or "")
        if not path.startswith("/") or path.startswith("//") or ".." in path or len(path) > 500:
            raise HTTPException(400, "immagine non valida")
        params = {"X-Plex-Token": server.token} if server.id == "plex" else {"api_key": server.token}
        resp = http.request("GET", server.base + path, params=params, headers={"Accept": "image/*"})
        if getattr(resp, "status_code", 200) >= 400:
            raise HTTPException(502, f"il server ha risposto {resp.status_code} per l'immagine")
        body = resp.content or b""
        if len(body) > MAX_IMAGE:
            raise HTTPException(502, "immagine troppo grande")
        return Response(content=body, media_type=resp.headers.get("content-type") or "image/jpeg",
                        headers={"Cache-Control": "max-age=3600"})

    @gs.route("config")
    def media_config():
        servers = configured()
        return {"servers": {k: _bare(v) for k, v in servers.items()},
                "sources": [k for k, v in servers.items() if v.get("base_url")]}

    @gs.route("config", methods=("POST",))
    def media_config_save(body: dict = Body(...)):
        source = str(body.get("source") or "").strip()
        if source not in ("jellyfin", "plex"):
            raise HTTPException(400, "source deve essere «jellyfin» o «plex»")
        base = _base_url(body.get("base_url"))
        conf = {"base_url": base}
        if source == "jellyfin":
            username, password = str(body.get("username") or ""), str(body.get("password") or "")
            key = str(body.get("api_key") or "").strip()
            if username and password:
                conf.update(jellyfin_login(base, username, password, http))
            elif key:
                conf["token"] = key
            else:
                raise HTTPException(400, "servono utente e password, oppure una chiave API di Jellyfin")
        else:
            token = str(body.get("token") or body.get("api_key") or "").strip()
            if not token:
                raise HTTPException(400, "serve il token del tuo account Plex (resta solo su questo PC)")
            conf["token"] = token
        servers = {**configured(), source: conf}
        gs.save_settings({"servers": servers})
        return {"ok": True, "servers": {k: _bare(v) for k, v in servers.items()}}

    @gs.route("test")
    def media_test(source: str = ""):
        try:
            items = adapter(source).list("", "", 1)
        except HTTPException as e:
            return {"ok": False, "error": str(e.detail)}
        return {"ok": True, "items": len(items)}
