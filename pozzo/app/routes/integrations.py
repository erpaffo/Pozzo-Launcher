"""Discord, Spotify, tasti multimediali, voce di Discord."""

from __future__ import annotations

import html

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import HTMLResponse

from ... import i18n as I



def build_router(ctx) -> APIRouter:
    DiscordVoiceError, SpotifyError, app, discord, discord_voice, spotify = ctx.DiscordVoiceError, ctx.SpotifyError, ctx.app, ctx.discord, ctx.discord_voice, ctx.spotify
    router = APIRouter()

    # ------------------------------------------------------------ integrazioni (Discord)
    @router.get("/api/integrations")
    def api_integrations():
        """Stato delle integrazioni esterne. Discord usa l'IPC locale (nessuna chiave, nessun server)."""
        from ... import applog
        return {"discord": discord.state(), "log_file": str(applog.current()) if applog.enabled() else None}

    @router.post("/api/integrations/discord")
    def api_integrations_discord(body: dict = Body(default={})):
        """Salva {enabled, client_id, show_time} e riallinea subito la presenza."""
        return {"discord": discord.apply(body)}

    def _media_http_error(error):
        raise HTTPException(error.status, detail=str(error))

    @router.get("/api/spotify/status")
    def api_spotify_status():
        return spotify.status()

    @router.post("/api/spotify/settings")
    def api_spotify_settings(body: dict = Body(default={})):
        try: return spotify.configure(body.get("client_id", ""))
        except SpotifyError as error: _media_http_error(error)

    @router.get("/api/spotify/login")
    def api_spotify_login():
        try: return {"url": spotify.login_url(), "redirect_uri": spotify.redirect_uri}
        except SpotifyError as error: _media_http_error(error)

    @router.get("/api/spotify/callback", response_class=HTMLResponse)
    def api_spotify_callback(code: str = "", state: str = "", error: str = ""):
        try:
            spotify.callback(code, state, error)
            message = I.tr("s.integrations.spotifyLinked")
        except SpotifyError as problem:
            message = str(problem)
        return HTMLResponse("<!doctype html><html lang='it'><meta charset='utf-8'><title>Spotify - Pozzo</title>"
                            f"<body style='font:16px sans-serif;background:#151923;color:#eee;padding:3rem'><h1>{html.escape(message)}</h1></body></html>")

    def _spotify_control(action, body):
        try: return spotify.control(action, (body or {}).get("value"))
        except SpotifyError as error: _media_http_error(error)

    for _path, _action in (("play", "play"), ("pause", "pause"), ("play-pause", "play_pause"),
                           ("next", "next"), ("prev", "previous"), ("volume", "volume")):
        def _handler(body: dict = Body(default={}), action=_action):
            return _spotify_control(action, body)
        app.add_api_route(f"/api/spotify/{_path}", _handler, methods=["POST"], name=f"api_spotify_{_path}")

    @router.post("/api/spotify/shuffle")
    def api_spotify_shuffle(body: dict = Body(default={})):
        try: return spotify.control("shuffle", body.get("state", False))
        except SpotifyError as error: _media_http_error(error)

    @router.post("/api/spotify/logout")
    def api_spotify_logout():
        spotify.logout()
        return spotify.public_status()

    @router.post("/api/media/keys")
    def api_media_keys(body: dict = Body(default={})):
        from ...mediakeys import send
        return send(str(body.get("action", "")))

    @router.get("/api/discord/config")
    def api_discord_voice_config(): return discord_voice.public_status()

    @router.get("/api/discord/status")
    def api_discord_voice_status(): return discord_voice.status()

    @router.post("/api/discord/settings")
    def api_discord_voice_settings(body: dict = Body(default={})):
        try:
            return discord_voice.configure(body.get("client_id", ""), body.get("client_secret", ""))
        except DiscordVoiceError as error: _media_http_error(error)

    @router.post("/api/discord/test")
    def api_discord_voice_test():
        try: return discord_voice.test()
        except DiscordVoiceError as error: _media_http_error(error)

    @router.post("/api/discord/mute")
    def api_discord_voice_mute(body: dict = Body(default={})):
        try: return discord_voice.set_voice(mute=body.get("enabled", True))
        except DiscordVoiceError as error: _media_http_error(error)

    @router.post("/api/discord/deafen")
    def api_discord_voice_deafen(body: dict = Body(default={})):
        try: return discord_voice.set_voice(deaf=body.get("enabled", True))
        except DiscordVoiceError as error: _media_http_error(error)

    @router.post("/api/discord/volume")
    def api_discord_voice_volume(body: dict = Body(default={})):
        try: return discord_voice.set_voice(volume=body.get("value", 100))
        except DiscordVoiceError as error: _media_http_error(error)

    @router.post("/api/discord/leave")
    def api_discord_voice_leave():
        try: return discord_voice.leave()
        except DiscordVoiceError as error: _media_http_error(error)

    return router
