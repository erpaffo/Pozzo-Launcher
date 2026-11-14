"""Interfaccia di rete dei download (di solito la VPN): i suoi indirizzi e i client httpx legati a quegli indirizzi.

Si lega per indirizzo e non per nome di dispositivo: psutil su Windows da' il nome amichevole («Ethernet 2»), mentre
libtorrent vorrebbe il GUID dell'adattatore; un indirizzo va bene a libtorrent, a httpx (local_address) e ai socket.
Se l'interfaccia scelta manca, BIND = (): ogni richiesta fallisce subito invece di uscire da un'altra strada.
"""
from __future__ import annotations

import ipaddress
import socket

import httpx

# None = nessuna interfaccia scelta (qualunque strada); () = scelta ma assente o spenta; altrimenti i suoi indirizzi, IPv4 prima
BIND: tuple[str, ...] | None = None
OFF = "Interfaccia di rete dei download non disponibile: niente traffico finché non torna"


def interfaces() -> list[dict]:
    """[{name, up, addrs}] delle interfacce di adesso (per la UI e per il controllo periodico)."""
    import psutil  # import qui: serve solo con un'interfaccia scelta o con la pagina delle impostazioni aperta
    stats = psutil.net_if_stats()
    out = []
    for name, addrs in sorted(psutil.net_if_addrs().items()):
        ips = []
        for a in addrs:
            if a.family not in (socket.AF_INET, socket.AF_INET6):
                continue
            try:
                ip = ipaddress.ip_address(a.address.split("%")[0])
            except ValueError:
                continue
            if not ip.is_link_local:  # fe80:: (serve lo scope) e 169.254 (nessuna rete vera): non si usano
                ips.append(str(ip))
        out.append({"name": name, "up": bool(getattr(stats.get(name), "isup", False)), "addrs": ips})
    return out


def addrs(name: str, found: list[dict] | None = None) -> tuple[str, ...]:
    """Indirizzi utilizzabili dell'interfaccia `name`, IPv4 prima; () se non c'e', e' spenta o non ha indirizzi."""
    for i in interfaces() if found is None else found:
        if i["name"] == name and i["up"]:
            return tuple(sorted(i["addrs"], key=lambda a: ":" in a))
    return ()


def local() -> str | None:
    """Indirizzo da cui escono le richieste HTTP: uno solo per client, IPv4 se c'e' (anyio poi cerca solo destinazioni
    della stessa famiglia). shortcut: con un'interfaccia dual-stack i siti solo IPv6 non si raggiungono."""
    return BIND[0] if BIND else None


class _Off(httpx.BaseTransport, httpx.AsyncBaseTransport):
    """Interfaccia scelta ma assente: nessuna richiesta parte (kill switch), anche se qualcuno ci prova lo stesso."""

    def handle_request(self, request):
        raise httpx.ConnectError(OFF, request=request)

    async def handle_async_request(self, request):
        raise httpx.ConnectError(OFF, request=request)


def client_kw(asynchronous: bool = False, **transport) -> dict:
    """Argomenti per httpx.Client/AsyncClient: nessuno senza interfaccia scelta. trust_env=False: un proxy delle
    variabili d'ambiente avrebbe un suo transport, non legato all'interfaccia."""
    if BIND is None:
        return {}
    if not BIND:
        return {"transport": _Off(), "trust_env": False}
    cls = httpx.AsyncHTTPTransport if asynchronous else httpx.HTTPTransport
    return {"transport": cls(local_address=BIND[0], **transport), "trust_env": False}


def source() -> tuple[str, int] | None:
    """source_address per socket.create_connection; ValueError se l'interfaccia scelta manca."""
    if BIND is None:
        return None
    if not BIND:
        raise ValueError(OFF)
    return (BIND[0], 0)
