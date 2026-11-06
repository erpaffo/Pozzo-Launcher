"""Motore ricette web: cataloghi multimediali da siti leciti e feed RSS/JSON.

Funzioni pure:
    parse_recipe(toml_text) -> dict   (ValueError se campi ignoti/mancanti o campo code/script)
    apply_recipe(recipe, html_o_json) -> [MediaItem-like]
    apply_detail(recipe, html_o_json, base_url="") -> dict
    fetch_url(url, recipe, cache_dir, ttl=1800, client=None, now=None, log=print) -> (bytes, dict)

Contratto fonte di media (Pozzo Media):
    list(kind, query) -> [MediaItem]
    detail(id) -> MediaItem
    play_target(id) -> {url, resume_pos}
    set_progress(id, pos, seen) -> {"ok": true}
    MediaItem = {id, kind, title, series?, season?, episode?, year?, duration?, poster?, backdrop?, overview?, source, resume_pos?, seen?}

Rotte (/plugin-api/ricette-web/...):
    GET  list?kind=&query=&recipe=&limit= -> [MediaItem]
    GET  detail?id=                       -> MediaItem
    GET  play_target?id=                  -> {"url", "resume_pos", "external"}
    POST set_progress                     <- {"id", "pos", "seen", "duration"?}
    POST external                         <- {"id"}  mpv/VLC se presenti, altrimenti il browser
    GET  kodi_addons                      -> {"addons": [...]}
    POST kodi_addons                      <- {"url"|"path"} installa, {"remove": id} rimuove
    GET  recipes                          -> {"recipes": [...]}
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
import time
import threading
import tomllib
import urllib.parse
import urllib.robotparser
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import soupsieve as sv
from bs4 import BeautifulSoup
from fastapi import Body, HTTPException

UA = "PozzoLauncher/1.0"
TTL = 30 * 60  # 30 minuti di cache predefinita
MIN_TTL = 15 * 60
BACKOFF_MAX = 6 * 3600
ROBOTS_TTL = 24 * 3600
RATE_LIMIT_DELAY = 0.5  # minimo intervallo per host in secondi

FORBIDDEN_WORDS = ("code", "script", "eval", "function", "handler", "exec")

ALLOWED_TOP_KEYS = {
    "name", "host", "type", "start_url", "list", "detail", "episodes", "pagination", "id",
}
REQUIRED_TOP_KEYS = ("name", "host", "type", "start_url", "list", "detail")

ALLOWED_LIST_KEYS = {"selector", "item", "title", "link", "cover"}
REQUIRED_LIST_KEYS = ("selector", "item", "title", "link")

ALLOWED_DETAIL_KEYS = {"title", "cover", "overview", "year", "duration", "stream_url"}
REQUIRED_DETAIL_KEYS = ("title",)

ALLOWED_EPISODES_KEYS = {"selector", "item", "title", "duration", "stream_url", "season", "episode"}
ALLOWED_PAGINATION_KEYS = {"next_url", "param", "increment", "limit"}

ITEM_KEYS = {
    "id", "kind", "title", "series", "season", "episode", "year", "duration",
    "poster", "backdrop", "overview", "source", "resume_pos", "seen", "album",
}
KINDS = ("film", "episodio", "brano")

# formati che il motore della finestra legge da solo: gli altri (.m3u8, embed) vanno al player esterno
DIRECT_STREAM_EXTS = (".mp4", ".webm", ".m4v", ".ogv", ".mp3", ".flac", ".ogg", ".m4a", ".opus", ".wav")
STREAM_RE = re.compile(r"""https?://[^\s"'<>\\]+?\.(?:m3u8|mp4|webm|m4v|ogv)(?=[?#"'\s<>]|$)""", re.I)
VIDEO_SRC_RE = re.compile(r"""<(?:video|source)[^>]+\bsrc\s*=\s*["']([^"']+)["']""", re.I)

_LAST_REQUEST: dict[str, float] = {}
_URL_MAP: dict[str, str] = {}
_STREAM_MAP: dict[str, str] = {}


# ---------------------------------------------------------------- validazione ricetta
def _check_forbidden(obj: object, path: str = "") -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(w in k_lower for w in FORBIDDEN_WORDS):
                raise ValueError(f"Campo vietato: '{k}' (nessun codice eseguibile consentito)")
            _check_forbidden(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _check_forbidden(item, f"{path}[{idx}]")


def parse_recipe(toml_text: str) -> dict:
    """Valida e converte il testo TOML di una ricetta.

    Solleva ValueError su campi ignoti, campi obbligatori mancanti o presenza di codice eseguibile.
    """
    if not isinstance(toml_text, str) or not toml_text.strip():
        raise ValueError("Ricetta vuota o non valida")
    try:
        data = tomllib.loads(toml_text)
    except Exception as e:
        raise ValueError(f"Errore di sintassi TOML: {e}") from e

    _check_forbidden(data)

    # Campi top-level
    for k in data:
        if k not in ALLOWED_TOP_KEYS:
            raise ValueError(f"Campo ignoto: '{k}'")
    for k in REQUIRED_TOP_KEYS:
        if k not in data or not str(data[k]).strip():
            raise ValueError(f"Campo obbligatorio mancante: '{k}'")

    if data["type"] not in ("html", "json", "rss"):
        raise ValueError(f"Tipo sorgente non valido: '{data['type']}', attesi: html, json, rss")

    if not re.match(r"^https?://[^\s]+$", str(data["start_url"]).strip()):
        raise ValueError(f"start_url non valido: '{data['start_url']}'")

    # Sezione [list]
    lst = data.get("list")
    if not isinstance(lst, dict):
        raise ValueError("Sezione [list] mancante o non valida")
    for k in lst:
        if k not in ALLOWED_LIST_KEYS:
            raise ValueError(f"Campo ignoto in [list]: '{k}'")
    for k in REQUIRED_LIST_KEYS:
        if k not in lst or not str(lst[k]).strip():
            raise ValueError(f"Campo obbligatorio mancante in [list]: '{k}'")

    # Sezione [detail]
    det = data.get("detail")
    if not isinstance(det, dict):
        raise ValueError("Sezione [detail] mancante o non valida")
    for k in det:
        if k not in ALLOWED_DETAIL_KEYS:
            raise ValueError(f"Campo ignoto in [detail]: '{k}'")
    for k in REQUIRED_DETAIL_KEYS:
        if k not in det or not str(det[k]).strip():
            raise ValueError(f"Campo obbligatorio mancante in [detail]: '{k}'")

    # Sezione [episodes]
    if "episodes" in data:
        ep = data["episodes"]
        if not isinstance(ep, dict):
            raise ValueError("Sezione [episodes] non valida")
        for k in ep:
            if k not in ALLOWED_EPISODES_KEYS:
                raise ValueError(f"Campo ignoto in [episodes]: '{k}'")

    # Sezione [pagination]
    if "pagination" in data:
        pg = data["pagination"]
        if not isinstance(pg, dict):
            raise ValueError("Sezione [pagination] non valida")
        for k in pg:
            if k not in ALLOWED_PAGINATION_KEYS:
                raise ValueError(f"Campo ignoto in [pagination]: '{k}'")
        if "increment" in pg and not isinstance(pg["increment"], int):
            raise ValueError("pagination.increment deve essere un intero")
        if "limit" in pg and not isinstance(pg["limit"], int):
            raise ValueError("pagination.limit deve essere un intero")

    if not data.get("id"):
        data["id"] = re.sub(r"[^a-z0-9]+", "-", data["name"].lower()).strip("-")
    return data


# ---------------------------------------------------------------- estrazione e parser
def _extract_year(s: str | None) -> int | None:
    if not s:
        return None
    m = re.findall(r"\b((?:18|19|20)\d{2})\b", str(s))
    return int(m[-1]) if m else None


def _parse_duration(val: str | None) -> float | None:
    if not val:
        return None
    val = str(val).strip()
    try:
        return round(float(val), 1)
    except ValueError:
        pass
    parts = val.split(":")
    try:
        if len(parts) == 2:
            return round(float(int(parts[0]) * 60 + int(parts[1])), 1)
        if len(parts) == 3:
            return round(float(int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])), 1)
    except ValueError:
        pass
    m = re.search(r"(\d+)\s*(?:min|m\b)", val, re.I)
    if m:
        return round(float(int(m.group(1)) * 60), 1)
    return None


def _extract_html_value(el, sel_pattern: str) -> str:
    if not el or not sel_pattern:
        return ""
    sel_pattern = sel_pattern.strip()
    if "@" in sel_pattern:
        css_sel, attr = sel_pattern.split("@", 1)
        css_sel, attr = css_sel.strip(), attr.strip()
    else:
        css_sel, attr = sel_pattern, None

    target = el
    if css_sel:
        found = el.select_one(css_sel)
        if found is not None:
            target = found
        elif hasattr(sv, "match") and sv.match(css_sel, el):
            target = el
        else:
            return ""

    if attr:
        val = target.get(attr)
        if isinstance(val, list):
            return " ".join(val).strip()
        return str(val or "").strip()
    return target.get_text(separator=" ", strip=True)


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower() if tag else ""


def _find_xml_val(elem, path: str) -> str:
    if elem is None or not path:
        return ""
    if "@" in path:
        elem_path, attr = path.split("@", 1)
        elem_path, attr = elem_path.strip(), attr.strip()
    else:
        elem_path, attr = path.strip(), None

    parts = [p.strip() for p in elem_path.split(">")] if elem_path else []
    curr = elem
    for p in parts:
        if not p:
            continue
        target_name = p.split(":")[-1].lower()
        found = None
        for child in curr.iter():
            if child is curr:
                continue
            if _ln(child.tag) == target_name:
                found = child
                break
        if found is None:
            return ""
        curr = found

    if attr:
        for k, v in curr.attrib.items():
            if _ln(k) == attr.lower() or k == attr:
                return v
        return ""
    return (curr.text or "").strip()


def _mini_addon_xml(xml_text: str) -> dict:
    """addon.xml letto senza kodi_bridge: solo i campi che servono all'elenco."""
    root = ET.fromstring(xml_text)
    return {"id": root.get("id", ""), "name": root.get("name", ""), "version": root.get("version", ""),
            "summary": _find_xml_val(root, "summary")}


def _extract_json_path(data, path: str):
    if not path:
        return data
    parts = path.strip().split(".")
    curr = data
    for part in parts:
        if not part:
            continue
        m = re.match(r"^([^\[\]]+)\[(\d+)\]$", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if isinstance(curr, dict) and key in curr:
                curr = curr[key]
            else:
                return None
            if isinstance(curr, (list, tuple)) and 0 <= idx < len(curr):
                curr = curr[idx]
            else:
                return None
        elif isinstance(curr, dict):
            if part in curr:
                curr = curr[part]
            else:
                return None
        else:
            return None
    return curr


def is_direct_stream(url: str) -> bool:
    """True se l'URL è un file audio/video che il browser riproduce da solo (HLS ed embed no)."""
    path = urllib.parse.urlparse(str(url or "")).path.lower().rstrip("/")
    return path.endswith(DIRECT_STREAM_EXTS)


def _extract_stream_url(soup, text: str, selector: str) -> str:
    """stream_url da selettore CSS oppure da «regex:<espressione>» sul testo grezzo della pagina."""
    selector = (selector or "").strip()
    if not selector.lower().startswith("regex:"):
        return _extract_html_value(soup, selector)
    try:
        m = re.search(selector[len("regex:"):].strip(), text, re.S)
    except re.error:
        return ""
    if not m:
        return ""
    return (m.group(1) if m.groups() else m.group(0)).strip()


def _fallback_stream_urls(text: str, base_url: str = "") -> list[str]:
    """Flussi trovati senza kodi_bridge: <video>/<source> e URL .m3u8/.mp4 negli script."""
    found = VIDEO_SRC_RE.findall(text) + STREAM_RE.findall(text)
    out: list[str] = []
    for url in found:
        url = urllib.parse.urljoin(base_url, url.strip())
        low = url.lower()
        if low.endswith((".webmanifest", ".xml", ".json", ".html", ".htm")) or "manifest." in low:
            continue
        if url.startswith(("http://", "https://")) and url not in out:
            out.append(url)
    return out


_KODI_BRIDGE = None


def kodi_bridge_module():
    """kodi_bridge.py accanto a questo file; None se non c'è (build parallelo) o non si carica."""
    global _KODI_BRIDGE
    if _KODI_BRIDGE is not None:
        return _KODI_BRIDGE
    path = Path(__file__).with_name("kodi_bridge.py")
    if not path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("ricette_kodi_bridge", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        return None
    _KODI_BRIDGE = mod
    return mod


def extract_streams(text: str, base_url: str = "") -> list[str]:
    """URL dei flussi presenti nella pagina: kodi_bridge se c'è, altrimenti la regex locale."""
    bridge = kodi_bridge_module()
    urls: list[str] = []
    if bridge is not None and hasattr(bridge, "extract_stream_urls"):
        try:
            found = bridge.extract_stream_urls(text, base_url)
        except Exception:
            found = []
        urls = [str(f.get("url", "")) if isinstance(f, dict) else str(f) for f in found]
        urls = [urllib.parse.urljoin(base_url, u) for u in urls if u]
    return urls or _fallback_stream_urls(text, base_url)


def apply_recipe(recipe: dict, html_o_json: str | bytes | dict | list) -> list[dict]:
    """Applica i selettori di lista della ricetta al contenuto HTML/RSS/JSON.

    Restituisce una lista di MediaItem conformi al contratto Pozzo Media.
    """
    rtype = recipe.get("type", "html")
    list_cfg = recipe.get("list") or {}
    base_url = recipe.get("start_url", "")
    items: list[dict] = []

    if rtype == "html":
        text = html_o_json.decode("utf-8", "ignore") if isinstance(html_o_json, bytes) else str(html_o_json)
        soup = BeautifulSoup(text, "html.parser")
        selector = list_cfg.get("selector", "").strip()
        item_sel = list_cfg.get("item", "").strip()

        if selector and item_sel:
            if selector == item_sel:
                raw_items = soup.select(item_sel)
            else:
                containers = soup.select(selector)
                if containers:
                    raw_items = []
                    for c in containers:
                        raw_items.extend(c.select(item_sel))
                else:
                    raw_items = soup.select(item_sel)
        elif item_sel:
            raw_items = soup.select(item_sel)
        elif selector:
            raw_items = soup.select(selector)
        else:
            raw_items = []

        for el in raw_items:
            title = _extract_html_value(el, list_cfg.get("title", ""))
            link = _extract_html_value(el, list_cfg.get("link", ""))
            cover = _extract_html_value(el, list_cfg.get("cover", ""))
            if not title and not link:
                continue
            if link and not link.startswith(("http://", "https://")):
                link = urllib.parse.urljoin(base_url, link)
            if cover and not cover.startswith(("http://", "https://")):
                cover = urllib.parse.urljoin(base_url, cover)

            item_id = hashlib.sha1(f"{recipe.get('host', '')}:{link or title}".encode()).hexdigest()[:16]
            if link:
                _URL_MAP[item_id] = link

            year = _extract_year(title)
            it: dict = {
                "id": item_id,
                "kind": "film",
                "title": title or "Senza titolo",
                "source": "ricette-web",
                "seen": False,
                "resume_pos": 0.0,
            }
            if year:
                it["year"] = year
            if cover:
                it["poster"] = cover
                it["backdrop"] = cover
            items.append(it)

    elif rtype == "rss":
        text = html_o_json.decode("utf-8", "ignore") if isinstance(html_o_json, bytes) else str(html_o_json)
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            root = ET.Element("rss")

        item_tag = list_cfg.get("item", "item").split(":")[-1].lower()
        raw_items = [e for e in root.iter() if _ln(e.tag) == item_tag]
        for el in raw_items:
            title = _find_xml_val(el, list_cfg.get("title", "title"))
            link = _find_xml_val(el, list_cfg.get("link", "link"))
            cover = _find_xml_val(el, list_cfg.get("cover", ""))
            if not title and not link:
                continue
            if link and not link.startswith(("http://", "https://")):
                link = urllib.parse.urljoin(base_url, link)
            if cover and not cover.startswith(("http://", "https://")):
                cover = urllib.parse.urljoin(base_url, cover)

            stream_url = _find_xml_val(el, "enclosure@url")
            overview = _find_xml_val(el, "description")
            pub_date = _find_xml_val(el, "pubDate")
            season_str = _find_xml_val(el, "itunes:season")
            ep_str = _find_xml_val(el, "itunes:episode")
            dur_str = _find_xml_val(el, "itunes:duration")

            item_id = hashlib.sha1(f"{recipe.get('host', '')}:{link or title}".encode()).hexdigest()[:16]
            target_url = stream_url or link
            if target_url:
                _URL_MAP[item_id] = target_url
            if stream_url:
                _STREAM_MAP[item_id] = stream_url

            it = {
                "id": item_id,
                "kind": "brano",
                "title": title or "Senza titolo",
                "source": "ricette-web",
                "seen": False,
                "resume_pos": 0.0,
            }
            if season_str.isdigit():
                it["season"] = int(season_str)
            if ep_str.isdigit():
                it["episode"] = int(ep_str)
            y = _extract_year(pub_date) or _extract_year(title)
            if y:
                it["year"] = y
            dur = _parse_duration(dur_str)
            if dur:
                it["duration"] = dur
            if cover:
                it["poster"] = cover
                it["backdrop"] = cover
            if overview:
                it["overview"] = overview[:600]
            items.append(it)

    elif rtype == "json":
        data = json.loads(html_o_json) if isinstance(html_o_json, (str, bytes)) else html_o_json
        raw_items = _extract_json_path(data, list_cfg.get("selector", ""))
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        elif not isinstance(raw_items, list):
            raw_items = []

        for el in raw_items:
            title = str(_extract_json_path(el, list_cfg.get("title", "")) or "")
            link = str(_extract_json_path(el, list_cfg.get("link", "")) or "")
            cover = str(_extract_json_path(el, list_cfg.get("cover", "")) or "")
            if not title and not link:
                continue
            if link and not link.startswith(("http://", "https://")):
                link = urllib.parse.urljoin(base_url, link)
            if cover and not cover.startswith(("http://", "https://")):
                cover = urllib.parse.urljoin(base_url, cover)

            item_id = hashlib.sha1(f"{recipe.get('host', '')}:{link or title}".encode()).hexdigest()[:16]
            if link:
                _URL_MAP[item_id] = link

            year = _extract_year(title)
            it = {
                "id": item_id,
                "kind": "film",
                "title": title or "Senza titolo",
                "source": "ricette-web",
                "seen": False,
                "resume_pos": 0.0,
            }
            if year:
                it["year"] = year
            if cover:
                it["poster"] = cover
                it["backdrop"] = cover
            items.append(it)

    return items


def apply_detail(recipe: dict, html_o_json: str | bytes | dict, base_url: str = "") -> dict:
    """Applica i selettori di dettaglio ed episodi al contenuto di una pagina di dettaglio."""
    rtype = recipe.get("type", "html")
    det_cfg = recipe.get("detail") or {}
    ep_cfg = recipe.get("episodes") or {}
    base_url = base_url or recipe.get("start_url", "")
    out: dict = {"episodes": []}

    if rtype == "html":
        text = html_o_json.decode("utf-8", "ignore") if isinstance(html_o_json, bytes) else str(html_o_json)
        soup = BeautifulSoup(text, "html.parser")

        title = _extract_html_value(soup, det_cfg.get("title", ""))
        cover = _extract_html_value(soup, det_cfg.get("cover", ""))
        overview = _extract_html_value(soup, det_cfg.get("overview", ""))
        year_str = _extract_html_value(soup, det_cfg.get("year", ""))
        dur_str = _extract_html_value(soup, det_cfg.get("duration", ""))
        stream_url = _extract_stream_url(soup, text, det_cfg.get("stream_url", ""))
        if not stream_url:  # flusso nascosto negli script JS: estrazione automatica
            found = extract_streams(text, base_url)
            stream_url = found[0] if found else ""

        if cover and not cover.startswith(("http://", "https://")):
            cover = urllib.parse.urljoin(base_url, cover)
        if stream_url and not stream_url.startswith(("http://", "https://")):
            stream_url = urllib.parse.urljoin(base_url, stream_url)

        out["title"] = title or None
        out["poster"] = cover or None
        out["backdrop"] = cover or None
        out["overview"] = overview or None
        out["year"] = _extract_year(year_str) or _extract_year(title)
        out["duration"] = _parse_duration(dur_str)
        out["stream_url"] = stream_url or None

        if ep_cfg and ep_cfg.get("item"):
            selector = ep_cfg.get("selector", "").strip()
            item_sel = ep_cfg.get("item", "").strip()
            if selector and item_sel and selector != item_sel:
                c = soup.select_one(selector)
                raw_eps = c.select(item_sel) if c else soup.select(item_sel)
            else:
                raw_eps = soup.select(item_sel)

            for ep_el in raw_eps:
                ep_title = _extract_html_value(ep_el, ep_cfg.get("title", ""))
                ep_dur = _extract_html_value(ep_el, ep_cfg.get("duration", ""))
                ep_stream = _extract_html_value(ep_el, ep_cfg.get("stream_url", ""))
                ep_s = _extract_html_value(ep_el, ep_cfg.get("season", ""))
                ep_e = _extract_html_value(ep_el, ep_cfg.get("episode", ""))

                if ep_stream and not ep_stream.startswith(("http://", "https://")):
                    ep_stream = urllib.parse.urljoin(base_url, ep_stream)

                ep_id = hashlib.sha1(f"{recipe.get('host', '')}:{ep_stream or ep_title}".encode()).hexdigest()[:16]
                if ep_stream:
                    _STREAM_MAP[ep_id] = ep_stream
                    _URL_MAP[ep_id] = ep_stream

                ep_item: dict = {
                    "id": ep_id,
                    "kind": "episodio",
                    "title": ep_title or "Episodio",
                    "series": title or None,
                    "source": "ricette-web",
                    "seen": False,
                    "resume_pos": 0.0,
                }
                if ep_stream:
                    ep_item["stream_url"] = ep_stream
                if ep_s.isdigit():
                    ep_item["season"] = int(ep_s)
                if ep_e.isdigit():
                    ep_item["episode"] = int(ep_e)
                dur = _parse_duration(ep_dur)
                if dur:
                    ep_item["duration"] = dur
                if cover:
                    ep_item["poster"] = cover
                    ep_item["backdrop"] = cover
                out["episodes"].append(ep_item)

    return out


# ---------------------------------------------------------------- rete, cache e robots.txt
def _can_fetch_robots(cache_dir: Path, host: str, url: str, client, log=print) -> bool:
    clean_host = re.sub(r"[^a-zA-Z0-9_.-]", "_", host)
    robots_file = cache_dir / f"robots_{clean_host}.txt"
    now = time.time()
    text = ""
    if robots_file.exists() and (now - robots_file.stat().st_mtime) < ROBOTS_TTL:
        try:
            text = robots_file.read_text("utf-8")
        except OSError:
            pass

    if not text:
        robots_url = f"https://{host}/robots.txt"
        try:
            r = client.get(robots_url, headers={"User-Agent": UA})
            if r.status_code == 200:
                text = r.text if hasattr(r, "text") else r.content.decode("utf-8", "ignore")
                robots_file.write_text(text, "utf-8")
            elif r.status_code in (401, 403):
                text = "User-agent: *\nDisallow: /"
                robots_file.write_text(text, "utf-8")
            else:
                text = "User-agent: *\nAllow: /"
                robots_file.write_text(text, "utf-8")
        except Exception as e:
            log(f"ricette-web: robots.txt non disponibile per {host}: {e}")
            return True

    rp = urllib.robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    return rp.can_fetch(UA, url)


def _wait_rate_limit(host: str) -> None:
    now = time.time()
    last = _LAST_REQUEST.get(host, 0.0)
    delta = now - last
    if delta < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - delta)
    _LAST_REQUEST[host] = time.time()


def fetch_url(url: str, recipe: dict, cache_dir: Path, ttl: int = TTL,
              client: httpx.Client | None = None, now: float | None = None,
              log=print) -> tuple[bytes, dict]:
    """Scarica un URL applicando isolamento di rete, robots.txt, limite richieste, cache su disco ed ETag."""
    now = time.time() if now is None else now
    cache_dir.mkdir(parents=True, exist_ok=True)

    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    allowed_host = recipe.get("host", "").lower().split(":")[0]
    if host != allowed_host and not host.endswith("." + allowed_host):
        raise ValueError(f"Host '{host}' non consentito dalla ricetta '{recipe.get('name')}' (atteso: {allowed_host})")

    url_hash = hashlib.sha1(url.encode()).hexdigest()[:16]
    meta_p = cache_dir / f"{url_hash}.json"
    body_p = cache_dir / f"{url_hash}.bin"

    try:
        meta = json.loads(meta_p.read_text("utf-8"))
    except (OSError, ValueError):
        meta = {}
    body = body_p.read_bytes() if body_p.exists() else b""

    # Backoff attivo: usa la versione cached se presente
    if now < meta.get("next_allowed_at", 0):
        return body, meta

    # Cache fresca: riusa senza fare richieste
    if body and (now - meta.get("fetched_at", 0) < max(ttl, MIN_TTL)):
        return body, meta

    def _perform_fetch(c) -> tuple[bytes, dict]:
        nonlocal body, meta
        if not _can_fetch_robots(cache_dir, allowed_host, url, c, log):
            log(f"ricette-web: robots.txt nega l'accesso a {url}")
            if body:
                return body, meta
            raise PermissionError(f"robots.txt vieta l'accesso a {url}")

        _wait_rate_limit(allowed_host)
        headers = {"User-Agent": UA}
        if meta.get("etag") and body:
            headers["If-None-Match"] = meta["etag"]
        if meta.get("last_modified") and body:
            headers["If-Modified-Since"] = meta["last_modified"]

        try:
            r = c.get(url, headers=headers)
            if r.status_code == 304:
                meta.update(fetched_at=now, fails=0, error="")
            elif r.status_code == 200:
                body = r.content
                body_p.write_bytes(body)
                etag = r.headers.get("etag", "")
                lm = r.headers.get("last-modified", "")
                meta.update(fetched_at=now, fails=0, error="", etag=etag, last_modified=lm)
            else:
                raise httpx.HTTPError(f"HTTP {r.status_code}")
        except Exception as e:
            fails = meta.get("fails", 0) + 1
            meta.update(fails=fails, error=str(e)[:200] or type(e).__name__,
                        next_allowed_at=now + min(BACKOFF_MAX, MIN_TTL * 2 ** (fails - 1)))
            if not body:
                raise
        try:
            meta_p.write_text(json.dumps(meta), "utf-8")
        except OSError as e:
            log(f"ricette-web: cache non scrivibile: {e}")
        return body, meta

    if client is not None:
        return _perform_fetch(client)
    with httpx.Client(timeout=15.0, follow_redirects=True) as new_client:
        return _perform_fetch(new_client)


# ---------------------------------------------------------------- database e contratto
def _db_init(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                recipe_id TEXT,
                kind TEXT,
                title TEXT,
                series TEXT,
                season INT,
                episode INT,
                year INT,
                duration REAL,
                poster TEXT,
                backdrop TEXT,
                overview TEXT,
                genre TEXT,
                url TEXT,
                stream_url TEXT,
                source TEXT DEFAULT 'ricette-web',
                resume_pos REAL DEFAULT 0.0,
                seen INT DEFAULT 0,
                updated REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                parent_id TEXT,
                recipe_id TEXT,
                title TEXT,
                series TEXT,
                season INT,
                episode INT,
                duration REAL,
                stream_url TEXT,
                url TEXT,
                poster TEXT,
                genre TEXT,
                source TEXT DEFAULT 'ricette-web',
                resume_pos REAL DEFAULT 0.0,
                seen INT DEFAULT 0,
                updated REAL
            )
        """)
        for tbl in ("items", "episodes"):
            try:
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN genre TEXT")
            except sqlite3.OperationalError:
                pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_parent ON episodes(parent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_recipe ON items(recipe_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_source ON items(source)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_title ON items(title)")
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        for tbl in ("items", "episodes"):
            conn.execute(
                f"UPDATE {tbl} SET stream_url='' WHERE stream_url LIKE '%a-ads.com%' OR stream_url LIKE '%size=300x250%' OR stream_url LIKE '%exoclick%' OR stream_url LIKE '%popads%'"
            )
        conn.execute(
            "DELETE FROM items WHERE (recipe_id LIKE 's4me:%' OR source='stream4me') AND (LOWER(TRIM(title)) IN ('dub', 'dub movie', 'dub ova', 'sub', 'ita', 'sub ita', 'anime casuale', 'telegram', 'instagram', 'sfondi scaricabili', 'aggiornamenti al sito') OR url LIKE '%animeunity.so%' OR url LIKE '%animeunity.tv%')"
        )
        conn.execute(
            "DELETE FROM episodes WHERE rowid NOT IN (SELECT MIN(rowid) FROM episodes GROUP BY parent_id, COALESCE(season, 1), COALESCE(episode, 0), CASE WHEN episode IS NULL THEN title ELSE '' END)"
        )
        conn.execute(
            "UPDATE items SET genre='Anime' WHERE (recipe_id LIKE '%animeunity%' OR recipe_id LIKE '%animeworld%' OR url LIKE '%animeunity%' OR url LIKE '%animeworld%') AND (genre IS NULL OR genre != 'Anime')"
        )
        conn.execute(
            "UPDATE items SET genre=CASE WHEN (series IS NOT NULL AND series != '') OR kind='episodio' THEN 'Serie TV' ELSE 'Film' END WHERE (recipe_id LIKE '%streamingcommunity%' OR recipe_id LIKE '%altadefinizione%' OR url LIKE '%streamingcommunity%' OR url LIKE '%altadefinizione%') AND (genre IS NULL OR genre='Anime')"
        )
        conn.commit()
    finally:
        conn.close()


def to_item(r: dict | sqlite3.Row) -> dict:
    """Trasforma un record del DB o un dizionario in un MediaItem conforme alle chiavi del contratto."""
    d = dict(r)
    it: dict = {
        "id": str(d["id"]),
        "kind": str(d.get("kind") or "episodio"),
        "title": str(d["title"]),
        "source": "ricette-web",
        "seen": bool(d.get("seen", 0)),
        "resume_pos": round(float(d.get("resume_pos") or 0.0), 1),
    }
    if d.get("series"):
        it["series"] = str(d["series"])
    for key in ("season", "episode", "year"):
        if d.get(key) is not None:
            it[key] = int(d[key])
    if d.get("duration"):
        it["duration"] = round(float(d["duration"]), 1)
    if d.get("poster"):
        it["poster"] = str(d["poster"])
    if d.get("backdrop"):
        it["backdrop"] = str(d["backdrop"])
    overview = str(d.get("overview") or "")
    genre = str(d.get("genre") or "")
    if genre.lower() == "anime" and "anime" not in overview.lower():
        overview = f"Anime · {overview}" if overview else "Anime"
    if overview:
        it["overview"] = overview
    if genre:
        it["genre"] = genre
    return it


def load_recipes(ext_dir: Path | None = None) -> list[dict]:
    """Carica tutte le ricette .toml presenti nella cartella dell'estensione."""
    if ext_dir is None:
        ext_dir = Path(__file__).parent
    recipes = []
    for p in sorted(ext_dir.glob("*.toml")):
        if p.name == "plugin.toml":
            continue
        try:
            recipe = parse_recipe(p.read_text("utf-8"))
            recipes.append(recipe)
        except Exception:
            pass
    return recipes


# ---------------------------------------------------------------- registrazione estensione
def register(gs) -> None:
    try:
        from pozzo.app.extensions import user_dir
        cache = user_dir(gs.cfg, "ricette-web-cache")
    except ImportError:
        base = gs.cfg.config_path.parent if getattr(gs.cfg, "config_path", None) else Path.cwd()
        cache = base / "ricette-web-cache"
        cache.mkdir(parents=True, exist_ok=True)
    db_path = cache / "ricette.db"
    _db_init(db_path)
    addons_root = cache / "kodi-addons"

    recipes = load_recipes(Path(__file__).parent)
    recipes_by_id = {r["id"]: r for r in recipes}

    # Registra player integrato ed esterno
    try:
        gs.add_player({"id": "integrato", "label": "Lettore integrato", "mode": "integrato"})
        gs.add_player({"id": "esterno", "label": "Lettore esterno", "mode": "esterno"})
    except Exception:
        pass

    # Registra scraper se supportato dall'API host
    for r in recipes:
        try:
            gs.add_scraper(r)
        except Exception:
            pass

    def sync_catalog(log=gs.log) -> None:
        """Sincronizza le ricette con il database locale."""
        for r in recipes:
            try:
                body, _ = fetch_url(r["start_url"], r, cache, ttl=TTL, log=log)
                items = apply_recipe(r, body)
                conn = sqlite3.connect(db_path)
                try:
                    for it in items:
                        link = _URL_MAP.get(it["id"], "")
                        stream_url = _STREAM_MAP.get(it["id"], "")
                        conn.execute("""
                            INSERT INTO items (id, recipe_id, kind, title, series, season, episode, year, duration, poster, backdrop, overview, url, stream_url, source, updated)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ricette-web', ?)
                            ON CONFLICT(id) DO UPDATE SET
                                title=excluded.title,
                                poster=COALESCE(excluded.poster, items.poster),
                                year=COALESCE(excluded.year, items.year),
                                updated=excluded.updated
                        """, (
                            it["id"], r["id"], it["kind"], it["title"], it.get("series"),
                            it.get("season"), it.get("episode"), it.get("year"), it.get("duration"),
                            it.get("poster"), it.get("backdrop"), it.get("overview"),
                            link, stream_url, time.time(),
                        ))
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                log(f"ricette-web: errore scansione catalogo '{r.get('name')}': {e}")

    @gs.route("list")
    def media_list(kind: str = "", query: str = "", q: str = "", recipe: str = "", limit: int = 200, offset: int = 0):
        kind = kind.strip() if kind in KINDS else ""
        term = (query or q or "").strip()[:200]
        _auto_refresh()  # in background: la risposta legge solo il DB locale
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            sql = "SELECT * FROM items"
            where, args = ["recipe_id != 'stream4me'"], []  # schede-canale del catalogo Kodi, non titoli
            active = _active_s4me_ids()
            if active is not None:
                where.append("(recipe_id NOT LIKE 's4me:%' OR substr(recipe_id, 6) IN (" + ",".join("?" * len(active)) + "))")
                args.extend(sorted(active))
            if kind:
                where.append("kind=?")
                args.append(kind)
            if recipe:
                where.append("(recipe_id=? OR source=?)")
                args.extend([recipe, recipe])
            if term:
                where.append("(title LIKE ? ESCAPE '\\' OR series LIKE ? ESCAPE '\\' OR overview LIKE ? ESCAPE '\\')")
                like = "%" + re.sub(r"([%_\\])", r"\\\1", term) + "%"
                args.extend([like, like, like])
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY CASE WHEN recipe_id='stream4me:pinned' THEN 0 ELSE 1 END, kind, title LIMIT ? OFFSET ?"
            args.extend([max(1, min(limit, 1000)), max(0, offset)])
            rows = conn.execute(sql, args).fetchall()
            # lo stesso titolo da più provider streaming: tiene quello con locandina
            best: dict[tuple, sqlite3.Row] = {}
            out_rows = []
            for r in rows:
                if r["source"] != "stream4me":
                    out_rows.append(r)
                    continue
                key = (r["kind"], re.sub(r"\s*\(ita\)\s*$", "", (r["title"] or "").lower()).strip())
                cur = best.get(key)
                if cur is None:
                    best[key] = r
                    out_rows.append(r)
                elif r["poster"] and not cur["poster"]:
                    out_rows[out_rows.index(cur)] = r
                    best[key] = r
            return [to_item(r) for r in out_rows]
        finally:
            conn.close()

    @gs.route("detail")
    def media_detail(id: str = ""):
        item_id = str(id or "").strip()
        if not item_id:
            raise HTTPException(400, "id mancante")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM items WHERE series=? OR title=? ORDER BY CASE WHEN recipe_id='stream4me:pinned' THEN 0 ELSE 1 END LIMIT 1",
                    (item_id, item_id),
                ).fetchone()
            if row is None:
                ep = conn.execute("SELECT * FROM episodes WHERE id=?", (item_id,)).fetchone()
                if ep is not None:
                    return to_item(ep)
                raise HTTPException(404, "elemento non trovato")

            item = dict(row)
            item_id = str(item["id"])
            rec_id = str(item.get("recipe_id") or "")
            rec = recipes_by_id.get(rec_id)
            # Se ha pagina di dettaglio da esplorare
            if rec and rec.get("detail") and item.get("url"):
                if not item.get("overview") or not item.get("stream_url"):
                    try:
                        body, _ = fetch_url(item["url"], rec, cache, ttl=TTL, log=gs.log)
                        det_info = apply_detail(rec, body, item["url"])
                        if det_info.get("overview"):
                            item["overview"] = det_info["overview"]
                        if det_info.get("stream_url"):
                            item["stream_url"] = det_info["stream_url"]
                        if det_info.get("duration") and not item.get("duration"):
                            item["duration"] = det_info["duration"]
                        if det_info.get("year") and not item.get("year"):
                            item["year"] = det_info["year"]
                        if det_info.get("poster") and not item.get("poster"):
                            item["poster"] = det_info["poster"]
                        conn.execute("""
                            UPDATE items SET overview=?, stream_url=?, duration=?, year=?, poster=?, updated=? WHERE id=?
                        """, (
                            item["overview"], item["stream_url"], item["duration"],
                            item["year"], item["poster"], time.time(), item_id,
                        ))
                        for ep in det_info.get("episodes") or []:
                            conn.execute("""
                                INSERT OR IGNORE INTO episodes (id, parent_id, recipe_id, title, series, season, episode, duration, stream_url, url, poster, source, updated)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ricette-web', ?)
                            """, (
                                ep["id"], item_id, rec["id"], ep["title"],
                                ep.get("series") or item["title"], ep.get("season"),
                                ep.get("episode"), ep.get("duration"), ep.get("stream_url"),
                                ep.get("stream_url"), ep.get("poster"), time.time(),
                            ))
                        conn.commit()
                    except Exception as e:
                        gs.log(f"ricette-web: errore recupero dettaglio per {item_id}: {e}")
            elif (rec_id.startswith("s4me:") or rec_id.startswith("stream4me") or item_id.startswith(("s4me:", "stream4me:")) or item.get("source") == "stream4me") and str(item.get("url") or "").startswith(("http://", "https://")):
                has_eps = conn.execute("SELECT 1 FROM episodes WHERE parent_id=? LIMIT 1", (item_id,)).fetchone()
                if not has_eps:
                    bridge = kodi_bridge_module()
                    try:
                        target_u = str(item["url"])
                        if bridge is not None and hasattr(bridge, "_normalize_provider_host"):
                            target_u = bridge._normalize_provider_host(target_u)
                        resp = httpx.get(target_u, headers={"User-Agent": UA}, timeout=10.0, follow_redirects=True)
                        if resp.status_code == 200 and bridge is not None:
                            ch_id = rec_id.split(":", 1)[1] if rec_id.startswith("s4me:") else (item_id.split(":")[1] if item_id.startswith("s4me:") and item_id.count(":") >= 2 else "")
                            series_name = str(item.get("series") or item["title"])
                            if hasattr(bridge, "scrape_channel_episodes"):
                                eps = bridge.scrape_channel_episodes(
                                    resp.text, target_u, series_title=series_name, channel_id=ch_id
                                )
                                if not eps and "animeunity." in target_u.lower():
                                    m_au = re.search(r"/anime/(\d+)", target_u)
                                    if m_au:
                                        r_api = httpx.get(
                                            f"https://www.animeunity.co/info_api/{m_au.group(1)}/1?start_range=1&end_range=120",
                                            headers={"User-Agent": UA, "Referer": target_u},
                                            timeout=10.0,
                                            follow_redirects=True,
                                        )
                                        if r_api.status_code == 200:
                                            eps = bridge.scrape_channel_episodes(
                                                r_api.text, target_u, series_title=series_name, channel_id=ch_id or "animeunity"
                                            )
                                if eps:
                                    conn.execute("DELETE FROM episodes WHERE parent_id=?", (item_id,))
                                    for ep in eps:
                                        conn.execute("""
                                            INSERT OR REPLACE INTO episodes (id, parent_id, recipe_id, title, series, season, episode, duration, stream_url, url, poster, genre, source, updated)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'stream4me', ?)
                                        """, (
                                            ep["id"], item_id, rec_id or "stream4me", ep["title"],
                                            ep.get("series") or series_name, ep.get("season"),
                                            ep.get("episode"), ep.get("duration"), ep.get("stream_url") or "",
                                            ep.get("url") or ep.get("stream_url") or "", ep.get("poster") or item.get("poster") or "",
                                            item.get("genre") or "",
                                            time.time(),
                                        ))
                            if not item.get("stream_url"):
                                resolved_s = (
                                    bridge.resolve_channel_stream(target_u, html_text=resp.text)
                                    if hasattr(bridge, "resolve_channel_stream")
                                    else ""
                                )
                                if not resolved_s and hasattr(bridge, "extract_stream_urls"):
                                    found_streams = bridge.extract_stream_urls(resp.text, base_url=target_u)
                                    if found_streams:
                                        resolved_s = found_streams[0]["url"]
                                if resolved_s:
                                    item["stream_url"] = resolved_s
                                    conn.execute("UPDATE items SET stream_url=?, updated=? WHERE id=?",
                                                 (item["stream_url"], time.time(), item_id))
                            conn.commit()
                    except Exception as e:
                        gs.log(f"ricette-web: errore dettaglio Stream4me per {item_id}: {e}")

            out = to_item(item)
            ep_rows = conn.execute("SELECT * FROM episodes WHERE parent_id=? ORDER BY season, episode, title", (item_id,)).fetchall()
            if ep_rows:
                dedup_eps = []
                seen_se = set()
                for e in ep_rows:
                    ed = to_item(e)
                    key = (ed.get("season") or 1, ed.get("episode") if ed.get("episode") is not None else ed.get("title"))
                    if key not in seen_se:
                        seen_se.add(key)
                        dedup_eps.append(ed)
                out["episodes"] = dedup_eps
            return out
        finally:
            conn.close()

    def find_row(conn, item_id: str):
        """Riga dell'elemento e nome della tabella che la contiene."""
        for table in ("items", "episodes"):
            row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,)).fetchone()
            if row is not None:
                return row, table
        return None, "items"

    def _find_s4me_dir(bridge) -> Path | None:
        if bridge is not None and hasattr(bridge, "find_stream4me_dir"):
            found = bridge.find_stream4me_dir(addons_root)
            if found is not None and found.is_dir():
                return found
        for cand in ("plugin.video.s4me", "plugin.video.stream4me", "stream4me"):
            d = addons_root / cand
            if d.is_dir():
                return d
        return None

    def resolve_stream(row, table: str, conn) -> str:
        """stream_url assente: scarica la pagina di dettaglio, estrae il flusso e lo salva nel DB."""
        recipe_id = str(row["recipe_id"] or "")
        item_url = str(row["url"] or "").strip()
        item_id = str(row["id"] or "")
        if not item_url:
            return ""

        # shortcut: risolve item Stream4me / Kodi tramite kodi_bridge
        is_s4me = (
            recipe_id == "stream4me"
            or recipe_id.startswith(("kodi:", "s4me:", "stream4me:"))
            or item_id.startswith(("stream4me:", "kodi:", "s4me:"))
            or str(row["source"] or "") == "stream4me"
        )
        if is_s4me:
            bridge = kodi_bridge_module()
            stream = ""
            if item_url.startswith("plugin://") and bridge and hasattr(bridge, "run_kodi_addon_directory"):
                s4me_dir = _find_s4me_dir(bridge)
                if s4me_dir is not None and s4me_dir.is_dir():
                    try:
                        resolved = bridge.run_kodi_addon_directory(s4me_dir, handle_url=item_url)
                        for r in resolved:
                            if r.get("stream_url"):
                                stream = r["stream_url"]
                                break
                    except Exception as e:
                        gs.log(f"ricette-web: errore run_kodi_addon_directory per {item_url}: {e}")

            if not stream and item_url.startswith(("http://", "https://")):
                try:
                    target_u = bridge._normalize_provider_host(item_url) if (bridge and hasattr(bridge, "_normalize_provider_host")) else item_url
                    if bridge and hasattr(bridge, "resolve_channel_stream"):
                        stream = bridge.resolve_channel_stream(target_u)
                    if not stream:
                        resp = httpx.get(target_u, headers={"User-Agent": UA}, timeout=15.0, follow_redirects=True)
                        if resp.status_code == 200:
                            if bridge and hasattr(bridge, "resolve_channel_stream"):
                                stream = bridge.resolve_channel_stream(target_u, html_text=resp.text)
                            if not stream and bridge and hasattr(bridge, "extract_stream_urls"):
                                found = bridge.extract_stream_urls(resp.text, base_url=target_u)
                                if found:
                                    stream = found[0]["url"]
                            if not stream:
                                found_fb = _fallback_stream_urls(resp.text, base_url=target_u)
                                if found_fb:
                                    stream = found_fb[0]
                except Exception as e:
                    gs.log(f"ricette-web: errore estrazione stream per {item_url}: {e}")

            if stream:
                conn.execute(f"UPDATE {table} SET stream_url=?, updated=? WHERE id=?", (stream, time.time(), row["id"]))
                conn.commit()
            return stream

        rec = recipes_by_id.get(recipe_id)
        if not rec:
            return ""
        try:
            body, _ = fetch_url(item_url, rec, cache, ttl=TTL, log=gs.log)
            stream = (apply_detail(rec, body, item_url) or {}).get("stream_url") or ""
        except Exception as e:
            gs.log(f"ricette-web: flusso non risolto per {row['id']}: {e}")
            return ""
        if stream:
            conn.execute(f"UPDATE {table} SET stream_url=?, updated=? WHERE id=?", (stream, time.time(), row["id"]))
            conn.commit()
        return stream

    @gs.route("play_target")
    def media_play_target(id: str = ""):
        item_id = str(id or "").strip()
        if not item_id:
            raise HTTPException(400, "id mancante")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row, table = find_row(conn, item_id)
            if row is None and item_id.startswith(("stream4me:", "kodi:")):
                stream4me_sections()
                row, table = find_row(conn, item_id)
            if row is None:
                raise HTTPException(404, "elemento non trovato")

            stream_url = (row["stream_url"] or "").strip()
            bridge = kodi_bridge_module()
            if stream_url and bridge and hasattr(bridge, "_is_ad") and bridge._is_ad(stream_url):
                stream_url = ""
            if (not stream_url or (stream_url == (row["url"] or "").strip() and not is_direct_stream(stream_url) and ".m3u8" not in stream_url.lower())) and row["url"]:
                resolved = resolve_stream(row, table, conn)
                if resolved:
                    stream_url = resolved
            stream_url = stream_url or row["url"] or _STREAM_MAP.get(item_id, "") or _URL_MAP.get(item_id, "")
            if stream_url and bridge and hasattr(bridge, "_is_ad") and bridge._is_ad(stream_url):
                stream_url = ""
            if not stream_url:
                raise HTTPException(404, "flusso non disponibile")

            pos = round(float(row["resume_pos"] or 0.0), 1)
            return {"url": stream_url, "resume_pos": pos, "external": not (is_direct_stream(stream_url) or urllib.parse.urlparse(stream_url).path.lower().endswith(".m3u8"))}
        finally:
            conn.close()

    @gs.route("external", methods=("POST",))
    def media_external(body: dict | None = Body(None), id: str = ""):
        """HLS e embed: mpv/VLC se installati, altrimenti il browser (il webview non legge .m3u8)."""
        data = body if isinstance(body, dict) else {}
        item_id = str(data.get("id") or id or "").strip()
        if not item_id:
            raise HTTPException(400, "id mancante")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row, _table = find_row(conn, item_id)
        finally:
            conn.close()
        if row is None:
            raise HTTPException(404, "elemento non trovato")

        url = str(row["stream_url"] or row["url"] or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            raise HTTPException(400, "flusso non valido")

        player = shutil.which("mpv") or shutil.which("vlc")
        if player:
            subprocess.Popen([player, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            webbrowser.open(url)
        return {"ok": True, "player": player or ""}


    @gs.route("set_progress", methods=("POST",))
    def media_set_progress(body: dict | None = Body(None), id: str = "", pos: float | None = None,
                           seen: bool | None = None, duration: float | None = None):
        data = body if isinstance(body, dict) else {}
        item_id = str(data.get("id") or id or "").strip()
        if not item_id:
            raise HTTPException(400, "id mancante")

        position = float(data.get("pos", pos) or 0.0)
        flag = data.get("seen", seen)
        length = float(data.get("duration", duration) or 0.0)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            table = "items"
            if row is None:
                row = conn.execute("SELECT * FROM episodes WHERE id=?", (item_id,)).fetchone()
                table = "episodes"
            if row is None:
                raise HTTPException(404, "elemento non trovato")

            known = length if length > 0 else float(row["duration"] or 0.0)
            watched = bool(flag) if flag is not None else bool(row["seen"])
            if known > 0 and position >= known * 0.9:
                watched = True

            new_pos = 0.0 if watched else max(0.0, position)
            new_seen = 1 if watched else 0

            conn.execute(f"UPDATE {table} SET resume_pos=?, seen=?, duration=COALESCE(?, duration), updated=? WHERE id=?",
                         (new_pos, new_seen, known or None, time.time(), item_id))
            conn.commit()
            updated_row = conn.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,)).fetchone()
            return {"ok": True, "item": to_item(updated_row)}
        finally:
            conn.close()

    @gs.route("kodi_addons")
    def kodi_addons_list():
        bridge = kodi_bridge_module()
        addons = []
        if addons_root.is_dir():
            for d in sorted(p for p in addons_root.iterdir() if p.is_dir()):
                xml = d / "addon.xml"
                if not xml.is_file():
                    continue
                try:
                    text = xml.read_text("utf-8")
                    info = bridge.parse_addon_xml(text) if bridge else _mini_addon_xml(text)
                except Exception:
                    continue
                addons.append({"id": str(info.get("id") or d.name), "name": str(info.get("name") or d.name),
                               "version": str(info.get("version") or ""),
                               "summary": str(info.get("summary") or ""), "path": str(d)})
        return {"addons": addons}

    @gs.route("kodi_addons", methods=("POST",))
    def kodi_addons_save(body: dict = Body(...)):
        bridge = kodi_bridge_module()
        if bridge is None:
            raise HTTPException(503, "kodi_bridge.py non disponibile")

        if body.get("remove"):
            addon_id = str(body["remove"]).strip()
            if not re.fullmatch(r"[A-Za-z0-9._-]+", addon_id):
                raise HTTPException(400, "id addon non valido")
            shutil.rmtree(addons_root / addon_id, ignore_errors=True)  # solo addon dentro kodi-addons/
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("DELETE FROM items WHERE recipe_id=?", (f"kodi:{addon_id}",))
                conn.commit()
            finally:
                conn.close()
            return {"ok": True, "removed": addon_id}

        source = str(body.get("url") or body.get("path") or "").strip()
        if not source:
            raise HTTPException(400, "serve 'url' o 'path'")
        try:
            addon = bridge.install_kodi_addon(source, addons_root)
        except Exception as e:
            raise HTTPException(400, f"installazione addon fallita: {e}")
        addon_id = str(addon.get("id") or "")
        if not addon_id:
            raise HTTPException(400, "addon.xml senza id")

        count = 0
        conn = sqlite3.connect(db_path)
        try:
            for ch in addon.get("channels") or []:
                if not isinstance(ch, dict):
                    continue
                name = str(ch.get("name") or ch.get("id") or "").strip()
                if not name:
                    continue
                poster = str(ch.get("poster") or "")
                conn.execute("""
                    INSERT INTO items (id, recipe_id, kind, title, overview, poster, backdrop, url, stream_url, source, updated)
                    VALUES (?, ?, 'film', ?, ?, ?, ?, ?, ?, 'kodi', ?)
                    ON CONFLICT(id) DO UPDATE SET title=excluded.title, overview=excluded.overview,
                        poster=COALESCE(NULLIF(excluded.poster, ''), items.poster), updated=excluded.updated
                """, (hashlib.sha1(f"kodi:{addon_id}:{ch.get('id') or name}".encode()).hexdigest()[:16],
                      f"kodi:{addon_id}", name, str(ch.get("summary") or ch.get("overview") or ""), poster, poster,
                      str(ch.get("search_url") or ch.get("host") or ""), str(ch.get("stream_url") or ""), time.time()))
                count += 1
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "addon": {k: str(addon.get(k) or "") for k in ("id", "name", "version", "summary")},
                "items": count}

    @gs.route("stream4me/install", methods=("POST",))
    def stream4me_install(body: dict | None = Body(None)):
        bridge = kodi_bridge_module()
        if bridge is None:
            raise HTTPException(503, "kodi_bridge.py non disponibile")
        data = body if isinstance(body, dict) else {}
        force = bool(data.get("force", False))
        s4me_dir = _find_s4me_dir(bridge)
        if s4me_dir is not None and s4me_dir.is_dir() and not force:
            if hasattr(bridge, "_clear_stream4me_caches"):
                bridge._clear_stream4me_caches()
            providers = bridge.list_stream4me_providers(s4me_dir) if hasattr(bridge, "list_stream4me_providers") else []
            return {"ok": True, "installed": True, "path": str(s4me_dir), "providers_count": len(providers)}

        default_url = getattr(bridge, "STREAM4ME_DEFAULT_URL", "https://github.com/Stream4me/addon")
        source = str(data.get("url") or data.get("path") or default_url).strip()
        try:
            res = bridge.install_kodi_addon(source, addons_root)
        except Exception as e:
            raise HTTPException(400, f"installazione Stream4me fallita: {e}")
        if hasattr(bridge, "_clear_stream4me_caches"):
            bridge._clear_stream4me_caches()
        s4me_dir = Path(res["path"]) if res and res.get("path") else _find_s4me_dir(bridge)
        providers = bridge.list_stream4me_providers(s4me_dir) if (s4me_dir and hasattr(bridge, "list_stream4me_providers")) else []
        return {"ok": True, "installed": bool(s4me_dir), "addon": res, "providers_count": len(providers)}

    prov_cfg_path = cache / "stream4me_providers_config.json"

    def _load_prov_cfg() -> dict:
        if prov_cfg_path.is_file():
            try:
                data = json.loads(prov_cfg_path.read_text("utf-8"))
                if isinstance(data, dict):
                    return {
                        "disabled": [str(x) for x in (data.get("disabled") or []) if x],
                        "enabled": [str(x) for x in (data.get("enabled") or []) if x],
                        "custom": [c for c in (data.get("custom") or []) if isinstance(c, dict) and c.get("id")],
                    }
            except Exception:
                pass
        return {"disabled": [], "enabled": [], "custom": []}

    def _save_prov_cfg(cfg_data: dict) -> None:
        try:
            prov_cfg_path.parent.mkdir(parents=True, exist_ok=True)
            prov_cfg_path.write_text(json.dumps(cfg_data, indent=2), "utf-8")
        except Exception as e:
            gs.log(f"ricette-web: errore salvataggio config provider: {e}")

    DEFAULT_ACTIVE_IDS = ("animeunity", "animeworld", "streamingcommunity", "altadefinizione01")

    def _build_providers_state(bridge, s4me_dir: Path | None) -> tuple[list[dict], list[dict]]:
        cfg_data = _load_prov_cfg()
        disabled = set(cfg_data["disabled"])
        enabled = set(cfg_data["enabled"])
        custom_list = cfg_data["custom"]

        all_builtin = (
            bridge.list_stream4me_providers(s4me_dir, only_active=False)
            if (bridge is not None and s4me_dir is not None and hasattr(bridge, "list_stream4me_providers"))
            else []
        )
        active_builtin = (
            bridge.list_stream4me_providers(s4me_dir, only_active=True)
            if (bridge is not None and s4me_dir is not None and hasattr(bridge, "list_stream4me_providers"))
            else []
        )
        all_builtin_ids = {p["id"] for p in all_builtin}
        has_any_curated = any(cid in all_builtin_ids for cid in DEFAULT_ACTIVE_IDS)
        if enabled:
            default_active_ids = set(enabled)
        elif has_any_curated:
            default_active_ids = set(DEFAULT_ACTIVE_IDS)
        else:
            default_active_ids = {p["id"] for p in active_builtin}

        providers: list[dict] = []
        available_inactive: list[dict] = []
        seen_ids: set[str] = set()

        for p in all_builtin:
            pid = p["id"]
            is_act = (pid in default_active_ids) and (pid not in disabled)
            if is_act:
                p_copy = dict(p)
                p_copy["active"] = True
                providers.append(p_copy)
                seen_ids.add(pid)
            else:
                p_copy = dict(p)
                p_copy["active"] = False
                available_inactive.append(p_copy)

        for cp in custom_list:
            cid = str(cp.get("id") or "")
            if not cid or cid in disabled:
                continue
            cp_copy = dict(cp)
            cp_copy["active"] = True
            cp_copy.setdefault("custom", True)
            if cid in seen_ids:
                providers = [cp_copy if x["id"] == cid else x for x in providers]
            else:
                providers.append(cp_copy)
                seen_ids.add(cid)

        order_map = {name: idx for idx, name in enumerate(DEFAULT_ACTIVE_IDS)}
        providers.sort(key=lambda x: order_map.get(x["id"], 999))
        return providers, available_inactive

    @gs.route("stream4me/providers")
    def stream4me_providers():
        bridge = kodi_bridge_module()
        s4me_dir = _find_s4me_dir(bridge)
        providers, available_inactive = _build_providers_state(bridge, s4me_dir)
        return {
            "installed": bool(s4me_dir) or bool(providers),
            "providers": providers,
            "available_inactive": available_inactive,
        }

    @gs.route("stream4me/providers", methods=("POST",))
    def stream4me_providers_add(body: dict = Body(...)):
        data = body if isinstance(body, dict) else {}
        cfg_data = _load_prov_cfg()
        bridge = kodi_bridge_module()
        s4me_dir = _find_s4me_dir(bridge)

        enable_id = str(data.get("enable") or "").strip()
        if enable_id:
            if enable_id not in cfg_data["enabled"]:
                cfg_data["enabled"].append(enable_id)
            cfg_data["disabled"] = [x for x in cfg_data["disabled"] if x != enable_id]
            _save_prov_cfg(cfg_data)
            providers, available_inactive = _build_providers_state(bridge, s4me_dir)
            prov = next((p for p in providers if p["id"] == enable_id), {"id": enable_id})
            return {"ok": True, "provider": prov, "providers": providers, "available_inactive": available_inactive}

        name = str(data.get("name") or "").strip()
        host = str(data.get("host") or data.get("url") or "").strip().rstrip("/")
        if not name or not re.match(r"^https?://", host, re.I):
            raise HTTPException(400, "name e host (http/https) obbligatori")
        prov_id = re.sub(r"[^a-z0-9_-]+", "-", str(data.get("id") or name).lower()).strip("-") or "custom"
        raw_cats = data.get("categories")
        if isinstance(raw_cats, str):
            categories = [c.strip() for c in raw_cats.split(",") if c.strip()]
        elif isinstance(raw_cats, list):
            categories = [str(c).strip() for c in raw_cats if str(c).strip()]
        else:
            categories = ["movie", "tvshow"]
        if not categories:
            categories = ["movie", "tvshow"]
        search_url = str(data.get("search_url") or f"{host}/?s={{query}}").strip()
        menus = data.get("menus") if isinstance(data.get("menus"), list) and data.get("menus") else [{"label": "Catalogo", "path": "/"}]
        prov = {
            "id": prov_id,
            "name": name,
            "host": host,
            "categories": categories,
            "poster": str(data.get("poster") or ""),
            "menus": menus,
            "search_url": search_url,
            "active": True,
            "custom": True,
        }
        cfg_data["custom"] = [c for c in cfg_data["custom"] if c.get("id") != prov_id] + [prov]
        cfg_data["disabled"] = [x for x in cfg_data["disabled"] if x != prov_id]
        _save_prov_cfg(cfg_data)
        providers, available_inactive = _build_providers_state(bridge, s4me_dir)
        return {"ok": True, "provider": prov, "providers": providers, "available_inactive": available_inactive}

    def _active_s4me_ids() -> set[str] | None:
        """Id dei provider attivi; None se non determinabili (nessun filtro)."""
        try:
            bridge = kodi_bridge_module()
            providers, _ = _build_providers_state(bridge, _find_s4me_dir(bridge))
            return {str(p["id"]) for p in providers} or None
        except Exception:
            return None

    def _purge_inactive_s4me() -> int:
        """Cancella titoli e schede-canale dei provider rimossi; i preferiti (pinned) restano."""
        active = _active_s4me_ids()
        conn = sqlite3.connect(db_path)
        try:
            n = conn.execute("DELETE FROM items WHERE recipe_id='stream4me'").rowcount
            if active is not None:
                n += conn.execute(
                    "DELETE FROM items WHERE recipe_id LIKE 's4me:%' AND substr(recipe_id, 6) NOT IN (" + ",".join("?" * len(active)) + ")",
                    sorted(active),
                ).rowcount
            conn.execute("DELETE FROM episodes WHERE parent_id NOT IN (SELECT id FROM items)")
            conn.commit()
            return n
        finally:
            conn.close()

    @gs.route("stream4me/cleanup", methods=("POST",))
    def stream4me_cleanup(body: dict | None = Body(None)):
        """Pulisce i provider eliminati e riscansiona quelli attivi."""
        removed = _purge_inactive_s4me()
        bridge = kodi_bridge_module()
        s4me_dir = _find_s4me_dir(bridge)
        custom = _load_prov_cfg().get("custom") or []
        providers, _ = _build_providers_state(bridge, s4me_dir)
        refreshed = 0
        if bridge is not None and hasattr(bridge, "browse_stream4me_channel"):
            def _one(pid: str) -> int:
                try:
                    res = bridge.browse_stream4me_channel(s4me_dir, pid, timeout=8.0, custom_providers=custom)
                    found = res.get("items") or []
                    _save_s4me_items(found, f"s4me:{pid}")
                    return len(found)
                except Exception as e:
                    gs.log(f"ricette-web: cleanup, scansione {pid} fallita: {e}")
                    return 0
            if providers:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(providers))) as ex:
                    refreshed = sum(ex.map(_one, [p["id"] for p in providers]))
        return {"ok": True, "removed": removed, "refreshed": refreshed, "providers": len(providers)}

    @gs.route("stream4me/providers/remove", methods=("POST",))
    def stream4me_providers_remove(body: dict = Body(...)):
        data = body if isinstance(body, dict) else {}
        prov_id = str(data.get("id") or "").strip()
        if not prov_id:
            raise HTTPException(400, "id mancante")
        cfg_data = _load_prov_cfg()
        if prov_id not in cfg_data["disabled"]:
            cfg_data["disabled"].append(prov_id)
        cfg_data["enabled"] = [x for x in cfg_data["enabled"] if x != prov_id]
        cfg_data["custom"] = [c for c in cfg_data["custom"] if c.get("id") != prov_id]
        _save_prov_cfg(cfg_data)
        _purge_inactive_s4me()
        bridge = kodi_bridge_module()
        s4me_dir = _find_s4me_dir(bridge)
        providers, available_inactive = _build_providers_state(bridge, s4me_dir)
        return {"ok": True, "removed": prov_id, "providers": providers, "available_inactive": available_inactive}

    def _save_s4me_items(items: list[dict], recipe_tag: str) -> None:
        if not items:
            return
        conn = sqlite3.connect(db_path)
        try:
            now_ts = time.time()
            for it in items:
                conn.execute("""
                    INSERT INTO items (id, recipe_id, kind, title, series, season, episode, year, overview, genre, poster, backdrop, url, stream_url, source, updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'stream4me', ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        kind=excluded.kind,
                        series=COALESCE(NULLIF(excluded.series, ''), items.series),
                        season=COALESCE(excluded.season, items.season),
                        episode=COALESCE(excluded.episode, items.episode),
                        overview=COALESCE(NULLIF(excluded.overview, ''), items.overview),
                        genre=COALESCE(NULLIF(excluded.genre, ''), items.genre),
                        poster=COALESCE(NULLIF(excluded.poster, ''), items.poster),
                        backdrop=COALESCE(NULLIF(excluded.backdrop, ''), items.backdrop),
                        url=COALESCE(NULLIF(excluded.url, ''), items.url),
                        stream_url=COALESCE(NULLIF(excluded.stream_url, ''), items.stream_url),
                        updated=excluded.updated
                """, (
                    it["id"], recipe_tag, it.get("kind", "film"), it["title"],
                    it.get("series") or "", it.get("season"), it.get("episode"), it.get("year"),
                    it.get("overview") or "", it.get("genre") or "",
                    it.get("poster") or "", it.get("poster") or "",
                    it.get("url") or "", it.get("stream_url") or "", now_ts,
                ))
            conn.commit()
        finally:
            conn.close()

    @gs.route("stream4me/browse")
    def stream4me_browse(channel: str = "", path: str = "", query: str = ""):
        bridge = kodi_bridge_module()
        if bridge is None or not hasattr(bridge, "browse_stream4me_channel"):
            return {"provider": None, "url": "", "items": []}
        s4me_dir = _find_s4me_dir(bridge)
        cfg_data = _load_prov_cfg()
        custom_provs = cfg_data.get("custom") or []
        if s4me_dir is None and not custom_provs:
            return {"installed": False, "provider": None, "url": "", "items": []}

        ch = (channel or "").strip()
        q = (query or "").strip()
        p = (path or "").strip()

        if ch and ch != "all":
            try:
                res = bridge.browse_stream4me_channel(s4me_dir, ch, path=p, query=q, custom_providers=custom_provs)
            except Exception as e:
                gs.log(f"ricette-web: browse_stream4me_channel({ch}) fallito: {e}")
                return {"provider": {"id": ch, "name": ch}, "url": "", "items": [], "error": str(e)}
            _save_s4me_items(res.get("items") or [], f"s4me:{ch}")
            return res

        if q:
            active_providers, _ = _build_providers_state(bridge, s4me_dir)
            providers = active_providers[:6]
            combined: list[dict] = []

            def _search_one(prov_id: str) -> list[dict]:
                try:
                    r = bridge.browse_stream4me_channel(s4me_dir, prov_id, query=q, timeout=5.0, custom_providers=custom_provs)
                    found = r.get("items") or []
                    _save_s4me_items(found, f"s4me:{prov_id}")
                    return found
                except Exception:
                    return []

            if providers:
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(providers))) as ex:
                    futures = [ex.submit(_search_one, prov["id"]) for prov in providers]
                    for fut in concurrent.futures.as_completed(futures, timeout=6.0):
                        try:
                            combined.extend(fut.result())
                        except Exception:
                            pass
            return {
                "provider": {"id": "all", "name": "Ricerca Globale Stream4me"},
                "url": "",
                "items": combined,
            }

        return {"provider": None, "url": "", "items": []}

    def _to_pinned_item(r: dict | sqlite3.Row) -> dict:
        d = dict(r)
        it = to_item(d)
        it["source"] = str(d.get("source") or "stream4me")
        it["url"] = str(d.get("url") or "")
        it["stream_url"] = str(d.get("stream_url") or "")
        it["pinned"] = True
        return it

    @gs.route("stream4me/pinned")
    def stream4me_pinned():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM items WHERE recipe_id='stream4me:pinned' ORDER BY updated DESC, title"
            ).fetchall()
            return {"items": [_to_pinned_item(r) for r in rows]}
        finally:
            conn.close()

    @gs.route("stream4me/pin", methods=("POST",))
    def stream4me_pin(body: dict = Body(...)):
        raw = body.get("item") if isinstance(body, dict) and isinstance(body.get("item"), dict) else body
        if not isinstance(raw, dict):
            raise HTTPException(400, "item non valido")
        title = str(raw.get("title") or "").strip()
        url = str(raw.get("url") or raw.get("stream_url") or "").strip()
        item_id = str(raw.get("id") or "").strip()
        if not item_id and (url or title):
            item_id = "s4me:pin:" + hashlib.sha1(f"{url}:{title}".encode("utf-8")).hexdigest()[:12]
        if not item_id or not title:
            raise HTTPException(400, "id e title obbligatori")
        kind = str(raw.get("kind") or "film")
        if kind not in KINDS:
            kind = "film"
        poster = str(raw.get("poster") or "")
        backdrop = str(raw.get("backdrop") or poster)
        overview = str(raw.get("overview") or raw.get("channel_name") or "Stream4me")
        genre = str(raw.get("genre") or "")
        prov_id = str(raw.get("channel_id") or "").lower()
        if not prov_id and item_id.startswith("s4me:"):
            parts = item_id.split(":")
            if len(parts) >= 3:
                prov_id = parts[1].lower()
        url_low = url.lower()

        if prov_id in ("animeunity", "animeworld") or "animeunity" in url_low or "animeworld" in url_low:
            is_anime = True
        elif prov_id in ("streamingcommunity", "altadefinizione01") or "streamingcommunity" in url_low or "altadefinizione" in url_low:
            is_anime = False
        else:
            ch_hay = f"{item_id} {raw.get('channel_id') or ''} {raw.get('channel_name') or ''} {overview} {genre} {url} {title}".lower()
            is_anime = (
                genre.lower() == "anime"
                or any(k in ch_hay for k in ("anime", "toon", "sub-ita"))
            )

        explicit_movie = bool(re.search(r"\b(?:film|movie)\b", f"{url} {title}".lower())) and kind == "film" and not raw.get("series")
        if is_anime:
            is_series = not explicit_movie
        else:
            is_series = (
                kind == "episodio"
                or bool(raw.get("series"))
                or ("/serie/" in url_low)
                or any(k in f"{url_low} {title.lower()}" for k in ("stagione", "season", "episod", "/tv/"))
            )
        if is_series:
            kind = "episodio"
            series = str(raw.get("series") or title)
            season = int(raw.get("season") or 1)
            episode = int(raw.get("episode") or 1)
        else:
            series = ""
            season = None
            episode = None

        if is_anime:
            genre = "Anime"
            if "anime" not in overview.lower():
                overview = f"Anime · {overview}" if overview else "Anime"
        elif not genre or genre == "Anime":
            genre = "Serie TV" if is_series else "Film"

        year = _extract_year(str(raw.get("year") or "")) if raw.get("year") else None
        stream_url = str(raw.get("stream_url") or "")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("""
                INSERT INTO items (id, recipe_id, kind, title, series, season, episode, year, poster, backdrop, overview, genre, url, stream_url, source, updated)
                VALUES (?, 'stream4me:pinned', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'stream4me', ?)
                ON CONFLICT(id) DO UPDATE SET
                    recipe_id='stream4me:pinned',
                    kind=excluded.kind,
                    title=excluded.title,
                    series=excluded.series,
                    season=excluded.season,
                    episode=excluded.episode,
                    year=COALESCE(excluded.year, items.year),
                    poster=COALESCE(NULLIF(excluded.poster, ''), items.poster),
                    backdrop=COALESCE(NULLIF(excluded.backdrop, ''), items.backdrop),
                    overview=COALESCE(NULLIF(excluded.overview, ''), items.overview),
                    genre=COALESCE(NULLIF(excluded.genre, ''), items.genre),
                    url=COALESCE(NULLIF(excluded.url, ''), items.url),
                    stream_url=COALESCE(NULLIF(excluded.stream_url, ''), items.stream_url),
                    source='stream4me',
                    updated=excluded.updated
            """, (item_id, kind, title, series, season, episode, year, poster, backdrop, overview, genre, url, stream_url, time.time()))
            conn.commit()
            saved = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            return {"ok": True, "item": _to_pinned_item(saved)}
        finally:
            conn.close()

    @gs.route("stream4me/unpin", methods=("POST",))
    def stream4me_unpin(body: dict = Body(...)):
        item_id = str((body or {}).get("id") or "").strip()
        if not item_id:
            raise HTTPException(400, "id mancante")
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("DELETE FROM items WHERE id=? AND recipe_id='stream4me:pinned'", (item_id,))
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "removed": item_id}

    @gs.route("stream4me/sections")
    def stream4me_sections():
        bridge = kodi_bridge_module()
        s4me_dir = _find_s4me_dir(bridge)

        sec_map = (
            bridge.get_stream4me_sections(s4me_dir if (s4me_dir and s4me_dir.is_dir()) else None)
            if bridge and hasattr(bridge, "get_stream4me_sections")
            else {}
        )
        if not sec_map:
            sec_map = {
                "film": [
                    {"id": "stream4me:film:nuove-uscite", "kind": "film", "title": "Stream4me: Nuove Uscite",
                     "poster": "", "overview": "Film in streaming", "source": "ricette-web", "source_label": "Stream4me",
                     "url": "https://stream4me.example/film", "stream_url": ""},
                ],
                "serie": [
                    {"id": "stream4me:serie:popolari", "kind": "film", "title": "Stream4me: Serie Popolari",
                     "poster": "", "overview": "Serie TV in streaming", "source": "ricette-web", "source_label": "Stream4me",
                     "url": "https://stream4me.example/serie", "stream_url": ""},
                ],
                "canali": [
                    {"id": "stream4me:canali:live", "kind": "film", "title": "Stream4me: Canali TV Live",
                     "poster": "", "overview": "Canali TV in diretta streaming", "source": "ricette-web", "source_label": "Stream4me",
                     "url": "https://stream4me.example/canali", "stream_url": "https://cdn.example/live/master.m3u8"},
                ],
                "animazione": [
                    {"id": "stream4me:animazione:anime", "kind": "film", "title": "Stream4me: Anime e Cartoni",
                     "poster": "", "overview": "Anime e animazione", "source": "ricette-web", "source_label": "Stream4me",
                     "url": "https://stream4me.example/anime", "stream_url": ""},
                ],
            }

        _store_sections(sec_map)

        return {
            "sections": [
                {"id": "stream4me-film", "title": "Stream4me: Film in Streaming", "items": sec_map.get("film", [])},
                {"id": "stream4me-serie", "title": "Stream4me: Serie TV", "items": sec_map.get("serie", [])},
                {"id": "stream4me-live", "title": "Stream4me: Canali Live", "items": sec_map.get("canali", [])},
                {"id": "stream4me-animazione", "title": "Stream4me: Anime e Cartoni", "items": sec_map.get("animazione", [])},
            ]
        }

    @gs.route("recipes")
    def get_recipes():
        return {"recipes": recipes}

    # ---------------------------------------------------------------- aggiornamento catalogo in background
    refresh_lock = threading.Lock()
    refresh_state = {"refreshing": False, "progress": ""}

    def _meta_get(key: str) -> str | None:
        conn = sqlite3.connect(db_path)
        try:
            r = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return r[0] if r else None
        finally:
            conn.close()

    def _meta_set(**kv) -> None:
        conn = sqlite3.connect(db_path)
        try:
            for k, v in kv.items():
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (k, None if v is None else str(v)))
            conn.commit()
        finally:
            conn.close()

    def _catalog_status() -> dict:
        conn = sqlite3.connect(db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM items WHERE recipe_id != 'stream4me'").fetchone()[0]
        finally:
            conn.close()
        ts = _meta_get("updated_at")
        return {
            "updated_at": float(ts) if ts else None,
            "refreshing": refresh_state["refreshing"],
            "progress": refresh_state["progress"],
            "last_error": _meta_get("last_error") or None,
            "total": total,
        }

    def _store_sections(sec_map: dict) -> None:
        conn = sqlite3.connect(db_path)
        try:
            for sec_items in sec_map.values():
                for it in sec_items:
                    conn.execute("""
                        INSERT INTO items (id, recipe_id, kind, title, overview, poster, backdrop, url, stream_url, source, updated)
                        VALUES (?, 'stream4me', ?, ?, ?, ?, ?, ?, ?, 'ricette-web', ?)
                        ON CONFLICT(id) DO UPDATE SET
                            title=excluded.title,
                            overview=excluded.overview,
                            poster=COALESCE(NULLIF(excluded.poster, ''), items.poster),
                            url=COALESCE(NULLIF(excluded.url, ''), items.url),
                            stream_url=COALESCE(NULLIF(excluded.stream_url, ''), items.stream_url),
                            updated=excluded.updated
                    """, (
                        it["id"], it.get("kind", "film"), it["title"],
                        it.get("overview", ""), it.get("poster", ""), it.get("poster", ""),
                        it.get("url", ""), it.get("stream_url", ""), time.time(),
                    ))
            conn.commit()
        finally:
            conn.close()

    def _do_refresh() -> None:
        t0 = time.time()
        err = None
        try:
            refresh_state["progress"] = "Catalogo ricette"
            sync_catalog()
            bridge = kodi_bridge_module()
            s4me_dir = _find_s4me_dir(bridge)
            can_browse = bridge is not None and hasattr(bridge, "browse_stream4me_channel")
            ok_tags: list[str] = []
            if bridge is not None and hasattr(bridge, "get_stream4me_sections"):
                refresh_state["progress"] = "Sezioni Stream4me"
                sec_map = bridge.get_stream4me_sections(s4me_dir if (s4me_dir and s4me_dir.is_dir()) else None, force=True)
                _store_sections(sec_map)
            if can_browse:
                custom = _load_prov_cfg().get("custom") or []
                providers, _ = _build_providers_state(bridge, s4me_dir)
                for i, p in enumerate(providers, 1):
                    refresh_state["progress"] = f"Provider {i}/{len(providers)}: {p.get('id')}"
                    try:
                        found = bridge.browse_stream4me_channel(s4me_dir, p["id"], timeout=8.0, custom_providers=custom).get("items") or []
                    except Exception as e:
                        gs.log(f"ricette-web: refresh, scansione {p.get('id')} fallita: {e}")
                        continue
                    if found:  # un provider vuoto/in errore non cancella nulla di suo
                        _save_s4me_items(found, f"s4me:{p['id']}")
                        ok_tags.append(f"s4me:{p['id']}")
            if ok_tags:  # elimina i titoli non rivisti in questa run (updated < t0)
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute(
                        "DELETE FROM items WHERE source='stream4me' AND recipe_id IN (" + ",".join("?" * len(ok_tags)) + ") AND updated < ?",
                        [*ok_tags, t0],
                    )
                    conn.execute("DELETE FROM episodes WHERE parent_id NOT IN (SELECT id FROM items)")
                    conn.commit()
                finally:
                    conn.close()
            elif can_browse:
                err = "nessun titolo Stream4me ricevuto: catalogo precedente mantenuto"
        except Exception as e:
            err = str(e) or e.__class__.__name__
            gs.log(f"ricette-web: refresh catalogo fallito: {e}")
        finally:
            try:
                _meta_set(last_error=err, **({} if err else {"updated_at": time.time()}))
            finally:
                refresh_state.update(refreshing=False, progress="")

    def _start_refresh(wait: bool = False) -> dict:
        """Idempotente: se un refresh e' in corso non ne avvia un altro."""
        with refresh_lock:
            th = None
            if not refresh_state["refreshing"]:
                refresh_state.update(refreshing=True, progress="Avvio")
                th = threading.Thread(target=_do_refresh, daemon=True, name="ricette-refresh")
                th.start()
        if wait and th is not None:
            th.join()
        return _catalog_status()

    def _auto_refresh() -> None:
        st = _catalog_status()
        if not st["refreshing"] and (not st["total"] or not st["updated_at"] or time.time() - st["updated_at"] > 86400):
            _start_refresh()

    @gs.route("catalog/status")
    def catalog_status():
        _auto_refresh()
        return _catalog_status()

    @gs.route("catalog/refresh", methods=("POST",))
    def catalog_refresh(body: dict | None = Body(None)):
        return _start_refresh()

    gs.job("sync-ricette", lambda log=gs.log: _start_refresh(wait=True), every=6 * 3600)
