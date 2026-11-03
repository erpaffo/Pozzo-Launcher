"""MultiUp: la pagina elenca i mirror dello stesso file su altri host. `mirrors` li legge tutti (la UI mostra un
pulsante per host), `find`/`resolve` ne scelgono uno per il resto della catena.

    multiup.io/<id>  ->  1fichier.com/?abc   (poi lo prende hosts.py / il debrid)

Markup verificato sul sito vivo (2026-11): /en/mirror/<id> si ottiene con un semplice GET (il pulsante «Download» di
/download/<id>/<nome> e' un form POST con csrf che apre solo quella stessa pagina in un popup: non serve replicarlo).
Ogni mirror e' `<a class="host" nameHost=".." link=".." href=".." validity="valid|invalid|unknown">` col link diretto
all'host (a volte `multiup.io/redirect/..`, un salto). UseNet e' un link interno a pagamento: scartato.
Si legge solo la pagina pubblica, senza aggirare nulla: captcha o nessun mirror -> lista vuota col motivo.
Se MultiUp cambia, si adatta solo `_mirrors`.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from . import hosts, resolvers

# Preferenza: host che il resto della catena sa portare a termine (1fichier/krakenfiles compilano il modulo,
# datanodes/filekeeper li clicca il browser). Chi non c'e' viene dopo; LAST = host senza un risolutore.
PREFER = ("1fichier.com", "krakenfiles.com", "datanodes.to", "filekeeper.net")
LAST = ("megaup", "gofile", "mixdrop", "clicknupload", "mega.nz", "mediafire", "pixeldrain")
_HOSTS = {"multiup.io", "multiup.org", "multiup.eu"}
_DEAD = re.compile(r"\b(invalid|dead|offline|deleted|removed)\b", re.I)
_GONE = re.compile(r"<title>[^<]*(?:non trouv|not found)", re.I)  # «Fichier non trouvé»: il file e' stato rimosso
_CHALLENGE = re.compile(r"g-recaptcha|h-captcha|cf-turnstile|cf-challenge|just a moment", re.I)


def is_page(url: str) -> bool:
    p = urlsplit(url or "")
    return hosts.host(url) in _HOSTS and p.path.strip("/") != ""


def _get(url: str, **kw) -> httpx.Response:  # unico punto di rete
    with httpx.Client(headers=hosts.HEADERS, timeout=hosts.TIMEOUT) as s:
        return s.get(url, **kw)


def _mirrors(html: str, base: str) -> list[tuple[str, str, bool]]:
    """(link, nome host, vivo) per ogni mirror della pagina, in ordine. Solo gli elementi con `nameHost` (non i social)."""
    out: list[tuple[str, str, bool]] = []
    for el in BeautifulSoup(html, "html.parser").find_all(attrs={"namehost": True}):
        raw = el.get("link") or el.get("href") or ""
        url = urljoin(base, raw.strip()) if isinstance(raw, str) else ""
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or url in [o[0] for o in out]:
            continue
        # i link interni di MultiUp non sono mirror (UseNet), tranne /redirect/ (un salto verso l'host vero)
        if hosts.host(url) in _HOSTS and "/redirect/" not in p.path:
            continue
        state = " ".join([str(el.get("validity") or ""), " ".join(el.get("class") or [])])
        out.append((url, str(el.get("namehost") or hosts.host(url)).lower(), not _DEAD.search(state)))
    return out


def _rank(name: str) -> int:
    for i, p in enumerate(PREFER):
        if p.split(".")[0] in name:
            return i
    return len(PREFER) + (1 if any(h in name for h in LAST) else 0)


def _hop(url: str) -> str:
    """Un solo salto di /redirect/ senza seguirlo: il Location e' l'host vero."""
    if "/redirect/" not in urlsplit(url).path:
        return url
    return urljoin(url, _get(url, follow_redirects=False, timeout=8).headers.get("location") or "")


def _name(html: str) -> str:
    """Nome del file dal <title> («Mirror list X - Mirror Upload - MultiUp.io», «Télécharger X - Upload mirroir - ...»)."""
    t = BeautifulSoup(html, "html.parser").title
    t = re.sub(r"^\s*(?:Mirror list|Télécharger|Telecharger|Download)\s+", "", t.get_text() if t else "")
    return t.rsplit(" - ", 2)[0].strip() if t.count(" - ") >= 2 else ""


def _tries(url: str) -> list[str]:
    """L'elenco sta in /en/mirror/<id>: da /<id> e /download/<id>/<nome> ci si arriva con l'id (32 esadecimali)."""
    m = re.search(r"/([0-9a-f]{32})(?:/|$)", urlsplit(url).path)
    alt = f"https://multiup.io/en/mirror/{m.group(1)}" if m else re.sub(r"/download/", "/mirror/", url, count=1)
    return list(dict.fromkeys([alt, url] if m else [url, alt]))


def _unhop(m: dict) -> dict:
    try:
        final = _hop(m["url"])
    except httpx.HTTPError:
        final = ""
    if final and hosts.host(final) not in _HOSTS:
        m.update(url=final, host=hosts.host(final))
        m.pop("redirect")
    return m


def mirrors(url: str) -> dict:
    """Tutti i mirror di una pagina MultiUp (qualunque forma di URL), vivi prima, con i /redirect/ risolti. Bloccante."""
    out = {"page": url, "name": "", "mirrors": [], "reason": ""}
    if not is_page(url):
        out["reason"] = "non e' una pagina MultiUp"
        return out
    reason = "nessun mirror nella pagina"
    for u in _tries(url):
        try:
            r = _get(u, follow_redirects=True)
        except httpx.HTTPError:
            reason = "MultiUp non risponde"
            continue
        found = _mirrors(r.text, str(r.url))
        if not found:
            if _GONE.search(r.text):
                out["reason"] = "il file non esiste più su MultiUp"
                return out
            if _CHALLENGE.search(r.text):
                reason = "la pagina chiede un captcha"
            continue
        ms = [{"host": hosts.host(l), "name": (n or hosts.host(l)).split(".")[0], "url": l, "live": ok,
               **({"redirect": True} if hosts.host(l) in _HOSTS else {})} for l, n, ok in found]
        with ThreadPoolExecutor(4) as ex:  # i salti sono indipendenti: in parallelo
            ms = list(ex.map(lambda m: _unhop(m) if m.get("redirect") else m, ms))
        ms = list({m["url"]: m for m in ms}.values())
        ms.sort(key=lambda m: (not m["live"], bool(m.get("redirect")), _rank(m["name"])))  # stabile: a parita' l'ordine della pagina
        out.update(page=str(r.url), name=_name(r.text), mirrors=ms,
                   reason="" if any(m["live"] for m in ms) else "tutti i mirror sono offline")
        return out
    out["reason"] = reason
    return out


def find(url: str) -> tuple[str, str]:
    """(mirror scelto, motivo se manca). Bloccante."""
    r = mirrors(url)
    pick = next((m for m in r["mirrors"] if m["live"] and not m.get("redirect")), None)
    return (pick["url"], "") if pick else ("", r["reason"] or "nessun mirror raggiungibile")


def resolve(url: str) -> str:
    link, reason = find(url)
    if reason and is_page(url):
        resolvers.note("MultiUp: " + reason)  # resta nella riga del download e nell'errore finale
    elif link and not hosts.is_host_page(link):
        resolvers.note(f"MultiUp: il mirror migliore è {hosts.host(link)}, che non sappiamo scaricare"
                       " (megaup e gofile vogliono il browser o un account): apri la pagina")
    return link
