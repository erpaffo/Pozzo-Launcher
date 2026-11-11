"""Feed RSS/Atom con filtri di auto-download: legge il feed, tiene gli item nuovi che combaciano con un filtro.

Nessuna rete qui dentro oltre a `fetch` (sostituibile nei test); gli item gia' visti li ricorda lo Store."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import httpx

from .. import net
from . import hosts

MAX_BYTES = 5 * 1024 * 1024
MAX_HOPS = 3
_OK = ("magnet:", "http://", "https://")


def _name(el) -> str:
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def parse(data: bytes) -> list[dict]:
    """[{id, title, links}] da un feed RSS 2.0 o Atom; `links` in ordine di preferenza (magnet, allegato, pagina).
    ValueError se non e' un feed leggibile."""
    if re.search(rb"<!(DOCTYPE|ENTITY)", data[:4096], re.I):  # niente entita' (billion laughs): nei feed veri non servono
        raise ValueError("Feed con DOCTYPE/ENTITY rifiutato")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"Feed non valido: {e}")
    out = []
    for it in root.iter():
        if _name(it) not in ("item", "entry"):
            continue
        f: dict[str, list[str]] = {}
        for c in it.iter():
            n = _name(c)
            if n == "link" and c.get("href"):  # Atom
                f.setdefault("link", []).append(c.get("href"))
            elif n == "enclosure" and c.get("url"):
                f.setdefault("enclosure", []).append(c.get("url"))
            elif c is not it and (c.text or "").strip():
                f.setdefault(n, []).append(c.text.strip())
        magnets = [x for k in f if k.endswith("magneturi") for x in f[k]]
        links = [*magnets, *(x for x in f.get("enclosure", []) + f.get("link", []) if x.lower().startswith("magnet:")),
                 *f.get("enclosure", []), *f.get("link", [])]
        links = [x for x in dict.fromkeys(links) if x.lower().startswith(_OK)]
        title = (f.get("title") or [""])[0]
        iid = (f.get("guid") or f.get("id") or links[:1] or [title])[0]
        if iid and links:
            out.append({"id": iid[:500], "title": title, "links": links})
    return out


def fetch(url: str) -> bytes:
    """Scarica il feed (sincrono, da un thread). Anti-SSRF come i download: ogni salto controllato da hosts.assert_public."""
    with httpx.Client(timeout=20, headers={"User-Agent": net.UA}, follow_redirects=False) as c:
        for _ in range(MAX_HOPS + 1):
            hosts.assert_public(url)
            with c.stream("GET", url) as r:
                if r.is_redirect and r.headers.get("location"):
                    url = str(r.url.join(r.headers["location"]))
                    continue
                r.raise_for_status()
                buf = b""
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        raise ValueError("Feed troppo grande")
                return buf
    raise ValueError("Troppi reindirizzamenti")


def match(items: list[dict], seen: set[str], filters: list[dict]) -> list[tuple[dict, str]]:
    """Item mai visti il cui titolo combacia con un filtro (il primo vale): [(item, categoria)]. Regex rotta = filtro saltato."""
    rx = []
    for f in filters:
        try:
            rx.append((re.compile(str(f.get("regex") or ""), re.I), str(f.get("category") or "")))
        except re.error:
            continue
    return [(i, next(c for r, c in rx if r.search(i["title"]))) for i in items
            if i["id"] not in seen and any(r.search(i["title"]) for r, _ in rx)]
