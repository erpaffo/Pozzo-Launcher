"""Apre una porta sul router con UPnP (IGD), senza dipendenze: ricerca SSDP + chiamate SOAP.

Serve alla netplay: chi ospita non deve configurare a mano il port forwarding. Tutto e' best effort: se il
router non risponde, `open_port` ritorna None e resta la guida manuale.
"""

from __future__ import annotations

import re
import socket
import urllib.request
from urllib.parse import urljoin
from xml.sax.saxutils import escape

SERVICE = re.compile(r"<serviceType>(urn:schemas-upnp-org:service:WAN(?:IP|PPP)Connection:\d)</serviceType>.*?"
                     r"<controlURL>([^<]+)</controlURL>", re.S)  # versione 1 o 2 (es. router Sercomm: 2)
_SEARCH = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
           "ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n\r\n").encode()


def _discover(timeout: float = 2.5) -> str | None:
    """URL della descrizione del router (header LOCATION della risposta SSDP)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(_SEARCH, ("239.255.255.250", 1900))
        m = re.search(rb"(?im)^location:\s*(\S+)", s.recvfrom(2048)[0])
        return m.group(1).decode() if m else None
    except OSError:
        return None
    finally:
        s.close()


def _control(location: str) -> tuple[str, str] | None:
    """(URL di controllo, tipo di servizio) del router."""
    try:
        xml = urllib.request.urlopen(location, timeout=4).read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return None
    m = SERVICE.search(xml)
    return (urljoin(location, m.group(2).strip()), m.group(1)) if m else None


def _soap(ctl: str, svc: str, action: str, args: dict) -> str | None:
    body = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in args.items())
    env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
           's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
           f'<u:{action} xmlns:u="{svc}">{body}</u:{action}></s:Body></s:Envelope>').encode()
    req = urllib.request.Request(ctl, env, {"Content-Type": 'text/xml; charset="utf-8"',
                                            "SOAPAction": f'"{svc}#{action}"'})
    try:
        return urllib.request.urlopen(req, timeout=5).read().decode("utf-8", "replace")
    except (OSError, ValueError):
        return None


def local_ip_towards(router_url: str) -> str:
    """IP di questo PC sulla rete del router (quello a cui inoltrare la porta)."""
    host = re.sub(r"^https?://([^/:]+).*$", r"\1", router_url)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, 80))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def open_port(port: int, proto: str = "UDP", name: str = "Pozzo Launcher", lease_s: int = 3600) -> dict | None:
    """Inoltra `port` verso questo PC (scade da sola dopo `lease_s`, se il router lo permette). Ritorna {"external_ip", "control", "service"} o None se non riesce."""
    loc = _discover()
    ctl = _control(loc) if loc else None
    local = local_ip_towards(loc) if loc else ""
    if not ctl or not local:
        return None
    url, svc = ctl
    for lease in (lease_s, 0):  # alcuni router accettano solo mappature permanenti (errore 725)
        ok = _soap(url, svc, "AddPortMapping", {
            "NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": proto, "NewInternalPort": port,
            "NewInternalClient": local, "NewEnabled": 1, "NewPortMappingDescription": name, "NewLeaseDuration": lease})
        if ok is not None:
            break
    else:
        return None
    r = _soap(url, svc, "GetExternalIPAddress", {}) or ""
    m = re.search(r"<NewExternalIPAddress>([^<]*)<", r)
    return {"external_ip": m.group(1) if m else "", "control": url, "service": svc, "port": port, "proto": proto}


def close_port(m: dict | None) -> None:
    if m:
        _soap(m["control"], m["service"], "DeletePortMapping",
              {"NewRemoteHost": "", "NewExternalPort": m["port"], "NewProtocol": m["proto"]})
