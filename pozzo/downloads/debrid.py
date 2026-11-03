"""Servizi debrid: dal link di un host al link diretto e veloce dell'abbonamento.

Si registra come risolutore: consulta gli host supportati dai servizi attivi e prova solo quelli compatibili.
Se nessuno ci riesce (host non supportato, chiave sbagliata, rete) resta il link originale.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from ..net import UA
from . import resolvers

SERVICES = ("realdebrid", "alldebrid", "premiumize", "torbox", "debridlink")
NAMES = {"realdebrid": "Real-Debrid", "alldebrid": "AllDebrid", "premiumize": "Premiumize", "torbox": "TorBox",
         "debridlink": "Debrid-Link"}
AGENT = "Pozzo"  # AllDebrid chiede il nome dell'app
TTL = 600  # secondi: un «riprendi» subito dopo non richiede di nuovo il link
_HOSTS_TTL = 600
TB_TRIES, TB_WAIT = 10, 3  # TorBox scarica prima il file sui suoi server: si aspetta un po', poi si lascia perdere
RD, AD, PM, TB = ("https://api.real-debrid.com/rest/1.0", "https://api.alldebrid.com/v4",
                  "https://www.premiumize.me/api", "https://api.torbox.app/v1/api")
DL = "https://debrid-link.com/api/v2"  # API v2: token personale, risposte {"success", "value"}
ERRORS = (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, IndexError)  # ValueError: JSON non valido

# parola chiave nell'errore del servizio -> motivo breve (nell'ordine: il primo che c'e' vince)
_WHY = (("support", "host non supportato"), ("token", "chiave non valida"), ("apikey", "chiave non valida"),
        ("api key", "chiave non valida"), ("auth", "chiave non valida"), ("premium", "serve un account premium"),
        ("limit", "limite del servizio raggiunto"), ("quota", "limite del servizio raggiunto"),
        ("traffic", "limite del servizio raggiunto"), ("not found", "link non disponibile"),
        ("link down", "link non disponibile"), ("dead", "link non disponibile"), ("unavailable", "link non disponibile"))


class _Fail(ValueError):
    """Il servizio ha risposto ma senza link: il testo e' il motivo."""


def _reason(d) -> str:
    """Motivo breve dalla risposta d'errore. Forme: DL {"error"}, RD {"error","error_code"}, AD {"error":{"code","message"}},
    PM {"message"}, TB {"detail"|"error"}."""
    if not isinstance(d, dict):
        return "risposta non valida"
    e = d.get("error")
    raw = f"{e.get('code') or ''} {e.get('message') or ''}" if isinstance(e, dict) else e
    raw = " ".join(str(raw or d.get("message") or d.get("detail") or "").split())
    low = raw.lower().replace("_", " ")
    return next((why for k, why in _WHY if k in low), raw[:100] or "nessun link restituito")


def _obj(r) -> dict:
    d = r.json()
    if not isinstance(d, dict):
        raise _Fail("risposta non valida")
    return d


_cache: dict[tuple[str, str], tuple[float, str]] = {}
_hosts_cache: dict[str, tuple[float, set[str]]] = {}


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(30, connect=10), headers={"User-Agent": UA}, follow_redirects=True)


def _domains(values) -> set[str]:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise _Fail("elenco host non valido")
    return {value.lower().rstrip(".") for value in values if value}


def _hoster_domains(items, status) -> set[str]:
    if not isinstance(items, list):
        raise _Fail("elenco host non valido")
    domains = set()
    for item in items:
        if not isinstance(item, dict):
            raise _Fail("elenco host non valido")
        if item.get("status") == status:
            domains.update(_domains(item.get("domains")))
    return domains


def _provider_hosts(c, svc: str) -> set[str]:
    if svc == "realdebrid":
        r = c.get(f"{RD}/hosts/domains")
        r.raise_for_status()
        return _domains(r.json())
    if svc == "alldebrid":
        r = c.get(f"{AD}/hosts/domains", params={"agent": AGENT})
        r.raise_for_status()
        d = _obj(r)
        if d.get("status") != "success":
            raise _Fail(_reason(d))
        return _domains((d.get("data") or {}).get("hosts"))
    if svc == "premiumize":
        r = c.get(f"{PM}/services/list")
        r.raise_for_status()
        d = _obj(r)
        if d.get("status") != "success":
            raise _Fail(_reason(d))
        return _domains(d.get("directdl"))
    if svc == "torbox":
        r = c.get(f"{TB}/webdl/hosters")
        r.raise_for_status()
        d = _obj(r)
        items = d.get("data")
        if not d.get("success") or not isinstance(items, list):
            raise _Fail(_reason(d))
        return _hoster_domains(items, True)
    if svc == "debridlink":
        r = c.get(f"{DL}/downloader/hosts")
        r.raise_for_status()
        d = _obj(r)
        items = d.get("value")
        if not d.get("success") or not isinstance(items, list):
            raise _Fail(_reason(d))
        return _hoster_domains(items, 1)
    raise _Fail("servizio non supportato")


def _supports(svc: str, url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if not host:
        return False
    now = time.time()
    cached = _hosts_cache.get(svc)
    if cached is None or now - cached[0] >= _HOSTS_TTL:
        with _client() as c:
            cached = (now, _provider_hosts(c, svc))
        _hosts_cache[svc] = cached
    return any(host == domain or host.endswith("." + domain) for domain in cached[1])


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def _iso(ts) -> str | None:
    return datetime.fromtimestamp(int(ts), timezone.utc).isoformat() if ts else None


# ---------------------------------------------------------------- sblocco: link diretto o ""
def _rd_unlock(c, key, url):
    d = _obj(c.post(f"{RD}/unrestrict/link", headers=_auth(key), data={"link": url}))
    if d.get("download"):
        return d["download"]
    raise _Fail(_reason(d))


def _ad_unlock(c, key, url):
    d = _obj(c.get(f"{AD}/link/unlock", headers=_auth(key), params={"agent": AGENT, "link": url}))
    if d.get("status") != "success":
        raise _Fail(_reason(d))
    data = d.get("data") or {}
    if data.get("link"):
        return data["link"]
    raise _Fail("il servizio sta preparando il file, riprova tra poco" if data.get("delayed") else "nessun link restituito")  # «delayed»: si lascia perdere


def _pm_unlock(c, key, url):
    d = _obj(c.post(f"{PM}/transfer/directdl", data={"apikey": key, "src": url}))
    if d.get("status") != "success":
        raise _Fail(_reason(d))
    files = d.get("content") or []
    if len(files) != 1:  # una cartella di file non e' un download solo
        raise _Fail("il link contiene più file" if files else "nessun link restituito")
    return files[0].get("link") or ""


def _tb_unlock(c, key, url):
    d = _obj(c.post(f"{TB}/webdl/createwebdownload", headers=_auth(key), data={"link": url}))
    wid = (d.get("data") or {}).get("webdownload_id") if d.get("success") else None
    if not wid:
        raise _Fail(_reason(d))
    for _ in range(TB_TRIES):
        r = _obj(c.get(f"{TB}/webdl/requestdl", params={"token": key, "web_id": wid}))
        if r.get("success") and r.get("data"):
            return r["data"]
        time.sleep(TB_WAIT)
    raise _Fail("file non ancora pronto, riprova tra poco")


def _dl_unlock(c, key, url):
    d = _obj(c.post(f"{DL}/downloader/add", headers=_auth(key), json={"url": url}))
    if not d.get("success"):
        raise _Fail(_reason(d))  # host non supportato, chiave sbagliata…
    return (d.get("value") or {}).get("downloadLink") or ""


# ---------------------------------------------------------------- account: {"user", "premium", "expires"}; ValueError se la chiave non va
def _rd_account(c, key):
    d = c.get(f"{RD}/user", headers=_auth(key)).json()
    if "error" in d:
        raise ValueError(d["error"])
    return {"user": d.get("username") or "", "premium": d.get("type") == "premium", "expires": d.get("expiration")}


def _ad_account(c, key):
    d = c.get(f"{AD}/user", headers=_auth(key), params={"agent": AGENT}).json()
    if d.get("status") != "success":
        raise ValueError((d.get("error") or {}).get("message") or "chiave non valida")
    u = d["data"]["user"]
    return {"user": u.get("username") or "", "premium": bool(u.get("isPremium")), "expires": _iso(u.get("premiumUntil"))}


def _pm_account(c, key):
    d = c.get(f"{PM}/account/info", params={"apikey": key}).json()
    if d.get("status") != "success":
        raise ValueError(d.get("message") or "chiave non valida")
    until = int(d.get("premium_until") or 0)
    return {"user": str(d.get("customer_id") or ""), "premium": until > time.time(), "expires": _iso(until)}


def _tb_account(c, key):
    d = c.get(f"{TB}/user/me", headers=_auth(key)).json()
    if not d.get("success"):
        raise ValueError(d.get("detail") or d.get("error") or "chiave non valida")
    u = d.get("data") or {}
    return {"user": u.get("email") or "", "premium": bool(u.get("plan")), "expires": u.get("premium_expires_at")}


def _dl_account(c, key):
    d = c.get(f"{DL}/account/infos", headers=_auth(key)).json()
    if not d.get("success"):
        raise ValueError((d.get("error") or d.get("message") or "chiave non valida"))
    v = d.get("value") or {}
    left = int(v.get("premiumLeft") or 0)  # secondi di premium rimasti
    return {"user": v.get("username") or "", "premium": left > 0, "expires": _iso(time.time() + left) if left > 0 else None}


_UNLOCK = {"realdebrid": _rd_unlock, "alldebrid": _ad_unlock, "premiumize": _pm_unlock, "torbox": _tb_unlock,
           "debridlink": _dl_unlock}
_ACCOUNT = {"realdebrid": _rd_account, "alldebrid": _ad_account, "premiumize": _pm_account, "torbox": _tb_account,
            "debridlink": _dl_account}


def account(svc: str, key: str) -> dict:
    """Prova della chiave (pulsante «Verifica» delle impostazioni)."""
    try:
        with _client() as c:
            return {"ok": True, "error": "", **_ACCOUNT[svc](c, key)}
    except ERRORS as e:
        return {"ok": False, "user": "", "premium": False, "expires": None, "error": str(e) or type(e).__name__}


def _why(e: Exception, key: str) -> str:
    """Motivo di un errore, senza mai far uscire la chiave (puo' stare nell'URL o nel testo)."""
    if isinstance(e, _Fail):
        msg = str(e)
    elif isinstance(e, httpx.TimeoutException):
        msg = "il servizio non risponde (timeout)"
    elif isinstance(e, httpx.HTTPError):
        msg = "servizio non raggiungibile"
    elif isinstance(e, ValueError):
        msg = "risposta non valida"
    else:
        msg = type(e).__name__
    return msg.replace(key, "***") if key else msg


def attempt(svc: str, key: str, url: str) -> tuple[str, str]:
    """(link diretto, motivo del fallimento). Bloccante: gira nel thread del risolutore."""
    now = time.time()
    hit = _cache.get((svc, url))
    if hit and now - hit[0] < TTL:
        return hit[1], ""
    try:
        with _client() as c:
            link = str(_UNLOCK[svc](c, key, url) or "")
    except ERRORS as e:
        return "", _why(e, key)
    if link.lower().startswith(("http://", "https://")):
        for k in [k for k, v in _cache.items() if now - v[0] >= TTL]:
            del _cache[k]
        _cache[(svc, url)] = (now, link)
        return link, ""
    return "", "nessun link restituito"


def unlock(svc: str, key: str, url: str) -> str:
    """Link diretto o "" (host non supportato, chiave sbagliata, rete)."""
    return attempt(svc, key, url)[0]


def resolver(get_conf):
    """Per resolvers.register. get_conf() -> {servizio: {"enabled", "key"}} letto a ogni link (le impostazioni cambiano dal vivo)."""
    def fn(url: str):
        if not url.lower().startswith(("http://", "https://")):
            return ""
        conf = get_conf() or {}
        for svc in SERVICES:
            c = conf.get(svc) or {}
            if c.get("enabled") and c.get("key"):
                try:
                    supported = _supports(svc, url)
                except ERRORS as e:
                    resolvers.note(f"{NAMES[svc]}: {_why(e, c['key'])}")
                    continue
                if not supported:
                    resolvers.note(f"{NAMES[svc]}: host non supportato")
                    continue
                link, why = attempt(svc, c["key"], url)
                if link:
                    return link, svc
                resolvers.note(f"{NAMES[svc]}: {why}")  # il manager lo mostra e lo porta nell'errore finale
        return ""
    return fn
