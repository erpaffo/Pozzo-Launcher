"""Ponte Kodi <-> Pozzo Media: addon.xml, canali Stream4me/Alfa, stream universali e shim xbmc*.

Solo libreria standard + bs4/httpx. L'esecuzione del codice di un addon avviene
esclusivamente in `run_kodi_addon_directory`, su richiesta esplicita del chiamante.
"""
from __future__ import annotations

import ast
import hashlib
import html as _html_mod
import io
import json
import re
import runpy
import shutil
import sys
import tempfile
import time
import types
import urllib.parse
import warnings
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

import httpx
from bs4 import BeautifulSoup

__all__ = [
    "parse_addon_xml",
    "extract_stream_urls",
    "parse_kodi_channel",
    "run_kodi_addon_directory",
    "normalize_github_zip_url",
    "install_kodi_addon",
    "is_direct_stream",
    "STREAM4ME_DEFAULT_URL",
    "get_stream4me_sections",
    "find_stream4me_dir",
    "list_stream4me_providers",
    "scrape_channel_items",
    "scrape_channel_episodes",
    "browse_stream4me_channel",
    "resolve_channel_stream",
]

STREAM4ME_DEFAULT_URL = "https://github.com/Stream4me/addon"
SOURCE = "ricette-web"
DIRECT_EXTS = (".mp4", ".webm", ".m4v", ".ogv", ".mp3", ".flac", ".ogg", ".m4a", ".wav")
PRIORITY = {"direct": 0, "hls": 1, "embed": 2}
AD_TOKENS = (
    "doubleclick", "googlesyndication", "googleadservices", "adservice",
    "adsystem", "facebook", "amazon-adsystem",
    "a-ads.com", "ad.a-ads", "exoclick", "popads", "popcash",
    "juicyads", "propellerads", "magsrv", "realsrv", "syndication",
    "adsterra", "hilltopads", "clickadu", "trafic", "histats",
    "yandex", "chatango", "disqus", "recaptcha", "cloudflare",
)
CHANNEL_SUFFIXES = (".json", ".py")
DEFAULT_ACTIVE_PROVIDER_IDS = ("animeunity", "animeworld", "streamingcommunity", "altadefinizione01")

_JS_KV_RE = re.compile(r"""(?is)\b(?:file|src|url|source)\s*:\s*["']([^"']+)["']""")
_JS_SOURCES_RE = re.compile(r"""(?is)["']?sources["']?\s*:\s*\[([^\]]*)\]""")
_QUOTED_RE = re.compile(r"""["']([^"']+)["']""")
_RAW_URL_RE = re.compile(
    r"""(?i)https?://[^\s"'<>\\]+\.(?:m3u8|mp4|webm|m4v|ogv|mp3|flac|ogg|m4a|wav)(?:\?[^\s"'<>\\]*)?"""
)
_GH_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?/?$", re.I
)
_AD_URL_RE = re.compile(r"(?i)(?:^https?://ad\.|/ads?/|/banner|[?&]size=\d+x\d+)")


# ---------------------------------------------------------------- helper
def _normalize_provider_host(host: str) -> str:
    if not host:
        return ""
    return re.sub(r"(?i)\banimeunity\.(?:so|tv)\b", "animeunity.co", str(host).strip())


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _resolve(url: str, base_url: str = "") -> str:
    """Normalizza un URL (anche relativo/protocol-relative); "" se non riproducibile."""
    url = (url or "").strip()
    if not url or url.lower().startswith(("javascript:", "data:", "blob:", "about:", "#")):
        return ""
    if url.startswith("//"):
        scheme = urllib.parse.urlparse(base_url).scheme or "https"
        url = f"{scheme}:{url}"
    return urllib.parse.urljoin(base_url, url) if base_url else url


def _classify(url: str) -> str | None:
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(".m3u8") or "/hls/" in path:
        return "hls"
    if path.endswith(DIRECT_EXTS):
        return "direct"
    return None


def is_direct_stream(url: str) -> bool:
    """True per i contenitori che il browser riproduce nativamente."""
    return _classify(_resolve(url)) == "direct"


def _is_ad(url: str) -> bool:
    low = (url or "").lower()
    if any(token.lower() in low for token in AD_TOKENS):
        return True
    return bool(_AD_URL_RE.search(url or ""))


def _tag_label(tag) -> str:
    for attr in ("title", "label", "aria-label"):
        val = tag.get(attr)
        if val:
            return str(val).strip()
    parent = tag.parent
    if parent is not None and getattr(parent, "name", None) in ("video", "audio"):
        for attr in ("title", "label"):
            val = parent.get(attr)
            if val:
                return str(val).strip()
    return str(tag.name)


def _duration_seconds(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return int(float(text))
    total = 0
    for part in text.split(":"):
        if not part.strip().isdigit():
            return None
        total = total * 60 + int(part)
    return total


def _year(value) -> int | None:
    if value is None or value == "":
        return None
    m = re.match(r"\s*(\d{4})", str(value))
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- addon.xml
def parse_addon_xml(xml_text: str) -> dict:
    """Legge addon.xml di Kodi. ValueError su XML malformato o id/name mancanti."""
    try:
        root = ET.fromstring(xml_text or "")
    except ET.ParseError as exc:
        raise ValueError(f"addon.xml malformato: {exc}") from exc
    if _localname(root.tag) != "addon":
        raise ValueError("addon.xml senza tag <addon>")
    addon_id = (root.get("id") or "").strip()
    name = (root.get("name") or "").strip()
    if not addon_id or not name:
        raise ValueError("addon.xml senza attributi 'id' o 'name'")

    entrypoint = "default.py"
    summary = ""
    description = ""
    provides: list[str] = []
    for ext in root:
        if _localname(ext.tag) != "extension":
            continue
        point = ext.get("point") or ""
        if point == "xbmc.python.pluginsource":
            entrypoint = (ext.get("library") or "").strip() or "default.py"
        for child in ext:
            tag = _localname(child.tag)
            text = (child.text or "").strip()
            if tag == "provides" and text:
                provides = text.split()
            elif point == "xbmc.addon.metadata" and tag == "summary" and text and not summary:
                summary = text
            elif point == "xbmc.addon.metadata" and tag == "description" and text and not description:
                description = text

    return {
        "id": addon_id,
        "name": name,
        "version": (root.get("version") or "").strip(),
        "entrypoint": entrypoint,
        "summary": summary or description,
        "provides": provides,
    }


# ---------------------------------------------------------------- stream universali
def extract_stream_urls(html_text: str, base_url: str = "") -> list[dict]:
    """Estrae stream riproducibili da tag media, iframe e config di player JS."""
    html = html_text or ""
    soup = BeautifulSoup(html, "html.parser")
    found: list[tuple[str, str, str]] = []

    for tag in soup.find_all(["video", "audio", "source"]):
        for attr in ("src", "data-src"):
            url = _resolve(tag.get(attr) or "", base_url)
            kind = _classify(url) if url else None
            if kind:
                found.append((url, kind, _tag_label(tag)))
                break

    for tag in soup.find_all("iframe"):
        url = _resolve(tag.get("src") or tag.get("data-src") or "", base_url)
        if not url or _is_ad(url):
            continue
        label = (tag.get("title") or "").strip() or urllib.parse.urlparse(url).netloc or "iframe"
        found.append((url, _classify(url) or "embed", label))

    for match in _JS_KV_RE.finditer(html):
        url = _resolve(match.group(1), base_url)
        kind = _classify(url) if url else None
        if kind:
            found.append((url, kind, "player"))

    for block in _JS_SOURCES_RE.finditer(html):
        for quoted in _QUOTED_RE.finditer(block.group(1)):
            url = _resolve(quoted.group(1), base_url)
            kind = _classify(url) if url else None
            if kind:
                found.append((url, kind, "player"))

    for match in _RAW_URL_RE.finditer(html):
        url = _resolve(match.group(0), base_url)
        kind = _classify(url) if url else None
        if kind:
            found.append((url, kind, "inline"))

    best: dict[str, tuple[str, str]] = {}
    for url, kind, label in found:
        prev = best.get(url)
        if prev is None or PRIORITY[kind] < PRIORITY[prev[0]]:
            best[url] = (kind, label)
    ordered = sorted(best.items(), key=lambda kv: PRIORITY[kv[1][0]])
    return [{"url": url, "kind": kind, "label": label} for url, (kind, label) in ordered]


# ---------------------------------------------------------------- canali Stream4me / Alfa
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        value = list(value.keys())
    out: list[str] = []
    for item in value if isinstance(value, (list, tuple)) else [value]:
        if isinstance(item, dict):
            item = item.get("name") or item.get("title") or item.get("id") or ""
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _urlish(text: str) -> bool:
    low = text.strip().lower()
    return low.startswith(("http://", "https://", "/", "?", "./")) or any(
        token in low for token in ("%s", "{", "=")
    )


def _candidate_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in ("url", "search_url", "search", "link", "pattern", "path"):
            if isinstance(value.get(key), str):
                yield value[key]
        for item in value.values():
            if isinstance(item, str):
                yield item
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _candidate_strings(item)


def _search_url(value, host: str) -> str:
    for cand in _candidate_strings(value):
        if _urlish(cand):
            return _resolve(cand, host)
    return ""


def _channel_from_dict(data: dict, channel_id: str) -> dict:
    name = str(data.get("name") or data.get("title") or channel_id or "").strip()
    categories = _str_list(
        data.get("categories") or data.get("category") or data.get("genres")
    )
    host = str(data.get("host") or data.get("base") or data.get("base_url") or "").strip()
    search_url = _search_url(
        data.get("find_videos") or data.get("search") or data.get("find") or data.get("search_url"),
        host,
    )
    if not host and search_url:
        parsed = urllib.parse.urlparse(search_url)
        host = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else ""
    return {
        "id": str(data.get("id") or channel_id or _slug(name) or "channel"),
        "name": name or channel_id or str(data.get("id") or "channel"),
        "host": host,
        "categories": categories,
        "search_url": search_url,
    }


def _channel_from_python(text: str, channel_id: str) -> dict:
    def grab(pattern: str, group: int = 1) -> str:
        m = re.search(pattern, text)
        return (m.group(group) or "").strip() if m else ""

    name = grab(r"""(?im)^\s{0,3}name\s*=\s*["']([^"']+)["']""")
    host = grab(r"""(?im)^\s{0,3}host\s*=\s*["']([^"']+)["']""")
    categories: list[str] = []
    cat_m = re.search(r"""(?is)\bcategories?\s*=\s*(\[[^\]]*\])""", text)
    if cat_m:
        try:
            categories = _str_list(json.loads(cat_m.group(1)))
        except json.JSONDecodeError:
            categories = _str_list([q.group(1) for q in _QUOTED_RE.finditer(cat_m.group(1))])
    else:
        categories = _str_list(grab(r"""(?i)\bcategories?\s*=\s*["']([^"']+)["']"""))

    search_url = ""
    for key in ("find_videos", "search_url", "search", "pattern"):
        pattern = rf"""(?is)\b{key}\s*=\s*(?:["']([^"']+)["']|\{{([^}}]*)\}})"""
        m = re.search(pattern, text)
        if not m:
            continue
        if m.group(1):
            search_url = _search_url(m.group(1), host)
        else:
            strings = [q.group(1) for q in _QUOTED_RE.finditer(m.group(2) or "")]
            search_url = _search_url(strings, host)
        if search_url:
            break

    if not host and search_url:
        parsed = urllib.parse.urlparse(search_url)
        host = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else ""
    return {
        "id": channel_id or _slug(name) or "channel",
        "name": name or channel_id or "channel",
        "host": host,
        "categories": categories,
        "search_url": search_url,
    }


def parse_kodi_channel(raw_text: str, channel_id: str = "") -> dict:
    """Normalizza un canale Kodi in JSON (Stream4me/Alfa) o in file .py con costanti."""
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("file canale vuoto")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # i canali Stream4me possono avere un'intestazione di commenti prima dell'oggetto
        start = text.find("{")
        try:
            data = json.loads(text[start:]) if start >= 0 else None
        except json.JSONDecodeError:
            data = None
    if isinstance(data, dict):
        return _channel_from_dict(data, channel_id)
    return _channel_from_python(text, channel_id)


def _domain_map(addon_root: Path) -> dict[str, str]:
    """Host correnti degli addon tipo Stream4me: `<addon>/channels.json` -> `direct.<id>`."""
    try:
        data = json.loads((addon_root / "channels.json").read_text("utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    direct = data.get("direct") if isinstance(data, dict) else None
    if not isinstance(direct, dict):
        return {}
    return {str(k): _normalize_provider_host(str(v)) for k, v in direct.items() if isinstance(v, str) and v}


def _channel_file_meta(path: Path, hosts: dict[str, str] | None = None) -> dict | None:
    """Canale da un file .json (descrittore) o da un .py senza gemello .json.

    None se il file non è un canale utilizzabile: helper `_*.py`, resolver con un
    descrittore .json accanto, canali `"active": false` (nascosti anche in Kodi).
    """
    if path.stem.startswith("_") or path.suffix.lower() not in CHANNEL_SUFFIXES:
        return None
    hosts = hosts or {}
    raw = path.read_text("utf-8", errors="replace")
    try:
        channel = parse_kodi_channel(raw, channel_id=path.stem)
    except ValueError:
        return None
    if path.suffix.lower() == ".json":
        channel["host"] = channel["host"] or hosts.get(path.stem, "")
        if not channel["host"] and path.with_suffix(".py").is_file():
            try:
                sibling = parse_kodi_channel(path.with_suffix(".py").read_text("utf-8", errors="replace"))
            except ValueError:
                sibling = {}
            channel["host"] = sibling.get("host") or ""
            channel["search_url"] = channel["search_url"] or sibling.get("search_url") or ""
        if channel["host"] and channel["search_url"].startswith("/"):
            channel["search_url"] = urllib.parse.urljoin(channel["host"], channel["search_url"])
        try:
            if json.loads(raw).get("active") is False:
                return None
        except (json.JSONDecodeError, AttributeError):
            pass
        return channel if (channel["host"] or channel["search_url"]) else None
    if path.with_suffix(".json").is_file() or not (channel["host"] or channel["search_url"]):
        return None
    return channel


# ---------------------------------------------------------------- shim xbmc*
def _noop(*_args, **_kwargs):
    return None


def _missing_attr(name: str):
    if name.startswith("__"):
        raise AttributeError(name)
    return _noop


class _Dummy:
    def __init__(self, *_args, **_kwargs):
        pass

    def __getattr__(self, _name: str):
        return _noop


class _ListItem:
    def __init__(self, label="", label2="", iconImage="", thumbnailImage="", path=""):
        self._label = str(label or "")
        self._label2 = str(label2 or "")
        self._art: dict[str, str] = {}
        self._info: dict = {}
        self._props: dict[str, str] = {}
        self._path = str(path or "")
        if thumbnailImage:
            self._art["thumb"] = str(thumbnailImage)
        if iconImage:
            self._art["icon"] = str(iconImage)

    def getLabel(self) -> str:
        return self._label

    def setLabel(self, value) -> None:
        self._label = str(value or "")

    def getLabel2(self) -> str:
        return self._label2

    def setLabel2(self, value) -> None:
        self._label2 = str(value or "")

    def setArt(self, art: dict) -> None:
        self._art.update({str(k): str(v) for k, v in (art or {}).items() if v})

    def getArt(self, key: str | None = None):
        return self._art.get(key, "") if key else dict(self._art)

    def setInfo(self, _type, infoLabels: dict) -> None:
        self._info.update(infoLabels or {})

    def setProperty(self, key, value) -> None:
        self._props[str(key)] = str(value)

    def getProperty(self, key) -> str:
        return self._props.get(str(key), "")

    def setPath(self, path) -> None:
        self._path = str(path or "")

    def getPath(self) -> str:
        return self._path

    # shortcut: metodi ListItem non implementati restano no-op, bastano per elencare una directory
    def __getattr__(self, _name: str):
        return _noop


class _Addon:
    def __init__(self, meta: dict, addon_dir: Path):
        self._meta = meta
        self._dir = addon_dir

    def getAddonInfo(self, key: str) -> str:
        key = str(key or "")
        if key == "path":
            return str(self._dir)
        if key == "profile":
            return str(self._dir / ".profile")
        if key == "icon":
            return str(self._dir / "icon.png")
        if key in ("id", "name", "version", "summary"):
            return str(self._meta.get(key) or "")
        return ""

    def getSetting(self, _key) -> str:
        return ""

    def getSettingBool(self, _key) -> bool:
        return False

    def setSetting(self, *_args) -> None:
        return None

    def getLocalizedString(self, _id) -> str:
        return ""

    # shortcut: attributi Addon non implementati restano no-op
    def __getattr__(self, _name: str):
        return _noop


class _VfsFile:
    def __init__(self, path, mode="r"):
        self._f = open(path, mode, encoding=None if "b" in mode else "utf-8")

    def read(self, size=-1):
        return self._f.read(size)

    def write(self, data):
        return self._f.write(data)

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


def _make_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    mod.__dict__["__getattr__"] = _missing_attr
    return mod


def _build_shims(addon_dir: Path, meta: dict, captured: list) -> dict[str, types.ModuleType]:
    def add_directory_item(handle, url, listitem, isFolder=False, totalItems=0):
        captured.append(["dir", str(url or ""), listitem, bool(isFolder)])
        return True

    def add_directory_items(handle, items, totalItems=0):
        for url, listitem, is_folder in items:
            add_directory_item(handle, url, listitem, is_folder)
        return True

    def set_resolved_url(handle, succeeded, listitem):
        path = listitem.getPath() if hasattr(listitem, "getPath") else ""
        captured.append(["resolved" if succeeded else "failed", str(path or ""), listitem, False])

    def vfs_exists(path) -> bool:
        return Path(str(path)).exists()

    def vfs_listdir(path):
        base = Path(str(path))
        if not base.is_dir():
            return [], []
        dirs = [p.name for p in base.iterdir() if p.is_dir()]
        files = [p.name for p in base.iterdir() if p.is_file()]
        return dirs, files

    def vfs_mkdirs(path) -> bool:
        Path(str(path)).mkdir(parents=True, exist_ok=True)
        return True

    xbmc = _make_module(
        "xbmc",
        log=_noop,
        executebuiltin=_noop,
        sleep=_noop,
        getCondVisibility=lambda *_a, **_k: False,
        getInfoLabel=lambda *_a, **_k: "",
        getLocalizedString=lambda *_a, **_k: "",
        getLanguage=lambda *_a, **_k: "Italian",
        getSkinDir=lambda *_a, **_k: "skin.estuary",
        translatePath=lambda path="": str(path or ""),
        Player=_Dummy,
        Monitor=_Dummy,
    )
    xbmcgui = _make_module(
        "xbmcgui",
        ListItem=_ListItem,
        Dialog=_Dummy,
        DialogProgress=_Dummy,
        DialogProgressBG=_Dummy,
        NOTIFICATION_INFO="info",
        NOTIFICATION_ERROR="error",
    )
    xbmcplugin = _make_module(
        "xbmcplugin",
        addDirectoryItem=add_directory_item,
        addDirectoryItems=add_directory_items,
        setResolvedUrl=set_resolved_url,
    )
    xbmcaddon = _make_module("xbmcaddon", Addon=lambda *_a, **_k: _Addon(meta, addon_dir))
    xbmcvfs = _make_module(
        "xbmcvfs",
        exists=vfs_exists,
        listdir=vfs_listdir,
        mkdirs=vfs_mkdirs,
        translatePath=lambda path="": str(path or ""),
        File=_VfsFile,
    )
    return {
        "xbmc": xbmc,
        "xbmcgui": xbmcgui,
        "xbmcplugin": xbmcplugin,
        "xbmcaddon": xbmcaddon,
        "xbmcvfs": xbmcvfs,
    }


def _addon_meta_from_dir(root: Path) -> dict:
    xml_path = root / "addon.xml"
    if not xml_path.is_file():
        return {}
    try:
        return parse_addon_xml(xml_path.read_text("utf-8", errors="replace"))
    except ValueError:
        return {}


def _item_from_capture(addon_id: str, idx: int, capture: list) -> dict:
    kind_capture, url, listitem, is_folder = capture
    info = getattr(listitem, "_info", {}) or {}
    art = getattr(listitem, "_art", {}) or {}
    title = (listitem.getLabel() if hasattr(listitem, "getLabel") else "") or str(info.get("title") or "")
    media = str(info.get("mediatype") or "").lower()
    if media in ("episode", "tvshow") or info.get("season") or info.get("episode"):
        kind = "episodio"
    elif media in ("song", "musicvideo", "album", "music"):
        kind = "brano"
    else:
        kind = "film"
    poster = art.get("poster") or art.get("thumb") or art.get("icon") or art.get("fanart") or ""
    item = {
        "id": f"kodi:{addon_id}:{idx}",
        "kind": kind,
        "title": title or Path(urllib.parse.urlparse(url).path).name,
        "poster": str(poster),
        "overview": str(info.get("plot") or info.get("plotoutline") or ""),
        "source": SOURCE,
        "url": url,
        "stream_url": url if (kind_capture == "resolved" or not is_folder) else "",
    }
    year = _year(info.get("year"))
    if year:
        item["year"] = year
    duration = _duration_seconds(info.get("duration"))
    if duration:
        item["duration"] = duration
    return item


def _channel_items(paths: list[Path], addon_id: str, query: str, hosts: dict[str, str]) -> list[dict]:
    needle = (query or "").strip().lower()
    items: list[dict] = []
    for path in paths:
        channel = _channel_file_meta(path, hosts)
        if channel is None:
            continue
        haystack = " ".join([channel["id"], channel["name"], *channel["categories"]]).lower()
        if needle and needle not in haystack:
            continue
        overview = f"Canale Kodi: {channel['name']}"
        if channel["categories"]:
            overview += f" ({', '.join(channel['categories'])})"
        items.append({
            "id": f"kodi:{addon_id}:{channel['id']}",
            "kind": "film",
            "title": channel["name"] or channel["id"],
            "poster": "",
            "overview": overview,
            "source": SOURCE,
            "url": channel["search_url"] or channel["host"],
            "stream_url": "",
        })
    return items


def run_kodi_addon_directory(
    addon_dir: Path, handle_url: str = "plugin://addon/", query: str = ""
) -> list[dict]:
    """Elenca i contenuti di un addon locale (canali Stream4me o entrypoint con shim xbmc)."""
    root = Path(addon_dir)
    if not root.is_dir():
        raise ValueError(f"cartella addon inesistente: {root}")
    meta = _addon_meta_from_dir(root)
    addon_id = str(meta.get("id") or root.name)

    channels_dir = root / "channels"
    channel_files = (
        [p for p in sorted(channels_dir.iterdir()) if p.suffix.lower() in CHANNEL_SUFFIXES]
        if channels_dir.is_dir()
        else []
    )
    if channel_files:
        return _channel_items(channel_files, addon_id, query, _domain_map(root))

    entrypoint = str(meta.get("entrypoint") or "default.py").replace("\\", "/")
    script = (root / entrypoint).resolve()
    if root.resolve() not in script.parents:
        raise ValueError(f"entrypoint fuori dalla cartella addon: {entrypoint}")
    if not script.is_file():
        return []

    target = handle_url
    if query:
        sep = "&" if "?" in target else "?"
        target = f"{target}{sep}{urllib.parse.urlencode({'q': query})}"

    captured: list = []
    shims = _build_shims(root, meta, captured)
    saved = {name: sys.modules.get(name) for name in shims}
    saved_argv = sys.argv[:]
    sys.modules.update(shims)
    sys.argv = [target, "-1", target]
    sys.path.insert(0, str(root))
    try:
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv[:] = saved_argv
        try:
            sys.path.remove(str(root))
        except ValueError:
            pass
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return [_item_from_capture(addon_id, idx, cap) for idx, cap in enumerate(captured)]


# ---------------------------------------------------------------- installazione addon
def normalize_github_zip_url(url: str) -> str:
    """Trasforma un URL di repository GitHub nell'URL dello zip del branch (master di default)."""
    match = _GH_RE.match((url or "").strip())
    if not match:
        return (url or "").strip()
    owner, repo, branch = match.groups()
    return f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch or 'master'}.zip"


def _safe_name(addon_id: str) -> str:
    name = str(addon_id).strip()
    if not name or name in (".", "..") or any(ch in name for ch in ("/", "\\", ":", "\0")):
        raise ValueError(f"id addon non valido: {addon_id!r}")
    return name


def _extract_zip(data: bytes, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"archivio zip non valido: {exc}") from exc
    with archive:
        for info in archive.infolist():
            name = info.filename
            if (
                PurePosixPath(name).is_absolute()
                or ".." in PurePosixPath(name).parts
                or name.startswith(("\\", "/"))
                or re.match(r"^[A-Za-z]:", name)
            ):
                raise ValueError(f"zip non sicuro (ZipSlip): {name}")
        archive.extractall(dest)
    return dest


def _locate_addon_xml(base: Path) -> tuple[dict, Path]:
    candidates = sorted(
        base.rglob("addon.xml"), key=lambda p: (len(p.relative_to(base).parts), str(p))
    )
    if not candidates:
        raise ValueError("addon.xml non trovato")
    error = ""
    for xml_path in candidates:
        try:
            return parse_addon_xml(xml_path.read_text("utf-8", errors="replace")), xml_path.parent
        except (OSError, ValueError) as exc:
            error = str(exc)
    raise ValueError(f"nessun addon.xml valido: {error}")


def _fetch_addon_zip(url: str, fetcher=None) -> bytes:
    if not re.match(r"^https?://", url, re.I):
        raise ValueError(f"sorgente addon non valida: {url}")
    candidates = [normalize_github_zip_url(url)]
    if candidates[0].endswith("/master.zip"):
        candidates.append(candidates[0][: -len("master.zip")] + "main.zip")
    last: object = "nessun tentativo"
    for candidate in candidates:
        try:
            if fetcher is not None:
                data = fetcher(candidate)
            else:
                response = httpx.get(candidate, follow_redirects=True, timeout=30.0)
                response.raise_for_status()
                data = response.content
            if data:
                return bytes(data)
            last = "risposta vuota"
        except Exception as exc:  # rete o 404 sul branch: si prova il successivo
            last = exc
    raise ValueError(f"download addon fallito da {url}: {last}")


def install_kodi_addon(source: str | Path, addons_root: Path, fetcher=None) -> dict:
    """Installa un addon da cartella, zip locale o URL (GitHub). Blocca lo ZipSlip."""
    root = Path(addons_root)
    root.mkdir(parents=True, exist_ok=True)
    local = source if isinstance(source, Path) else Path(str(source))
    with tempfile.TemporaryDirectory(prefix="pozzo-kodi-") as tmp:
        work = Path(tmp) / "addon"
        if local.is_dir():
            shutil.copytree(local, work, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        elif local.is_file() and local.suffix.lower() == ".zip":
            _extract_zip(local.read_bytes(), work)
        elif re.match(r"^https?://", str(source), re.I):
            _extract_zip(_fetch_addon_zip(str(source), fetcher), work)
        else:
            raise ValueError(f"sorgente addon non valida: {source}")

        meta, addon_root = _locate_addon_xml(work)
        channels: list[dict] = []
        channels_dir = addon_root / "channels"
        if channels_dir.is_dir():
            hosts = _domain_map(addon_root)
            for path in sorted(channels_dir.iterdir()):
                channel = _channel_file_meta(path, hosts)
                if channel is not None:
                    channels.append(channel)
        dest = root / _safe_name(meta["id"])
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(addon_root, dest)

    _clear_stream4me_caches()
    return {
        "id": meta["id"],
        "name": meta["name"],
        "version": meta["version"],
        "path": str(dest),
        "channels": channels,
    }


# ---------------------------------------------------------------- sezioni Stream4me
_STREAM4ME_SIMULATED: dict[str, list[dict]] = {
    "film": [
        {
            "id": "stream4me:film:nuove-uscite",
            "kind": "film",
            "title": "Nuove Uscite Film",
            "poster": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=400",
            "overview": "Film in streaming: nuove uscite, novità cinema e prime visioni",
            "source": SOURCE,
            "source_label": "Stream4me",
            "url": "https://stream4me.example/film/nuove-uscite",
            "stream_url": "",
        },
        {
            "id": "stream4me:film:top-visti",
            "kind": "film",
            "title": "Top Film Più Visti",
            "poster": "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=400",
            "overview": "I film più visti e popolari della settimana su Stream4me",
            "source": SOURCE,
            "source_label": "Stream4me",
            "url": "https://stream4me.example/film/top-visti",
            "stream_url": "",
        },
    ],
    "serie": [
        {
            "id": "stream4me:serie:serie-popolari",
            "kind": "film",
            "title": "Serie TV Popolari",
            "poster": "https://images.unsplash.com/photo-1522869635100-9f4c5e86aa37?w=400",
            "overview": "Serie TV in streaming complete di stagioni ed episodi",
            "source": SOURCE,
            "source_label": "Stream4me",
            "url": "https://stream4me.example/serie/popolari",
            "stream_url": "",
        },
        {
            "id": "stream4me:serie:aggiornamenti",
            "kind": "film",
            "title": "Nuove Stagioni ed Episodi",
            "poster": "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=400",
            "overview": "Ultimi episodi e nuove stagioni aggiunte a Stream4me",
            "source": SOURCE,
            "source_label": "Stream4me",
            "url": "https://stream4me.example/serie/novita",
            "stream_url": "",
        },
    ],
    "canali": [
        {
            "id": "stream4me:canali:live-tv",
            "kind": "film",
            "title": "Canali TV Nazionali",
            "poster": "https://images.unsplash.com/photo-1461151304267-38535e780c79?w=400",
            "overview": "Canali TV italiani e internazionali in diretta streaming",
            "source": SOURCE,
            "source_label": "Stream4me",
            "url": "https://stream4me.example/canali/live",
            "stream_url": "https://cdn.example/live/canali.m3u8",
        },
    ],
    "animazione": [
        {
            "id": "stream4me:animazione:anime-streaming",
            "kind": "film",
            "title": "Anime e Cartoni",
            "poster": "https://images.unsplash.com/photo-1578632767115-351597cf2477?w=400",
            "overview": "Serie anime giapponesi e cartoni animati in streaming",
            "source": SOURCE,
            "source_label": "Stream4me",
            "url": "https://stream4me.example/anime",
            "stream_url": "",
        },
    ],
}


def _classify_channel(categories: list[str], name: str) -> list[str]:
    cats = [c.lower() for c in categories]
    text = (name + " " + " ".join(cats)).lower()
    sections: list[str] = []
    if any(k in text for k in ("anime", "animazione", "cartoni", "animation", "manga", "toon")):
        sections.append("animazione")
    if any(k in text for k in ("canali", "live", "iptv", "diretta", "tv live", "tv streaming", "sport")):
        sections.append("canali")
    if any(k in text for k in ("serie", "series", "fiction", "telefilm", "episodes", "show", "stagioni")):
        sections.append("serie")
    if any(k in text for k in ("film", "movie", "cinema", "pellicole")) or not sections:
        sections.append("film")
    return sections


def get_stream4me_sections(addon_dir: Path | str | None = None) -> dict[str, list[dict]]:
    """Estrae o simula le categorie principali di Stream4me (film, serie, canali, animazione)."""
    sections: dict[str, list[dict]] = {k: [] for k in _STREAM4ME_SIMULATED}
    root = Path(addon_dir) if addon_dir is not None else None
    if root is not None:
        if not (root / "addon.xml").is_file():
            found = find_stream4me_dir(root)
            if found is not None:
                root = found
        if root.is_dir():
            channels_dir = root / "channels"
            channel_files = (
                [p for p in sorted(channels_dir.iterdir()) if p.suffix.lower() in CHANNEL_SUFFIXES]
                if channels_dir.is_dir()
                else []
            )
            if channel_files:
                hosts = _domain_map(root)
                meta = _addon_meta_from_dir(root)
                addon_id = str(meta.get("id") or root.name)
                for path in channel_files:
                    ch = _channel_file_meta(path, hosts)
                    if ch is None:
                        continue
                    item = {
                        "id": f"kodi:{addon_id}:{ch['id']}",
                        "kind": "film",
                        "title": ch["name"] or ch["id"],
                        "poster": str(ch.get("poster") or ""),
                        "overview": f"Stream4me: {ch['name']}" + (f" ({', '.join(ch['categories'])})" if ch.get("categories") else ""),
                        "source": SOURCE,
                        "source_label": "Stream4me",
                        "url": ch.get("search_url") or ch.get("host") or "",
                        "stream_url": str(ch.get("stream_url") or ""),
                    }
                    for sec in _classify_channel(ch.get("categories") or [], ch.get("name") or ""):
                        if sec in sections:
                            sections[sec].append(item)
            elif (root / "addon.xml").is_file():
                for it in run_kodi_addon_directory(root):
                    item = dict(it)
                    item["source"] = SOURCE
                    item["source_label"] = "Stream4me"
                    if item.get("kind") == "episodio":
                        sections["serie"].append(item)
                    elif "live" in item.get("url", "").lower() or item.get("stream_url", "").endswith(".m3u8"):
                        sections["canali"].append(item)
                    else:
                        sections["film"].append(item)

    # shortcut: se una sezione non ha elementi estratti, usa i preset simulati, espandibile con repository remoto
    for sec, default_items in _STREAM4ME_SIMULATED.items():
        if not sections[sec]:
            sections[sec] = [dict(it) for it in default_items]

    return sections


# ---------------------------------------------------------------- provider browser e scraper Stream4me
_PROVIDER_CACHE: dict[tuple[str, bool], list[dict]] = {}
_BROWSE_CACHE: dict[tuple[str, str], tuple[float, dict]] = {}
_BROWSE_TTL = 600.0
_SCRAPE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
_NAV_SKIP_RE = re.compile(
    r"^(?:home|contatti|dmca|privacy|login|registrati|avanti|indietro|pagina|next|prev|previous|cerca|search|menu|faq|disclaimer|cookie|terms|\d+|«|»|‹|›|\.\.\.)$",
    re.I,
)


def _clear_stream4me_caches() -> None:
    _PROVIDER_CACHE.clear()
    _BROWSE_CACHE.clear()


def find_stream4me_dir(addons_root: Path | str | None) -> Path | None:
    """Individua la cartella dell'addon Stream4me (plugin.video.s4me, plugin.video.stream4me, ecc.)."""
    if not addons_root:
        return None
    root = Path(addons_root)
    if not root.is_dir():
        return None
    if (root / "channels.json").is_file() or (root / "channels").is_dir():
        return root
    for cand in ("plugin.video.s4me", "plugin.video.stream4me", "stream4me"):
        d = root / cand
        if d.is_dir():
            return d
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if (d / "channels.json").is_file() or (d / "channels").is_dir():
            return d
    return None


def _extract_menus_from_py(py_text: str) -> list[dict]:
    menus: list[dict] = []
    seen_paths: set[str] = set()

    def _add(label: str, path: str) -> None:
        label = re.sub(r"\[/?(?:COLOR|B|I)[^\]]*\]", "", label or "").strip()
        path = (path or "").strip()
        if not path or not (path.startswith("/") or path.startswith("?") or path.startswith("http")):
            return
        if path in seen_paths:
            return
        seen_paths.add(path)
        menus.append({"label": label or "Catalogo", "path": path})

    if py_text:
        for m in re.finditer(
            r"""\(\s*['"]([^'"]{2,45})['"]\s*,\s*\[?\s*['"]([^'"]+)['"]""", py_text
        ):
            lbl, pth = m.group(1), m.group(2)
            if any(k in lbl.lower() for k in ("cerca", "search")):
                continue
            _add(lbl, pth)

        label_map = {
            "movie": "Film",
            "film": "Film",
            "tvshow": "Serie TV",
            "serie": "Serie TV",
            "anime": "Anime",
            "cartoni": "Cartoni",
            "novita": "Novità",
            "peliculas": "Film",
        }
        for var, lbl in label_map.items():
            m = re.search(rf"""(?im)^\s*{var}\s*=\s*(?:\[\s*)?['"]([^'"]+)['"]""", py_text)
            if m:
                _add(lbl, m.group(1))

    if not menus:
        menus.append({"label": "Catalogo", "path": "/"})
    return menus


def _extract_py_host_and_search(py_text: str, host: str) -> tuple[str, str]:
    if not py_text:
        return host, ""
    if not host:
        for pat in (
            r"""(?im)^\s*(?:host|HOST|ALT_HOST)\s*=\s*['"](https?://[^'"]+)['"]""",
            r"""['"](https?://[a-zA-Z0-9.-]+\.[a-z]{2,10})/?['"]""",
        ):
            m = re.search(pat, py_text)
            if m:
                host = m.group(1).rstrip("/")
                break

    search_url = ""
    for pat in (
        r"""['"]([^'"]*(?:\?s=|\?do=search[^'"]*story=|/animelist\?search=|/filter\?keyword=|/search\?[^'"]*q=)[^'"]*)['"]""",
    ):
        m = re.search(pat, py_text)
        if m:
            cand = m.group(1)
            search_url = urllib.parse.urljoin(host + "/", cand) if host and cand.startswith(("/", "?")) else cand
            break
    return host, search_url


def list_stream4me_providers(addon_dir: Path | str | None, only_active: bool = True) -> list[dict]:
    """Elenca i canali/provider di Stream4me con host, categorie, menu e search_url (con cache in memoria)."""
    if not addon_dir:
        return []
    root = find_stream4me_dir(addon_dir) or Path(addon_dir)
    if not root.is_dir():
        return []
    cache_key = (str(root.resolve()), bool(only_active))
    if cache_key in _PROVIDER_CACHE:
        return _PROVIDER_CACHE[cache_key]

    channels_dir = root / "channels"
    if not channels_dir.is_dir():
        return []

    hosts = _domain_map(root)
    stems: dict[str, dict[str, Path]] = {}
    for p in sorted(channels_dir.iterdir()):
        if p.stem.startswith("_") or p.suffix.lower() not in CHANNEL_SUFFIXES:
            continue
        stems.setdefault(p.stem, {})[p.suffix.lower()] = p

    all_providers: list[tuple[dict, bool]] = []
    for cid, files in stems.items():
        json_p = files.get(".json")
        py_p = files.get(".py")
        data: dict = {}
        is_active = True
        if json_p is not None:
            raw_json = json_p.read_text("utf-8", errors="replace")
            try:
                data = json.loads(raw_json)
            except json.JSONDecodeError:
                start = raw_json.find("{")
                try:
                    data = json.loads(raw_json[start:]) if start >= 0 else {}
                except json.JSONDecodeError:
                    data = {}
            if isinstance(data, dict) and data.get("active") is False:
                is_active = False

        py_text = py_p.read_text("utf-8", errors="replace") if py_p is not None else ""
        base_meta: dict = {}
        if data:
            base_meta = _channel_from_dict(data, cid)
        elif py_text:
            base_meta = _channel_from_python(py_text, cid)
        else:
            continue

        host = _normalize_provider_host((base_meta.get("host") or hosts.get(cid) or "").rstrip("/"))
        py_host, py_search = _extract_py_host_and_search(py_text, host)
        host = _normalize_provider_host(host or py_host).rstrip("/")
        if not host and not base_meta.get("search_url"):
            continue

        search_url = _normalize_provider_host(base_meta.get("search_url") or py_search)
        if host and search_url and search_url.startswith(("/", "?")):
            search_url = urllib.parse.urljoin(host + "/", search_url)
        if not search_url and host:
            search_url = f"{host}/?s={{query}}"

        thumb = str(data.get("thumbnail") or data.get("poster") or "").strip() if isinstance(data, dict) else ""
        poster = thumb if thumb.startswith(("http://", "https://")) else ""

        menus = _extract_menus_from_py(py_text)
        if cid == "animeunity":
            menus = [
                {"label": "Ultimi Episodi", "path": "/"},
                {"label": "Archivio Anime", "path": "/archivio"},
            ]
        elif cid == "animeworld":
            search_url = f"{host}/filter?keyword={{query}}"
            menus = [
                {"label": "Ultimi Episodi", "path": "/updated"},
                {"label": "In Corso", "path": "/ongoing"},
                {"label": "Nuove Aggiunte", "path": "/newest"},
                {"label": "ITA", "path": "/filter?dub=1&sort=0"},
                {"label": "SUB-ITA", "path": "/filter?dub=0&sort=0"},
            ]
        elif cid == "animesaturn":
            search_url = f"{host}/filter?key={{query}}"

        provider = {
            "id": str(base_meta.get("id") or cid),
            "name": str(base_meta.get("name") or cid),
            "host": host,
            "categories": list(base_meta.get("categories") or []),
            "poster": poster,
            "menus": menus,
            "search_url": search_url,
            "active": is_active,
        }
        all_providers.append((provider, is_active))

    if only_active:
        curated_set = set(DEFAULT_ACTIVE_PROVIDER_IDS)
        filtered = [p for p, act in all_providers if act and p["id"] in curated_set]
        if not filtered:
            filtered = [p for p, act in all_providers if act]
        order_map = {name: idx for idx, name in enumerate(DEFAULT_ACTIVE_PROVIDER_IDS)}
        filtered.sort(key=lambda x: order_map.get(x["id"], 999))
    else:
        filtered = [p for p, _ in all_providers]

    _PROVIDER_CACHE[cache_key] = filtered
    return filtered


_BADGE_TITLE_RE = re.compile(
    r"^(?:dub|sub|ita|sub[\s-]*ita|dub\s+movie|dub\s+ova|dub\s+ona|dub\s+special|sub\s+movie|sub\s+ova|ova|ona|movie|tv|special|dettagli|guarda|play|watch|streaming|hd|full\s*hd|4k|\d+p|\d+)$",
    re.I,
)
_NOISE_DOMAINS = (
    "t.me/", "telegram.", "instagram.com", "facebook.com", "twitter.com",
    "x.com", "discord.", "youtube.com", "vk.com",
)
_NOISE_PATHS = (
    "/random", "/anime-casuale", "/wallpaper", "/sfondi", "/changelog",
    "/aggiornamenti", "/news", "/rss", "/feed", "/donate", "/staff", "/regolamento",
    "/login", "/register", "/contact", "/contatti", "/dmca", "/privacy", "/faq",
)
_NOISE_TITLES = {
    "anime casuale", "telegram", "instagram", "sfondi scaricabili",
    "aggiornamenti al sito", "discord", "facebook", "donazioni",
    "contatti", "lista anime", "archivio",
}


def _clean_title(raw: str) -> str:
    txt = _html_mod.unescape(raw or "")
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\[/?(?:COLOR|B|I)[^\]]*\]", "", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _infer_kind(url: str, title: str, channel_id: str = "") -> str:
    hay = f"{url} {title} {channel_id}".lower()
    if any(k in hay for k in ("serie", "tvshow", "stagione", "episod", "season", "anime", "toon", "cartoon", "sub-ita")):
        return "episodio"
    return "film"


def _is_noise_link(url: str, title: str, base_url: str) -> bool:
    t_strip = (title or "").strip()
    t_low = t_strip.lower()
    if len(t_strip) < 2 or _NAV_SKIP_RE.match(t_strip) or _BADGE_TITLE_RE.match(t_strip) or t_low in _NOISE_TITLES:
        return True
    u_clean = (url or "").rstrip("/")
    b_clean = (base_url or "").rstrip("/")
    if not u_clean or u_clean == b_clean:
        return True
    u_low = u_clean.lower()
    if any(dom in u_low for dom in _NOISE_DOMAINS):
        return True
    parsed = urllib.parse.urlparse(u_clean)
    path = parsed.path.lower().rstrip("/")
    if not path or path in _NOISE_PATHS or any(path.startswith(np + "/") or path == np for np in _NOISE_PATHS):
        return True
    if re.search(r"/(?:page|pagina)/\d+$", path) or re.search(r"[?&](?:page|paged)=\d+$", u_low):
        return True
    if any(seg in path for seg in ("/category/", "/genre/", "/genere/", "/tag/", "/anno/", "/year/", "/az-list")):
        if len(path.strip("/").split("/")) <= 2:
            return True
    return False


def _extract_patrons_from_py(py_source: str) -> list[str]:
    if not py_source:
        return []
    patrons: list[str] = []

    def _str_val(node) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if hasattr(ast, "Str") and isinstance(node, getattr(ast, "Str")):
            return node.s
        if isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                sv = _str_val(v)
                if sv is not None:
                    parts.append(sv)
            return "".join(parts)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = _str_val(node.left)
            right = _str_val(node.right)
            if left is not None and right is not None:
                return left + right
        return None

    def _walk_block(stmts: list, env: dict[str, str]) -> None:
        local_env = dict(env)
        for stmt in stmts:
            if isinstance(stmt, ast.Assign):
                val = _str_val(stmt.value)
                if val is not None:
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Name) and tgt.id in ("patron", "patronvideos"):
                            local_env[tgt.id] = val
                            patrons.append(val)
            elif isinstance(stmt, ast.AugAssign) and isinstance(stmt.op, ast.Add):
                val = _str_val(stmt.value)
                if val is not None and isinstance(stmt.target, ast.Name) and stmt.target.id in ("patron", "patronvideos"):
                    cur = local_env.get(stmt.target.id, "") + val
                    local_env[stmt.target.id] = cur
                    patrons.append(cur)
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _walk_block(stmt.body, {})
            elif isinstance(stmt, ast.If):
                _walk_block(stmt.body, local_env)
                if stmt.orelse:
                    _walk_block(stmt.orelse, local_env)
            elif isinstance(stmt, (ast.For, ast.While, ast.With, ast.Try)):
                _walk_block(getattr(stmt, "body", []), local_env)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(py_source)
        _walk_block(tree.body, {})
    except SyntaxError:
        pass

    if not patrons:
        cur = ""
        for m in re.finditer(r"""(?m)^\s*(patron(?:videos)?)\s*(\+?=)\s*r?(?:'([^']+)'|"([^"]+)")""", py_source):
            op = m.group(2)
            chunk = m.group(3) if m.group(3) is not None else (m.group(4) or "")
            if op == "+=":
                cur += chunk
            else:
                cur = chunk
            if cur:
                patrons.append(cur)

    # Deduplicate keeping longest / final versions first or preserving order
    out: list[str] = []
    for p in reversed(patrons):
        if p and p not in out:
            out.append(p)
    out.reverse()
    return out


def _extract_embedded_json_items(html: str, base_url: str) -> list[dict]:
    candidates: list[dict] = []
    norm_base = _normalize_provider_host(base_url or "https://www.animeunity.co")
    parsed_b = urllib.parse.urlparse(norm_base)
    base_host = f"{parsed_b.scheme or 'https'}://{parsed_b.netloc}" if parsed_b.netloc else "https://www.animeunity.co"

    # 1. AnimeUnity items-json / records Vue props or /archivio/get-animes JSON response
    au_blobs: list[str] = []
    for attr in ("items-json", "records"):
        for m in re.finditer(rf'\b{attr}\s*=\s*"([^"]+)"', html):
            au_blobs.append(_html_mod.unescape(m.group(1)))
        for m in re.finditer(rf"\b{attr}\s*=\s*'([^']+)'", html):
            au_blobs.append(_html_mod.unescape(m.group(1)))
    stripped = html.strip()
    if stripped.startswith("{") and '"records"' in stripped:
        au_blobs.append(stripped)

    for blob in au_blobs:
        try:
            data = json.loads(blob)
        except Exception:
            continue
        records = []
        if isinstance(data, dict):
            records = data.get("data") or data.get("records") or []
        elif isinstance(data, list):
            records = data
        if not isinstance(records, list):
            continue
        au_host = base_host if "animeunity." in base_host else "https://www.animeunity.co"
        for it in records:
            if not isinstance(it, dict):
                continue
            anime = it.get("anime") if isinstance(it.get("anime"), dict) else it
            aid = anime.get("id")
            slug = anime.get("slug") or ""
            title = _clean_title(str(anime.get("title") or anime.get("title_eng") or anime.get("title_it") or anime.get("name") or ""))
            if not aid or not title:
                continue
            if str(anime.get("dub") or "") == "1" and "(ITA)" not in title.upper():
                title = f"{title} (ITA)"
            poster = str(anime.get("imageurl") or anime.get("imageurl_cover") or anime.get("cover") or "").strip()
            if poster:
                poster = _normalize_provider_host(_resolve(poster, au_host))
            plot = _clean_title(str(anime.get("plot") or ""))
            year = _year(anime.get("date"))
            url = f"{au_host.rstrip('/')}/anime/{aid}-{slug}" if slug else f"{au_host.rstrip('/')}/anime/{aid}"
            candidates.append({
                "url": _normalize_provider_host(url),
                "title": title,
                "poster": poster,
                "year": year,
                "overview": plot,
            })

    # 2. StreamingCommunity Inertia.js data-page
    if "data-page=" in html:
        m_dp = re.search(r'\bdata-page="([^"]+)"', html) or re.search(r"\bdata-page='([^']+)'", html)
        if m_dp:
            try:
                dp = json.loads(_html_mod.unescape(m_dp.group(1)))
            except Exception:
                dp = {}
            props = (dp.get("props") if isinstance(dp, dict) else None) or {}
            if isinstance(props, dict):
                sc_titles: list[dict] = []
                raw_titles = props.get("titles")
                if isinstance(raw_titles, dict):  # risorsa paginata {"data": [...]}
                    raw_titles = raw_titles.get("data")
                if isinstance(raw_titles, list):
                    sc_titles.extend(t for t in raw_titles if isinstance(t, dict))
                for s in (props.get("sliders") or []):
                    if isinstance(s, dict) and isinstance(s.get("titles"), list):
                        sc_titles.extend(t for t in s["titles"] if isinstance(t, dict))
                cdn_host = str(props.get("cdn_url") or "").rstrip("/") or re.sub(r"://(?:www\.)?", "://cdn.", base_host)
                for it in sc_titles:
                    tid = it.get("id")
                    slug = it.get("slug") or ""
                    name = _clean_title(str(it.get("name") or it.get("title") or ""))
                    if not tid or not name:
                        continue
                    poster = ""
                    imgs = [i for i in (it.get("images") or []) if isinstance(i, dict) and i.get("filename")]
                    imgs.sort(key=lambda i: {"poster": 0, "cover": 1}.get(i.get("type"), 2))
                    if imgs:
                        poster = str(imgs[0]["filename"])
                        if not poster.startswith("http"):
                            poster = f"{cdn_host}/images/{poster.lstrip('/')}"
                    elif isinstance(it.get("poster"), str):
                        poster = _resolve(it["poster"], base_host)
                    plot = _clean_title(str(it.get("plot") or ""))
                    year = _year(it.get("release_date") or it.get("year"))
                    url = f"{base_host.rstrip('/')}/it/titles/{tid}-{slug}" if slug else f"{base_host.rstrip('/')}/it/titles/{tid}"
                    candidates.append({
                        "url": url,
                        "title": name,
                        "poster": poster,
                        "year": year,
                        "overview": plot,
                        "is_series": {"tv": True, "movie": False}.get(str(it.get("type") or "")),
                    })

    return candidates


def scrape_channel_items(
    html_text: str,
    base_url: str,
    channel_id: str = "",
    channel_name: str = "",
    py_source: str = "",
    channel_categories: list[str] | None = None,
) -> list[dict]:
    """Estrae film/serie/anime dall'HTML di un canale tramite JSON embedded, patron regex (.py) e fallback BeautifulSoup."""
    html = html_text or ""
    if not html.strip():
        return []
    base_url = _normalize_provider_host(base_url)

    raw_candidates: list[dict] = _extract_embedded_json_items(html, base_url)

    if len(raw_candidates) < 2 and py_source:
        patrons = _extract_patrons_from_py(py_source)
        for pat in patrons:
            if "(?P<url>" not in pat or "(?P<title>" not in pat:
                continue
            try:
                rx = re.compile(pat, re.DOTALL | re.IGNORECASE)
            except re.error:
                continue
            for m in rx.finditer(html):
                gd = m.groupdict()
                u = _normalize_provider_host(_resolve(gd.get("url") or "", base_url))
                t = _clean_title(gd.get("title") or "")
                if not u or not t or _BADGE_TITLE_RE.match(t):
                    continue
                lang = (gd.get("lang") or "").strip().upper()
                if lang == "ITA" and "(ITA)" not in t.upper():
                    t = f"{t} (ITA)"
                thumb = _normalize_provider_host(_resolve(gd.get("thumb") or gd.get("thumbnail") or "", base_url))
                year = _year(gd.get("year") or "") or _year(re.search(r"\b((?:19|20)\d{2})\b", t).group(1) if re.search(r"\b((?:19|20)\d{2})\b", t) else "")
                plot = _clean_title(gd.get("plot") or "")
                raw_candidates.append({
                    "url": u,
                    "title": t,
                    "poster": thumb,
                    "year": year,
                    "overview": plot,
                })

    if len(raw_candidates) < 2:
        soup = BeautifulSoup(html, "html.parser")
        main_root = soup.select_one(".film-list, .results, .result-items, .search-results, .archive-items")
        scope = main_root if main_root is not None else soup
        containers = scope.select(
            ".boxgrid, .cover_kapsul, .ml-item, article, .movieItem, .post, .cover, .item, .film-poster, .anime-card, .card, .TPost, .result-item, .blog-item"
        )
        if not containers:
            containers = [
                a for a in scope.find_all("a", href=True)
                if a.find("img") or a.find(["h2", "h3", "h4", "h5"]) or "title" in " ".join(a.get("class") or []).lower()
            ]
        has_img_cards = any(c.find("img") is not None for c in containers)
        title_sels = (".name", ".ac__title", ".title", ".entry-title", ".film-name", ".serieTitle", "h2", "h3", "h4", "h5")
        for el in containers:
            if hasattr(el, "find_parent") and (el.find_parent(class_=("widget-body", "nav-menu-mobile", "sidebar")) or el.find_parent(id="sidebar")):
                continue
            el_classes = [c.lower() for c in (el.get("class") or [])] if hasattr(el, "get") else []
            if has_img_cards and any(c in ("item", "post") for c in el_classes):
                if el.find("img") is None and not el.get("data-jtitle") and not el.find(attrs={"data-jtitle": True}):
                    continue
            a_tag = el if getattr(el, "name", None) == "a" and el.get("href") else el.find("a", href=True)
            if not a_tag:
                continue

            t = ""
            for h_sel in title_sels:
                h_el = el.select_one(h_sel) if hasattr(el, "select_one") else None
                if h_el:
                    cand_t = _clean_title(h_el.get_text(" ", strip=True) or h_el.get("title") or h_el.get("data-jtitle") or "")
                    if cand_t and not _BADGE_TITLE_RE.match(cand_t):
                        t = cand_t
                        if getattr(h_el, "name", None) == "a" and h_el.get("href"):
                            a_tag = h_el
                        elif h_el.find("a", href=True):
                            a_tag = h_el.find("a", href=True)
                        break

            u = _normalize_provider_host(_resolve(a_tag.get("href") or "", base_url))
            if not u:
                continue

            img = el.find("img")
            if not t or _BADGE_TITLE_RE.match(t):
                for raw_cand in (
                    a_tag.get("data-jtitle"),
                    a_tag.get("title"),
                    el.get("data-jtitle") if hasattr(el, "get") else None,
                    img.get("alt") if img else None,
                    img.get("title") if img else None,
                ):
                    cand_t = _clean_title(str(raw_cand or ""))
                    if cand_t and not _BADGE_TITLE_RE.match(cand_t):
                        t = cand_t
                        break

            if not t or _BADGE_TITLE_RE.match(t):
                a_clone = BeautifulSoup(str(a_tag), "html.parser")
                for badge in a_clone.select(".dub, .status, .ep, .type, .trdublaj, .se_num, .quality, span.badge"):
                    badge.decompose()
                cand_t = _clean_title(a_clone.get_text(" ", strip=True))
                if cand_t and not _BADGE_TITLE_RE.match(cand_t):
                    t = cand_t

            if not t:
                continue

            # If card has a .dub badge (e.g. AnimeWorld ITA dub), append (ITA) if not already present
            dub_el = el.select_one(".dub") if hasattr(el, "select_one") else None
            if dub_el and "(ITA)" not in t.upper():
                dub_txt = dub_el.get_text(" ", strip=True).upper()
                if "DUB" in dub_txt or "ITA" in dub_txt:
                    t = f"{t} (ITA)"

            poster = ""
            if img:
                for attr in ("data-src", "data-lazy-src", "data-original", "src"):
                    val = img.get(attr)
                    if val and not str(val).startswith("data:"):
                        poster = _normalize_provider_host(_resolve(str(val), base_url))
                        if poster:
                            break

            year_m = re.search(r"\b((?:19|20)\d{2})\b", t) or re.search(r"\b((?:19|20)\d{2})\b", el.get_text(" ", strip=True)[:200])
            year = int(year_m.group(1)) if year_m else None
            raw_candidates.append({
                "url": u,
                "title": t,
                "poster": poster,
                "year": year,
                "overview": "",
            })

    seen_urls: set[str] = set()
    items: list[dict] = []
    cid = channel_id or "stream4me"
    cname = channel_name or channel_id or "Stream4me"
    cats_low = [str(c).lower() for c in (channel_categories or [])]
    ch_text = f"{cid} {cname}".lower()
    ch_is_anime = (
        any(k in ch_text for k in ("anime", "toon"))
        or cats_low == ["anime"]
        or any("anime" in c or "toon" in c for c in cats_low)
    )
    for cand in raw_candidates:
        u = cand["url"]
        t = cand["title"]
        if _is_noise_link(u, t, base_url):
            continue
        norm_u = u.rstrip("/")
        if norm_u in seen_urls:
            continue
        seen_urls.add(norm_u)
        uid_hash = hashlib.sha1(norm_u.encode("utf-8")).hexdigest()[:12]

        ut_low = f"{u} {t}".lower()
        cid_low = cid.lower()
        if cid_low in ("animeunity", "animeworld") or "animeunity" in u.lower() or "animeworld" in u.lower():
            is_anime = True
        elif cid_low in ("streamingcommunity", "altadefinizione01") or "streamingcommunity" in u.lower() or "altadefinizione" in u.lower():
            is_anime = False
        else:
            is_anime = ch_is_anime or any(k in ut_low for k in ("/anime", "sub-ita", "[anime]", "anime"))

        explicit_movie = bool(re.search(r"\b(?:film|movie)\b", ut_low))
        if cand.get("is_series") is not None:
            is_series = bool(cand["is_series"])
        elif is_anime:
            is_series = not explicit_movie
        else:
            is_series = (
                ("serie" in cid_low)
                or any(k in ut_low for k in ("serie", "tvshow", "stagione", "season", "episod", "/tv/"))
            )
        if is_series:
            kind = "episodio"
            series_val = t
            season_val = 1
            episode_val = 1
        else:
            kind = "film"
            series_val = ""
            season_val = None
            episode_val = None

        genre = "Anime" if is_anime else ("Serie TV" if is_series else "Film")
        overview_raw = cand.get("overview") or f"Da {cname}"
        if is_anime and "anime" not in overview_raw.lower():
            overview_raw = f"Anime · {overview_raw}"

        item: dict = {
            "id": f"s4me:{cid}:{uid_hash}",
            "kind": kind,
            "title": t,
            "series": series_val,
            "year": cand.get("year"),
            "poster": cand.get("poster") or "",
            "overview": overview_raw,
            "genre": genre,
            "url": u,
            "source": "stream4me",
            "source_label": cname,
            "channel_id": cid,
            "channel_name": cname,
        }
        if season_val is not None:
            item["season"] = season_val
            item["episode"] = episode_val
        items.append(item)
    return items


def scrape_channel_episodes(
    html_text: str,
    base_url: str,
    series_title: str = "",
    channel_id: str = "",
    py_source: str = "",
) -> list[dict]:
    """Estrae la lista di episodi o link riproducibili dalla pagina di dettaglio di una serie/anime."""
    html = html_text or ""
    if not html.strip():
        return []
    base_url = _normalize_provider_host(base_url)
    cid = channel_id or "stream4me"
    episodes: list[dict] = []
    seen_urls: set[str] = set()
    seen_se: set[tuple[int, int]] = set()

    # 1. AnimeUnity: <video-player episodes="..."> oppure JSON /info_api/{id}/1 con "episodes"
    au_eps_raw = ""
    if "video-player" in html and "episodes=" in html:
        m_vp = re.search(r'\bepisodes="([^"]+)"', html) or re.search(r"\bepisodes='([^']+)'", html)
        if m_vp:
            au_eps_raw = _html_mod.unescape(m_vp.group(1))
    elif html.strip().startswith("{") and '"episodes"' in html:
        au_eps_raw = html.strip()

    if au_eps_raw:
        try:
            au_data = json.loads(au_eps_raw)
            ep_list = au_data.get("episodes") if isinstance(au_data, dict) else (au_data if isinstance(au_data, list) else [])
        except Exception:
            ep_list = []
        if isinstance(ep_list, list) and ep_list:
            parsed_b = urllib.parse.urlparse(base_url)
            au_host = f"{parsed_b.scheme or 'https'}://{parsed_b.netloc}" if "animeunity." in (parsed_b.netloc or "") else "https://www.animeunity.co"
            for idx, ep_obj in enumerate(ep_list, 1):
                if not isinstance(ep_obj, dict):
                    continue
                eid = ep_obj.get("id")
                if not eid:
                    continue
                num_str = str(ep_obj.get("number") or idx)
                m_num = re.search(r"(\d+)", num_str)
                ep_num = int(m_num.group(1)) if m_num else idx
                se_key = (1, ep_num)
                if se_key in seen_se:
                    continue
                seen_se.add(se_key)
                u = f"{au_host.rstrip('/')}/embed-url/{eid}"
                uid_hash = hashlib.sha1(f"{u}:1:{ep_num}".encode("utf-8")).hexdigest()[:12]
                episodes.append({
                    "id": f"s4me:{cid}:ep:{uid_hash}",
                    "kind": "episodio",
                    "title": f"Episodio {ep_num}",
                    "series": series_title,
                    "season": 1,
                    "episode": ep_num,
                    "url": u,
                    "stream_url": "",
                    "source": "stream4me",
                })
            episodes.sort(key=lambda x: (x.get("season") or 1, x.get("episode") or 1))
            return episodes

    sc_props = _sc_page_props(html)
    sc_title = sc_props.get("title") or {}
    sc_eps = (sc_props.get("loadedSeason") or {}).get("episodes") or []
    if sc_title.get("id") and sc_eps:
        # shortcut: solo la stagione già caricata nella pagina; le altre servono richieste Inertia, da aggiungere se servono
        season = int((sc_props["loadedSeason"].get("number")) or 1)
        pu = urllib.parse.urlparse(base_url)
        host = f"{pu.scheme or 'https'}://{pu.netloc}"
        for ep_obj in sc_eps:
            if not isinstance(ep_obj, dict) or not ep_obj.get("id"):
                continue
            n = int(ep_obj.get("number") or len(episodes) + 1)
            u = f"{host}/it/titles/{sc_title['id']}-{sc_title.get('slug') or ''}?episode_id={ep_obj['id']}"
            uid_hash = hashlib.sha1(f"{u}:{season}:{n}".encode("utf-8")).hexdigest()[:12]
            episodes.append({
                "id": f"s4me:{cid}:ep:{uid_hash}",
                "kind": "episodio",
                "title": _clean_title(str(ep_obj.get("name") or "")) or f"Episodio {n}",
                "series": series_title,
                "season": season,
                "episode": n,
                "url": u,
                "stream_url": "",
                "source": "stream4me",
            })
        episodes.sort(key=lambda x: x["episode"])
        return episodes

    soup = BeautifulSoup(html, "html.parser")
    active_srv = soup.select(".server.active, .tab-pane.active")
    if active_srv:
        containers = active_srv
    else:
        containers = soup.select(".episodes, .stagione, .les-content, .episodios, .tab-pane, .episodes-list, #episodes")
    anchors = [a for c in containers for a in c.find_all("a", href=True)] if containers else []
    if not anchors:
        anchors = soup.find_all("a", href=True)

    ep_re_sx = re.compile(r"(?i)(?:s?(\d{1,2})\s*[x×e]\s*(\d{1,3})|stagione\s*(\d{1,2}).*?episodio\s*(\d{1,3}))")
    ep_re_num = re.compile(r"(?i)\b(?:episodio|ep\.?|episode)\s*(\d{1,4})\b")
    ep_re_href = re.compile(r"(?i)/(?:episode/[^/]+/)?ep-(\d{1,4})\b")

    for a in anchors:
        raw_href = a.get("href") or a.get("data-link") or ""
        u = _normalize_provider_host(_resolve(raw_href, base_url))
        if not u:
            continue
        text = _clean_title(a.get_text(" ", strip=True) or a.get("title") or "")
        combined = f"{text} {u}"

        season_num: int | None = None
        ep_num: int | None = None
        data_ep = a.get("data-episode-num") or a.get("data-num")
        if data_ep and re.search(r"\d+", str(data_ep)):
            season_num = 1
            ep_num = int(re.search(r"\d+", str(data_ep)).group(0))
        else:
            m_sx = ep_re_sx.search(combined)
            if m_sx:
                s_g = m_sx.group(1) or m_sx.group(3)
                e_g = m_sx.group(2) or m_sx.group(4)
                season_num = int(s_g)
                ep_num = int(e_g)
            else:
                m_href = ep_re_href.search(u)
                m_ep = ep_re_num.search(combined)
                if m_href:
                    season_num = 1
                    ep_num = int(m_href.group(1))
                elif m_ep:
                    season_num = 1
                    ep_num = int(m_ep.group(1))
                elif containers and re.fullmatch(r"\d{1,4}", text):
                    season_num = 1
                    ep_num = int(text)
                else:
                    continue

        norm_u = u.rstrip("/")
        if norm_u in seen_urls or norm_u == (base_url or "").rstrip("/"):
            continue
        se_key = (season_num, ep_num)
        if se_key in seen_se:
            continue
        seen_urls.add(norm_u)
        seen_se.add(se_key)

        ep_title = text if text and not re.fullmatch(r"\d{1,4}", text) and not ep_re_href.search(u) else f"Episodio {ep_num}"
        uid_hash = hashlib.sha1(f"{norm_u}:{season_num}:{ep_num}".encode("utf-8")).hexdigest()[:12]
        stream_u = u if _classify(u) in ("direct", "hls") else ""
        episodes.append({
            "id": f"s4me:{cid}:ep:{uid_hash}",
            "kind": "episodio",
            "title": ep_title,
            "series": series_title,
            "season": season_num,
            "episode": ep_num,
            "url": u,
            "stream_url": stream_u,
            "source": "stream4me",
        })

    episodes.sort(key=lambda x: (x.get("season") or 1, x.get("episode") or 1))
    return episodes


def _build_search_target(channel: dict, query: str) -> str:
    host = _normalize_provider_host((channel.get("host") or "").rstrip("/"))
    cid = str(channel.get("id") or "").lower()
    q_enc = urllib.parse.quote_plus(query.strip())
    if cid in ("animeworld", "dreamsub") and host:
        return f"{host}/filter?keyword={q_enc}"
    if cid == "animesaturn" and host:
        return f"{host}/filter?key={q_enc}"
    if cid == "streamingcommunity" and host:
        return f"{host}/it/search?q={q_enc}"
    if cid == "animeunity" and host:
        return f"{host}/archivio"
    tmpl = _normalize_provider_host(channel.get("search_url") or "")
    if tmpl:
        if "{query}" in tmpl:
            return tmpl.replace("{query}", q_enc)
        if "%s" in tmpl:
            return tmpl.replace("%s", q_enc)
        if tmpl.endswith(("=", "?s=", "story=", "search=", "keyword=", "key=", "q=")):
            return f"{tmpl}{q_enc}"
    return f"{host}/?s={q_enc}" if host else ""


def _fetch_with_security_cookie(url: str, headers: dict, timeout: float) -> httpx.Response:
    resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=timeout)
    if "SecurityAW" in resp.text:
        ck = re.search(r'document\.cookie\s*=\s*"([^";]+)', resp.text)
        if ck:
            h2 = dict(headers)
            h2["Cookie"] = ck.group(1).strip()
            resp = httpx.get(url, headers=h2, follow_redirects=True, timeout=timeout)
    return resp


def browse_stream4me_channel(
    addon_dir: Path | str | None,
    channel_id: str,
    path: str = "",
    query: str = "",
    fetcher=None,
    timeout: float = 8.0,
    custom_providers: list[dict] | None = None,
) -> dict:
    """Esplora o cerca in un canale Stream4me dal vivo, con cache TTL di 10 minuti."""
    providers = list(list_stream4me_providers(addon_dir, only_active=False))
    if custom_providers:
        seen_ids = {p["id"] for p in providers}
        for cp in custom_providers:
            if isinstance(cp, dict) and cp.get("id") and cp["id"] not in seen_ids:
                cp_norm = dict(cp)
                if cp_norm.get("host"):
                    cp_norm["host"] = _normalize_provider_host(str(cp_norm["host"])).rstrip("/")
                if cp_norm.get("search_url"):
                    cp_norm["search_url"] = _normalize_provider_host(str(cp_norm["search_url"]))
                providers.append(cp_norm)
                seen_ids.add(cp_norm["id"])
    channel = next((p for p in providers if p["id"] == channel_id), None)
    if channel is None:
        raise ValueError(f"Canale Stream4me non trovato: {channel_id}")

    host = _normalize_provider_host((channel.get("host") or "").rstrip("/"))
    channel = dict(channel)
    channel["host"] = host
    if query and query.strip():
        target_url = _build_search_target(channel, query)
    elif path and path.strip():
        target_url = _resolve(path.strip(), host + "/")
    else:
        menus = channel.get("menus") or []
        first_path = menus[0].get("path", "/") if menus else "/"
        target_url = _resolve(first_path, host + "/") if host else first_path
    target_url = _normalize_provider_host(target_url)

    if not target_url:
        return {"provider": channel, "url": "", "items": []}

    now = time.time()
    cache_key = (channel_id, f"{target_url}::{query.strip()}")
    cached = _BROWSE_CACHE.get(cache_key)
    if cached is not None and (now - cached[0]) < _BROWSE_TTL:
        return cached[1]

    py_source = ""
    root = find_stream4me_dir(addon_dir) if addon_dir else None
    if root:
        py_file = root / "channels" / f"{channel_id}.py"
        if py_file.is_file():
            py_source = py_file.read_text("utf-8", errors="replace")

    if fetcher is not None:
        raw_html = fetcher(target_url)
        html_text = raw_html.decode("utf-8", errors="replace") if isinstance(raw_html, bytes) else str(raw_html or "")
    elif channel["id"] == "animeunity" and ((query and query.strip()) or "/archivio" in target_url):
        au_host = host or "https://www.animeunity.co"
        arch_url = f"{au_host}/archivio"
        headers = {"User-Agent": _SCRAPE_UA, "Referer": au_host + "/"}
        r_arch = httpx.get(arch_url, headers=headers, follow_redirects=True, timeout=timeout)
        r_arch.raise_for_status()
        csrf_m = re.search(r'name="csrf-token"\s+content="([^"]+)"', r_arch.text)
        if csrf_m:
            post_headers = {
                "X-CSRF-TOKEN": csrf_m.group(1),
                "Content-Type": "application/json",
                "Referer": arch_url,
                "User-Agent": _SCRAPE_UA,
            }
            payload = {
                "title": query.strip() if (query and query.strip()) else False,
                "type": False,
                "year": False,
                "order": "Lista A-Z",
                "status": False,
                "genres": False,
                "offset": 0,
                "dubbed": False,
                "season": False,
            }
            r_post = httpx.post(
                f"{au_host}/archivio/get-animes",
                headers=post_headers,
                cookies=r_arch.cookies,
                json=payload,
                follow_redirects=True,
                timeout=timeout,
            )
            r_post.raise_for_status()
            html_text = r_post.text
        else:
            html_text = r_arch.text
    else:
        headers = {"User-Agent": _SCRAPE_UA}
        if host:
            headers["Referer"] = host + "/"
        resp = _fetch_with_security_cookie(target_url, headers, timeout)
        resp.raise_for_status()
        html_text = resp.text

    items = scrape_channel_items(
        html_text,
        base_url=target_url,
        channel_id=channel["id"],
        channel_name=channel["name"],
        py_source=py_source,
        channel_categories=channel.get("categories"),
    )
    result = {"provider": channel, "url": target_url, "items": items}
    _BROWSE_CACHE[cache_key] = (now, result)
    return result


def _vix_hls_url(vix_html: str, embed_url: str = "") -> str:
    """Compone la playlist HLS di VixCloud da window.masterPlaylist (url + token/expires/asn)."""
    m_url = re.search(r"""window\.masterPlaylist\s*=\s*\{.*?\burl\s*:\s*['"](https?://[^'"]+)['"]""", vix_html, re.S)
    if not m_url:
        return ""
    m_par = re.search(r"window\.masterPlaylist\s*=\s*\{\s*params\s*:\s*\{(.*?)\}", vix_html, re.S)
    query = dict(re.findall(r"""['"](\w+)['"]\s*:\s*['"]([^'"]*)['"]""", m_par.group(1))) if m_par else {}
    emb_q = urllib.parse.parse_qs(urllib.parse.urlparse(embed_url).query)
    if "canPlayFHD" in vix_html and re.search(r"canPlayFHD\s*=\s*true", vix_html):
        query["h"] = "1"
    query.setdefault("lang", (emb_q.get("lang") or ["it"])[0])
    base = m_url.group(1)
    return base + ("&" if "?" in base else "?") + urllib.parse.urlencode(query)


def _sc_page_props(page_html: str) -> dict:
    m = re.search(r'\bdata-page="([^"]+)"', page_html or "") or re.search(r"\bdata-page='([^']+)'", page_html or "")
    if not m:
        return {}
    try:
        return (json.loads(_html_mod.unescape(m.group(1))).get("props")) or {}
    except Exception:
        return {}


def resolve_channel_stream(
    item_url: str,
    html_text: str = "",
    fetcher=None,
    timeout: float = 10.0,
) -> str:
    """Risolve un URL episodio/film di un canale Stream4me nel vero flusso video (.mp4, .m3u8 o embed reale)."""
    u = _normalize_provider_host((item_url or "").strip())
    if not u:
        return ""
    if _classify(u) in ("direct", "hls"):
        return u

    def _get_text(target: str, referer: str = "") -> str:
        target = _normalize_provider_host(target)
        if fetcher is not None:
            raw = fetcher(target)
            return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw or "")
        hdrs = {"User-Agent": _SCRAPE_UA, "Referer": referer or u}
        resp = _fetch_with_security_cookie(target, hdrs, timeout)
        return resp.text if resp.status_code == 200 else ""

    parsed = urllib.parse.urlparse(u)
    origin = f"{parsed.scheme or 'https'}://{parsed.netloc}" if parsed.netloc else ""
    u_low = u.lower()

    # 0. StreamingCommunity: /it/titles/<id>-<slug>[?episode_id=N] -> /it/iframe/<id> -> vixcloud embed -> playlist .m3u8
    if "/titles/" in parsed.path and any(k in u_low for k in ("streamingcommunity", "streamingunity")):
        sc_page = html_text or _get_text(u.split("?")[0], origin + "/")
        props = _sc_page_props(sc_page)
        title = props.get("title") or {}
        tid = title.get("id") or (re.search(r"/titles/(\d+)", parsed.path) or [None, None])[1]
        ep_id = (urllib.parse.parse_qs(parsed.query).get("episode_id") or [""])[0]
        if tid and not ep_id and title.get("type") == "tv":
            eps = (props.get("loadedSeason") or {}).get("episodes") or []
            ep_id = str(eps[0]["id"]) if eps and isinstance(eps[0], dict) and eps[0].get("id") else ""
        iframe_u = f"{origin}/it/iframe/{tid}" + (f"?episode_id={ep_id}&next_episode=1" if ep_id else "")
        if tid:
            m_if = re.search(r'<iframe[^>]+src="([^"]+)"', _get_text(iframe_u, origin + "/"))
            if m_if:
                emb = _html_mod.unescape(m_if.group(1))
                hls = _vix_hls_url(_get_text(emb, origin + "/"), emb)
                if hls:
                    return hls

    # 1. AnimeWorld: /play/<slug>/<ep_id> -> /api/episode/info?id=<ep_id> -> grabber .mp4
    if "animeworld." in u_low:
        page_html = html_text or ""
        m_aw = re.search(r"/play/[^/?#]+/([A-Za-z0-9_-]+)", parsed.path)
        ep_id = m_aw.group(1) if m_aw else ""
        if not ep_id:
            if not page_html:
                page_html = _get_text(u, origin + "/")
            m_act = (
                re.search(r'<a[^>]+class="[^"]*active[^"]*"[^>]+data-id="([^"]+)"', page_html)
                or re.search(r'<a[^>]+data-id="([^"]+)"[^>]+class="[^"]*active[^"]*"', page_html)
                or re.search(r'\bdata-id="([A-Za-z0-9_-]+)"', page_html)
            )
            if m_act:
                ep_id = m_act.group(1)
        if ep_id and origin:
            api_txt = _get_text(f"{origin}/api/episode/info?id={ep_id}", referer=u)
            if api_txt:
                try:
                    data = json.loads(api_txt)
                except Exception:
                    data = {}
                grabber = str((data.get("grabber") if isinstance(data, dict) else "") or "").strip()
                if grabber and not _is_ad(grabber):
                    if _classify(grabber) in ("direct", "hls"):
                        return grabber
                    return grabber

    # 2. AnimeUnity / VixCloud: /anime/<id>-<slug> o /embed-url/<ep_id> -> vixcloud -> window.downloadUrl (.mp4) / masterPlaylist (.m3u8)
    if "animeunity." in u_low or "vixcloud." in u_low:
        au_origin = origin if "animeunity." in u_low else "https://www.animeunity.co"
        vix_url = ""
        if "vixcloud." in u_low:
            vix_url = u
        elif "/embed-url/" in u_low:
            vix_url = _get_text(u, referer=au_origin + "/").strip()
        elif "/anime/" in u_low:
            page_html = html_text or _get_text(u, referer=au_origin + "/")
            eps = scrape_channel_episodes(page_html, u, channel_id="animeunity")
            if eps and eps[0].get("url"):
                vix_url = _get_text(eps[0]["url"], referer=u).strip()
            else:
                m_aid = re.search(r"/anime/(\d+)", parsed.path)
                if m_aid:
                    info_txt = _get_text(
                        f"{au_origin}/info_api/{m_aid.group(1)}/1?start_range=1&end_range=1",
                        referer=u,
                    )
                    eps_api = scrape_channel_episodes(info_txt, u, channel_id="animeunity")
                    if eps_api and eps_api[0].get("url"):
                        vix_url = _get_text(eps_api[0]["url"], referer=u).strip()

        if vix_url and vix_url.startswith(("http://", "https://")):
            vix_html = _get_text(vix_url, referer=au_origin + "/")
            if vix_html:
                m_dl = re.search(r"""window\.downloadUrl\s*=\s*['"](https?://[^'"]+)['"]""", vix_html)
                if m_dl:
                    return m_dl.group(1).strip()
                hls = _vix_hls_url(vix_html, vix_url)
                if hls:
                    return hls
                vix_streams = extract_stream_urls(vix_html, base_url=vix_url)
                if vix_streams:
                    return vix_streams[0]["url"]
            return vix_url

    # 3. AnimeSaturn: /anime/... -> /ep/... -> /watch?file=... -> .mp4 / .m3u8
    page_html = html_text or _get_text(u, referer=(origin + "/") if origin else u)
    if "animesaturn." in u_low and page_html:
        if "/anime/" in u_low:
            m_ep = re.search(r'href="(https?://[^"]*/ep/[^"]+)"', page_html)
            if m_ep:
                u = m_ep.group(1)
                page_html = _get_text(u, referer=origin + "/")
        m_watch = re.search(r'href="(https?://[^"]*/watch\?file=[^"]+)"', page_html)
        if m_watch:
            watch_url = m_watch.group(1)
            w_html = _get_text(watch_url, referer=u)
            if w_html:
                w_streams = extract_stream_urls(w_html, base_url=watch_url)
                for st in w_streams:
                    if st.get("kind") in ("direct", "hls"):
                        return st["url"]
                return watch_url

    # 4. Generic / Multi-hop embeds (Supervideo, Dropload, MixDrop, Guardaserie data-link, etc.)
    if not page_html:
        return ""
    found = extract_stream_urls(page_html, base_url=u)
    for st in found:
        if st.get("kind") in ("direct", "hls") and not _is_ad(st["url"]):
            return st["url"]

    embed_candidates = [st["url"] for st in found if st.get("kind") == "embed" and not _is_ad(st["url"])]
    for m_dl in re.finditer(r'\bdata-link="(https?://[^"]+)"', page_html):
        dl_u = _resolve(m_dl.group(1), u)
        if dl_u and not _is_ad(dl_u) and dl_u not in embed_candidates:
            embed_candidates.append(dl_u)

    for emb_u in embed_candidates[:3]:
        if _classify(emb_u) in ("direct", "hls"):
            return emb_u
        try:
            emb_html = _get_text(emb_u, referer=u)
        except Exception:
            emb_html = ""
        if emb_html:
            inner = extract_stream_urls(emb_html, base_url=emb_u)
            for st in inner:
                if st.get("kind") in ("direct", "hls") and not _is_ad(st["url"]):
                    return st["url"]
        return emb_u

    return ""
