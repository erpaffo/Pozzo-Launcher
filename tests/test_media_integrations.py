"""Test deterministici per OAuth Spotify, tasti multimediali e protocollo RPC Discord."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
import urllib.parse
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pozzo import discordrpc
from pozzo.discordvoice import DiscordVoice, DiscordVoiceError, parse_voice
from pozzo.mediakeys import send as send_media_key
from pozzo.spotify import (TOKEN_URL, SpotifyClient, SpotifyError, map_error, parse_playback,
                           pkce_pair)


class FakeResponse:
    def __init__(self, value, status=200, headers=None):
        self.status, self.headers = status, headers or {}
        self.payload = json.dumps(value).encode()

    def read(self):
        return self.payload


class FakeDiscordChannel:
    def __init__(self):
        self.buffer = bytearray()
        self.requests = []
        self.closed = False

    def write(self, data):
        op, request = discordrpc.read_frame(io.BytesIO(data).read)
        self.requests.append((op, request))
        if op == discordrpc.OP_HANDSHAKE:
            reply = {"cmd": "DISPATCH", "evt": "READY", "data": {}}
        elif request.get("cmd") == "AUTHORIZE":
            reply = {"cmd": "AUTHORIZE", "nonce": request["nonce"], "data": {"code": "rpc-code"}}
        elif request.get("cmd") == "AUTHENTICATE":
            reply = {"cmd": "AUTHENTICATE", "nonce": request["nonce"], "data": {}}
        else:
            values = {"GET_VOICE_SETTINGS": {"mute": False, "deaf": True, "output": {"volume": 80}},
                      "GET_SELECTED_VOICE_CHANNEL": {"channel": None}}
            reply = {"cmd": request["cmd"], "nonce": request["nonce"], "data": values.get(request["cmd"], {})}
        self.buffer.extend(discordrpc.frame(discordrpc.OP_FRAME, reply))

    def read(self, size):
        if not self.buffer:
            return b""
        chunk = self.buffer[:size]
        del self.buffer[:size]
        return bytes(chunk)

    def close(self):
        self.closed = True


def test_pkce_and_oauth_refresh():
    verifier, challenge = pkce_pair("test-verifier")
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert challenge == expected

    cfg = SimpleNamespace(app={"port": 9911})
    now = [1000]
    calls = []

    def opener(request, timeout=0):
        values = urllib.parse.parse_qs((request.data or b"").decode())
        calls.append((request.full_url, values))
        if request.full_url == TOKEN_URL:
            grant = values["grant_type"][0]
            return FakeResponse({"access_token": "access-" + str(len(calls)), "refresh_token": "refresh",
                                 "expires_in": 3600})
        return FakeResponse({})

    saved = {}
    client = SpotifyClient(cfg, save=saved.update, opener=opener, clock=lambda: now[0])
    client.configure("spotify-client-id")
    login = urllib.parse.urlparse(client.login_url())
    verifier = client.pending["verifier"]
    query = urllib.parse.parse_qs(login.query)
    assert query["redirect_uri"] == ["http://127.0.0.1:9911/api/spotify/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert client.callback("auth-code", query["state"][0])["authenticated"]
    code_request = calls[-1][1]
    assert code_request["grant_type"] == ["authorization_code"]
    assert code_request["code_verifier"] == [verifier]
    now[0] = 5000
    assert client.refresh() == "access-2"
    assert calls[-1][1]["grant_type"] == ["refresh_token"]
    assert saved["refresh_token"] == "refresh"
    assert "access_token" not in client.public_status() and "refresh_token" not in client.public_status()


def test_status_parsing_and_error_mapping():
    parsed = parse_playback({"item": {"name": "Traccia", "artists": [{"name": "Artista"}],
                                  "album": {"images": [{"url": "https://cover.test/a.jpg"}]}, "duration_ms": 120000},
                             "progress_ms": 30000, "is_playing": True, "shuffle_state": True,
                             "device": {"name": "TV", "volume_percent": 45, "is_active": True}})
    assert parsed["track"] == "Traccia" and parsed["artists"] == ["Artista"]
    assert parsed["cover"].endswith("a.jpg") and parsed["progress_ms"] == 30000
    assert parsed["is_playing"] and parsed["shuffle"] and parsed["volume"] == 45
    assert map_error(403, {}).code == "premium_required"
    assert map_error(404, {}).code == "no_device"
    limited = map_error(429, {}, "12")
    assert limited.code == "rate_limited" and limited.retry_after == 12
    assert map_error(401, {}).code == "token_expired"


def test_system_media_keys_are_mockable():
    calls = []
    def keybd_event(*args): calls.append(args)
    result = send_media_key("play_pause", platform="win32", keybd_event=keybd_event)
    assert result["ok"] and len(calls) == 2
    assert calls[0][:3] == (0xB3, 0, 0) and calls[1][:3] == (0xB3, 0, 2)

    run_calls = []
    def runner(args, **kwargs):
        run_calls.append(args)
        return SimpleNamespace(returncode=0)
    result = send_media_key("next", platform="linux", runner=runner, which=lambda name: "playerctl" if name == "playerctl" else None)
    assert result["ok"] and run_calls == [["playerctl", "next"]]
    assert not send_media_key("bad", platform="win32", keybd_event=keybd_event)["ok"]


def test_discord_rpc_frames_and_voice():
    encoded = discordrpc.frame(discordrpc.OP_FRAME, {"cmd": "GET_VOICE_SETTINGS", "nonce": "n"})
    op, payload = discordrpc.read_frame(io.BytesIO(encoded).read)
    assert op == discordrpc.OP_FRAME and payload["nonce"] == "n"
    voice = parse_voice({"id": "room", "name": "Sala", "voice_states": [
        {"user": {"username": "Giocatore"}, "voice_state": {"speaking": True}}]})
    assert voice["in_call"] and voice["channel"] == "Sala" and voice["speakers"] == ["Giocatore"]
    assert not parse_voice(None)["in_call"]

    cfg = SimpleNamespace(app={"discord_voice": {"client_id": "app-id", "client_secret": "app-secret"}})
    channel = FakeDiscordChannel()
    def opener(request, timeout=0): return FakeResponse({"access_token": "rpc-token", "refresh_token": "rpc-refresh", "expires_in": 1000})
    service = DiscordVoice(cfg, save=lambda data: cfg.app.update(discord_voice=data), connect=lambda path: channel,
                           opener=opener, clock=lambda: 100)
    settings = service.command("GET_VOICE_SETTINGS", authorize=True)
    assert settings["mute"] is False and settings["output"]["volume"] == 80
    assert any(payload.get("cmd") == "AUTHORIZE" and payload["args"]["scopes"] == ["rpc", "rpc.voice.read", "rpc.voice.write"]
               for _, payload in channel.requests)
    assert cfg.app["discord_voice"]["access_token"] == "rpc-token" and channel.closed


def test_ui_hooks_and_configuration():
    root = Path(__file__).resolve().parent.parent / "pozzo/app/static"
    widget = (root / "bigpicture.html").read_text(encoding="utf-8")
    settings = (root / "settings/integrazioni.html").read_text(encoding="utf-8")
    module = (root / "media.js").read_text(encoding="utf-8")
    server = "".join(p.read_text(encoding="utf-8")
                     for p in [root.parent / "server.py", *sorted((root.parent / "routes").glob("*.py"))])
    assert 'id="bp-media-widget"' in widget and 'data-media-action="leave"' in widget
    assert "Musica e chiamate" in settings and "developer.spotify.com/dashboard" in settings
    for action in ("toggle", "next", "prev", "playPause", "muteMic", "deafen"):
        assert f"{action}()" in module
    assert "setTimeout(() => refresh(), 5000)" in module
    assert '"/api/spotify/callback"' in server and '"/api/discord/leave"' in server


def test_freeze_guards():
    import threading
    import time

    root = Path(__file__).resolve().parent.parent / "pozzo/app/static"
    module = (root / "media.js").read_text(encoding="utf-8")
    assert "observe(document.body" not in module, "l'observer non deve osservare tutto il body"
    assert "observe(settingsBody" in module and "requestAnimationFrame(checkSettings)" in module

    # pipe Discord che accetta tutto ma non risponde mai: status() deve tornare entro il timeout
    class SilentChannel:
        def __init__(self):
            self.gate, self.closed = threading.Event(), False
        def write(self, data): pass
        def read(self, size):
            self.gate.wait(30)
            return b""
        def close(self):
            self.closed = True
            self.gate.set()

    channels = []
    def connect(path):
        channels.append(SilentChannel())
        return channels[-1]

    cfg = SimpleNamespace(app={"discord_voice": {"client_id": "app-id", "client_secret": "app-secret"}})
    service = DiscordVoice(cfg, save=lambda data: None, connect=connect, clock=lambda: 100)
    service.STATUS_TIMEOUT = 0.5
    started = time.monotonic()
    result = service.status()
    assert time.monotonic() - started < 3 and result["state"] == "timeout", result
    assert channels and all(channel.closed for channel in channels)
    started = time.monotonic()
    assert service.status()["state"] == "timeout" and time.monotonic() - started < 0.2  # cache TTL
    try:
        service.COMMAND_TIMEOUT = 0.5
        service.command("GET_VOICE_SETTINGS")
        raise AssertionError("atteso timeout")
    except DiscordVoiceError as error:
        assert error.code == "timeout"

    # Spotify lento: la cache evita una chiamata di rete a ogni poll
    calls = []
    def opener(request, timeout=0):
        calls.append(timeout)
        return FakeResponse({"is_playing": False, "item": None, "device": {}})
    cfg = SimpleNamespace(app={"port": 9911, "spotify": {"client_id": "x", "access_token": "t", "refresh_token": "r", "expires_at": 9999}})
    spotify = SpotifyClient(cfg, save=lambda data: None, opener=opener, clock=lambda: 1000)
    spotify.status(); spotify.status(); spotify.status()
    assert len(calls) == 1 and calls[0] <= 5


def main():
    test_pkce_and_oauth_refresh()
    test_status_parsing_and_error_mapping()
    test_system_media_keys_are_mockable()
    test_discord_rpc_frames_and_voice()
    test_ui_hooks_and_configuration()
    test_freeze_guards()
    print("ok  OAuth PKCE/refresh, Spotify status/errori, tasti mock, frame IPC, hook UI e anti-freeze")


if __name__ == "__main__":
    main()
