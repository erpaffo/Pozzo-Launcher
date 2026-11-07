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

/** Episodi della serie di currentId, ordinati per stagione ed episodio, e posizione dell'episodio ({list: [], index: -1} se non c'è). */
export function episodeSiblings(items, currentId) {
  const none = { list: [], index: -1 };
  if (!items || !items.length || currentId == null) return none;
  const cur = items.find((i) => i && String(i.id) === String(currentId));
  if (!cur) return none;
  const seriesKey = String(cur.series || "").trim().toLowerCase();
  const list = items.filter((i) => {
    if (!i) return false;
    if (i.kind && i.kind !== "episodio" && i.episode == null && i.season == null) return false;
    return String(i.series || "").trim().toLowerCase() === seriesKey;
  });
  list.sort((a, b) => {
    const sa = a.season != null ? Number(a.season) : 1;
    const sb = b.season != null ? Number(b.season) : 1;
    if (sa !== sb) return sa - sb;
    const ea = a.episode != null ? Number(a.episode) : 0;
    const eb = b.episode != null ? Number(b.episode) : 0;
    return ea - eb || String(a.title || "").localeCompare(String(b.title || ""));
  });
  return { list, index: list.findIndex((i) => String(i.id) === String(currentId)) };
}

/** Episodio successivo nella stessa serie; null se è l'ultimo, se currentId non si trova o se items è vuoto. */
export function nextEpisode(items, currentId) {
  const { list, index } = episodeSiblings(items, currentId);
  return (index >= 0 && index + 1 < list.length) ? list[index + 1] : null;
}

/** Episodio precedente nella stessa serie; null se è il primo o currentId non si trova. */
export function prevEpisode(items, currentId) {
  const { list, index } = episodeSiblings(items, currentId);
  return index > 0 ? list[index - 1] : null;
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
export function sourceBadge(source, provider) {
  const p = String(provider || "").trim().toLowerCase();
  if (p === "kodi") return { id: "kodi", label: "Kodi Addon", icon: "🧩" };
  if (p === "stream4me") return { id: "web", label: "Stream4me", icon: "🧩" };
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

/** Badge di tutte le sorgenti di un item (item.sources dopo il dedup), il primo e' quello dell'item. */
export function sourceBadges(item) {
  const first = sourceBadge(item?.source, item?.provider);
  const out = [first];
  for (const src of item?.sources || []) {
    const b = sourceBadge(src, src === item?.source ? item?.provider : "");
    if (!out.some((x) => x.id === b.id && x.label === b.label)) out.push(b);
  }
  return out;
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
    const ids = sourceBadges(it).map((b) => b.id); // item fusi: conta ogni sorgente in `sources`

    // Tab filter
    if (tabNorm === "film" && it.kind !== "film") return false;
    if (tabNorm === "serie" && !(it.kind === "episodio" || Boolean(it.series && it.kind !== "brano"))) return false;
    if (tabNorm === "musica" && it.kind !== "brano") return false;
    if (tabNorm === "web" || tabNorm === "stream4me") {
      if (!ids.some((b) => b === "web" || b === "kodi")) return false;
    }

    // Source filter
    if (srcFilterNorm === "locale") {
      if (!ids.includes("locale")) return false;
    } else if (srcFilterNorm === "server") {
      if (!ids.some((b) => b === "jellyfin" || b === "plex")) return false;
    } else if (srcFilterNorm === "web") {
      // «Web» = ricette web: i titoli salvati da Stream4me hanno la loro scheda
      if (it.provider === "stream4me" || !ids.some((b) => b === "web" || b === "kodi")) return false;
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

const SOURCE_RANK = { "media-locale": 0, locale: 0, jellyfin: 1, plex: 2 };
const srcRank = (it) => SOURCE_RANK[String(it.source || "media-locale").toLowerCase()] ?? 3;

const normTitleBasic = (t) => String(t || "").toLowerCase().replace(/\(\s*ita\s*\)/g, " ")
  .normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();

/** Chiave di dedup cross-sorgente; "" se non calcolabile. */
function dedupKey(it) {
  const kind = it.kind || "";
  if (kind === "episodio" && it.series) {
    return `${kind}|${normTitleBasic(it.series)}|${it.season ?? ""}|${it.episode ?? ""}`;
  }
  const t = normTitleBasic(it.title);
  // shortcut: omonimi con stesso anno (o senza anno) dello stesso kind si fondono; se serve, aggiungere un id esterno (imdb/tmdb).
  return t ? `${kind}|${t}|${it.year ?? ""}` : "";
}

/** Deduplica mantenendo la sorgente preferita; ogni item risultante ha `sources`. */
function dedupItems(rawItems) {
  const byKey = new Map();
  const seenCk = new Set();
  for (const it of rawItems) {
    if (!it) continue;
    const ck = compositeKey(it);
    if (ck) {
      if (seenCk.has(ck)) continue;
      seenCk.add(ck);
    }
    const key = dedupKey(it) || ck || `#${byKey.size}`;
    const src = String(it.source || "media-locale");
    const cur = byKey.get(key);
    if (!cur) {
      byKey.set(key, { ...it, sources: [src] });
      continue;
    }
    const sources = cur.sources.includes(src) ? cur.sources : [...cur.sources, src];
    byKey.set(key, srcRank(it) < srcRank(cur) ? { ...it, sources } : { ...cur, sources });
  }
  return [...byKey.values()];
}

/**
 * Interroga in parallelo le sorgenti locali, server e web, restituendo gli item deduplicati e lo stato.
 * onPartial(items, sourcesStatus) viene chiamata a ogni sorgente completata (items cumulativi).
 * sourcesStatus: [{id, state: "ok"|"slow"|"absent"|"error", count, ms}].
 */
export async function federatedList(gs, { kind = "", query = "", timeoutMs = 2000, onPartial } = {}) {
  const qp = [];
  if (kind) qp.push(`kind=${encodeURIComponent(kind)}`);
  if (query) {
    qp.push(`query=${encodeURIComponent(query)}`);
    qp.push(`q=${encodeURIComponent(query)}`);
  }
  qp.push("limit=2000");
  const qs = qp.join("&");

  const sources = [
    { id: "media-locale", url: `/plugin-api/media-locale/list?${qs}` },
    { id: "media-server", url: `/plugin-api/media-server/list?${qs}` },
    { id: "ricette-web", url: `/plugin-api/ricette-web/list?${qs}` },
  ];
  const status = sources.map((s) => ({ id: s.id, state: "slow", count: 0, ms: timeoutMs }));
  const lists = sources.map(() => []);
  const snapshot = () => dedupItems(lists.flat());

  await Promise.all(sources.map(async (s, i) => {
    const t0 = Date.now();
    const ac = typeof AbortController === "function" ? new AbortController() : null;
    let timer = null;
    let expired = false;
    const timeout = new Promise((resolve) => {
      timer = setTimeout(() => { expired = true; if (ac) ac.abort(); resolve(null); }, timeoutMs);
    });
    const call = Promise.resolve().then(() => gs.api(s.url, ac ? { signal: ac.signal } : undefined))
      .then((value) => ({ value }), (err) => ({ err }));
    const res = await Promise.race([call, timeout.then(() => ({ slow: true }))]);
    if (timer != null) clearTimeout(timer);
    const ms = Date.now() - t0;
    if (res.slow || (expired && res.err)) {
      status[i] = { id: s.id, state: "slow", count: 0, ms };
    } else if (res.err) {
      const absent = /404|not found|non trovat|not installed|non installat/i.test(String(res.err?.message || res.err));
      status[i] = { id: s.id, state: absent ? "absent" : "error", count: 0, ms };
    } else if (!res.value || res.value.error) {
      status[i] = { id: s.id, state: "error", count: 0, ms };
    } else {
      const val = res.value;
      lists[i] = Array.isArray(val) ? val : (Array.isArray(val?.items) ? val.items : []);
      status[i] = { id: s.id, state: "ok", count: lists[i].length, ms };
    }
    if (typeof onPartial === "function") onPartial(snapshot(), status.map((x) => ({ ...x })));
  }));

  return { items: snapshot(), sourcesStatus: status };
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

export const WATCHLIST_CATEGORIES = {
  film: { id: "film", label: "Film", icon: "🎬" },
  serie: { id: "serie", label: "Serie TV", icon: "📺" },
  anime: { id: "anime", label: "Anime", icon: "🇯🇵" },
};

/** Categoria della voce: esplicita se valida, altrimenti dedotta (anime / film / serie). */
export function categoryOf(entry) {
  const e = entry && typeof entry === "object" ? entry : {};
  const c = String(e.category || "").trim().toLowerCase();
  if (WATCHLIST_CATEGORIES[c]) return c;
  if (/anime/i.test(`${e.source || ""} ${e.genre ?? e.genres ?? ""}`)) return "anime";
  if (String(e.kind || "film") === "film" && !String(e.series || "").trim()) return "film";
  return "serie";
}

/** Titolo normalizzato per il confronto: senza accenti, punteggiatura, articoli iniziali e suffissi (ita/stagione). */
export function normTitle(s) {
  let t = String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/\([^)]*\)|\[[^\]]*\]/g, " ")
    .replace(/\b(?:season|stagione|stag|part|parte)\s*\d+\b|\b\d+(?:st|nd|rd|th)\s+season\b/g, " ")
    .replace(/\b(?:sub[\s-]*ita|ita|dub)\b/g, " ")
    .replace(/[^a-z0-9]+/g, " ").trim();
  t = t.replace(/^(?:il|lo|la|i|gli|le|l|un|uno|una|the|a|an)\s+(?=\S)/, "");
  return t.replace(/\s+/g, " ").trim();
}

const wlSrcRank = (it) => ({ "media-locale": 0, locale: 0, jellyfin: 1, plex: 2 })[String(it?.source || "media-locale").toLowerCase()] ?? 3;

/**
 * Cerca nel catalogo il titolo corrispondente alla voce. Ritorna {item, score}|null.
 * Per serie/anime l'item e' un episodio rappresentativo (il chiamante usa item.series).
 * Soglia alta: titolo esatto, oppure contenimento forte con anno compatibile (±1).
 */
export function matchLibraryItem(entry, items) {
  const e = normalizeWatchlistEntry(entry);
  const names = [...new Set([e.title, e.original_title].map(normTitle).filter(Boolean))];
  if (!names.length || !Array.isArray(items)) return null;
  const wantFilm = e.category === "film";
  let best = null;
  for (const it of items) {
    if (!it) continue;
    const isEp = it.kind === "episodio" || Boolean(it.series);
    if (wantFilm === isEp) continue;
    const cand = normTitle(isEp ? (it.series || it.title) : it.title);
    if (!cand) continue;
    const y1 = e.year, y2 = Number.isFinite(Number(it.year)) && Number(it.year) > 0 ? Math.trunc(Number(it.year)) : null;
    const yearKnown = y1 != null && y2 != null;
    if (yearKnown && Math.abs(y1 - y2) > 1) continue;
    let score = 0;
    for (const n of names) {
      if (n === cand) { score = Math.max(score, yearKnown ? 1 : 0.9); continue; }
      const [sh, lo] = n.length <= cand.length ? [n, cand] : [cand, n];
      if (yearKnown && sh.length >= 5 && sh.length / lo.length >= 0.6 && ` ${lo} `.includes(` ${sh} `)) {
        score = Math.max(score, 0.7 + 0.2 * (sh.length / lo.length));
      }
    }
    if (score < 0.7) continue;
    if (!best || score > best.score || (score === best.score && wlSrcRank(it) < wlSrcRank(best.item))) best = { item: it, score };
  }
  return best;
}

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

  const toCount = (v) => (Number.isFinite(Number(v)) && Number(v) > 0 ? Math.trunc(Number(v)) : 0);
  const extIds = e.ext_ids && typeof e.ext_ids === "object" && !Array.isArray(e.ext_ids) ? e.ext_ids : {};
  const category = categoryOf({ ...fb, ...e, kind, series, genre });

  return {
    ...fb,
    ...e,
    category,
    progress: toCount(e.progress),
    total: toCount(e.total),
    linked_key: typeof e.linked_key === "string" ? e.linked_key.trim() : "",
    ext_ids: extIds,
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
export function sortAndFilterWatchlist(entries, { status = "all", priority = "all", query = "", sortBy = "priority", category = "all" } = {}) {
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

    if (category && category !== "all" && e.category !== category) return false;

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
    by_category: { film: 0, serie: 0, anime: 0 },
  };
  for (const raw of entries || []) {
    if (!raw) continue;
    const st = WATCHLIST_STATUSES[raw.status] ? raw.status : "plan_to_watch";
    const pr = WATCHLIST_PRIORITIES[raw.priority] ? raw.priority : "medium";
    stats.total += 1;
    stats[st] += 1;
    stats.by_category[categoryOf(raw)] += 1;
    if (pr === "high") {
      stats.high_priority += 1;
    }
  }
  return stats;
}

/** Profilo attivo del core (GET /api/profiles); "default" se non c'è. */
export function activeProfile() {
  try { return String(globalThis.GS?.library?.()?.profiles?.active || "") || "default"; } catch { return "default"; }
}

/** Chiave per profilo: `<chiave>:<profilo>`. */
export function profileKey(base, profile = activeProfile()) { return `${base}:${profile}`; }

/**
 * Migrazione una tantum: se manca la chiave del profilo ma c'è la vecchia chiave globale, la copia nel profilo attivo
 * e toglie la vecchia (così un altro profilo non la riceve). Ritorna la chiave per profilo.
 */
export function migrateToProfileKey(storage, base, profile = activeProfile()) {
  const key = profileKey(base, profile);
  try {
    if (storage && storage.getItem(key) == null) {
      const old = storage.getItem(base);
      if (old != null) { storage.setItem(key, old); storage.removeItem?.(base); }
    }
  } catch { /* storage non disponibile */ }
  return key;
}

export const CATALOG_SNAPSHOT_KEY = "gs.pm_catalog_snapshot";
const SNAPSHOT_MAX = 1500;
const SNAPSHOT_FIELDS = ["id", "kind", "title", "series", "season", "episode", "year", "duration", "poster", "backdrop",
  "source", "sources", "provider", "seen", "resume_pos", "album", "genres", "channel_id", "source_label", "url"];

/** Ultimo catalogo federato, salvato per mostrarlo subito all'apertura mentre le sorgenti si aggiornano. Mai blocca: storage assente o pieno = nessuna cache. */
export function saveCatalogSnapshot(items, storage = (typeof localStorage !== "undefined" ? localStorage : null), profile = activeProfile()) {
  if (!storage || !Array.isArray(items) || !items.length) return false;
  const slim = items.slice(0, SNAPSHOT_MAX).map((it) => {
    const o = {};
    for (const k of SNAPSHOT_FIELDS) if (it && it[k] != null && it[k] !== "") o[k] = it[k];
    if (it && it.overview) o.overview = String(it.overview).slice(0, 200);
    return o;
  });
  try { storage.setItem(profileKey(CATALOG_SNAPSHOT_KEY, profile), JSON.stringify({ t: Date.now(), items: slim })); return true; } catch { return false; }
}

/** Catalogo salvato più di recente; [] se manca, è illeggibile o più vecchio di `maxAgeMs` (7 giorni). */
export function loadCatalogSnapshot(storage = (typeof localStorage !== "undefined" ? localStorage : null), maxAgeMs = 7 * 864e5, profile = activeProfile()) {
  try {
    const raw = storage && storage.getItem(migrateToProfileKey(storage, CATALOG_SNAPSHOT_KEY, profile));
    const snap = raw ? JSON.parse(raw) : null;
    if (!snap || !Array.isArray(snap.items) || Date.now() - Number(snap.t || 0) > maxAgeMs) return [];
    return snap.items.filter((it) => it && it.id != null && it.title != null);
  } catch { return []; }
}

/**
 * Unisce la watchlist del server con la copia del browser senza perdere nulla: stessa voce = vince la più recente
 * (a parità, il server); `localOnly` sono le voci che il server non ha (salvataggi falliti in passato) da rimandargli.
 */
export function mergeWatchlists(server, local) {
  const keyOf = (e) => String(e?.item_key || (e?.source && e?.item_id ? `${e.source}:${e.item_id}` : "") || e?.item_id || "");
  const out = new Map();
  for (const e of server || []) { const k = keyOf(e); if (k) out.set(k, e); }
  const serverKeys = new Set(out.keys());
  const localOnly = [];
  for (const e of local || []) {
    const k = keyOf(e);
    if (!k) continue;
    const cur = out.get(k);
    if (!cur) { out.set(k, e); localOnly.push(e); }
    else if (Number(e.updated_at || 0) > Number(cur.updated_at || 0)) out.set(k, { ...cur, ...e });
  }
  return { entries: [...out.values()], localOnly: localOnly.filter((e) => !serverKeys.has(keyOf(e))) };
}

/**
 * Una «serie» con una sola puntata è un film (es. «Snatch - Lo strappo» catalogato come serie TV). Si decide per
 * prova: il provider ha detto di avere 1 solo episodio (`episode_count`), oppure in elenco c'è una sola puntata della serie
 * (per tutte le sorgenti insieme: se un'altra ne ha di più, resta serie). Non modifica gli originali.
 * shortcut: una serie locale con UNA sola puntata scaricata diventa film finché non ne arrivano altre; da rivedere se serve un'eccezione.
 */
/**
 * Le voci dei provider streaming (Stream4me, Kodi, ricette web) sono righe di CATALOGO: ognuna è un titolo intero (una serie
 * con tutti i suoi episodi), non una puntata. Solo file locali e server Jellyfin/Plex hanno una riga per episodio.
 */
export function isCatalogRow(it) {
  const src = String(it?.source || "").toLowerCase();
  return it?.provider === "stream4me" || it?.provider === "kodi" || src === "ricette-web" || src === "stream4me" || src === "web";
}

/**
 * Riepilogo «N stagioni · M episodi» di una serie dalle sue voci. Con episodi veri (file, server) si contano quelli;
 * con righe di catalogo streaming il numero reale lo sa solo il provider (`episode_count`/`season_count`, noti dopo aver
 * aperto il dettaglio): finché manca, `known: false` e l'interfaccia non mostra numeri inventati.
 */
export function seriesSummary(eps) {
  const list = Array.isArray(eps) ? eps.filter(Boolean) : [];
  const real = list.filter((e) => !isCatalogRow(e));
  if (real.length) {
    const pairs = new Set(real.map((e) => `${e.season ?? 1}:${e.episode ?? e.id}`));
    const seasons = new Set(real.map((e) => e.season ?? 1));
    return { count: pairs.size, seasonsCount: seasons.size, known: true };
  }
  const n = Math.max(0, ...list.map((e) => Number(e.episode_count) || 0));
  const st = Math.max(0, ...list.map((e) => Number(e.season_count) || 0));
  return n > 0 ? { count: n, seasonsCount: st || 1, known: true } : { count: 0, seasonsCount: 0, known: false };
}

export function collapseSingleEpisodeSeries(items) {
  const list = Array.isArray(items) ? items : [];
  const key = (it) => String(it.series || "").trim().toLowerCase();
  const seen = new Map(); // serie -> puntate distinte (stagione:episodio) viste in elenco
  for (const it of list) {
    if (!it || !it.series || it.kind === "brano" || (it.kind && it.kind !== "episodio") || isCatalogRow(it)) continue;
    const k = key(it);
    if (!seen.has(k)) seen.set(k, new Set());
    seen.get(k).add(`${it.season ?? 1}:${it.episode ?? it.id}`);
  }
  return list.map((it) => {
    if (!it || it.kind === "brano") return it;
    const known = Number(it.episode_count);
    const isSeriesLike = Boolean(it.series) || it.kind === "episodio" || /serie/i.test(String(it.genre || ""));
    const single = (Number.isFinite(known) && known === 1 && isSeriesLike)
      || (it.series && it.kind === "episodio" && !isCatalogRow(it) && seen.get(key(it))?.size === 1);
    if (!single) return it;
    const out = { ...it, kind: "film", title: it.series || it.title, series: "" };
    delete out.season; delete out.episode;
    if (/^serie/i.test(String(out.genre || ""))) out.genre = "Film";
    return out;
  });
}
