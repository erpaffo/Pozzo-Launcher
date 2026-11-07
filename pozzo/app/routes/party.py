"""Gioca con un amico: codice invito + netplay RetroArch (Fase 0, nessun server)."""

from __future__ import annotations

import getpass
import os
import secrets
import time

from fastapi import APIRouter, Body, HTTPException

from ...matching import normalize
from ... import config as C, i18n as I, edenroom as EDR, netaddr as NA, netplay as NP, platforms as P, protocol as PR, upnp as UP
from ...library import launcher as L
from ...remote.certs import lan_ips


def build_router(ctx) -> APIRouter:
    api_play, cfg, launcher, lib, user = ctx.api_play, ctx.cfg, ctx.launcher, ctx.lib, ctx.user
    router = APIRouter()
    active: dict = {}  # partita ospitata adesso (vuoto = nessuna)
    room: dict = {}  # stanza di Eden avviata da Pozzo: {"proc": Popen}
    incoming: dict = {}  # ultimo invito ricevuto (da link o incolla): {"code": ...}
    try:  # invito arrivato con il link quando l'app era chiusa (variabile impostata al lancio)
        codice = PR.parse_url(os.environ.pop("POZZO_PENDING_JOIN", "") or "")
        if codice is not None:
            incoming.update(code=codice)
    except Exception:
        pass

    def _conf() -> dict:
        return dict(cfg.app.get("netplay") or {})

    def _nick(conf: dict) -> str:
        try:
            d = getpass.getuser()
        except Exception:
            d = ""
        return str(conf.get("nick") or d or "Giocatore")

    def _plan(g: dict) -> dict | None:
        p = P.PLATFORMS.get(g["key"].split("/")[0])
        try:
            return L.plan(cfg, p, user.profile(g["key"])) if p else None
        except L.LaunchError:
            return None

    def _play(g: dict, extra: list[str]):
        """Avvia con gli argomenti di netplay; se l'avvio fallisce non restano per il gioco successivo."""
        launcher.next_args = extra
        try:
            api_play(g["id"])
        except Exception:
            launcher.next_args = []
            raise

    @router.get("/api/party")
    def api_party():
        conf, hosts = _conf(), lan_ips()
        return {"nick": _nick(conf), "host": conf.get("host") or (hosts[0] if hosts else ""), "hosts": hosts,
                "port": int(conf.get("port") or NP.PORT), "eden_port": int(conf.get("eden_port") or NP.EDEN_PORT),
                "active": active or None, "incoming": dict(incoming) or None, "kinds": {ip: NA.address_kind(ip) for ip in hosts},
                "register_protocol": bool(conf.get("register_protocol", True))}

    @router.post("/api/party/invite")
    def api_party_invite(body: dict = Body(...)):
        g = lib.by_key.get(str(body.get("key") or ""))
        if not g:
            raise HTTPException(404, I.tr("s.party.notFound"))
        plan = _plan(g)
        emu = (plan or {}).get("emulator", "")
        if not plan or not NP.supported(emu):
            raise HTTPException(409, {"error": "no-netplay", "emulator": emu, "suggest": "stream"})
        eden = emu == "eden"
        conf, hosts = _conf(), lan_ips()
        nick = str(body.get("nick") or _nick(conf)).strip() or "Giocatore"
        host = str(body.get("host") or conf.get("host") or (hosts[0] if hosts else "")).strip()
        mapping = None
        if body.get("where") == "internet":  # porta aperta da sola sul router (UPnP) e IP pubblico nel codice
            UP.close_port(room.pop("map", None))
            try:
                nport = int(body.get("port") or (conf.get("eden_port") or NP.EDEN_PORT if eden else conf.get("port") or NP.PORT))
            except (ValueError, TypeError):
                raise HTTPException(400, I.tr("s.party.badPort"))
            mapping = UP.open_port(nport, "UDP" if eden else "TCP")
            ip = (mapping or {}).get("external_ip") or NA.public_ip()
            if ip and NA.address_kind(ip)["kind"] != "public":  # IP del router privato/condiviso: CGNAT
                UP.close_port(mapping)
                raise HTTPException(409, {"error": "cgnat", "ip": ip})
            if not ip:
                raise HTTPException(409, I.tr("s.party.noPublicIp"))
            host = ip
        pw = secrets.token_urlsafe(6) if eden else ""  # solo [A-Za-z0-9_-]: Eden separa nick:password@host:porta
        try:
            port = int(body.get("port") or (conf.get("eden_port") or NP.EDEN_PORT if eden else conf.get("port") or NP.PORT))
            info = {"v": 1, "k": g["key"], "e": emu, "c": "" if eden else plan.get("core") or "", "h": host, "p": port,
                    "n": nick, "t": g["title"][:50], "x": int(time.time()) + NP.TTL}
            if pw:
                info["w"] = pw
            code = NP.encode(info)
            NP.decode(code)  # IP o porta sbagliati: errore qui, non dall'amico
        except (ValueError, TypeError) as e:
            raise HTTPException(400, str(e))
        conf.update(nick=nick, host=host)
        conf["eden_port" if eden else "port"] = port
        C.save_settings(cfg, app={"netplay": conf})
        cfg.app["netplay"] = conf
        proc = None
        if eden:  # la stanza e' un processo a parte; anche l'ospite entra da "ospite" su questo PC
            EDR.stop(room.pop("proc", None))
            try:
                proc = EDR.start(EDR.room_cmd(plan["exe"], g["title"], port, pw, g["title"]))
            except OSError as e:
                raise HTTPException(409, I.tr("s.party.edenStart", e=e))
            if not EDR.alive(proc):
                EDR.stop(proc)
                raise HTTPException(409, I.tr("s.party.edenClosed"))
            EDR.prefill(plan["exe"], NP.eden_nick(nick), "127.0.0.1", port)
        try:
            _play(g, NP.args("join" if eden else "host", host="127.0.0.1", port=port, nick=nick, emulator=emu, password=pw))
        except Exception:
            EDR.stop(proc)
            raise
        if proc:
            room["proc"] = proc
        if mapping:
            room["map"] = mapping
        ctx.discord.set_party({"id": "poz-" + secrets.token_hex(3), "size": [1, 2]})
        active.clear()
        active.update(key=g["key"], title=g["title"], host=host, port=port, code=code, emulator=emu)
        return {"ok": True, "code": code, "title": g["title"], "host": host, "port": port, "emulator": emu,
                "upnp": bool(mapping) if body.get("where") == "internet" else None, "steps": EDR.STEPS if eden else "", "link": NP.link(code),
                "message": NP.invite_message(code, g["title"], emu)}

    @router.post("/api/party/settings")
    def api_party_settings(body: dict = Body(...)):
        conf = _conf()
        if "register_protocol" in body:
            v = body["register_protocol"]
            if not isinstance(v, bool):
                raise HTTPException(400, I.tr("s.party.regProtoBool"))
            conf["register_protocol"] = v
            C.save_settings(cfg, app={"netplay": conf})
            cfg.app["netplay"] = conf
            try:  # la registrazione del link non deve far fallire la rotta
                if v:
                    PR.register()
                else:
                    PR.unregister()
            except Exception:
                pass
        return {"register_protocol": bool(conf.get("register_protocol", True))}

    @router.post("/api/party/close")
    def api_party_close():
        """Chiude la stanza di Eden avviata da Pozzo (il gioco resta aperto)."""
        EDR.stop(room.pop("proc", None))
        UP.close_port(room.pop("map", None))
        active.clear()
        return {"ok": True}

    def _find(t: dict) -> dict | None:
        """Il gioco dell'invito nella mia libreria. La chiave dipende da nome file e dimensione (nessun CRC per
        Switch): due dump dello stesso gioco hanno chiavi diverse, quindi si ripiega su console + titolo."""
        g = lib.by_key.get(t["k"])
        if g or not t.get("t"):
            return g
        pid, want = t["k"].split("/")[0], normalize(t["t"])
        return next((x for x in lib.by_key.values() if x["key"].split("/")[0] == pid and normalize(x["title"]) == want), None)

    def _decode(body: dict) -> dict:
        try:
            return NP.decode(NP.extract_code(str(body.get("code") or "")))
        except ValueError as e:
            raise HTTPException(400, str(e))

    @router.post("/api/party/incoming")
    def api_party_incoming(body: dict = Body(...)):
        # Solo registra l'invito: non avvia nessun gioco (lo fa l'utente dalla UI).
        if body.get("url"):
            code = PR.parse_url(str(body.get("url")))
            if code is None:
                raise HTTPException(400, I.tr("s.party.badLink"))
        else:
            code = str(body.get("code") or "")
        try:
            NP.decode(code)
        except ValueError as e:
            raise HTTPException(400, str(e))
        incoming.clear()
        incoming.update(code=code)
        try:
            ctx.events.emit("party_invite", {"code": code})
        except Exception:
            pass  # il SSE non deve far fallire la rotta
        return {"ok": True}

    @router.post("/api/party/public-ip")
    def api_party_public_ip():
        ip = NA.public_ip()
        if not ip:
            return {"ip": "", "kind": "", "tip": "", "error": I.tr("s.party.noPublicIp")}
        k = NA.address_kind(ip)
        return {"ip": ip, "kind": k["kind"], "tip": k["tip"], "error": ""}

    @router.post("/api/party/preview")
    def api_party_preview(body: dict = Body(...)):
        t = _decode(body)
        g = _find(t)
        return {"title": g["title"] if g else t["k"], "nick": t["n"], "host": t["h"], "port": t["p"], "have": bool(g)}

    @router.post("/api/party/join")
    def api_party_join(body: dict = Body(...)):
        t = _decode(body)
        g = _find(t)
        if not g:
            raise HTTPException(404, I.tr("s.party.notInLibrary"))
        if t.get("e") == "eden":
            plan = _plan(g) or {}
            if plan.get("emulator") != "eden":
                raise HTTPException(409, {"error": "emulator-mismatch", "local": plan.get("emulator") or "", "remote": "eden"})
            nick = NP.eden_nick(_nick(_conf()))
            pre = EDR.prefill(plan.get("exe"), nick, t["h"], t["p"])
            _play(g, NP.args("join", host=t["h"], port=t["p"], nick=nick, emulator="eden", password=t.get("w") or ""))
            return {"ok": True, "title": g["title"], "steps": EDR.STEPS, "prefilled": bool(pre)}
        local = (_plan(g) or {}).get("core") or ""
        if t.get("c") and local != t["c"]:
            raise HTTPException(409, {"error": "core-mismatch", "local": local, "remote": t["c"]})
        _play(g, NP.args("join", host=t["h"], port=t["p"], nick=_nick(_conf())))
        return {"ok": True, "title": g["title"]}

    try:  # link pozzo:// registrato ad ogni avvio, salvo disattivazione in impostazioni
        if _conf().get("register_protocol", True):
            PR.register()
    except Exception:
        pass

    return router
