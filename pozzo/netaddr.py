"""Classificazione dell'indirizzo IP per la netplay e IP pubblico."""

from __future__ import annotations

import ipaddress

import httpx

_TIP = {
    "shared": "Indirizzo di una VPN come Tailscale o ZeroTier: funziona da qualsiasi rete che usa la stessa VPN.",
    "lan": "Indirizzo della rete di casa: funziona solo se l'amico e' sulla stessa rete (Wi-Fi o cavo di casa).",
    "public": "Indirizzo pubblico: l'amico puo' collegarsi solo se la porta e' aperta sul router (vedi la guida).",
    "invalid": "Indirizzo non valido.",
}


def address_kind(ip: str) -> dict:
    """Ritorna {"kind": ..., "tip": ...} per l'indirizzo dato."""
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return {"kind": "invalid", "tip": _TIP["invalid"]}
    if addr.is_loopback:
        return {"kind": "loopback", "tip": ""}
    if addr in ipaddress.ip_network("100.64.0.0/10"):
        kind = "shared"
    elif addr.is_private or addr.is_link_local:
        kind = "lan"
    else:
        kind = "public"
    return {"kind": kind, "tip": _TIP[kind]}


def public_ip(timeout: float = 5) -> str:
    """IP pubblico visto da internet, o "" se non disponibile."""
    try:
        r = httpx.get("https://api.ipify.org", timeout=timeout)
        text = r.text.strip()
        if r.is_success:
            ipaddress.ip_address(text)
            return text
    except Exception:
        pass
    return ""
