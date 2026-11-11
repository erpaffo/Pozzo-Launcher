"""Controllo online dei link prima di accodarli, ed estrazione dei link da testo libero (appunti).

Solo richieste normali (GET con Range 0-0): nessun captcha risolto, nessuna protezione aggirata. Un host che
risponde con muri (403, 429, 5xx, pagine a captcha) resta «unknown»: non e' un link morto.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from urllib.parse import unquote, urlsplit

import httpx

from ..net import UA
from . import hosts

MAX_LINKS = 50
WORKERS = 5  # richieste insieme: abbastanza per 50 link in pochi secondi senza martellare un host
HOPS = 5  # redirect seguiti a mano, ognuno ricontrollato con assert_public
TIMEOUT = httpx.Timeout(8, connect=5)
_URL = re.compile(r"(?:https?://[^\s<>\"'`]+|magnet:\?[^\s<>\"'`]+)", re.I)
_TAIL = ".,;:!?)]}>"  # punteggiatura che chiude la frase, non il link


def parse_links(text: str, public=hosts.assert_public) -> list[str]:
    """Link http(s)/magnet nel testo, senza doppioni (ordine di apparizione), al massimo MAX_LINKS.
    Scarta chi punta a una rete privata/LAN (SSRF); `public` e' iniettabile per i test (DNS)."""
    seen, cand = set(), []
    for m in _URL.findall(str(text or "")[:200_000]):
        u = m.rstrip(_TAIL)
        if u.lower() not in seen:
            seen.add(u.lower())
            cand.append(u)

    def ok(u: str) -> bool:
        if u.lower().startswith("magnet:"):
            return "xt=" in u.lower()
        try:
            public(u)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(WORKERS) as ex:
        good = list(ex.map(ok, cand[:MAX_LINKS * 2]))  # un po' di margine: gli scartati non tolgono posto
    return [u for u, g in zip(cand, good) if g][:MAX_LINKS]


def _name(r: httpx.Response) -> str:
    cd = r.headers.get("content-disposition") or ""
    if cd:
        msg = Message()
        msg["content-disposition"] = cd
        n = msg.get_filename()
        if n:
            return n.replace("\\", "/").rsplit("/", 1)[-1][:200]
    return unquote(urlsplit(str(r.url)).path.rsplit("/", 1)[-1])[:200]


def check(url: str, client: httpx.Client | None = None) -> dict:
    """{url, status: online|offline|unknown, size, name}. Mai eccezioni: l'esito e' lo stato."""
    out = {"url": url, "status": "unknown", "size": 0, "name": ""}
    if not url.lower().startswith(("http://", "https://")):
        return out  # magnet/torrent: niente da interrogare
    own = client is None
    c = client or httpx.Client(timeout=TIMEOUT, headers={"User-Agent": UA}, follow_redirects=False)
    try:
        cur = url
        for _ in range(HOPS + 1):
            hosts.assert_public(cur)  # anche su ogni redirect
            with c.stream("GET", cur, headers={"Range": "bytes=0-0"}) as r:
                if r.is_redirect and r.headers.get("location"):
                    cur = str(r.url.join(r.headers["location"]))
                    continue
                code = r.status_code
                if code in (404, 410):
                    out["status"] = "offline"
                elif 200 <= code < 300:
                    out["status"] = "online"
                    cr = re.fullmatch(r"bytes \d+-\d+/(\d+)", r.headers.get("content-range") or "")
                    ln = r.headers.get("content-length") or "0"
                    out["size"] = int(cr[1]) if cr else int(ln) if code == 200 and ln.isdigit() else 0
                    out["name"] = _name(r)
                return out
    except (httpx.HTTPError, ValueError, OSError):
        pass  # rete giu', DNS, link verso la LAN: «sconosciuto», non «offline»
    finally:
        if own:
            c.close()
    return out


def check_many(urls: list[str], fn=check) -> list[dict]:
    """Stesso ordine dell'ingresso, WORKERS richieste alla volta."""
    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(fn, urls[:MAX_LINKS]))
