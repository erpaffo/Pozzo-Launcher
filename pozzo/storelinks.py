"""Link di download elencati nella pagina di un gioco degli store online (nxbrew, ziperto e simili).

La pagina di un gioco elenca, per ogni file (gioco base, aggiornamento, DLC, versione in un'altra lingua,
parte di un archivio grande), un link per provider di hosting. Le regole per sito:

  nxbrew   <p><strong>Base Game NSP (996 MB)</strong></p> seguito da un <p> per provider
           («<strong>DataNodes</strong><br><a href=…>Download</a>»)
  ziperto  «Download (Base Game) Links: NSP (168MB)» con i provider nella stessa riga
           («<a>MegaUp</a> | <a>Send</a> | …»)
  repack PC (fitgirl e simili)  un <ul> in cui ogni <li> è una fonte: pagina del torrent, magnet,
           «.torrent file only», paste dei filehoster («Filehoster: MultiUpload») e, dentro lo spoiler
           «Click to show direct links», i file veri (part01.rar, part02.rar…)

Ogni link ha un `role`: «download» (il caso di nxbrew/ziperto), «magnet», «page» (una pagina da aprire),
«paste» (un elenco di link, vedi `paste()`) o «direct» (un file vero).

Alcuni provider passano da un accorciatore con pubblicita' (ouo.io): la pagina vera e' dietro un
controllo che solo un browser supera, quindi la risolve l'app desktop (finestra WebView nascosta,
`set_resolver`) e il risultato resta in cache.
"""

from __future__ import annotations

import base64
import json
import re
import threading
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlsplit

import httpx

try:  # come catalog.py: beautifulsoup4 serve solo a questi due formati
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - installazione senza la dipendenza opzionale
    BeautifulSoup = None  # type: ignore[assignment]

from .catalog import _clean_text, _require_soup

CACHE_PREFIX = "storelinks4:"  # versione 4: solo i link che scaricano davvero (magnet, paste, file) e righe per sito
PASTE_PREFIX = "storepaste:"
RESOLVED_PREFIX = "resolved:"
MAX_AGE = 7 * 86400  # le pagine cambiano quando esce un aggiornamento
RESOLVED_TTL = 30 * 86400
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36"),
           "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9,it;q=0.8"}
SHORTENERS = {"ouo.io", "ouo.press"}
# link della pagina che non sono file: strumenti consigliati e la pagina stessa
_SKIP_HOSTS = {"nxbrew.net", "ziperto.com", "tinfoil.io", "github.com", "7-zip.org", "winrar.com", "rarlab.com",
               "jdownloader.org", "internetdownloadmanager.com"}
# host dei paste degli store (elenchi di link incollati): si leggono con `paste()`
_PASTE_HOST = re.compile(r"paste|rentry\.co|controlc\.com|justpaste\.it|telegra\.ph", re.I)
_FILE = re.compile(r"\.(rar|zip|7z|iso|bin|exe|nsp|xci|nsz|pkg|tar|gz)$|\.(part\d+|r\d{2}|\d{3})$", re.I)
# host che danno il file vero: tutto il resto (sito dello sviluppatore, forum, immagini) non è un download
FILE_HOSTS = {"fuckingfast.co", "dl.fuckingfast.co", "datanodes.to", "filekeeper.net", "1fichier.com",
              "megaup.net", "krakenfiles.com", "pixeldrain.com", "gofile.io", "multiup.io", "multiup.org",
              "multiup.eu", "zippyshare.com", "letsupload.io", "onedrive.live.com", "1drv.ms",
              "drive.google.com", "mega.nz", "mediafire.com", "racaty.net", "bowfile.com", "mixdrop.co"}
# siti che elencano il torrent: si aprono nel browser (a scaricare è il magnet)
TORRENT_SITES = {"1337x.to", "1337x.st", "1337x.gd", "1377x.to", "rutor.info", "rutor.is", "tapochek.net",
                 "rutracker.org", "nnmclub.to", "thepiratebay.org", "torrentgalaxy.to", "glodls.to",
                 "limetorrents.lol", "kickasstorrents.to", "torrentdownloads.me", "yts.mx"}
KIND_ORDER = ("game", "update", "dlc", "extra")
KIND_LABELS = {"game": "Gioco", "update": "Aggiornamento", "dlc": "DLC", "extra": "Altro"}

_KIND_RULES = (
    (re.compile(r"\bdlc\b|\badd-?ons?\b|\bexpansion\b|\bseason pass\b", re.I), "dlc"),
    (re.compile(r"\bupdate\b|\bpatch\b", re.I), "update"),
    (re.compile(r"\bbase game\b|\bmain game\b|\bgame\b", re.I), "game"),
)
_PART = re.compile(r"\b(?:part|parte)\s*(\d+)\b", re.I)
_JUNK = re.compile(r"\s*[-–—_]{3,}.*$")  # separatori e testo pubblicitario in coda alla riga
_LINK_WORDS = ("download", "download now", "here", "link", "mirror", "scarica")


def _label(text: str) -> str:
    return _JUNK.sub("", text or "").strip(" -–—:")[:120]


def host(url: str) -> str:
    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def is_shortener(url: str) -> bool:
    return host(url) in SHORTENERS


def kind_of(text: str) -> str:
    """Tipo del file a cui si riferisce una riga («Update NSP», «Download (DLC) Links», «Base Game»)."""
    for regex, kind in _KIND_RULES:
        if regex.search(text or ""):
            return kind
    return ""


def part_of(text: str) -> int:
    m = _PART.search(text or "")
    return int(m.group(1)) if m else 0


def series_of(name: str) -> str:
    """Nome comune delle parti di un archivio: «Gioco.part01.rar» e «Gioco.part02.rar» -> «Gioco»."""
    stem = Path(unquote(urlsplit(name or "").path)).name
    return re.sub(r"(\.part\d+\.rar|\.r\d{2}|\.\d{3})$", "", stem, flags=re.I)


def _provider(text: str) -> str:
    """«Filehoster: MultiUpload (10+ hosters…)» -> «MultiUpload»."""
    name = re.sub(r"^filehosters?:\s*", "", (text or "").strip(), flags=re.I)
    return re.sub(r"\s*\(.*$", "", name).strip()[:60]


def _mk(kind: str, label: str, provider: str, href: str, role: str) -> dict:
    parts = urlsplit(href)
    name = Path(unquote(parts.path)).name
    frag = unquote(parts.fragment)
    if frag and "." in frag and "." not in name:  # fuckingfast: il nome del file sta nel frammento
        name = frag
    return {"kind": kind, "label": label[:120], "provider": provider[:60], "url": href, "host": host(href),
            "part": part_of(name or label), "short": is_shortener(href), "role": role,
            "file": name if role == "direct" else "", "series": series_of(name) if role == "direct" else ""}


def _li_text(li) -> str:
    """Testo di un <li> senza il contenuto degli spoiler (i link diretti sono decine e non sono un'etichetta)."""
    out = []
    for child in li.children:
        if getattr(child, "name", None):
            if any("spoiler-content" in c for c in (child.get("class") or [])):
                continue
            out.append(child.get_text(" ", strip=True))
        else:
            out.append(str(child))
    return re.sub(r"\s+", " ", " ".join(out)).strip()


def _li_links(li, text: str, section: dict, skip: set[str]) -> list[dict]:
    """Link di una riga <li> di uno store di repack: magnet, pagina del torrent, paste o file diretto.

    Restano solo i link che portano davvero a un file (o a un elenco di file): sito dello sviluppatore,
    forum e immagini sono rumore e si scartano.
    """
    kind = kind_of(text) or section["kind"]
    anchors = [(a, (a.get("href") or "").strip()) for a in li.find_all("a", href=True)]
    has_magnet = any(href.startswith("magnet:") for _, href in anchors)
    # l'etichetta della riga è il nome del sito («1337x», «DataNodes»), non tutta la frase con i consigli
    names = [_provider(_clean_text(a)) for a, href in anchors
             if href.startswith("http") and host(href) not in skip]
    names = [n for n in names if n and n.lower() not in _LINK_WORDS and "torrent file" not in n.lower()]
    label = names[0] if names else _label(text)
    out = []
    for a, href in anchors:
        name = _clean_text(a)
        if href.startswith("magnet:"):
            out.append(_mk(kind, label, "magnet", href, "magnet"))
            continue
        if not href.startswith(("http://", "https://")) or host(href) in skip:
            continue
        h = host(href)
        parts = urlsplit(href)
        # il nome del file può stare nella pagina (spoiler) o nel frammento (fuckingfast: #Gioco.part01.rar)
        probe = " ".join((name, unquote(parts.path), unquote(parts.fragment)))
        if _PASTE_HOST.search(h):
            if "torrent" in name.lower() and has_magnet:  # il magnet scarica la stessa cosa
                continue
            out.append(_mk(kind, label, _provider(name) or h, href, "paste"))
        elif a.find_parent(class_="su-spoiler-content") is not None or _FILE.search(probe) or h in FILE_HOSTS:
            out.append(_mk(kind, label, h, href, "direct"))
        elif h in TORRENT_SITES:
            out.append(_mk(kind, label, _provider(name) or h, href, "page"))
    return out


def parse_page(page: str, url: str) -> dict:
    """Link {kind, label, provider, url, host, part, role} letti dalla pagina di un gioco."""
    _require_soup()
    soup = BeautifulSoup(page, "html.parser")
    root = None
    for sel in ("article .entry", ".entry-content", "article"):
        root = soup.select_one(sel)
        if root:
            break
    root = root or soup.body or soup
    for junk in root.select(".su-spoiler-title"):  # «Click to show direct links»: non è un link
        junk.decompose()
    links: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    section = {"kind": "game", "label": ""}
    skip = _SKIP_HOSTS | {host(url)}  # la pagina stessa non è un link di download

    def add(items: list[dict]):
        for it in items:
            key = (it["kind"], it["provider"].lower(), it["url"])
            if key not in seen:
                seen.add(key)
                links.append(it)

    for node in root.find_all(("p", "li")):
        text = _li_text(node) if node.name == "li" else _clean_text(node)
        anchors = []
        for a in node.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if href.startswith("magnet:") or (href.startswith(("http://", "https://")) and host(href) not in skip):
                anchors.append((a, href))
        kind = kind_of(text)
        if not anchors:
            if kind:  # riga di intestazione: «Base Game NSP (996 MB)», «Update NSP (v1.2)», «Part 1»
                section = {"kind": kind, "label": _label(text)}
            continue
        if kind:  # ziperto: intestazione e provider nella stessa riga
            section = {"kind": kind, "label": _label(text)}
        if node.name == "li":
            add(_li_links(node, text, section, skip))
            continue
        p = node
        strong = _clean_text(p.find("strong")) if p.find("strong") else ""
        for a, href in anchors:
            if href.startswith("magnet:"):  # un magnet in un paragrafo: come nelle righe dei repack
                add([_mk(section["kind"], section["label"] or _label(text), "magnet", href, "magnet")])
                continue
            name = _clean_text(a)
            provider = strong if (not name or name.lower() in _LINK_WORDS) and strong and strong.lower() not in _LINK_WORDS else name
            provider = (provider or host(href)).strip()[:60]
            add([_mk(section["kind"], section["label"], provider, href, "download")])
    return {"url": url, "site": host(url), "links": links}


# ---------------------------------------------------------------- cache

def cached(cache, url: str) -> dict | None:
    """Link gia' letti per quella pagina (None se mancano o sono vecchi)."""
    return cache.kv_get(CACHE_PREFIX + url, MAX_AGE)


def put(cache, url: str, data: dict) -> dict:
    cache.kv_set(CACHE_PREFIX + url, data)
    return data


# ---------------------------------------------------------------- paste dei filehoster

def cached_paste(cache, url: str) -> dict | None:
    return cache.kv_get(PASTE_PREFIX + url, MAX_AGE)


def put_paste(cache, url: str, data: dict) -> dict:
    cache.kv_set(PASTE_PREFIX + url, data)
    return data


def _b64(s: str) -> bytes:
    s = (s or "").strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4))


_CIPHER = re.compile(r'\{\s*"(?:v|ct)"[^{}]*\}')  # il messaggio cifrato che PrivateBin mette nella pagina


def _decipher(blob: dict, key: bytes) -> str:
    """PrivateBin: v1 AES-GCM con la chiave del frammento (#…), v2 con la stessa chiave passata da PBKDF2."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    ct = _b64(blob["ct"])
    if int(blob.get("v") or 1) >= 2:
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=int(blob.get("ks") or 256) // 8,
                         salt=_b64(blob.get("salt") or ""), iterations=int(blob.get("iter") or 100000)).derive(key)
    aead = AESGCM(key)
    for adata in ({_b64(blob["adata"]) if blob.get("adata") else b""}, b""):
        try:  # la AAD cambia tra le versioni: se non torna, il tag non verifica e si prova la successiva
            return aead.decrypt(_b64(blob["iv"]), ct, adata).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - chiave sbagliata o AAD diversa: si prova l'altra
            continue
    raise ValueError("paste cifrato con una chiave che non torna")


def _magnet(data: bytes) -> str:
    """Da un file .torrent al magnet equivalente (stesso contenuto, niente file temporaneo)."""
    try:
        import libtorrent as lt
        ti = lt.torrent_info(data)
        h = ti.info_hashes()
        ih = str(h.v1 or h.v2)
        out = f"magnet:?xt=urn:btih:{ih}&dn={quote(ti.name())}"
        for t in ti.trackers():
            out += "&tr=" + quote(t["url"], safe="")
        return out
    except Exception:  # noqa: BLE001 - senza libtorrent il magnet non serve: resta il paste da aprire
        return ""


def _links_of(text: str) -> list[str]:
    out = []
    if "<a" in text.lower():
        _require_soup()
        soup = BeautifulSoup(text, "html.parser")
        out = [a["href"].strip() for a in soup.find_all("a", href=True)]
    else:
        out = re.findall(r"https?://[^\s<>\"']+", text)
    seen, clean = set(), []
    for u in out:
        if not u.startswith(("http://", "https://")) or host(u) in _SKIP_HOSTS:
            continue
        if _PASTE_HOST.search(host(u)):  # il paste che linka se stesso o altri paste: non sono file
            continue
        if u not in seen:
            seen.add(u)
            clean.append(u)
    return clean


def _paste_get(url: str, timeout: float) -> httpx.Response:
    """Unico punto di rete dei paste: solo indirizzi pubblici (un paste non deve leggere la rete di casa)."""
    from .webmeta import safe_client

    with safe_client(headers=HEADERS, timeout=httpx.Timeout(timeout, connect=8), follow_redirects=True) as c:
        return c.get(url)


def paste(url: str, timeout: float = 20.0) -> dict:
    """Link contenuti in un paste dei filehoster (decifrato se è PrivateBin): {url, site, links, magnet}."""
    r = _paste_get(url, timeout)
    r.raise_for_status()
    page = r.text
    key = urlsplit(url).fragment
    text = ""
    if key:
        for raw in _CIPHER.findall(page):
            try:
                text = _decipher(json.loads(raw), _b64(key))
                break
            except (ValueError, KeyError, TypeError):
                continue
    if not text:
        text = page
    if text.lstrip().startswith("d8:"):  # dentro c'è il file .torrent
        return {"url": url, "site": host(url), "links": [], "magnet": _magnet(text.encode("utf-8", "replace"))}
    files = [_mk("game", "", host(u), u, "direct") for u in _links_of(text)]
    return {"url": url, "site": host(url), "links": files, "magnet": ""}


# ---------------------------------------------------------------- risoluzione degli accorciatori

RESOLVER: dict = {"fn": None, "reason": None}
_LOCK = threading.Lock()  # una finestra nascosta alla volta: piu' download insieme non devono aprirne tre


def set_resolver(fn, reason=None) -> None:
    """fn(url) -> link finale | None: impostata dall'app desktop, che ha un browser vero da usare.
    `reason()` dice perché l'ultima risoluzione non è arrivata al file (finisce nelle note della coda)."""
    RESOLVER["fn"], RESOLVER["reason"] = fn, reason


BROWSER_TIMEOUT = 90  # secondi: tetto di tutta l'attesa (il risolutore del browser ne usa 75, piu' l'apertura e la coda)
# parametri di una URL firmata: il link vale per poco, non va messo in cache per 30 giorni
_SIGNED = re.compile(r"[?&](sig|signature|token|expires|policy|auth|key)=", re.I)


def with_browser(url: str, timeout: float | None = None) -> str:
    """Apre `url` nella finestra nascosta dell'app e aspetta il link vero ("" senza app desktop, o oltre `timeout`).

    Serve agli accorciatori e agli host che mettono un captcha: lì un client HTTP non passa. Il motivo di un
    fallimento va nelle note del risolutore in corso (resolvers.note): il download lo mostra.
    """
    from .downloads import resolvers  # import qui: downloads tira dietro httpx/torrent
    timeout = timeout or BROWSER_TIMEOUT
    fn = RESOLVER["fn"]
    if not fn:
        resolvers.note("browser nascosto non disponibile")
        return ""
    resolvers.phase(f"Apro la pagina nel browser nascosto (fino a {timeout:g} s)…")
    out, gone = [], threading.Event()

    def run():  # thread a parte: se la finestra si pianta l'attesa finisce lo stesso
        with _LOCK:
            if gone.is_set():  # l'attesa e' gia' scaduta mentre un'altra finestra era aperta
                return
            try:
                out.append(fn(url) or "")
            except Exception:  # finestra del browser non disponibile: il link originale resta valido
                out.append("")

    th = threading.Thread(target=run, daemon=True, name="browser-hidden")
    th.start()
    th.join(timeout)
    gone.set()
    if not out:
        resolvers.note(f"il browser nascosto non ha risposto entro {timeout:g} s")
        return ""
    if not out[0]:
        why = ""
        if RESOLVER["reason"]:
            try:
                why = RESOLVER["reason"]() or ""
            except Exception:  # un motivo rotto non deve nascondere il fallimento
                why = ""
        resolvers.note(why or "il browser nascosto non ha trovato il link")
    return out[0]


def resolve(cache, url: str) -> str:
    """Link vero dietro un accorciatore pubblicitario (o lo stesso link, se non lo e')."""
    if not is_shortener(url):
        return url
    hit = cache.kv_get(RESOLVED_PREFIX + url, RESOLVED_TTL)
    if hit:
        return hit
    final = ""
    try:  # alcuni accorciatori non chiedono nulla: un semplice GET basta
        r = httpx.get(url, headers=HEADERS, timeout=httpx.Timeout(15, connect=8), follow_redirects=True)
        if r.status_code == 200 and not is_shortener(str(r.url)):
            final = str(r.url)
    except httpx.HTTPError:
        pass
    if not final:
        final = with_browser(url)
    if final and not is_shortener(final):
        if not _SIGNED.search(final):  # URL firmata (scade): in cache a 30 giorni farebbe danni
            cache.kv_set(RESOLVED_PREFIX + url, final)
        return final
    return url


def fetch(url: str, timeout: float = 20.0) -> dict:
    """Scarica la pagina del gioco e ne legge i link."""
    r = httpx.get(url, headers=HEADERS, timeout=httpx.Timeout(timeout, connect=8), follow_redirects=True)
    r.raise_for_status()
    return parse_page(r.text, str(r.url))
