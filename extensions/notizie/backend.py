"""Notizie videogiochi: feed RSS/Atom di case e siti, con cache su disco.

Funzioni importabili (per filtro «i miei giochi», seguire un gioco, riepilogo settimanale):
    parse_feed(xml_bytes, source) -> [item]   item: {id, source, casa, title, link, summary, image, published(ISO UTC), tags, kind}
    classify(item) -> "annuncio" | "patch" | "dlc" | "uscita" | "notizia"
    validate_settings(body) -> {"disabled_sources": [...], "custom_sources": [...]}   (ValueError se non valido)
    all_sources(settings) -> [{id, casa, nome, url, custom, enabled}]
    collect(cache_dir, sources, ttl=1800) -> (items ordinati dal piu' recente, [stato fonte])
    select(items, casa="", q="", kind="", limit=50, before="") -> [item]

Rotte (/plugin-api/notizie/...):
    GET  feed?casa=&q=&kind=&limit=50&before=ISO -> {"items": [...], "sources": [{id,casa,nome,ok,error,fetched_at}]}
    GET  sources -> {"sources": [{id,casa,nome,url,custom,enabled}]}
    POST sources {"disabled_sources": [id], "custom_sources": [{casa,nome,url}]} -> {"ok": true, "sources": [...]}
    GET  follows -> {"follows": [{id,title,steam_appid,last_seen_ts}]}
    POST follow {id,title,steam_appid?} / POST unfollow {id} / POST follows/seen {id} -> {"ok": true, "follows": [...]}
    GET  follows/news -> {"games": [{id,title,unread,items: [{title,link,published,kind,unread}]}]}
    GET  digest -> rassegna della settimana (digest-AAAA-SS.json in cache, 8 settimane); la crea se manca

Lavoro «rassegna-settimanale» (ogni 6 ore, crea la rassegna se manca per la settimana, una notifica sola).

Cache: <cartella config>/notizie-cache/<id>.json (+ .xml). Si riscarica solo oltre il TTL (30 min, minimo 15) con
If-None-Match/If-Modified-Since; su 429/5xx/errori backoff esponenziale per fonte (next_allowed_at). Max 4 richieste in parallelo.
"""

import hashlib
import html
import json
import re
import sqlite3
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
from fastapi import HTTPException

UA = "PozzoLauncher/1.0"
TTL = 30 * 60
MIN_TTL = 15 * 60
BACKOFF_MAX = 6 * 3600


def _s(id, casa, nome, url):
    return {"id": id, "casa": casa, "nome": nome, "url": url}


# URL verificati con richiesta reale (feed RSS/Atom validi). Ufficiali: Nintendo (Giappone), PlayStation, Xbox, Steam e
# Square Enix (Lodestone di FFXIV). Epic, CD Projekt (feed fermo al 2019), Ubisoft, Capcom, Bandai Namco e Sega non hanno un
# feed ufficiale raggiungibile (403/404/429): per quelle case si usano i feed novita' Steam di un loro titolo.
SOURCES = [
    _s("nintendo-life", "Nintendo", "Nintendo Life", "https://www.nintendolife.com/feeds/news"),
    _s("nintendo-everything", "Nintendo", "Nintendo Everything", "https://www.nintendoeverything.com/feed/"),
    _s("nintendo-jp", "Nintendo", "Nintendo (Giappone, ufficiale)", "https://www.nintendo.co.jp/news/whatsnew.xml"),
    _s("nintendo-insider", "Nintendo", "Nintendo Insider", "https://www.nintendo-insider.com/feed"),
    _s("playstation-blog", "PlayStation", "PlayStation Blog", "https://blog.playstation.com/feed"),
    _s("xbox-wire", "Xbox", "Xbox Wire", "https://news.xbox.com/en-us/feed"),
    _s("steam-news", "Valve", "Steam News", "https://store.steampowered.com/feeds/news/"),
    _s("cdpr-cyberpunk", "CD Projekt", "Cyberpunk 2077 (Steam)", "https://store.steampowered.com/feeds/news/app/1091500/"),
    _s("ubisoft-ac", "Ubisoft", "Assassin's Creed Valhalla (Steam)", "https://store.steampowered.com/feeds/news/app/2208920/"),
    _s("capcom-mh", "Capcom", "Monster Hunter World (Steam)", "https://store.steampowered.com/feeds/news/app/582010/"),
    _s("bandai-elden", "Bandai Namco", "Elden Ring (Steam)", "https://store.steampowered.com/feeds/news/app/1245620/"),
    _s("squareenix-ffxiv", "Square Enix", "Final Fantasy XIV (Lodestone, ufficiale)", "https://eu.finalfantasyxiv.com/lodestone/news/news.xml"),
    _s("sega-sonic", "Sega", "Sonic Frontiers (Steam)", "https://store.steampowered.com/feeds/news/app/1237320/"),
    _s("gematsu", "Generale", "Gematsu", "https://www.gematsu.com/feed"),
    _s("siliconera", "Generale", "Siliconera", "https://www.siliconera.com/feed/"),
    _s("eurogamer", "Generale", "Eurogamer", "https://www.eurogamer.net/feed"),
    _s("gamesindustry", "Generale", "GamesIndustry.biz", "https://www.gamesindustry.biz/feed"),
    _s("retrododo", "Retro", "Retrododo", "https://retrododo.com/rss/"),
    _s("everyeye", "Italiano", "Everyeye.it", "https://www.everyeye.it/feed/feed_news_rss.asp"),
    _s("spaziogames", "Italiano", "SpazioGames", "https://www.spaziogames.it/feed"),
]

KEYWORDS = [  # ordine = priorita'
    ("patch", ("patch", "update", "hotfix", "aggiornamento", "changelog")),
    ("dlc", ("dlc", "expansion", "espansione", "season pass", "add-on")),
    ("annuncio", ("announce", "reveal", "trailer", "coming", "annunci", "svelat", "teaser", "unveil")),
    ("uscita", ("release", "out now", "launches", "disponibile", "uscita", "now available", "è uscito")),
]


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def classify(item: dict) -> str:
    t = (item.get("title") or "").lower()
    for kind, words in KEYWORDS:
        if any(w in t for w in words):
            return kind
    return "notizia"


# ---------------------------------------------------------------- parsing
def _ln(el) -> str:
    return el.tag.rsplit("}", 1)[-1].lower() if isinstance(el.tag, str) else ""


def _text(el, *names) -> str:
    for n in names:
        for c in el:
            if _ln(c) == n and (c.text or "").strip():
                return c.text.strip()
    return ""


def _date(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(h: str, n: int = 400) -> str:
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", h or "")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _image(e, raw_html: str) -> str:
    for c in e.iter():
        n, u = _ln(c), c.get("url") or ""
        if u and (n == "thumbnail" or n in ("content", "enclosure") and ("image" in (c.get("type") or "") or c.get("medium") == "image")):
            return u
        if n == "link" and c.get("rel") == "enclosure" and "image" in (c.get("type") or "") and c.get("href"):
            return c.get("href")
    m = re.search(r"""<img[^>]+src=["']([^"']+)""", html.unescape(raw_html or ""), re.I)
    return m.group(1) if m else ""


def parse_feed(xml_bytes: bytes, source: dict, log=print) -> list[dict]:
    """RSS 2.0 e Atom. Feed non valido -> [] (e una riga di log)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log(f"notizie: feed {source.get('id')} non valido: {e}")
        return []
    out = []
    for e in root.iter():
        if _ln(e) not in ("item", "entry"):
            continue
        link = _text(e, "link")
        if not link:  # Atom: <link href=...>
            ls = [c for c in e if _ln(c) == "link"]
            alt = next((x for x in ls if x.get("rel") in (None, "alternate")), ls[0] if ls else None)
            link = (alt.get("href") if alt is not None else "") or ""
        title = _clean(_text(e, "title"), 300)
        if not title:
            continue
        raw = _text(e, "encoded", "content", "description", "summary")
        short = _text(e, "description", "summary") or raw
        guid = _text(e, "guid", "id") or link or title
        item = {"id": hashlib.sha1(guid.encode()).hexdigest()[:16], "source": source.get("id", ""), "casa": source.get("casa", ""),
                "title": title, "link": link, "summary": _clean(short), "image": _image(e, raw or short),
                "published": _date(_text(e, "pubdate", "published", "updated", "date")),
                "tags": [(c.text or c.get("term") or "").strip() for c in e if _ln(c) == "category" and (c.text or c.get("term"))][:8]}
        item["kind"] = classify(item)
        out.append(item)
    return out


# ---------------------------------------------------------------- cache + rete
def _fetch(cache_dir: Path, src: dict, ttl: int, client, now: float, log=print) -> tuple[list[dict], dict]:
    """(items, stato). Usa la cache se fresca; su errore ripiega sull'ultimo corpo noto."""
    meta_p, body_p = cache_dir / f"{src['id']}.json", cache_dir / f"{src['id']}.xml"
    try:
        meta = json.loads(meta_p.read_text("utf-8"))
    except (OSError, ValueError):
        meta = {}
    body = body_p.read_bytes() if body_p.exists() else b""
    if now >= meta.get("next_allowed_at", 0) and (not body or now - meta.get("fetched_at", 0) >= max(ttl, MIN_TTL)):
        h = {"User-Agent": UA}
        if meta.get("etag") and body:
            h["If-None-Match"] = meta["etag"]
        if meta.get("last_modified") and body:
            h["If-Modified-Since"] = meta["last_modified"]
        try:
            r = client.get(src["url"], headers=h)
            if r.status_code == 304:
                meta.update(fetched_at=now, fails=0, error="")
            elif r.status_code == 200:
                body = r.content
                body_p.write_bytes(body)
                meta.update(fetched_at=now, fails=0, error="", etag=r.headers.get("etag", ""), last_modified=r.headers.get("last-modified", ""))
            else:
                raise httpx.HTTPError(f"HTTP {r.status_code}")
        except httpx.HTTPError as e:
            fails = meta.get("fails", 0) + 1
            meta.update(fails=fails, error=str(e)[:200] or type(e).__name__, next_allowed_at=now + min(BACKOFF_MAX, MIN_TTL * 2 ** (fails - 1)))
        try:
            meta_p.write_text(json.dumps(meta), "utf-8")
        except OSError as e:
            log(f"notizie: cache non scrivibile: {e}")
    items = parse_feed(body, src, log) if body else []
    err = meta.get("error", "") or ("" if items else "nessun dato")
    fa = meta.get("fetched_at")
    return items, {"id": src["id"], "casa": src["casa"], "nome": src["nome"], "ok": bool(items) and not err, "error": err,
                   "fetched_at": datetime.fromtimestamp(fa, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if fa else ""}


def collect(cache_dir: Path, sources: list[dict], ttl: int = TTL, log=print) -> tuple[list[dict], list[dict]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    with httpx.Client(timeout=10, follow_redirects=True) as client, ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda s: _fetch(cache_dir, s, ttl, client, now, log), sources))
    seen, items = set(), []
    for its, _ in res:
        for it in its:
            if it["id"] not in seen:
                seen.add(it["id"])
                items.append(it)
    items.sort(key=lambda i: i["published"], reverse=True)
    return items, [st for _, st in res]


def select(items: list[dict], casa: str = "", q: str = "", kind: str = "", limit: int = 50, before: str = "") -> list[dict]:
    qs = fold(q).split()
    out = []
    for i in items:
        if casa and i["casa"] != casa or kind and i["kind"] != kind or before and not (i["published"] and i["published"] < before):
            continue
        if qs:
            hay = fold(i["title"] + " " + i["summary"] + " " + " ".join(i["tags"]))
            if not all(w in hay for w in qs):
                continue
        out.append(i)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- impostazioni
def all_sources(settings: dict) -> list[dict]:
    off = set(settings.get("disabled_sources") or [])
    return [{**s, "custom": c, "enabled": s["id"] not in off}
            for c, lst in ((False, SOURCES), (True, settings.get("custom_sources") or [])) for s in lst]


def validate_settings(body: dict) -> dict:
    custom = []
    for c in body.get("custom_sources") or []:
        url, nome = str(c.get("url", "")).strip(), str(c.get("nome", "")).strip()[:60]
        if not re.match(r"https?://[^\s/]+", url, re.I):
            raise ValueError(f"URL non valido: {url[:80]}")
        if not nome:
            raise ValueError("nome mancante")
        cid = "c-" + hashlib.sha1(url.encode()).hexdigest()[:8]
        if cid not in {x["id"] for x in custom}:
            custom.append({"id": cid, "casa": str(c.get("casa", "")).strip()[:40] or "Personali", "nome": nome, "url": url})
    known = {s["id"] for s in SOURCES} | {c["id"] for c in custom}
    return {"disabled_sources": [i for i in dict.fromkeys(body.get("disabled_sources") or []) if i in known], "custom_sources": custom}


# ---------------------------------------------------------------- segui un gioco + rassegna
STEAM_NEWS = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid={}&count=10&maxlength=400"
STEAM_TTL = 3600
KIND_W = {"annuncio": 3, "uscita": 3, "patch": 2, "dlc": 2, "notizia": 1}  # peso nella rassegna
WEEK = 7 * 86400
DIGEST_KEEP = 8
FOLLOW_ITEMS = 20  # notizie per gioco nella risposta (il conteggio «unread» le considera tutte)


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def parse_steam_news(data: dict) -> list[dict]:
    """Risposta di GetNewsForApp/v2 ({"appnews": {"newsitems": [...]}}) -> item nel formato dei feed."""
    out = []
    for n in (data.get("appnews") or {}).get("newsitems") or []:
        title = _clean(str(n.get("title") or ""), 300)
        if not title:
            continue
        item = {"id": hashlib.sha1(str(n.get("gid") or n.get("url") or title).encode()).hexdigest()[:16],
                "source": "steam", "casa": "Steam", "title": title, "link": str(n.get("url") or ""),
                "summary": _clean(str(n.get("contents") or "")), "image": "",
                "published": iso(int(n["date"])) if n.get("date") else "", "tags": []}
        item["kind"] = classify(item)
        out.append(item)
    return out


def steam_news(cache: Path, appid: int, client, now: float, log=print) -> list[dict]:
    """Novita' Steam di un gioco: cache su disco di un'ora; su errore backoff come per i feed, con l'ultimo dato noto."""
    p = cache / f"steam-{appid}.json"
    try:
        meta = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        meta = {}
    if now >= meta.get("next_allowed_at", 0) and now - meta.get("fetched_at", 0) >= STEAM_TTL:
        try:
            r = client.get(STEAM_NEWS.format(int(appid)), headers={"User-Agent": UA})
            if r.status_code != 200:
                raise httpx.HTTPError(f"HTTP {r.status_code}")
            meta.update(fetched_at=now, fails=0, error="", items=parse_steam_news(r.json()))
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as e:
            fails = meta.get("fails", 0) + 1
            meta.update(fails=fails, error=str(e)[:200] or type(e).__name__,
                        next_allowed_at=now + min(BACKOFF_MAX, MIN_TTL * 2 ** (fails - 1)))
        try:
            p.write_text(json.dumps(meta), "utf-8")
        except OSError as e:
            log(f"notizie: cache non scrivibile: {e}")
    return meta.get("items") or []


def match_items(items: list[dict], title: str) -> list[dict]:
    """Gioco senza appid Steam: il suo titolo compare nel titolo della notizia (senza maiuscole e segni)."""
    t = fold(title)
    return [i for i in items if len(t) >= 3 and t in fold(i["title"])]


def mark_unread(items: list[dict], last_seen: str) -> list[dict]:
    return [{**i, "unread": bool(i["published"]) and i["published"] > last_seen} for i in items]


def digest(items: list[dict], titles: list[str], now: float) -> dict:
    """Ultimi 7 giorni: top 10 per tipo e recenza, max 3 per casa, novita' dei giochi in libreria."""
    start = iso(now - WEEK)
    week = [i for i in items if i["published"] and i["published"] >= start]
    ranked = sorted(week, key=lambda i: KIND_W.get(i["kind"], 1) + max(0.0, 1 - (now - _ts(i["published"])) / WEEK), reverse=True)
    per_casa: dict[str, list] = {}
    for i in ranked:
        lst = per_casa.setdefault(i["casa"], [])
        if len(lst) < 3:
            lst.append(i)
    tit = [t for t in (fold(x) for x in titles) if len(t) >= 3]
    mine = [i for i in ranked if any(t in fold(i["title"]) for t in tit)]
    tipi: dict[str, int] = {}
    for i in week:
        tipi[i["kind"]] = tipi.get(i["kind"], 0) + 1
    return {"week_start": start[:10], "week_end": iso(now)[:10], "top": ranked[:10], "per_casa": per_casa, "mine": mine,
            "counts": {"totale": len(week), "mine": len(mine), "per_tipo": tipi}}


def digest_path(cache: Path, now: float) -> Path:
    y, w, _ = datetime.fromtimestamp(now, timezone.utc).isocalendar()
    return cache / f"digest-{y}-{w:02d}.json"


def store_digest(cache: Path, now: float, d: dict) -> None:
    digest_path(cache, now).write_text(json.dumps(d, ensure_ascii=False), "utf-8")
    for old in sorted(cache.glob("digest-*.json"))[:-DIGEST_KEEP]:
        old.unlink(missing_ok=True)


def library_titles(cfg) -> list[str]:
    p = Path(cfg.cache) / "library.db"
    if not p.exists():
        return []
    db = sqlite3.connect(p)
    try:
        return [r[0] for r in db.execute("SELECT title FROM games WHERE is_primary=1 AND COALESCE(store,'') != 'online'") if r[0]]
    finally:
        db.close()


def register(gs):
    from pozzo.app.extensions import user_dir
    cache = user_dir(gs.cfg, "notizie-cache")

    @gs.route("feed")
    def feed(casa: str = "", q: str = "", kind: str = "", limit: int = 50, before: str = ""):
        items, st = collect(cache, [s for s in all_sources(gs.settings) if s["enabled"]], TTL, gs.log)
        return {"items": select(items, casa, q, kind, max(1, min(limit, 200)), before), "sources": st}

    @gs.route("sources")
    def sources():
        return {"sources": all_sources(gs.settings)}

    @gs.route("sources", methods=("POST",))
    def save_sources(body: dict):
        try:
            v = validate_settings(body)
        except ValueError as e:
            raise HTTPException(400, str(e))
        gs.save_settings(v)
        return {"ok": True, "sources": all_sources(gs.settings)}

    def enabled_items():
        return collect(cache, [s for s in all_sources(gs.settings) if s["enabled"]], TTL, gs.log)[0]

    def set_follows(fl):
        gs.save_settings({"follows": fl})
        return {"ok": True, "follows": fl}

    @gs.route("follows")
    def follows():
        return {"follows": gs.settings.get("follows") or []}

    @gs.route("follow", methods=("POST",))
    def follow(body: dict):
        gid, title = str(body.get("id") or "").strip(), str(body.get("title") or "").strip()[:200]
        if not gid or not title:
            raise HTTPException(400, "id e titolo richiesti")
        try:
            appid = int(body.get("steam_appid") or 0) or None
        except (TypeError, ValueError):
            raise HTTPException(400, "steam_appid non valido")
        fl = [f for f in gs.settings.get("follows") or [] if f["id"] != gid]
        fl.append({"id": gid, "title": title, "steam_appid": appid, "last_seen_ts": iso(time.time())})
        return set_follows(fl)

    @gs.route("unfollow", methods=("POST",))
    def unfollow(body: dict):
        gid = str(body.get("id") or "")
        return set_follows([f for f in gs.settings.get("follows") or [] if f["id"] != gid])

    @gs.route("follows/seen", methods=("POST",))
    def follows_seen(body: dict):
        gid = str(body.get("id") or "")
        fl = gs.settings.get("follows") or []
        hit = [f for f in fl if f["id"] == gid]
        if not hit:
            raise HTTPException(404, "gioco non seguito")
        hit[0]["last_seen_ts"] = iso(time.time())
        return set_follows(fl)

    @gs.route("follows/news")
    def follows_news():
        now, out, feed = time.time(), [], None
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            for f in gs.settings.get("follows") or []:
                if f.get("steam_appid"):
                    items = steam_news(cache, f["steam_appid"], client, now, gs.log)
                else:
                    feed = enabled_items() if feed is None else feed
                    items = match_items(feed, f["title"])
                items = mark_unread(items, f.get("last_seen_ts") or "")
                out.append({"id": f["id"], "title": f["title"], "unread": sum(i["unread"] for i in items),
                            "items": items[:FOLLOW_ITEMS]})
        return {"games": out}

    def build_digest(now: float) -> dict:
        return digest(enabled_items(), library_titles(gs.cfg), now)

    @gs.route("digest")
    def digest_get():
        now = time.time()
        p = digest_path(cache, now)
        if p.exists():
            return json.loads(p.read_text("utf-8"))
        d = build_digest(now)
        store_digest(cache, now, d)
        return d

    def rassegna_settimanale():
        now = time.time()
        if digest_path(cache, now).exists():
            return
        d = build_digest(now)
        store_digest(cache, now, d)
        from pozzo import notify
        notify.send(gs.cfg, f"Rassegna settimanale pronta: {d['counts']['totale']} novità", "Aprila dalla pagina Notizie.")

    gs.job("rassegna-settimanale", rassegna_settimanale, every=6 * 3600, run_at_start=True)
