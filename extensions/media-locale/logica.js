// Helper puri di media-locale (senza DOM ne' rete): durate, raggruppamento episodi, avanzamento, prossimo episodio.

/** Formatta i secondi in mm:ss oppure h:mm:ss (es. 75 -> "1:15", 3665 -> "1:01:05"). Vuoto se non valido o negativo. */
export function formatDuration(sec) {
  if (sec == null || sec === "") return "";
  const n = Number(sec);
  if (!Number.isFinite(n) || n < 0) return "";
  const s = Math.floor(n);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const pad = (v) => String(v).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(r)}` : `${m}:${pad(r)}`;
}

/** Percentuale di avanzamento (0..100 intero). 100 se segnato visto; altrimenti resume_pos/duration. */
export function resumeOf(item) {
  if (!item) return 0;
  if (item.seen === true || item.seen === 1 || item.seen === "true") return 100;
  const pos = Number(item.resume_pos ?? item.pos ?? 0);
  const dur = Number(item.duration ?? 0);
  if (!Number.isFinite(pos) || !Number.isFinite(dur) || dur <= 0 || pos <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((pos / dur) * 100)));
}

/** Vero se l'item e' segnato come visto (seen=true) oppure se la posizione supera il 90% della durata. */
export function isSeen(item) {
  if (!item) return false;
  if (item.seen === true || item.seen === 1 || item.seen === "true") return true;
  const pos = Number(item.resume_pos ?? item.pos ?? 0);
  const dur = Number(item.duration ?? 0);
  return Number.isFinite(pos) && Number.isFinite(dur) && dur > 0 && (pos / dur) >= 0.9;
}

/**
 * Raggruppa gli episodi per serie e stagione, ordinando le puntate per numero (poi titolo).
 * Restituisce { [serie]: { [stagione]: [episodi...] } }. Ignora item privi di info serie/episodio.
 */
export function groupEpisodes(items) {
  const raw = {};
  for (const it of items || []) {
    if (!it) continue;
    if (it.kind && it.kind !== "episodio" && it.episode == null && it.season == null) continue;
    const series = String(it.series || it.show || it.title || "Varie").trim();
    const season = it.season != null && !Number.isNaN(Number(it.season)) ? Number(it.season) : 1;
    if (!raw[series]) raw[series] = {};
    if (!raw[series][season]) raw[series][season] = [];
    raw[series][season].push(it);
  }
  const out = {};
  for (const s of Object.keys(raw).sort((a, b) => a.localeCompare(b))) {
    out[s] = {};
    const seasons = Object.keys(raw[s]).sort((a, b) => Number(a) - Number(b));
    for (const sn of seasons) {
      out[s][sn] = raw[s][sn].slice().sort((a, b) => {
        const ea = a.episode != null ? Number(a.episode) : 0;
        const eb = b.episode != null ? Number(b.episode) : 0;
        return ea - eb || String(a.title || "").localeCompare(String(b.title || ""));
      });
    }
  }
  return out;
}

/**
 * Restituisce l'episodio successivo a currentId all'interno della stessa serie (ordinata per stagione ed episodio).
 * Restituisce null se e' l'ultimo episodio, se currentId non e' trovato o se items e' vuoto.
 */
export function nextEpisode(items, currentId) {
  if (!items || !items.length || currentId == null) return null;
  const cur = items.find((i) => i && String(i.id) === String(currentId));
  if (!cur) return null;
  const seriesKey = String(cur.series || "").trim().toLowerCase();
  const sameSeries = items.filter((i) => {
    if (!i) return false;
    if (i.kind && i.kind !== "episodio" && i.episode == null && i.season == null) return false;
    return String(i.series || "").trim().toLowerCase() === seriesKey;
  });
  sameSeries.sort((a, b) => {
    const sa = a.season != null ? Number(a.season) : 1;
    const sb = b.season != null ? Number(b.season) : 1;
    if (sa !== sb) return sa - sb;
    const ea = a.episode != null ? Number(a.episode) : 0;
    const eb = b.episode != null ? Number(b.episode) : 0;
    return ea - eb || String(a.title || "").localeCompare(String(b.title || ""));
  });
  const idx = sameSeries.findIndex((i) => String(i.id) === String(currentId));
  return (idx >= 0 && idx + 1 < sameSeries.length) ? sameSeries[idx + 1] : null;
}

/**
 * Chiave univoca dell'item nel formato "${source}:${id}".
 * Restituisce stringa vuota se l'item o l'id non sono validi.
 */
export function compositeKey(item) {
  if (!item || item.id == null) return "";
  const idStr = String(item.id).trim();
  if (idStr === "" || idStr === "undefined" || idStr === "null") return "";
  return `${item.source || "media-locale"}:${item.id}`;
}

/**
 * Restituisce badge informativo ({ id, label, icon }) per la sorgente specificata.
 */
export function sourceBadge(source) {
  const s = String(source || "").trim().toLowerCase();
  if (s === "media-locale" || s === "locale") {
    return { id: "locale", label: "Disco Locale", icon: "📁" };
  }
  if (s === "jellyfin") {
    return { id: "jellyfin", label: "Jellyfin", icon: "🌐" };
  }
  if (s === "plex") {
    return { id: "plex", label: "Plex", icon: "🟠" };
  }
  if (s === "kodi" || s.startsWith("kodi")) {
    return { id: "kodi", label: "Kodi Addon", icon: "🧩" };
  }
  if (s === "stream4me" || s.startsWith("stream4me") || s === "s4me") {
    return { id: "web", label: "Stream4me", icon: "🧩" };
  }
  return { id: "web", label: "Web / Streaming", icon: "📡" };
}

/**
 * Filtra gli elementi dell'hub multimediale in base a tab, sorgente, ricerca testuale e preferiti.
 */
export function filterHubItems(items, { tab = "tutti", sourceFilter = "all", query = "", onlyFavs = false, favs = new Set() } = {}) {
  const list = items || [];
  const tabNorm = String(tab || "tutti").toLowerCase();
  const srcFilterNorm = String(sourceFilter || "all").toLowerCase();
  const q = String(query || "").trim().toLowerCase();

  const checkFav = (key) => {
    if (!key || !favs) return false;
    if (typeof favs.has === "function") return favs.has(key);
    if (Array.isArray(favs)) return favs.includes(key);
    return false;
  };

  return list.filter((it) => {
    if (!it) return false;

    // Tab filter
    if (tabNorm === "film" && it.kind !== "film") return false;
    if (tabNorm === "serie" && !(it.kind === "episodio" || Boolean(it.series && it.kind !== "brano"))) return false;
    if (tabNorm === "musica" && it.kind !== "brano") return false;
    if (tabNorm === "web" || tabNorm === "stream4me") {
      const bId = sourceBadge(it.source).id;
      if (bId !== "web" && bId !== "kodi") return false;
    }

    // Source filter
    if (srcFilterNorm === "locale") {
      if (sourceBadge(it.source).id !== "locale") return false;
    } else if (srcFilterNorm === "server") {
      const bId = sourceBadge(it.source).id;
      if (bId !== "jellyfin" && bId !== "plex") return false;
    } else if (srcFilterNorm === "web") {
      const bId = sourceBadge(it.source).id;
      if (bId !== "web" && bId !== "kodi") return false;
    }

    // Text query
    if (q) {
      const t = String(it.title || "").toLowerCase();
      const s = String(it.series || "").toLowerCase();
      const a = String(it.album || "").toLowerCase();
      const o = String(it.overview || "").toLowerCase();
      const g = String(it.genre || it.genres || "").toLowerCase();
      const y = String(it.year || "").toLowerCase();
      if (!t.includes(q) && !s.includes(q) && !a.includes(q) && !o.includes(q) && !g.includes(q) && !y.includes(q)) {
        return false;
      }
    }

    // Favorites filter
    if (onlyFavs) {
      const ck = compositeKey(it);
      const idStr = it.id != null ? String(it.id) : "";
      const seriesKey = it.series ? `series:${it.series}` : "";
      const isFav = (ck && checkFav(ck)) || (idStr && checkFav(idStr)) || (seriesKey && checkFav(seriesKey));
      if (!isFav) return false;
    }

    return true;
  });
}

/**
 * Unisce gli item in corso tra dati live e cache locale, con priorita' ai dati live.
 */
export function mergeContinueWatching(liveItems, cachedItems, limit = 20) {
  const result = [];
  const liveKeys = new Set();
  const addedKeys = new Set();

  for (const it of liveItems || []) {
    if (!it) continue;
    const ck = compositeKey(it);
    if (!ck) continue;
    liveKeys.add(ck);
    if (!addedKeys.has(ck) && resumeOf(it) > 0 && !isSeen(it)) {
      addedKeys.add(ck);
      result.push(it);
    }
  }

  for (const it of cachedItems || []) {
    if (!it) continue;
    const ck = compositeKey(it);
    if (!ck) continue;
    if (liveKeys.has(ck)) continue;
    if (!addedKeys.has(ck) && resumeOf(it) > 0 && !isSeen(it)) {
      addedKeys.add(ck);
      result.push(it);
    }
  }

  const max = typeof limit === "number" && limit >= 0 ? limit : 20;
  return result.slice(0, max);
}

/**
 * Seleziona l'elemento in evidenza (hero banner) prioritizzando l'ultimo in visione o con poster/backdrop.
 */
export function pickHeroItem(items, resumeItems) {
  if (resumeItems && resumeItems.length > 0 && resumeItems[0]) {
    return resumeItems[0];
  }
  const list = Array.isArray(items) ? items : [];
  for (const it of list) {
    if (it && (it.backdrop || it.poster)) {
      return it;
    }
  }
  return list[0] || null;
}

/**
 * Interroga in parallelo le sorgenti locali, server e web, restituendo gli item deduplicati e lo stato.
 */
export async function federatedList(gs, { kind = "", query = "", timeoutMs = 1500 } = {}) {
  const qp = [];
  if (kind) qp.push(`kind=${encodeURIComponent(kind)}`);
  if (query) {
    qp.push(`query=${encodeURIComponent(query)}`);
    qp.push(`q=${encodeURIComponent(query)}`);
  }
  qp.push("limit=2000");
  const qs = qp.join("&");

  const sources = [
    { key: "media-locale", url: `/plugin-api/media-locale/list?${qs}` },
    { key: "media-server", url: `/plugin-api/media-server/list?${qs}` },
    { key: "ricette-web", url: `/plugin-api/ricette-web/list?${qs}` },
  ];

  const fetchSource = (url) => {
    let timer = null;
    const timeoutPromise = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("Timeout")), timeoutMs);
    });
    return Promise.race([
      gs.api(url),
      timeoutPromise,
    ]).finally(() => {
      if (timer != null) clearTimeout(timer);
    });
  };

  const results = await Promise.allSettled(sources.map((s) => fetchSource(s.url)));

  const sourcesStatus = {
    "media-locale": false,
    "media-server": false,
    "ricette-web": false,
  };
  const rawItems = [];

  results.forEach((res, i) => {
    const key = sources[i].key;
    if (res.status === "fulfilled" && res.value && !res.value.error) {
      sourcesStatus[key] = true;
      const val = res.value;
      const list = Array.isArray(val) ? val : (Array.isArray(val?.items) ? val.items : []);
      rawItems.push(...list);
    }
  });

  const items = [];
  const seenKeys = new Set();
  for (const it of rawItems) {
    if (!it) continue;
    const ck = compositeKey(it);
    if (ck) {
      if (seenKeys.has(ck)) continue;
      seenKeys.add(ck);
    }
    items.push(it);
  }

  return { items, sourcesStatus };
}

export const WATCHLIST_STATUSES = {
  plan_to_watch: { id: "plan_to_watch", label: "Da guardare", icon: "📌", order: 1 },
  watching: { id: "watching", label: "In corso", icon: "▶", order: 2 },
  on_hold: { id: "on_hold", label: "In pausa", icon: "⏸", order: 3 },
  completed: { id: "completed", label: "Completato", icon: "✓", order: 4 },
  dropped: { id: "dropped", label: "Abbandonato", icon: "✕", order: 5 },
};

export const WATCHLIST_PRIORITIES = {
  high: { id: "high", label: "Alta", icon: "🔥", weight: 3 },
  medium: { id: "medium", label: "Media", icon: "⚡", weight: 2 },
  low: { id: "low", label: "Bassa", icon: "💤", weight: 1 },
};

/**
 * Normalizza un elemento della watchlist, riempiendo i metadati mancanti da itemFallback se fornito.
 */
export function normalizeWatchlistEntry(entry, itemFallback = null) {
  const e = entry && typeof entry === "object" ? entry : {};
  const fb = itemFallback && typeof itemFallback === "object" ? itemFallback : {};

  const source = String(e.source || fb.source || "media-locale").trim() || "media-locale";
  const rawId = e.item_id ?? e.id ?? fb.item_id ?? fb.id ?? "";
  let itemId = String(rawId).trim();
  if (itemId === "undefined" || itemId === "null") itemId = "";

  let itemKey = String(e.item_key || "").trim();
  if (!itemKey) {
    itemKey = compositeKey({ id: itemId || e.id, source }) || compositeKey(fb);
  }
  if (!itemId && itemKey.includes(":")) {
    itemId = itemKey.split(":", 2)[1] || "";
  }

  const title = String(e.title || fb.title || itemId || itemKey || "").trim();
  const kind = String(e.kind || fb.kind || "film").trim() || "film";
  const series = String(e.series ?? fb.series ?? "").trim();
  const poster = String(e.poster ?? fb.poster ?? "").trim();
  const backdrop = String(e.backdrop ?? fb.backdrop ?? "").trim();
  const genre = String(e.genre ?? e.genres ?? fb.genre ?? fb.genres ?? "").trim();
  const overview = String(e.overview ?? fb.overview ?? "").trim();
  const url = String(e.url ?? fb.url ?? "").trim();

  const rawYear = e.year != null && e.year !== "" ? e.year : fb.year;
  const parsedYear = rawYear != null && rawYear !== "" && Number.isFinite(Number(rawYear)) ? Math.trunc(Number(rawYear)) : null;

  const statusKey = String(e.status || "").trim();
  const status = WATCHLIST_STATUSES[statusKey] ? statusKey : "plan_to_watch";

  const prioKey = String(e.priority || "").trim();
  const priority = WATCHLIST_PRIORITIES[prioKey] ? prioKey : "medium";

  const rawRating = Number(e.rating ?? 0);
  const rating = Number.isFinite(rawRating) ? Math.min(10, Math.max(0, Math.round(rawRating))) : 0;

  const notes = e.notes != null ? String(e.notes) : "";
  const added_at = Number.isFinite(Number(e.added_at)) ? Number(e.added_at) : 0;
  const updated_at = Number.isFinite(Number(e.updated_at)) ? Number(e.updated_at) : added_at;

  return {
    ...fb,
    ...e,
    item_key: itemKey,
    item_id: itemId,
    id: itemId || e.id || fb.id || itemKey,
    source,
    title,
    kind,
    series,
    poster,
    backdrop,
    year: parsedYear,
    genre,
    overview,
    url,
    status,
    priority,
    rating,
    notes,
    added_at,
    updated_at,
  };
}

/**
 * Filtra e ordina gli elementi della watchlist.
 */
export function sortAndFilterWatchlist(entries, { status = "all", priority = "all", query = "", sortBy = "priority" } = {}) {
  const list = Array.isArray(entries) ? entries : [];
  const stFilter = String(status || "all").trim();
  const prFilter = String(priority || "all").trim();
  const q = String(query || "").trim().toLowerCase();
  const sortMode = String(sortBy || "priority").trim();

  const filtered = list.filter((raw) => {
    if (!raw) return false;
    const e = normalizeWatchlistEntry(raw);

    if (stFilter && stFilter !== "all") {
      if (stFilter === "active") {
        if (e.status === "completed" || e.status === "dropped") return false;
      } else if (e.status !== stFilter) {
        return false;
      }
    }

    if (prFilter && prFilter !== "all") {
      if (e.priority !== prFilter) return false;
    }

    if (q) {
      const hay = [
        e.title,
        e.series,
        e.notes,
        e.genre,
        e.overview,
      ].map((v) => String(v || "").toLowerCase());
      if (!hay.some((field) => field.includes(q))) return false;
    }

    return true;
  });

  const weightOf = (e) => WATCHLIST_PRIORITIES[e?.priority]?.weight ?? 2;
  const orderOf = (e) => WATCHLIST_STATUSES[e?.status]?.order ?? 1;
  const isFinished = (e) => e?.status === "completed" || e?.status === "dropped";
  const recencyOf = (e) => Number(e?.updated_at || e?.added_at || 0);

  return filtered.slice().sort((a, b) => {
    if (sortMode === "status") {
      const oa = orderOf(a);
      const ob = orderOf(b);
      if (oa !== ob) return oa - ob;
      const wa = weightOf(a);
      const wb = weightOf(b);
      if (wa !== wb) return wb - wa;
      return String(a?.title || "").localeCompare(String(b?.title || ""));
    }

    if (sortMode === "rating") {
      const ra = Number(a?.rating || 0);
      const rb = Number(b?.rating || 0);
      if (ra !== rb) return rb - ra;
      const wa = weightOf(a);
      const wb = weightOf(b);
      if (wa !== wb) return wb - wa;
      return String(a?.title || "").localeCompare(String(b?.title || ""));
    }

    if (sortMode === "recent") {
      const ta = recencyOf(a);
      const tb = recencyOf(b);
      if (ta !== tb) return tb - ta;
      return String(a?.title || "").localeCompare(String(b?.title || ""));
    }

    if (sortMode === "title") {
      return String(a?.title || "").localeCompare(String(b?.title || ""));
    }

    // Default: "priority" -> active before finished, then priority weight DESC, then updated_at DESC, then title A-Z
    const fa = isFinished(a) ? 1 : 0;
    const fb = isFinished(b) ? 1 : 0;
    if (fa !== fb) return fa - fb;

    const wa = weightOf(a);
    const wb = weightOf(b);
    if (wa !== wb) return wb - wa;

    const ua = Number(a?.updated_at || 0);
    const ub = Number(b?.updated_at || 0);
    if (ua !== ub) return ub - ua;

    return String(a?.title || "").localeCompare(String(b?.title || ""));
  });
}

/**
 * Calcola le statistiche aggregate della watchlist.
 */
export function watchlistStats(entries) {
  const stats = {
    total: 0,
    plan_to_watch: 0,
    watching: 0,
    on_hold: 0,
    completed: 0,
    dropped: 0,
    high_priority: 0,
  };
  for (const raw of entries || []) {
    if (!raw) continue;
    const st = WATCHLIST_STATUSES[raw.status] ? raw.status : "plan_to_watch";
    const pr = WATCHLIST_PRIORITIES[raw.priority] ? raw.priority : "medium";
    stats.total += 1;
    stats[st] += 1;
    if (pr === "high") {
      stats.high_priority += 1;
    }
  }
  return stats;
}
