"""Dalla pagina di un host di file al link diretto:

    ouo.io/xxx  ->  datanodes.to/abc123  ->  https://s12.datanodes.to/d/abc123/Gioco.nsp

Gli store online (NXBrew, Ziperto) non linkano il file: linkano l'accorciatore, che porta alla pagina
dell'host. Questo modulo fa il passo successivo, compilando il modulo «download gratuito» della pagina.

Gli host che mettono un captcha non hanno un modulo da compilare: lì si apre la pagina nel browser
nascosto dell'app (lo stesso degli accorciatori) e si aspetta che il link cambi. Un host sconosciuto
resta com'è: il motore HTTP rifiuta di salvare una pagina HTML, quindi l'errore si vede subito.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

import httpx

from ..net import UA
from . import resolvers


class Blocked(Exception):
    """L'host ha detto di no e il browser nascosto non cambierebbe nulla (limite per IP, captcha): il testo e' il motivo."""


TIMEOUT = httpx.Timeout(25, connect=8)
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9,it;q=0.8"}


def host(url: str) -> str:
    return (urlsplit(url or "").hostname or "").lower().removeprefix("www.")


_FILE_PATH = re.compile(r"\.(nsp|xci|nsz|zip|rar|7z|iso|bin|pkg|dmg|torrent)$", re.I)
_FORM_PATH = ("/download", "/login", "/register", "/premium", "/account")


def is_file_url(url: str, page: str = "") -> bool:
    """Il link è il file e non la pagina che lo offre: CDN diverso, /d/, /download/<token>, o un'estensione."""
    a, b = urlsplit(url or ""), urlsplit(page or "")
    if a.scheme not in ("http", "https"):
        return False
    path = a.path.lower()
    if path.rstrip("/") in _FORM_PATH:  # il modulo di download, non il file
        return False
    if b.hostname and (a.hostname or "").lower() != (b.hostname or "").lower():
        return True  # nodo CDN diverso dalla pagina
    return bool(_FILE_PATH.search(path)) or "/d/" in path or path.startswith("/download/")


def _same_page(a: str, b: str) -> bool:
    pa, pb = urlsplit(a), urlsplit(b)
    return (pa.hostname or "").lower() == (pb.hostname or "").lower() and pa.path.rstrip("/") == pb.path.rstrip("/")


def _fichier(url: str, s: httpx.Client) -> str:
    """1fichier: un POST sulla pagina stessa, il link sta nel pulsante arancione."""
    page = s.post(url).text
    w = re.search(r"must wait\s+(?:about\s+)?(\d+)\s*(min|sec)?", page, re.I)
    if w:  # limite per IP: lo dice il server, inutile insistere (e inutile il browser)
        raise Blocked(f"1fichier: limite per IP, riprova tra {w[1]} {'secondi' if (w[2] or '').lower() == 'sec' else 'minuti'}")
    m = re.search(r'<a[^>]+class="[^"]*btn-orange[^"]*"[^>]*href="([^"]+)"', page) or \
        re.search(r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*btn-orange', page)
    if not m and re.search(r"g-recaptcha|h-captcha|cf-turnstile", page, re.I):
        raise Blocked("1fichier: chiede un captcha, scaricalo dal browser")  # la finestra e' nascosta: non lo risolve
    if not m and "adz" not in page:  # né il modulo né il pulsante: 1fichier mostra la home per i file rimossi
        raise Blocked("1fichier: il file non esiste più (la pagina rimanda alla home)")
    return m.group(1) if m else ""


def _krakenfiles(url: str, s: httpx.Client) -> str:
    """KrakenFiles: la pagina ha un form con un token; POST in JSON restituisce l'url."""
    page = s.get(url).text
    action = re.search(r'<form[^>]*id="dl-form"[^>]*action="([^"]+)"', page) or \
        re.search(r'<form[^>]*action="([^"]+)"[^>]*id="dl-form"', page)
    token = re.search(r'<input[^>]*id="dl-token"[^>]*value="([^"]+)"', page) or \
        re.search(r'<input[^>]*value="([^"]+)"[^>]*id="dl-token"', page)
    if not action or not token:
        return ""
    data = s.post(urljoin(url, action.group(1)), data={"token": token.group(1)}).json()
    return str(data.get("url") or "") if data.get("status") == "ok" else ""


def _megaup(url: str, s: httpx.Client) -> str:
    """MegaUp: il pulsante di download compare dopo il conto alla rovescia; se chiede un captcha si passa al browser."""
    page = s.get(url).text
    m = re.search(r'<a[^>]+id="btn-download"[^>]+href="([^"]+)"', page) or \
        re.search(r'<a[^>]+href="(https?://[^"]*/download/[^"]+)"', page)
    return urljoin(url, m.group(1)) if m else ""


_SITES = {"1fichier.com": _fichier, "krakenfiles.com": _krakenfiles, "megaup.net": _megaup}
# DataNodes dà il file solo come download vero dopo il conto alla rovescia: nel DOM il link non c'è mai.
# Lo prende la finestra nascosta dell'app, che clicca e legge l'URL del download (app/browserdl.py).
# FuckingFast ha la stessa pagina con Cloudflare davanti (il POST /f/<id>/go da qui prende 403): serve il browser.
BROWSER_ONLY = {"datanodes.to", "filekeeper.net", "fuckingfast.co", "dl.fuckingfast.co"}
# Host il cui conto alla rovescia si ferma nelle finestre nascoste (Chromium sospende i timer): la finestra
# va mostrata, altrimenti la pagina resta su «LAUNCH IN 5S» per sempre.
VISIBLE = {"filekeeper.net"}


def is_host_page(url: str) -> bool:
    return host(url) in _SITES or host(url) in BROWSER_ONLY


def resolve(url: str) -> str:
    """Link diretto al file, oppure "" (host sconosciuto, captcha, o limite del server)."""
    h = host(url)
    if h not in _SITES and h not in BROWSER_ONLY:
        return ""
    final = ""
    if h in _SITES:
        try:
            with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as s:
                final = _SITES[h](url, s) or ""
        except Blocked as e:
            resolvers.note(str(e))
            return ""
        except (httpx.HTTPError, ValueError, KeyError, AttributeError, TypeError):  # JSON o pagina cambiati
            final = ""
        final = urljoin(url, final.strip()) if final else ""
        if final and is_file_url(final, url):
            return final
    # shortcut: il link trovato dal browser non porta con sé i cookie della finestra (1fichier li chiede),
    # se un host rifiuta il download passare lì i cookie: task.options["headers"] li manda HTTP.run
    from .. import storelinks as SL  # import qui: storelinks tira dietro beautifulsoup
    final = SL.with_browser(url)
    if not final or _same_page(final, url) or urlsplit(final).path.lower().rstrip("/") in _FORM_PATH:
        return ""  # il browser a volte finisce sul modulo («/download»): non e' un file
    return final
