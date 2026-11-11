"""Ricerca immagini sul web (DuckDuckGo, poi Bing) e scarico sicuro del risultato.

Interfaccia: `search(query, n) -> [url]` e `fetch_image(url) -> Fetched`. Gli errori sono `SearchError` con un
messaggio gia' leggibile. Nessun URL finisce nei log: al massimo il dominio.

shortcut: scraping NON ufficiale delle pagine dei motori (nessuna API key): se DuckDuckGo/Bing cambiano il
codice della pagina o bloccano l'IP la ricerca fallisce con un errore chiaro; migliorare passando a un'API
ufficiale (es. Bing Image Search a pagamento o SearXNG locale) se diventa instabile. Controlla i termini d'uso.
"""

from __future__ import annotations

import html
import io
import json
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlsplit

import httpx

from .downloads.hosts import assert_public
from .net import UA

MAX_BYTES = 15 * 1024 * 1024
MIN_SIDE = 100  # sotto, di solito e' un'icona o un pixel di tracciamento
MAX_PIXELS = 60_000_000
MAX_REDIRECTS = 4
FETCH_DEADLINE = 20  # secondi totali per un'immagine
TIMEOUT = httpx.Timeout(8, connect=4)
FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif", "BMP": "bmp"}
# l'User-Agent dell'app e' riconoscibile come bot: i motori rispondono meglio a uno da browser
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class SearchError(Exception):
    """Il testo e' un codice (network|blocked|http|changed): la rotta lo traduce."""


@dataclass
class Fetched:
    data: bytes
    ext: str
    w: int
    h: int


_gap = threading.Lock()
_last = [0.0]


def _polite():
    """Almeno 1 s tra due richieste ai motori: meno probabilita' di essere bloccati."""
    with _gap:
        wait = _last[0] + 1.0 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def _get(url: str, headers: dict | None = None) -> str:
    """GET di una pagina dei motori (host fissi, non scelti dall'utente). Sostituibile nei test."""
    _polite()
    h = {"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9", **(headers or {})}
    try:
        r = httpx.get(url, headers=h, timeout=TIMEOUT, follow_redirects=True)
    except httpx.HTTPError:
        raise SearchError("network")
    if r.status_code in (403, 429, 202):
        raise SearchError("blocked")
    if r.status_code != 200:
        raise SearchError("http")
    return r.text[:3_000_000]


# ------------------------------------------------------------------ parsing (funzioni pure, testate)
def parse_ddg_vqd(page: str) -> str | None:
    m = re.search(r"vqd=[\"']?([\d-]+)", page)
    return m.group(1) if m else None


def parse_ddg_results(text: str) -> list[str]:
    try:
        items = json.loads(text).get("results") or []
    except (ValueError, AttributeError):
        return []
    return [i["image"] for i in items if isinstance(i, dict) and isinstance(i.get("image"), str)]


def parse_bing(page: str) -> list[str]:
    """Ogni risultato ha un attributo m="{...&quot;murl&quot;:&quot;<immagine>&quot;...}"."""
    out = []
    for raw in re.findall(r'\bm="(\{[^"]*\})"', page):
        try:
            u = json.loads(html.unescape(raw)).get("murl")
        except ValueError:
            continue
        if isinstance(u, str):
            out.append(u)
    return out


def _ddg(query: str) -> list[str]:
    q = quote(query)
    vqd = parse_ddg_vqd(_get(f"https://duckduckgo.com/?q={q}&iax=images&ia=images"))
    if not vqd:
        raise SearchError("changed")
    return parse_ddg_results(_get(f"https://duckduckgo.com/i.js?l=us-en&o=json&q={q}&vqd={vqd}&f=,,,,,&p=1",
                                  {"Referer": "https://duckduckgo.com/"}))


def _bing(query: str) -> list[str]:
    return parse_bing(_get(f"https://www.bing.com/images/search?q={quote(query)}&form=HDRSC2&first=1&safeSearch=Moderate"))


PROVIDERS = [("duckduckgo", _ddg), ("bing", _bing)]


def search(query: str, n: int = 1) -> list[str]:
    """Primi `n` indirizzi http(s) di immagini per `query`; prova DuckDuckGo e poi Bing.
    Lista vuota se nessun risultato; SearchError(codice: network|blocked|http|changed) se i motori non rispondono."""
    errs: list[str] = []
    for _name, fn in PROVIDERS:
        try:
            urls = [u for u in fn(query) if u.startswith(("http://", "https://"))]
        except SearchError as e:
            errs.append(str(e))
            continue
        if urls:
            return urls[:max(1, n)]
    if errs and len(errs) == len(PROVIDERS):
        raise SearchError(errs[0])
    return []


# ------------------------------------------------------------------ scarico sicuro
def validate_image(data: bytes) -> Fetched:
    """Pillow decide: formato ammesso, dimensioni plausibili, file integro. ValueError altrimenti."""
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt, (w, h) = im.format, im.size
            if fmt not in FORMATS:
                raise ValueError("formato")
            if w * h > MAX_PIXELS:
                raise ValueError("troppo grande")
            if min(w, h) < MIN_SIDE:
                raise ValueError("troppo piccola")
            im.load()  # file troncato o corrotto: solleva qui
    except (OSError, Image.DecompressionBombError, SyntaxError) as e:
        raise ValueError("non e' un'immagine") from e
    return Fetched(data, FORMATS[fmt], w, h)


def fetch_image(url: str) -> Fetched:
    try:
        return _fetch(url)
    except httpx.HTTPError as e:
        raise ValueError("rete") from e


def _fetch(url: str) -> Fetched:
    """Scarica e valida. ValueError con la ragione se non va bene. Ogni salto (anche i redirect) passa da assert_public.
    shortcut: la risoluzione DNS di assert_public e quella di httpx sono due momenti diversi (DNS rebinding); accettabile per un'app locale."""
    deadline = time.monotonic() + FETCH_DEADLINE
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": BROWSER_UA, "Accept": "image/*"}) as c:
        for _ in range(MAX_REDIRECTS + 1):
            assert_public(url)
            with c.stream("GET", url) as r:
                if r.is_redirect:
                    loc = r.headers.get("location")
                    if not loc:
                        raise ValueError("redirect")
                    url = urljoin(url, loc)
                    continue
                if r.status_code != 200:
                    raise ValueError(f"HTTP {r.status_code}")
                if int(r.headers.get("content-length") or 0) > MAX_BYTES:
                    raise ValueError("troppo grande")
                buf = bytearray()
                for chunk in r.iter_bytes(65536):
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        raise ValueError("troppo grande")
                    if time.monotonic() > deadline:
                        raise ValueError("timeout")
                return validate_image(bytes(buf))
    raise ValueError("troppi redirect")


def domain(url: str) -> str:
    return (urlsplit(url).hostname or "?").lower()
