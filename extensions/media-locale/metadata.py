"""Metadati automatici da AniList (anime, zero API key) e TMDB / Wikipedia (film e serie)."""

from __future__ import annotations

import os
import re
import httpx

ANILIST_URL = "https://graphql.anilist.co"
ANILIST_QUERY = """
query ($search: String) {
  Media (search: $search, type: ANIME) {
    id
    title { romaji english native }
    coverImage { extraLarge large medium }
    bannerImage
    description
    genres
    format
    averageScore
  }
}
"""

TIMEOUT = 2.0
USER_AGENT = "PozzoLauncher/1.0 (https://github.com/pozzo)"
HTML_TAGS = re.compile(r"<[^>]+>")
KNOWN_ANIME = {
    "one piece", "naruto", "dragon ball", "bleach", "death note",
    "attack on titan", "shingeki no kyojin", "demon slayer", "kimetsu no yaiba",
    "jujutsu kaisen", "my hero academia", "boku no hero academia", "hunter x hunter",
    "fullmetal alchemist", "chainsaw man", "spy x family", "tokyo ghoul"
}


def _clean_html(text: str) -> str:
    if not text:
        return ""
    s = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    s = HTML_TAGS.sub("", s)
    return " ".join(s.split())


def fetch_anime_metadata(title: str, episode: int | None = None) -> dict:
    """Interroga AniList GraphQL (zero API key) con timeout 2.0s. Restituisce metadati o {}."""
    if not title or not str(title).strip():
        return {}
    query_title = str(title).strip()
    try:
        r = httpx.post(
            ANILIST_URL,
            json={"query": ANILIST_QUERY, "variables": {"search": query_title}},
            headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return {}
        data = r.json().get("data", {}).get("Media")
        if not data:
            return {}
        cover = data.get("coverImage") or {}
        poster = cover.get("extraLarge") or cover.get("large") or cover.get("medium") or ""
        backdrop = data.get("bannerImage") or ""
        overview = _clean_html(data.get("description") or "")
        genres = data.get("genres") or []
        return {
            "poster": poster,
            "backdrop": backdrop,
            "overview": overview,
            "genres": genres,
            "format": data.get("format") or "",
            "averageScore": data.get("averageScore"),
        }
    except Exception:
        return {}


def fetch_tmdb_metadata(title: str, kind: str = "film", year: int | None = None) -> dict:
    """Cerca metadati su TMDB (se API key) o Wikipedia open catalog con timeout 2.0s."""
    if not title or not str(title).strip():
        return {}
    query_title = str(title).strip()
    api_key = os.environ.get("TMDB_API_KEY", "")

    # 1. TMDB se c'è una API key
    if api_key:
        endpoint = "movie" if kind == "film" else "tv"
        url = f"https://api.themoviedb.org/3/search/{endpoint}"
        params = {"api_key": api_key, "query": query_title, "language": "it-IT"}
        if year:
            params["year" if kind == "film" else "first_air_date_year"] = str(year)
        try:
            r = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            if r.status_code == 200:
                results = r.json().get("results") or []
                if results:
                    top = results[0]
                    p = top.get("poster_path")
                    b = top.get("backdrop_path")
                    date_str = top.get("release_date") or top.get("first_air_date") or ""
                    y = int(date_str[:4]) if date_str and date_str[:4].isdigit() else year
                    return {
                        "poster": f"https://image.tmdb.org/t/p/w500{p}" if p else "",
                        "backdrop": f"https://image.tmdb.org/t/p/w1280{b}" if b else "",
                        "overview": top.get("overview") or "",
                        "year": y,
                    }
        except Exception:
            pass

    # 2. Fallback Wikipedia open catalog (zero key)
    try:
        for lang in ("it", "en"):
            url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{query_title.replace(' ', '_')}"
            r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            if r.status_code == 200:
                d = r.json()
                extract = d.get("extract") or ""
                thumb = (d.get("thumbnail") or {}).get("source") or ""
                orig = (d.get("originalimage") or {}).get("source") or ""
                y = year
                if not y and extract:
                    m = re.search(r"\b((?:19|20)\d{2})\b", extract)
                    if m:
                        y = int(m.group(1))
                return {
                    "poster": thumb,
                    "backdrop": orig,
                    "overview": extract,
                    "year": y,
                }
    except Exception:
        pass

    return {}


def is_anime_item(item: dict) -> bool:
    """Verifica se l'item appartiene a una serie/cartella anime."""
    path = str(item.get("path") or "").lower()
    series = str(item.get("series") or "").lower()
    title = str(item.get("title") or "").lower()
    if any(k in path for k in ("/anime/", "\\anime\\", "/animazione/", "\\animazione\\")):
        return True
    if any(series == a or series.startswith(a) for a in KNOWN_ANIME):
        return True
    if any(title == a or title.startswith(a) for a in KNOWN_ANIME):
        return True
    if item.get("kind") == "episodio" and (item.get("episode") or 0) > 100:
        return True
    return False


def enrich_item(item: dict) -> dict:
    """Se mancano locandina o trama, arricchisce l'item interrogando AniList o TMDB."""
    has_poster = bool(item.get("poster"))
    has_overview = bool(item.get("overview"))
    if has_poster and has_overview:
        return item

    meta: dict = {}
    if is_anime_item(item):
        query = item.get("series") or item.get("title") or ""
        meta = fetch_anime_metadata(query, episode=item.get("episode"))

    if not meta or (not meta.get("poster") and not meta.get("overview")):
        query = item.get("series") if item.get("kind") == "episodio" and item.get("series") else item.get("title") or ""
        meta = fetch_tmdb_metadata(query, kind=item.get("kind") or "film", year=item.get("year"))

    if not meta:
        return item

    res = dict(item)
    if not has_poster and meta.get("poster"):
        res["poster"] = meta["poster"]
    if not res.get("backdrop") and meta.get("backdrop"):
        res["backdrop"] = meta["backdrop"]
    if not has_overview and meta.get("overview"):
        res["overview"] = meta["overview"]
    if not res.get("genres") and meta.get("genres"):
        g = meta["genres"]
        res["genres"] = ", ".join(g) if isinstance(g, (list, tuple)) else str(g)
    if not res.get("year") and meta.get("year"):
        res["year"] = meta["year"]
    return res
