"""Controlli vocali Discord tramite RPC IPC locale (richiede autorizzazione esplicita)."""

from __future__ import annotations

import json
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import discordrpc

SCOPES = ["rpc", "rpc.voice.read", "rpc.voice.write"]
TOKEN_URL = "https://discord.com/api/oauth2/token"


class DiscordVoiceError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


def parse_voice(channel, settings=None) -> dict:
    if not channel:
        return {"in_call": False, "channel": "", "participants": [], "speakers": []}
    voice_states = channel.get("voice_states") or []
    members = []
    speakers = []
    for row in voice_states:
        user = row.get("user") or {}
        state = row.get("voice_state") or row
        name = user.get("username") or user.get("global_name") or user.get("id") or "Partecipante"
        members.append({"name": name, "speaking": bool(state.get("speaking")), "mute": bool(state.get("mute")),
                        "deaf": bool(state.get("deaf"))})
        if state.get("speaking"):
            speakers.append(name)
    return {"in_call": True, "channel": channel.get("name") or "Canale vocale", "participants": members,
            "speakers": speakers, "volume": (settings or {}).get("output", {}).get("volume")}


def _unwrap(reply: dict) -> dict:
    if reply.get("evt") == "ERROR" or reply.get("cmd") == "ERROR":
        data = reply.get("data") or {}
        if reply.get("cmd") in ("AUTHORIZE", "AUTHENTICATE"):
            raise DiscordVoiceError("not_authorized", "Discord non ha autorizzato l'app: verifica owner/tester e scope RPC vocali.", 403)
        raise DiscordVoiceError("rpc_error", str(data.get("message") or "Discord ha rifiutato il comando."), 403)
    return reply.get("data") if isinstance(reply.get("data"), dict) else {}


class DiscordVoice:
    # tempi massimi: lo stato viene chiesto di continuo dal widget e non deve mai tenere occupati i thread del server
    STATUS_TIMEOUT, COMMAND_TIMEOUT, AUTHORIZE_TIMEOUT, STATUS_TTL = 2.5, 5.0, 90.0, 2.0

    def __init__(self, cfg, save=None, connect=None, opener=None, clock=time.time):
        self.cfg, self.save = cfg, save or (lambda data: None)
        self.connect = connect or discordrpc._Channel
        self.opener, self.clock = opener or urllib.request.urlopen, clock
        self._speaker_lock = threading.Lock()
        self._speaker_channel = None
        self._speaker_names = {}
        self._speakers = set()
        self._speaker_thread = None
        self._open: set = set()  # canali di comandi in corso: si chiudono se scade il tempo
        self._status_lock = threading.Lock()
        self._status_cache: tuple[float, dict] | None = None

    @property
    def settings(self):
        return self.cfg.app.get("discord_voice", {})

    def configure(self, client_id: str, client_secret: str = "") -> dict:
        client_id, client_secret = str(client_id or "").strip(), str(client_secret or "").strip()
        if len(client_id) > 160 or len(client_secret) > 256:
            raise DiscordVoiceError("invalid_credentials", "Credenziali Discord non valide.")
        saved = {"client_id": client_id}
        same_app = client_id == self.settings.get("client_id", "")
        if client_secret:
            saved["client_secret"] = client_secret
        elif same_app and self.settings.get("client_secret"):
            saved["client_secret"] = self.settings["client_secret"]
        if not same_app:
            saved.update({"access_token": "", "refresh_token": "", "expires_at": 0})
        self._store(saved)
        return self.public_status()

    def _store(self, values: dict):
        merged = {**self.settings, **values}
        self.save(merged)
        self.cfg.app["discord_voice"] = merged

    def public_status(self) -> dict:
        return {"client_id": self.settings.get("client_id", ""),
                "client_secret_set": bool(self.settings.get("client_secret")), "connected": False,
                "state": "configured" if self.settings.get("client_id") else "not_configured",
                "message": "" if self.settings.get("client_id") else "Inserisci Client ID e Client Secret Discord."}

    def _token(self, code: str = ""):
        data = self.settings
        if code:
            body = {"grant_type": "authorization_code", "code": code, "client_id": data.get("client_id", ""),
                    "client_secret": data.get("client_secret", "")}
        else:
            refresh = data.get("refresh_token")
            if not refresh:
                raise DiscordVoiceError("authorization_required", "Autorizza il controllo vocale da Discord.", 401)
            body = {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": data.get("client_id", ""),
                    "client_secret": data.get("client_secret", "")}
        req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(body).encode(),
                                     headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            response = self.opener(req, timeout=8)
            status, payload = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, payload = error.code, error.read()
        except (OSError, urllib.error.URLError) as error:
            raise DiscordVoiceError("network_error", f"Discord non raggiungibile: {error}", 503) from error
        try:
            result = json.loads(payload.decode("utf-8")) if payload else {}
        except (ValueError, UnicodeDecodeError):
            result = {}
        if status != 200 or not result.get("access_token"):
            raise DiscordVoiceError("token_error", str(result.get("error_description") or result.get("error") or
                                                              "Autorizzazione Discord non riuscita."), 401)
        self._store({"access_token": result["access_token"], "refresh_token": result.get("refresh_token", data.get("refresh_token", "")),
                     "expires_at": self.clock() + int(result.get("expires_in", 604800))})
        return result["access_token"]

    def _read(self, channel):
        while True:
            op, response = discordrpc.read_frame(channel.read)
            if op == discordrpc.OP_PING:
                channel.write(discordrpc.frame(discordrpc.OP_PONG, response))
                continue
            return op, response

    def _exchange(self, channel, command: str, args: dict | None = None):
        nonce = uuid.uuid4().hex
        channel.write(discordrpc.frame(discordrpc.OP_FRAME, {"cmd": command, "args": args or {}, "nonce": nonce}))
        while True:
            op, response = self._read(channel)
            if op == discordrpc.OP_PING:
                channel.write(discordrpc.frame(discordrpc.OP_PONG, response))
                continue
            if op == discordrpc.OP_CLOSE:
                raise DiscordVoiceError("discord_closed", "Discord ha chiuso la connessione RPC.", 503)
            ready = command == "AUTHENTICATE" and response.get("evt") == "READY"
            if response.get("nonce") != nonce and response.get("cmd") not in ("AUTHORIZE", "AUTHENTICATE", command) and not ready:
                continue
            return _unwrap(response)

    def _session(self, authorize: bool = False):
        if not self.settings.get("client_id") or not self.settings.get("client_secret"):
            raise DiscordVoiceError("not_configured", "Inserisci Client ID e Client Secret Discord.", 400)
        channel = None
        last_error = None
        for path in discordrpc.pipe_paths():
            try:
                channel = self.connect(path)
                break
            except (OSError, FileNotFoundError) as error:
                last_error = error
        if channel is None:
            raise DiscordVoiceError("discord_closed", "Apri Discord sul PC per usare i controlli vocali.", 503) from last_error
        self._open.add(channel)
        try:
            channel.write(discordrpc.frame(discordrpc.OP_HANDSHAKE, {"v": 1, "client_id": str(self.settings["client_id"])}))
            op, ready = self._read(channel)
            if op != discordrpc.OP_FRAME or (ready.get("evt") != "READY" and ready.get("cmd") != "READY"):
                raise DiscordVoiceError("rpc_handshake", "Discord non ha completato la connessione RPC.", 503)
            expires = float(self.settings.get("expires_at", 0))
            access = self.settings.get("access_token") if expires > self.clock() + 60 else None
            if not access and self.settings.get("refresh_token"):
                access = self._token()
            if access:
                try:
                    self._exchange(channel, "AUTHENTICATE", {"access_token": access})
                    return channel
                except DiscordVoiceError:
                    if not authorize:
                        raise
            if not authorize:
                raise DiscordVoiceError("authorization_required", "Autorizza il controllo vocale Discord con ?Testa connessione?.", 401)
            auth = self._exchange(channel, "AUTHORIZE", {"client_id": str(self.settings["client_id"]), "scopes": SCOPES})
            code = auth.get("code") or (auth.get("data") or {}).get("code")
            if not code:
                raise DiscordVoiceError("not_authorized", "Discord non ha autorizzato l'app. L'ID deve appartenere a un owner/tester.", 403)
            access = self._token(code)
            self._exchange(channel, "AUTHENTICATE", {"access_token": access})
            return channel
        except DiscordVoiceError:
            self._open.discard(channel)
            channel.close()
            raise
        except (OSError, ConnectionError, ValueError, json.JSONDecodeError) as error:
            self._open.discard(channel)
            channel.close()
            raise DiscordVoiceError("discord_closed", f"Connessione RPC Discord non disponibile: {error}", 503) from error

    def _deadline(self, work, seconds: float):
        """Esegue work in un thread con tempo massimo: se Discord non risponde chiude i canali aperti
        (sblocca il thread) e restituisce un errore invece di tenere occupato un worker del server."""
        box: dict = {}

        def run():
            try:
                box["value"] = work()
            except BaseException as error:
                box["error"] = error
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        thread.join(seconds)
        if thread.is_alive():
            for channel in list(self._open):
                self._open.discard(channel)
                try: channel.close()
                except OSError: pass
            raise DiscordVoiceError("timeout", "Discord non risponde.", 504)
        if "error" in box:
            raise box["error"]
        return box["value"]

    def command(self, name: str, args: dict | None = None, authorize: bool = False):
        def work():
            channel = self._session(authorize=authorize)
            try:
                return self._exchange(channel, name, args)
            except DiscordVoiceError:
                raise
            except (OSError, ValueError) as error:
                raise DiscordVoiceError("rpc_error", f"Risposta RPC Discord non valida: {error}", 503) from error
            finally:
                self._open.discard(channel)
                channel.close()
        return self._deadline(work, self.AUTHORIZE_TIMEOUT if authorize else self.COMMAND_TIMEOUT)

    def _stop_speakers(self):
        channel, self._speaker_channel = self._speaker_channel, None
        self._speaker_names, self._speakers = {}, set()
        if channel is not None:
            channel.close()

    def _subscribe_speakers(self, voice_channel: dict) -> tuple[list[str], bool]:
        channel_id = str(voice_channel.get("id") or "")
        if not channel_id:
            self._stop_speakers()
            return [], False
        rows = voice_channel.get("voice_states") or []
        names = {str((row.get("user") or {}).get("id")): ((row.get("user") or {}).get("username")
                 or (row.get("user") or {}).get("global_name") or "Partecipante") for row in rows
                 if (row.get("user") or {}).get("id")}
        with self._speaker_lock:
            if self._speaker_channel is not None and getattr(self._speaker_channel, "_pozzo_channel_id", None) == channel_id:
                self._speaker_names = names
                return [names.get(uid, uid) for uid in self._speakers], True
            self._stop_speakers()
            try:
                ipc = self._session()
                ipc._pozzo_channel_id = channel_id
                self._exchange(ipc, "SUBSCRIBE", {"evt": "SPEAKING_START", "channel_id": channel_id})
                self._exchange(ipc, "SUBSCRIBE", {"evt": "SPEAKING_STOP", "channel_id": channel_id})
            except (DiscordVoiceError, OSError, ConnectionError):
                try:
                    self._open.discard(ipc)
                    ipc.close()
                except (UnboundLocalError, OSError): pass
                return [], False
            self._open.discard(ipc)
            self._speaker_channel, self._speaker_names = ipc, names
            self._speakers = set()
            self._speaker_thread = threading.Thread(target=self._speaker_loop, args=(ipc,), daemon=True)
            self._speaker_thread.start()
            return [], True

    def _speaker_loop(self, channel):
        try:
            while channel is self._speaker_channel:
                op, event = self._read(channel)
                if op == discordrpc.OP_CLOSE:
                    break
                if op == discordrpc.OP_PING:
                    channel.write(discordrpc.frame(discordrpc.OP_PONG, event))
                    continue
                if op != discordrpc.OP_FRAME or event.get("cmd") != "DISPATCH":
                    continue
                data = event.get("data") or {}
                user_id = str(data.get("user_id") or (data.get("user") or {}).get("id") or "")
                if not user_id:
                    continue
                with self._speaker_lock:
                    if event.get("evt") == "SPEAKING_START": self._speakers.add(user_id)
                    elif event.get("evt") == "SPEAKING_STOP": self._speakers.discard(user_id)
        except (DiscordVoiceError, OSError, ConnectionError, ValueError):
            pass
        finally:
            if channel is self._speaker_channel:
                self._speaker_channel = None
                try: channel.close()
                except OSError: pass

    def test(self) -> dict:
        self.command("GET_VOICE_SETTINGS", authorize=True)
        result = self.status()
        if not result.get("connected"):
            raise DiscordVoiceError(result.get("state", "discord_unavailable"), result.get("message") or "Discord non disponibile.", 503)
        return result

    def status(self) -> dict:
        base = self.public_status()
        if base["state"] == "not_configured":
            return base
        # una sola richiesta alla volta e risposta in cache per pochi secondi: il widget fa polling continuo
        if not self._status_lock.acquire(timeout=0.5):
            cached = self._status_cache
            return cached[1] if cached else {**base, "state": "timeout", "message": "Discord non risponde."}
        try:
            cached = self._status_cache
            if cached and time.monotonic() - cached[0] < self.STATUS_TTL:
                return cached[1]
            try:
                result = self._deadline(lambda: self._status(base), self.STATUS_TIMEOUT)
            except DiscordVoiceError as error:
                result = {**base, "state": error.code, "message": str(error)}
            self._status_cache = (time.monotonic(), result)
            return result
        finally:
            self._status_lock.release()

    def _status(self, base: dict) -> dict:
        try:
            voice = self.command("GET_VOICE_SETTINGS")
            selected = self.command("GET_SELECTED_VOICE_CHANNEL")
            channel = selected.get("channel") if isinstance(selected.get("channel"), dict) else selected
            if not channel or not (channel.get("id") or channel.get("name")):
                channel = None
            parsed = parse_voice(channel, voice)
            if channel:
                parsed["speakers"], parsed["speaking_available"] = self._subscribe_speakers(channel)
            else:
                self._stop_speakers()
                parsed["speaking_available"] = False
            return {**base, "connected": True, "state": "in_call" if channel else "ready", "message": "",
                    **parsed, "muted": bool(voice.get("mute")), "deafened": bool(voice.get("deaf")),
                    "volume": voice.get("output", {}).get("volume")}
        except DiscordVoiceError as error:
            return {**base, "state": error.code, "message": str(error)}

    def set_voice(self, **values):
        args = {}
        for key in ("mute", "deaf"):
            if key in values:
                args[key] = bool(values[key])
        if "volume" in values:
            args["output"] = {"volume": max(0, min(200, int(values["volume"]))) }
        if not args:
            raise DiscordVoiceError("invalid_action", "Impostazione vocale non valida.")
        self.command("SET_VOICE_SETTINGS", args)
        self._status_cache = None
        return {"ok": True}

    def leave(self):
        self.command("SELECT_VOICE_CHANNEL", {"channel_id": None})
        self._status_cache = None
        return {"ok": True}
