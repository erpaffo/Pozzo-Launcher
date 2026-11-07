"""Importazione della watchlist da altri servizi (AniList, MyAnimeList, Letterboxd, Trakt, CSV/JSON/testo).

Tutto gira in locale: nessun account nostro, nessuna credenziale inviata. Le funzioni `parse_*` sono pure
(testo in, lista di voci fuori); `fetch_anilist` e' l'unica che usa la rete (liste pubbliche, nome utente).
`bulk_save` salva le voci in un'unica transazione senza mai peggiorare cio' che l'utente ha gia'.

Voce: {title, original_title, year|None, category ('film'|'serie'|'anime'|''), status, progress, total,
rating (0-10), poster, overview, kind ('film'|'episodio'), ext_ids {anilist,mal,tmdb,imdb,...}, import_source}
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET

STATUSES = ("plan_to_watch", "watching", "on_hold", "completed", "dropped")
CATEGORIES = ("film", "serie", "anime")
MAX_ENTRIES = 5000
MAX_TITLE = 300
ANILIST_URL = "https://graphql.anilist.co"

_ANILIST_STATUS = {"CURRENT": "watching", "REPEATING": "watching", "COMPLETED": "completed",
                   "PLANNING": "plan_to_watch", "PAUSED": "on_hold", "DROPPED": "dropped"}
_TEXT_STATUS = {
    "watching": "watching", "current": "watching", "in corso": "watching", "1": "watching",
    "completed": "completed", "complete": "completed", "watched": "completed", "finished": "completed",
    "visto": "completed", "completato": "completed", "2": "completed",
    "on-hold": "on_hold", "on hold": "on_hold", "on_hold": "on_hold", "paused": "on_hold", "3": "on_hold",
    "dropped": "dropped", "abbandonato": "dropped", "4": "dropped",
    "plan to watch": "plan_to_watch", "plan_to_watch": "plan_to_watch", "planned": "plan_to_watch",
    "planning": "plan_to_watch", "watchlist": "plan_to_watch", "da vedere": "plan_to_watch", "6": "plan_to_watch",
}
_CAT = {"movie": "film", "movies": "film", "film": "film", "show": "serie", "shows": "serie", "tv": "serie",
        "series": "serie", "serie": "serie", "episode": "serie", "season": "serie", "anime": "anime"}

_ANILIST_QUERY = """query($u:String){MediaListCollection(userName:$u,type:ANIME){lists{entries{status progress
score(format:POINT_10_DECIMAL) media{id idMal title{romaji english native} format episodes startDate{year}
coverImage{large} description}}}}}"""


def _int(v, default=0) -> int:
    try:
        return max(0, int(float(v)))
    except (TypeError, ValueError):
        return default


def _year(v):
    m = re.search(r"\b(1[89]\d\d|20\d\d)\b", str(v or ""))
    return int(m.group(1)) if m else None


def _rating(v, scale=10.0) -> float:
    """Voto -> 0-10 (scale e' il massimo della scala di partenza)."""
    try:
        r = float(v) * 10.0 / scale
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(10.0, r)), 1)


class _Out:
    """Raccoglie le voci scartando quelle senza titolo e rispettando i limiti difensivi."""

    def __init__(self, provider: str):
        self.provider, self.entries, self.skipped, self.warnings = provider, [], 0, []

    def add(self, title, *, category="", status="plan_to_watch", **kw):
        title = re.sub(r"\s+", " ", str(title or "")).strip()[:MAX_TITLE]
        if not title:
            self.skipped += 1
            return
        if len(self.entries) >= MAX_ENTRIES:
            self.skipped += 1
            if not self.warnings:
                self.warnings.append(f"Importate solo le prime {MAX_ENTRIES} voci.")
            return
        category = category if category in CATEGORIES else ""
        ext = {k: v for k, v in (kw.get("ext_ids") or {}).items() if v not in (None, "", 0)}
        self.entries.append({
            "title": title,
            "original_title": str(kw.get("original_title") or "")[:MAX_TITLE],
            "year": _year(kw.get("year")),
            "category": category,
            "status": status if status in STATUSES else "plan_to_watch",
            "progress": _int(kw.get("progress")),
            "total": _int(kw.get("total")),
            "rating": _rating(kw.get("rating")),
            "poster": str(kw.get("poster") or ""),
            "overview": str(kw.get("overview") or ""),
            "kind": "film" if category == "film" else "episodio",
            "ext_ids": ext,
            "import_source": self.provider,
        })

    def done(self, report):
        if isinstance(report, dict):
            report["skipped"] = report.get("skipped", 0) + self.skipped
            report.setdefault("warnings", []).extend(self.warnings)
        return self.entries


# ------------------------------------------------------------------ AniList
def parse_anilist(collection_json, report=None) -> list[dict]:
    """`collection_json`: risposta GraphQL completa, oppure solo MediaListCollection."""
    data = collection_json if isinstance(collection_json, dict) else {}
    data = data.get("data", data)
    data = data.get("MediaListCollection", data) if isinstance(data, dict) else {}
    out, seen = _Out("anilist"), set()
    for lst in (data.get("lists") or []) if isinstance(data, dict) else []:
        for e in (lst or {}).get("entries") or []:
            media = (e or {}).get("media") or {}
            mid = media.get("id")
            if mid in seen:  # la stessa voce compare anche nelle liste personalizzate
                continue
            seen.add(mid)
            t = media.get("title") or {}
            score = float(e.get("score") or 0)
            out.add(t.get("english") or t.get("romaji") or t.get("native"), category="anime",
                    original_title=t.get("romaji") or "", year=(media.get("startDate") or {}).get("year"),
                    status=_ANILIST_STATUS.get(str(e.get("status") or "").upper(), "plan_to_watch"),
                    progress=e.get("progress"), total=media.get("episodes"),
                    rating=_rating(score, 100.0 if score > 10 else 10.0),
                    poster=(media.get("coverImage") or {}).get("large"),
                    overview=re.sub(r"<[^>]+>", "", media.get("description") or "").strip(),
                    ext_ids={"anilist": mid, "mal": media.get("idMal")})
    return out.done(report)


def fetch_anilist(username: str, client=None, report=None) -> list[dict]:
    """Scarica la lista ANIME pubblica di `username` (nessun token) e la converte."""
    if client is None:
        import httpx as client
    username = (username or "").strip()
    if not username:
        raise ValueError("Inserisci il nome utente AniList.")
    try:
        r = client.post(ANILIST_URL, json={"query": _ANILIST_QUERY, "variables": {"u": username}}, timeout=10)
    except Exception as e:  # rete assente, timeout, DNS
        raise ValueError(f"AniList non raggiungibile: {e}") from e
    try:
        body = r.json()
    except Exception:
        body = {}
    errors = body.get("errors") or [] if isinstance(body, dict) else []
    if errors or getattr(r, "status_code", 200) >= 400:
        msg = " ".join(str(x.get("message", "")) for x in errors if isinstance(x, dict)).lower()
        if "private" in msg or getattr(r, "status_code", 0) == 403:
            raise ValueError("La lista AniList di questo utente è privata: rendila pubblica nelle impostazioni.")
        if "not found" in msg or getattr(r, "status_code", 0) == 404 or not msg:
            raise ValueError(f"Utente AniList «{username}» non trovato.")
        raise ValueError(f"AniList ha risposto con un errore: {msg}")
    return parse_anilist(body, report)


# ------------------------------------------------------------------ MyAnimeList
def parse_mal_xml(text: str, report=None) -> list[dict]:
    if re.search(r"<!\s*(doctype|entity)", text or "", re.I):
        raise ValueError("File XML non valido: DOCTYPE/ENTITY non ammessi.")
    try:
        root = ET.fromstring((text or "").lstrip("﻿").strip())
    except ET.ParseError as e:
        raise ValueError(f"File XML non valido: {e}") from e
    out = _Out("mal")
    for a in root.iter("anime"):
        g = lambda k: (a.findtext(k) or "").strip()  # noqa: E731
        out.add(g("series_title"), category="anime", status=_TEXT_STATUS.get(g("my_status").lower(), "plan_to_watch"),
                progress=g("my_watched_episodes"), total=g("series_episodes"), rating=g("my_score"),
                ext_ids={"mal": _int(g("series_animedb_id")) or None})
    return out.done(report)


# ------------------------------------------------------------------ CSV / JSON / testo
def _row_to_entry(out: _Out, row: dict, provider_default="") -> None:
    """Riga generica (CSV o oggetto JSON) con chiavi in minuscolo."""
    g = lambda *ks: next((str(row[k]).strip() for k in ks if row.get(k) not in (None, "")), "")  # noqa: E731
    cat = _CAT.get(g("type", "category", "kind", "categoria", "tipo").lower(), "")
    ext = {"imdb": g("imdb", "imdb_id", "imdbid"), "tmdb": _int(g("tmdb", "tmdb_id", "tmdbid")) or None}
    out.add(g("title", "titolo", "name"), category=cat, status=_TEXT_STATUS.get(g("status", "stato").lower(), "plan_to_watch"),
            year=g("year", "anno"), progress=g("progress", "episodes_watched"), total=g("total", "episodes"),
            rating=g("rating", "score", "voto"), ext_ids=ext, original_title=g("original_title"),
            poster=g("poster"), overview=g("overview"))


def parse_csv(text: str, report=None) -> list[dict]:
    text = (text or "").lstrip("﻿")
    head = text.split("\n", 1)[0]
    delim = max(",;\t", key=head.count)
    rows = [{(k or "").strip().lower(): v for k, v in r.items()} for r in csv.DictReader(io.StringIO(text), delimiter=delim)]
    cols = set(rows[0]) if rows else set()
    letterboxd = "name" in cols and "title" not in cols
    out = _Out("letterboxd" if letterboxd else "csv")
    for r in rows:
        if letterboxd:
            # watched/ratings/diary hanno rating o data di visione; watchlist.csv e watched.csv sono indistinguibili
            visto = "rating" in cols or "watched date" in cols
            out.add(r.get("name"), category="film", year=r.get("year"), status="completed" if visto else "plan_to_watch",
                    rating=_rating(r.get("rating") or 0, 5.0))
        else:
            _row_to_entry(out, r)
    return out.done(report)


def _trakt_entry(out: _Out, el: dict) -> bool:
    typ = el.get("type") if el.get("type") in ("movie", "show") else next((k for k in ("movie", "show") if isinstance(el.get(k), dict)), "")
    info = el.get(typ) if typ else None
    if not isinstance(info, dict):
        return False
    ids = info.get("ids") or {}
    visto = any(el.get(k) for k in ("watched_at", "last_watched_at", "plays"))
    out.add(info.get("title"), category="film" if typ == "movie" else "serie", year=info.get("year"),
            status="completed" if visto else "plan_to_watch", rating=el.get("rating"),
            ext_ids={"imdb": ids.get("imdb"), "tmdb": ids.get("tmdb"), "trakt": ids.get("trakt")})
    return True


def parse_json(text: str, report=None) -> list[dict]:
    try:
        data = json.loads((text or "").lstrip("﻿"))
    except ValueError as e:
        raise ValueError(f"File JSON non valido: {e}") from e
    if isinstance(data, dict):
        data = next((data[k] for k in ("items", "entries", "list", "watchlist") if isinstance(data.get(k), list)), [data])
    out = _Out("json")
    for el in data if isinstance(data, list) else []:
        if not isinstance(el, dict):
            out.skipped += 1
        elif not _trakt_entry(out, el):
            _row_to_entry(out, {str(k).lower(): v for k, v in el.items()})
    for e in out.entries:
        if "trakt" in e["ext_ids"]:
            e["import_source"] = "trakt"
    return out.done(report)


def parse_text(text: str, report=None) -> list[dict]:
    out = _Out("text")
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(.*?)\s*\((\d{4})\)\s*$", line)
        out.add(m.group(1) if m else line, year=m.group(2) if m else None)
    return out.done(report)


def parse_pozzo(text: str, report=None) -> list[dict]:
    """Backup JSON di Pozzo (GET watchlist/export): conserva chiavi, note, priorita', voto, stato e avanzamento."""
    if len(text or "") > 10_000_000:
        raise ValueError("File troppo grande.")
    try:
        data = json.loads((text or "").lstrip("\ufeff"))
    except ValueError as e:
        raise ValueError(f"File JSON non valido: {e}") from e
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError("Non è un backup della watchlist di Pozzo (versione 1).")
    out = _Out("pozzo")
    for el in data["entries"]:
        if not isinstance(el, dict):
            out.skipped += 1
            continue
        ext = el.get("ext_ids")
        ext = _loads(ext) if isinstance(ext, str) else ext
        n = len(out.entries)
        out.add(el.get("title"), category=el.get("category"), status=el.get("status"), year=el.get("year"),
                progress=el.get("progress"), total=el.get("total"), rating=el.get("rating"), poster=el.get("poster"),
                overview=el.get("overview"), ext_ids=ext if isinstance(ext, dict) else {})
        if len(out.entries) > n:
            e = out.entries[-1]
            if el.get("kind") in ("film", "episodio"):
                e["kind"] = el["kind"]
            e["item_key"] = str(el.get("item_key") or "")[:300]
            e["linked_key"] = str(el.get("linked_key") or "")
            e["notes"] = str(el.get("notes") or "")
            e["priority"] = el.get("priority") if el.get("priority") in ("high", "medium", "low") else "medium"
            for k in ("item_id", "source", "series", "backdrop", "genre", "url"):
                e[k] = str(el.get(k) or "")
    return out.done(report)


def run_import(provider: str, content: str = "", username: str = "", client=None) -> dict:
    """Anteprima: {entries, skipped, warnings}. ValueError con messaggio italiano se l'input non e' valido."""
    report: dict = {"skipped": 0, "warnings": []}
    content = content or ""
    if len(content) > 10_000_000:
        raise ValueError("File troppo grande.")
    if provider == "anilist":
        entries = fetch_anilist(username, client, report)
    elif provider in ("mal", "csv", "json", "text", "pozzo"):
        entries = {"mal": parse_mal_xml, "csv": parse_csv, "json": parse_json, "text": parse_text,
                   "pozzo": parse_pozzo}[provider](content, report)
    else:
        raise ValueError("Servizio di importazione sconosciuto.")
    return {"entries": entries, "skipped": report["skipped"], "warnings": report["warnings"]}


# ------------------------------------------------------------------ salvataggio in blocco
def norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in t if not unicodedata.combining(c))).strip()


def _slug(t: str) -> str:
    return norm_title(t).replace(" ", "-")


def _loads(s) -> dict:
    try:
        d = json.loads(s) if s else {}
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def bulk_save(conn, entries, now=None, profile="default") -> dict:
    """Unisce `entries` alla watchlist del profilo (una transazione). Non distruttivo: vedi docstring del modulo."""
    now = now or time.time()
    rows = {r["item_key"]: dict(r) for r in conn.execute("SELECT * FROM watchlist WHERE profile=?", (profile,))}
    by_ext: dict = {}
    by_title: dict = {}

    def index(key, r):
        for k, v in _loads(r.get("ext_ids")).items():
            by_ext[(k, str(v))] = key
        by_title.setdefault((norm_title(r["title"]), r.get("year")), []).append(key)

    for k, r in rows.items():
        index(k, r)
    added = updated = skipped = 0
    for e in entries if isinstance(entries, list) else []:
        try:
            if not isinstance(e, dict):
                raise ValueError
            title = str(e.get("title") or "").strip()[:MAX_TITLE]
            if not title:
                raise ValueError
            cat = e.get("category") if e.get("category") in CATEGORIES else ""
            ext = {str(k): v for k, v in (e.get("ext_ids") or {}).items() if v not in (None, "")} if isinstance(e.get("ext_ids"), dict) else {}
            year = _year(e.get("year"))
            status = e.get("status") if e.get("status") in STATUSES else "plan_to_watch"
            progress, total = _int(e.get("progress")), _int(e.get("total"))
            rating = int(round(_rating(e.get("rating"))))
            src = str(e.get("import_source") or "")[:40]
            linked = str(e.get("linked_key") or "").strip()
            kind = "film" if cat == "film" or e.get("kind") == "film" else "episodio"
            pozzo = src == "pozzo"  # backup di Pozzo: chiavi, note e priorita' tornano come erano
            pkey = str(e.get("item_key") or "").strip()[:300] if pozzo else ""
            notes = str(e.get("notes") or "") if pozzo else ""
            priority = e.get("priority") if e.get("priority") in ("high", "medium", "low") else "medium"
            extra = {k: str(e.get(k) or "") for k in ("item_id", "source", "series", "backdrop", "genre", "url") if e.get(k)} if pozzo else {}
            poster, overview = str(e.get("poster") or ""), str(e.get("overview") or "")
        except (ValueError, TypeError, AttributeError):
            skipped += 1
            continue

        key = pkey if pkey in rows else (linked if linked in rows else None)
        for k in ("anilist", "mal", "tmdb", "imdb"):
            if key is None and k in ext:
                key = by_ext.get((k, str(ext[k])))
        if key is None:
            for cand in by_title.get((norm_title(title), year), []):
                if not cat or not rows[cand].get("category") or rows[cand]["category"] == cat:
                    key = cand
                    break
        if key is None:
            first = next(iter(ext.items()), None)
            key = pkey or linked or (f"wl:{src or 'import'}:{first[1]}" if first else f"wl:{_slug(title)}-{year or ''}")
            while key in rows and not linked and not pkey:  # stesso titolo/anno ma categoria diversa
                key += f"-{cat or 'x'}"
        old = rows.get(key)
        if old is None:
            new = {"profile": profile, "item_key": key, "item_id": key, "source": "watchlist-import", "title": title,
                   "kind": kind, "series": "", "poster": poster, "backdrop": "", "year": year, "genre": "",
                   "overview": overview, "url": "", "status": status, "priority": priority, "rating": rating,
                   "notes": notes,
                   "added_at": now, "updated_at": now, "category": cat, "progress": progress, "total": total,
                   "linked_key": linked, "ext_ids": json.dumps(ext), "import_source": src, **extra}
            conn.execute(f"INSERT INTO watchlist({','.join(new)}) VALUES({','.join('?' * len(new))})", list(new.values()))
            rows[key] = new
            index(key, new)
            added += 1
            continue
        merged_ext = {**ext, **_loads(old.get("ext_ids"))}
        upd = {
            "progress": max(_int(old.get("progress")), progress),
            "total": max(_int(old.get("total")), total),
            "status": status if (old.get("status") or "plan_to_watch") == "plan_to_watch" else old["status"],
            "rating": old.get("rating") or rating,
            "category": old.get("category") or cat,
            "poster": old.get("poster") or poster,
            "overview": old.get("overview") or overview,
            "year": old.get("year") or year,
            "linked_key": old.get("linked_key") or linked,
            "import_source": old.get("import_source") or src,
            "ext_ids": json.dumps(merged_ext),
        }
        if pozzo:  # non sovrascrive quanto l'utente ha gia' impostato in questo profilo
            if not old.get("notes"):
                upd["notes"] = notes
            if (old.get("priority") or "medium") == "medium":
                upd["priority"] = priority
        if all((old.get(k) or "") == (v or "") or old.get(k) == v for k, v in upd.items()):
            skipped += 1
            continue
        upd["updated_at"] = now
        conn.execute(f"UPDATE watchlist SET {','.join(k + '=?' for k in upd)} WHERE profile=? AND item_key=?", [*upd.values(), profile, key])
        old.update(upd)
        index(key, old)
        updated += 1
    conn.commit()
    return {"added": added, "updated": updated, "skipped": skipped}
