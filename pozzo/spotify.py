"""Client Spotify con OAuth Authorization Code + PKCE, senza client secret."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from . import profilecfg as PC

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_URL = "https://api.spotify.com/v1"
SCOPES = "user-read-playback-state user-modify-playback-state"
HTTP_TIMEOUT = 4
STATUS_TTL = 2.0


class SpotifyError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, retry_after: int | None = None):
        super().__init__(message)
        self.code, self.status, self.retry_after = code, status, retry_after


def pkce_pair(verifier: str | None = None) -> tuple[str, str]:
    verifier = verifier or secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def parse_playback(data: dict) -> dict:
    item = data.get("item") or {}
    artists = item.get("artists") or []
    images = ((item.get("album") or {}).get("images") or [])
    device = data.get("device") or {}
    return {
        "track": item.get("name") or "",
        "artists": [a.get("name", "") for a in artists if a.get("name")],
        "cover": images[0].get("url", "") if images else "",
        "progress_ms": int(data.get("progress_ms") or 0),
        "duration_ms": int(item.get("duration_ms") or 0),
        "is_playing": bool(data.get("is_playing")),
        "shuffle": bool(data.get("shuffle_state")),
        "volume": device.get("volume_percent"),
        "device": device.get("name") or "",
        "device_active": bool(device.get("is_active")),
    }


def map_error(status: int, body: dict, retry_after: str | None = None) -> SpotifyError:
    if status == 429:
        try:
            delay = max(1, int(float(retry_after or body.get("retry_after") or 1)))
        except (TypeError, ValueError):
            delay = 1
        return SpotifyError("rate_limited", f"Spotify ha chiesto di attendere {delay} secondi.", 429, delay)
    if status == 401:
        return SpotifyError("token_expired", "Accesso Spotify scaduto: riconnetti l'account.", 401)
    if status == 403:
        return SpotifyError("premium_required", "Spotify Premium ? necessario per controllare la riproduzione.", 403)
    if status == 404:
        return SpotifyError("no_device", "Nessun dispositivo Spotify attivo.", 404)
    detail = body.get("error_description") or (body.get("error") or {}).get("message") or "Richiesta a Spotify non riuscita."
    return SpotifyError("spotify_error", str(detail), status if 400 <= status < 600 else 502)


class SpotifyClient:
    def __init__(self, cfg, save: Callable | None = None, opener=None, clock=time.time):
        self.cfg, self.save, self.opener, self.clock = cfg, save or (lambda data: None), opener or urllib.request.urlopen, clock
        self.pending: dict | None = None

    @property
    def settings(self) -> dict:
        return PC.get(self.cfg, "spotify", {})

    @property
    def redirect_uri(self) -> str:
        port = int(self.cfg.app.get("port", 8765))
        return f"http://127.0.0.1:{port}/api/spotify/callback"

    def _store(self, values: dict):
        merged = {**self.settings, **values}
        self.save(merged)
        self.cfg.app["spotify"] = merged  # specchio in memoria (senza cartella dati le letture passano da qui)

    def configure(self, client_id: str) -> dict:
        client_id = str(client_id or "").strip()
        if len(client_id) > 160:
            raise SpotifyError("invalid_client_id", "Client ID Spotify non valido.")
        values = {"client_id": client_id}
        if client_id != self.settings.get("client_id", ""):
            values.update({"access_token": "", "refresh_token": "", "expires_at": 0})
        self._store(values)
        return self.public_status()

    def public_status(self) -> dict:
        return {"client_id": self.settings.get("client_id", ""),
                "authenticated": bool(self.settings.get("refresh_token") or self.settings.get("access_token")),
                "redirect_uri": self.redirect_uri}

    def login_url(self) -> str:
        client_id = self.settings.get("client_id", "")
        if not client_id:
            raise SpotifyError("missing_client_id", "Inserisci prima il Client ID di Spotify.")
        verifier, challenge = pkce_pair()
        state = secrets.token_urlsafe(24)
        self.pending = {"verifier": verifier, "state": state}
        query = urllib.parse.urlencode({"client_id": client_id, "response_type": "code", "redirect_uri": self.redirect_uri,
                                        "code_challenge_method": "S256", "code_challenge": challenge,
                                        "scope": SCOPES, "state": state})
        return f"{AUTH_URL}?{query}"

    def callback(self, code: str, state: str, error: str = "") -> dict:
        pending, self.pending = self.pending, None
        if error:
            raise SpotifyError("authorization_denied", "Accesso Spotify annullato o negato.")
        if not pending or not secrets.compare_digest(str(state or ""), pending["state"]):
            raise SpotifyError("invalid_state", "La sessione di accesso Spotify non ? valida. Riprova.")
        tokens = self._token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri,
                                      "client_id": self.settings.get("client_id", ""), "code_verifier": pending["verifier"]})
        self._store({"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token", self.settings.get("refresh_token", "")),
                     "expires_at": self.clock() + int(tokens.get("expires_in", 3600))})
        return self.public_status()

    def _send(self, method: str, url: str, *, data: dict | None = None, headers: dict | None = None):
        payload = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=payload, headers={"User-Agent": "PozzoLauncher/1.0", **(headers or {})}, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            response = self.opener(req, timeout=HTTP_TIMEOUT)
            status, response_headers, raw = response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            status, response_headers, raw = error.code, error.headers, error.read()
        except (OSError, urllib.error.URLError) as error:
            raise SpotifyError("network_error", f"Spotify non raggiungibile: {error}", 503) from error
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            body = {}
        return status, response_headers, body

    def _token_request(self, data: dict) -> dict:
        status, headers, body = self._send("POST", TOKEN_URL, data=data)
        if status != 200 or not body.get("access_token"):
            raise map_error(status, body, headers.get("Retry-After"))
        return body

    def refresh(self, force: bool = False):
        settings = self.settings
        token, refresh_token = settings.get("access_token"), settings.get("refresh_token")
        if not force and token and float(settings.get("expires_at", 0)) > self.clock() + 60:
            return token
        if not refresh_token:
            if token:
                raise SpotifyError("token_expired", "Accesso Spotify scaduto: riconnetti l'account.", 401)
            return None
        tokens = self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token,
                                      "client_id": settings.get("client_id", "")})
        self._store({"access_token": tokens["access_token"], "refresh_token": tokens.get("refresh_token", refresh_token),
                     "expires_at": self.clock() + int(tokens.get("expires_in", 3600))})
        return tokens["access_token"]

    def _api(self, method: str, path: str, params: dict | None = None, body: dict | None = None):
        token = self.refresh()
        if not token:
            raise SpotifyError("not_connected", "Accedi a Spotify dalle impostazioni.", 401)
        url = API_URL + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        payload = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=payload, headers={"Authorization": f"Bearer {token}",
            "Content-Type": "application/json", "User-Agent": "PozzoLauncher/1.0"}, method=method)
        try:
            response = self.opener(req, timeout=HTTP_TIMEOUT)
            status, headers, raw = response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            status, headers, raw = error.code, error.headers, error.read()
        except (OSError, urllib.error.URLError) as error:
            raise SpotifyError("network_error", f"Spotify non raggiungibile: {error}", 503) from error
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            data = {}
        if status == 401 and self.settings.get("refresh_token"):
            token = self.refresh(force=True)
            req.add_header("Authorization", f"Bearer {token}")
            try:
                response = self.opener(req, timeout=HTTP_TIMEOUT)
                status, headers, raw = response.status, response.headers, response.read()
            except urllib.error.HTTPError as error:
                status, headers, raw = error.code, error.headers, error.read()
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, ValueError):
                data = {}
        if status == 204:
            return None
        if status < 200 or status >= 300:
            raise map_error(status, data, headers.get("Retry-After"))
        return data

    def status(self) -> dict:
        base = self.public_status()
        if not base["authenticated"]:
            return {**base, "state": "not_connected", "message": "Spotify non collegato."}
        # cache breve: il polling del widget non deve generare una chiamata di rete per ogni richiesta
        cached = getattr(self, "_status_cache", None)
        if cached and time.monotonic() - cached[0] < STATUS_TTL and cached[1].get("client_id") == base["client_id"]:
            return cached[1]
        result = self._status(base)
        self._status_cache = (time.monotonic(), result)
        return result

    def _status(self, base: dict) -> dict:
        try:
            data = self._api("GET", "/me/player")
            if data is None:
                return {**base, "state": "no_device", "message": "Nessun dispositivo Spotify attivo."}
            return {**base, "state": "playing" if data.get("is_playing") else "paused", "message": "",
                    **parse_playback(data)}
        except SpotifyError as error:
            return {**base, "state": error.code, "message": str(error), "retry_after": error.retry_after}

    def control(self, action: str, value=None):
        self._status_cache = None
        if action == "play_pause":
            status = self.status()
            if status.get("state") not in ("playing", "paused"):
                raise SpotifyError(status.get("state", "unavailable"), status.get("message", "Riproduzione non disponibile."), 409)
            action = "pause" if status["is_playing"] else "play"
        if action in ("play", "pause", "next", "previous"):
            path, method = {"play": ("/me/player/play", "PUT"), "pause": ("/me/player/pause", "PUT"),
                            "next": ("/me/player/next", "POST"), "previous": ("/me/player/previous", "POST")}[action]
            self._api(method, path)
        elif action == "volume":
            try:
                level = max(0, min(100, int(value)))
            except (TypeError, ValueError):
                raise SpotifyError("invalid_volume", "Volume Spotify non valido.")
            self._api("PUT", "/me/player/volume", {"volume_percent": level})
        elif action == "shuffle":
            self._api("PUT", "/me/player/shuffle", {"state": str(bool(value)).lower()})
        else:
            raise SpotifyError("invalid_action", "Comando Spotify non valido.")
        self._status_cache = None
        return {"ok": True}

    def logout(self):
        self.pending = None
        client_id = self.settings.get("client_id", "")
        self.save({"client_id": client_id})
        self.cfg.app["spotify"] = {"client_id": client_id}
