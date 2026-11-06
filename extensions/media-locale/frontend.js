// Media locale: vista media center unificata stile Netflix (Hero cinematografica, Caroselli, Modal Dettaglio, Impostazioni Drawer).
import * as logicaModule from "./logica.js";
import {
  formatDuration,
  resumeOf,
  isSeen,
  groupEpisodes,
  nextEpisode,
  compositeKey,
  sourceBadge,
  filterHubItems,
  mergeContinueWatching,
  pickHeroItem,
  federatedList,
} from "./logica.js";
import { attachPlay, play, loadContinueCache, removeFromContinueCache } from "./player.js";

export const WATCHLIST_STATUSES = logicaModule.WATCHLIST_STATUSES || {
  plan_to_watch: { id: "plan_to_watch", label: "Da guardare", icon: "📌", order: 1 },
  watching: { id: "watching", label: "In corso", icon: "▶", order: 2 },
  on_hold: { id: "on_hold", label: "In pausa", icon: "⏸", order: 3 },
  completed: { id: "completed", label: "Completato", icon: "✓", order: 4 },
  dropped: { id: "dropped", label: "Abbandonato", icon: "✕", order: 5 },
};

export const WATCHLIST_PRIORITIES = logicaModule.WATCHLIST_PRIORITIES || {
  high: { id: "high", label: "Alta", icon: "🔥", weight: 3 },
  medium: { id: "medium", label: "Media", icon: "⚡", weight: 2 },
  low: { id: "low", label: "Bassa", icon: "💤", weight: 1 },
};

export const normalizeWatchlistEntry = logicaModule.normalizeWatchlistEntry || function (entry, itemFallback = null) {
  const e = entry && typeof entry === "object" ? entry : {};
  const fb = itemFallback && typeof itemFallback === "object" ? itemFallback : {};
  const source = String(e.source || fb.source || "media-locale").trim() || "media-locale";
  const rawId = e.item_id ?? e.id ?? fb.item_id ?? fb.id ?? "";
  let itemId = String(rawId).trim();
  if (itemId === "undefined" || itemId === "null") itemId = "";
  let itemKey = String(e.item_key || "").trim();
  if (!itemKey) {
    itemKey = (compositeKey ? compositeKey({ id: itemId || e.id, source }) : `${source}:${itemId}`) || (compositeKey ? compositeKey(fb) : "");
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
};

export const sortAndFilterWatchlist = logicaModule.sortAndFilterWatchlist || function (entries, { status = "all", priority = "all", query = "", sortBy = "priority" } = {}) {
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
      } else if (e.status !== stFilter) return false;
    }
    if (prFilter && prFilter !== "all" && e.priority !== prFilter) return false;
    if (q) {
      const hay = [e.title, e.series, e.notes, e.genre, e.overview].map((v) => String(v || "").toLowerCase());
      if (!hay.some((f) => f.includes(q))) return false;
    }
    return true;
  });
  const weightOf = (e) => WATCHLIST_PRIORITIES[e?.priority]?.weight ?? 2;
  const orderOf = (e) => WATCHLIST_STATUSES[e?.status]?.order ?? 1;
  const isFinished = (e) => e?.status === "completed" || e?.status === "dropped";
  const recencyOf = (e) => Number(e?.updated_at || e?.added_at || 0);
  return filtered.slice().sort((a, b) => {
    if (sortMode === "status") return (orderOf(a) - orderOf(b)) || (weightOf(b) - weightOf(a)) || String(a?.title || "").localeCompare(String(b?.title || ""));
    if (sortMode === "rating") return (Number(b?.rating || 0) - Number(a?.rating || 0)) || (weightOf(b) - weightOf(a)) || String(a?.title || "").localeCompare(String(b?.title || ""));
    if (sortMode === "recent") return (recencyOf(b) - recencyOf(a)) || String(a?.title || "").localeCompare(String(b?.title || ""));
    if (sortMode === "title") return String(a?.title || "").localeCompare(String(b?.title || ""));
    return ((isFinished(a) ? 1 : 0) - (isFinished(b) ? 1 : 0)) || (weightOf(b) - weightOf(a)) || (Number(b?.updated_at || 0) - Number(a?.updated_at || 0)) || String(a?.title || "").localeCompare(String(b?.title || ""));
  });
};

export const watchlistStats = logicaModule.watchlistStats || function (entries) {
  const stats = { total: 0, plan_to_watch: 0, watching: 0, on_hold: 0, completed: 0, dropped: 0, high_priority: 0 };
  for (const raw of entries || []) {
    if (!raw) continue;
    const st = WATCHLIST_STATUSES[raw.status] ? raw.status : "plan_to_watch";
    const pr = WATCHLIST_PRIORITIES[raw.priority] ? raw.priority : "medium";
    stats.total += 1;
    stats[st] += 1;
    if (pr === "high") stats.high_priority += 1;
  }
  return stats;
};

export const isHttpUrl = (u) => /^https?:\/\//i.test(String(u || ""));

export const safeMediaUrl = (u) => {
  const s = String(u || "").trim();
  return /^https?:\/\//i.test(s) || s.startsWith("/") ? s : "";
};

const defaultEsc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));

const FAVS_KEY = "pm_favorites";

function loadFavs(gs) {
  try {
    const list = gs?.store?.get ? gs.store.get(FAVS_KEY, []) : JSON.parse(localStorage.getItem("gs." + FAVS_KEY) || "[]");
    return new Set(Array.isArray(list) ? list : []);
  } catch {
    return new Set();
  }
}

function saveFavs(gs, favs) {
  const arr = [...favs];
  try { if (gs?.store?.set) gs.store.set(FAVS_KEY, arr); } catch {}
  try { localStorage.setItem("gs." + FAVS_KEY, JSON.stringify(arr)); } catch {}
}

export function isAnimeItem(item) {
  if (!item) return false;
  if (item.kind === "anime" || item.category === "anime") return true;
  const provId = String(item.channel_id || item.recipe_id || item.source_label || item.id || "").toLowerCase();
  const url = String(item.url || "").toLowerCase();
  if (
    provId.includes("animeunity") ||
    provId.includes("animeworld") ||
    url.includes("animeunity") ||
    url.includes("animeworld")
  ) {
    return true;
  }
  if (
    provId.includes("streamingcommunity") ||
    provId.includes("altadefinizione01") ||
    url.includes("streamingcommunity") ||
    url.includes("altadefinizione")
  ) {
    const g = String(item.genre || item.genres || "").toLowerCase();
    return g.includes("anime") || g.includes("animazione");
  }
  const g = String(item.genre || item.genres || "").toLowerCase();
  if (g.includes("anime") || g.includes("animazione")) return true;
  const s = (String(item.title || "") + " " + String(item.series || "")).toLowerCase();
  const animeKeywords = [
    "one piece", "naruto", "dragon ball", "bleach", "attack on titan",
    "shingeki", "death note", "jujutsu", "demon slayer", "kimetsu",
    "my hero academia", "boku no hero", "hunter x hunter", "fullmetal",
    "chainsaw man", "spy x family", "tokyo ghoul", "evangelion", "sword art online", "frieren"
  ];
  return animeKeywords.some((kw) => s.includes(kw));
}

export function isStream4meItem(item) {
  if (!item) return false;
  const s = String(item.source || "").toLowerCase();
  const a = String(item.addon || "").toLowerCase();
  const id = String(item.id || "").toLowerCase();
  return s === "stream4me" || s === "s4me" || a.includes("stream4me") || s.includes("kodi") || id.startsWith("s4me:") || id.startsWith("stream4me:") || id.startsWith("s4m:") || id.startsWith("kodi:");
}

export function normalizePlayItem(item) {
  if (!item || typeof item !== "object") return item;
  const s = String(item.source || "").toLowerCase();
  const id = String(item.id || "").toLowerCase();
  if (
    isStream4meItem(item) ||
    s === "web" ||
    s.includes("ricette") ||
    id.startsWith("s4me:") ||
    id.startsWith("stream4me:") ||
    id.startsWith("s4m:") ||
    id.startsWith("kodi:") ||
    id.startsWith("recipe:")
  ) {
    return { ...item, source: "ricette-web" };
  }
  return item;
}

export function deduplicateStream4meEpisodes(episodes, parentItem = null, fallbackSeriesTitle = "") {
  if (!Array.isArray(episodes) || !episodes.length) return [];
  const p = parentItem && typeof parentItem === "object" ? parentItem : {};
  const seriesTitle = String(fallbackSeriesTitle || p.series || p.title || "").trim();
  const seenKeys = new Set();
  const out = [];
  episodes.forEach((ep, idx) => {
    if (!ep) return;
    const season = ep.season != null && !Number.isNaN(Number(ep.season)) ? Number(ep.season) : 1;
    const epNum = ep.episode != null && !Number.isNaN(Number(ep.episode)) ? Number(ep.episode) : (idx + 1);
    const dedupKey = `${season}:${epNum}`;
    if (seenKeys.has(dedupKey)) return;
    seenKeys.add(dedupKey);
    out.push({
      ...ep,
      id: ep.id ?? `${p.id || "s4m"}_ep_${idx + 1}`,
      title: ep.title || `Episodio ${epNum}`,
      series: ep.series || seriesTitle,
      kind: ep.kind || "episodio",
      genre: ep.genre || p.genre || "",
      season,
      episode: epNum,
      poster: ep.poster || p.poster,
      backdrop: ep.backdrop || p.backdrop || p.poster,
      overview: ep.overview || "",
      source: ep.source || "stream4me",
    });
  });
  return out;
}

export function renderWatchlistControlsHtml(itemKey, entry = null, esc = defaultEsc) {
  const k = String(itemKey ?? "");
  if (!k) return "";
  if (!entry) {
    return `
      <div class="pm-wl-controls">
        <button type="button" class="pm-player-btn pm-primary" data-wl-add="${esc(k)}">📋 ＋ Aggiungi alla Watchlist</button>
        <button type="button" class="pm-player-btn" data-wl-add="${esc(k)}" data-wl-add-priority="high" title="Aggiungi con priorità Alta">🔥 Alta</button>
        <button type="button" class="pm-player-btn" data-wl-add="${esc(k)}" data-wl-add-priority="medium" title="Aggiungi con priorità Media">⚡ Media</button>
        <button type="button" class="pm-player-btn" data-wl-add="${esc(k)}" data-wl-add-priority="low" title="Aggiungi con priorità Bassa">💤 Bassa</button>
      </div>
    `.trim();
  }

  const norm = normalizeWatchlistEntry(entry, { item_key: k });
  const ratingOptions = [`<option value="0" ${!norm.rating ? "selected" : ""}>Senza voto</option>`];
  for (let r = 1; r <= 10; r++) {
    ratingOptions.push(`<option value="${r}" ${norm.rating === r ? "selected" : ""}>★ ${r}</option>`);
  }

  return `
    <div class="pm-wl-controls">
      <select class="pm-source-select" data-wl-status="${esc(k)}" aria-label="Stato Watchlist">
        <option value="plan_to_watch" ${norm.status === "plan_to_watch" ? "selected" : ""}>📌 Da guardare</option>
        <option value="watching" ${norm.status === "watching" ? "selected" : ""}>▶ In corso</option>
        <option value="on_hold" ${norm.status === "on_hold" ? "selected" : ""}>⏸ In pausa</option>
        <option value="completed" ${norm.status === "completed" ? "selected" : ""}>✓ Completato</option>
        <option value="dropped" ${norm.status === "dropped" ? "selected" : ""}>✕ Abbandonato</option>
      </select>
      <select class="pm-source-select" data-wl-priority="${esc(k)}" aria-label="Priorità Watchlist">
        <option value="high" ${norm.priority === "high" ? "selected" : ""}>🔥 Priorità Alta</option>
        <option value="medium" ${norm.priority === "medium" ? "selected" : ""}>⚡ Priorità Media</option>
        <option value="low" ${norm.priority === "low" ? "selected" : ""}>💤 Priorità Bassa</option>
      </select>
      <select class="pm-source-select" data-wl-rating="${esc(k)}" aria-label="Voto personale">
        ${ratingOptions.join("")}
      </select>
      <input type="text" class="pm-wl-note-input" data-wl-note-input="${esc(k)}" value="${esc(norm.notes || "")}" placeholder="Nota personale (es. ep. dove sono rimasto)…">
      <button type="button" class="pm-player-btn" data-wl-save-note="${esc(k)}">Salva nota</button>
      <button type="button" class="pm-player-btn" data-wl-remove="${esc(k)}">✕ Rimuovi</button>
    </div>
  `.trim();
}

export function renderWatchlistViewHtml(entries = [], filterState = {}, esc = defaultEsc) {
  const list = Array.isArray(entries) ? entries : [];
  const statusFilter = filterState?.status || "all";
  const priorityFilter = filterState?.priority || "all";
  const sortBy = filterState?.sortBy || "priority";
  const query = filterState?.query || "";

  const stats = watchlistStats(list);
  const filtered = sortAndFilterWatchlist(list, {
    status: statusFilter,
    priority: priorityFilter,
    query,
    sortBy,
  });

  const statPills = [
    { status: "all", label: "Totale", count: stats.total, active: statusFilter === "all" && priorityFilter === "all" },
    { status: "plan_to_watch", label: "📌 Da guardare", count: stats.plan_to_watch, active: statusFilter === "plan_to_watch" },
    { status: "watching", label: "▶ In corso", count: stats.watching, active: statusFilter === "watching" },
    { status: "on_hold", label: "⏸ In pausa", count: stats.on_hold, active: statusFilter === "on_hold" },
    { status: "completed", label: "✓ Completati", count: stats.completed, active: statusFilter === "completed" },
    { status: "all", priority: "high", label: "🔥 Alta priorità", count: stats.high_priority, active: priorityFilter === "high" },
  ];

  const statusTabs = [
    { id: "all", label: "Tutti" },
    { id: "plan_to_watch", label: "📌 Da guardare" },
    { id: "watching", label: "▶ In corso" },
    { id: "on_hold", label: "⏸ In pausa" },
    { id: "completed", label: "✓ Completato" },
    { id: "dropped", label: "✕ Abbandonato" },
  ];

  return `
    <div class="pm-netflix-home">
      <div class="pm-wl-stats">
        ${statPills.map((p) => `
          <button type="button" class="pm-wl-stat-pill ${p.active ? "pm-active" : ""}" data-wl-filter-status="${esc(p.status)}" ${p.priority ? `data-wl-stat-priority="${esc(p.priority)}"` : ""}>
            <span>${esc(p.label)}</span>
            <strong>${esc(p.count)}</strong>
          </button>
        `).join("")}
      </div>

      <div class="pm-wl-toolbar">
        <div class="pm-season-tabs" role="tablist">
          ${statusTabs.map((t) => `
            <button type="button" role="tab" class="pm-season-tab ${statusFilter === t.id ? "pm-active" : ""}" data-wl-filter-status="${esc(t.id)}">
              ${esc(t.label)}
            </button>
          `).join("")}
        </div>
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <select class="pm-source-select" data-wl-filter-priority aria-label="Filtra priorità">
            <option value="all" ${priorityFilter === "all" ? "selected" : ""}>Tutte le priorità</option>
            <option value="high" ${priorityFilter === "high" ? "selected" : ""}>🔥 Alta priorità</option>
            <option value="medium" ${priorityFilter === "medium" ? "selected" : ""}>⚡ Media priorità</option>
            <option value="low" ${priorityFilter === "low" ? "selected" : ""}>💤 Bassa priorità</option>
          </select>
          <select class="pm-source-select" data-wl-sort aria-label="Ordina Watchlist">
            <option value="priority" ${sortBy === "priority" ? "selected" : ""}>Priorità (Alta → Bassa)</option>
            <option value="status" ${sortBy === "status" ? "selected" : ""}>Stato</option>
            <option value="recent" ${sortBy === "recent" ? "selected" : ""}>Aggiunti di recente</option>
            <option value="rating" ${sortBy === "rating" ? "selected" : ""}>Voto più alto</option>
            <option value="title" ${sortBy === "title" ? "selected" : ""}>Titolo A-Z</option>
          </select>
        </div>
      </div>

      ${filtered.length ? `
        <div class="pm-wl-list">
          ${filtered.map((raw) => {
            const e = normalizeWatchlistEntry(raw);
            const k = e.item_key || compositeKey(e) || String(e.id || "");
            const poster = safeMediaUrl(e.poster || e.backdrop);
            const defaultIcon = e.kind === "brano" ? "🎵" : (e.kind === "episodio" ? "📺" : "🎬");
            const badge = sourceBadge ? sourceBadge(e.source) : null;
            const badgeLabel = badge?.label || e.source || "Locale";
            const badgeIcon = badge?.icon ? `${badge.icon} ` : "";
            const prioMeta = WATCHLIST_PRIORITIES[e.priority] || WATCHLIST_PRIORITIES.medium;
            const stMeta = WATCHLIST_STATUSES[e.status] || WATCHLIST_STATUSES.plan_to_watch;

            const ratingOpts = [`<option value="0" ${!e.rating ? "selected" : ""}>Senza voto</option>`];
            for (let r = 1; r <= 10; r++) {
              ratingOpts.push(`<option value="${r}" ${e.rating === r ? "selected" : ""}>★ ${r}</option>`);
            }

            return `
              <article class="pm-wl-card" data-wl-card="${esc(k)}">
                <div class="pm-list-thumb" data-detail-key="${esc(k)}" data-detail-id="${esc(e.id)}" style="width: 64px; height: 92px;">
                  ${poster ? `<img class="pm-list-thumb-img" src="${esc(poster)}" alt="" loading="lazy">` : defaultIcon}
                </div>
                <div class="pm-list-info" style="gap: 6px;">
                  <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <h4 class="pm-list-title" title="${esc(e.title)}" data-detail-key="${esc(k)}" data-detail-id="${esc(e.id)}" style="font-size: 1rem; cursor: pointer;">${esc(e.title)}</h4>
                    <span class="pm-wl-priority-badge pm-wl-priority-${esc(e.priority)}">${esc(prioMeta.icon)} ${esc(prioMeta.label)}</span>
                    <span class="pm-wl-status-badge">${esc(stMeta.icon)} ${esc(stMeta.label)}</span>
                    <span class="pm-source-badge">${esc(badgeIcon)}${esc(badgeLabel)}</span>
                    ${e.series && e.series !== e.title ? `<span class="pm-badge">${esc(e.series)}</span>` : ""}
                    ${e.year ? `<span class="pm-badge">${esc(e.year)}</span>` : ""}
                    ${e.genre ? `<span class="pm-badge">${esc(e.genre)}</span>` : ""}
                  </div>
                  <div class="pm-wl-controls">
                    <select class="pm-source-select" data-wl-status="${esc(k)}" aria-label="Stato">
                      <option value="plan_to_watch" ${e.status === "plan_to_watch" ? "selected" : ""}>📌 Da guardare</option>
                      <option value="watching" ${e.status === "watching" ? "selected" : ""}>▶ In corso</option>
                      <option value="on_hold" ${e.status === "on_hold" ? "selected" : ""}>⏸ In pausa</option>
                      <option value="completed" ${e.status === "completed" ? "selected" : ""}>✓ Completato</option>
                      <option value="dropped" ${e.status === "dropped" ? "selected" : ""}>✕ Abbandonato</option>
                    </select>
                    <select class="pm-source-select" data-wl-priority="${esc(k)}" aria-label="Priorità">
                      <option value="high" ${e.priority === "high" ? "selected" : ""}>🔥 Priorità Alta</option>
                      <option value="medium" ${e.priority === "medium" ? "selected" : ""}>⚡ Priorità Media</option>
                      <option value="low" ${e.priority === "low" ? "selected" : ""}>💤 Priorità Bassa</option>
                    </select>
                    <select class="pm-source-select" data-wl-rating="${esc(k)}" aria-label="Voto">
                      ${ratingOpts.join("")}
                    </select>
                    <input type="text" class="pm-wl-note-input" data-wl-note-input="${esc(k)}" value="${esc(e.notes || "")}" placeholder="Nota personale (es. ep. dove sono rimasto)…">
                    <button type="button" class="pm-player-btn" data-wl-save-note="${esc(k)}" style="padding: 4px 10px; font-size: 0.78rem;">Salva nota</button>
                  </div>
                </div>
                <div class="pm-list-actions">
                  <button type="button" class="pm-player-btn pm-primary" data-detail-key="${esc(k)}" data-detail-id="${esc(e.id)}" data-play-key="${esc(k)}" data-play-id="${esc(e.id)}">▶ Apri / Riproduci</button>
                  <button type="button" class="pm-player-btn" data-wl-remove="${esc(k)}" title="Rimuovi dalla Watchlist">✕</button>
                </div>
              </article>
            `;
          }).join("")}
        </div>
      ` : `
        <div class="pm-provider-status">
          <p class="muted" style="margin: 0;">Nessun titolo nella Watchlist per i filtri selezionati. Aggiungi film, serie TV o anime con il pulsante 📋 sulle locandine o nei dettagli!</p>
        </div>
      `}
    </div>
  `.trim();
}

export function renderHeroHtml(item, esc = defaultEsc) {
  if (!item) return "";
  const key = compositeKey ? compositeKey(item) : `${item.source || "locale"}:${item.id ?? ""}`;
  const badge = sourceBadge ? sourceBadge(item.source) : null;
  const badgeLabel = badge?.label || item.source_label || item.source || "Locale";
  const badgeIcon = badge?.icon ? `${badge.icon} ` : "";
  const bg = safeMediaUrl(item.backdrop || item.poster);
  const title = item.title || "";
  const desc = item.overview || "";
  const dur = item.duration ? formatDuration(item.duration) : "";

  return `
    <article class="pm-hero" data-play-key="${esc(key)}" data-play-id="${esc(item.id ?? '')}">
      ${bg ? `<img class="pm-hero-backdrop" src="${esc(bg)}" alt="" loading="lazy">` : ""}
      <div class="pm-hero-gradient"></div>
      <div class="pm-hero-body">
        <div class="pm-hero-badges" style="display: flex; align-items: center; gap: 8px;">
          <span class="pm-source-badge">${esc(badgeIcon)}${esc(badgeLabel)}</span>
          ${item.year ? `<span class="pm-badge">${esc(item.year)}</span>` : ""}
          ${item.genre ? `<span class="pm-badge">${esc(item.genre)}</span>` : ""}
          <span class="pm-badge">HD</span>
          ${dur ? `<span class="pm-badge">${esc(dur)}</span>` : ""}
        </div>
        <h2 class="pm-hero-title">${esc(title)}</h2>
        ${desc ? `<p class="pm-hero-desc">${esc(desc)}</p>` : ""}
        <div class="pm-hero-actions" style="display: flex; gap: 10px; margin-top: 8px;">
          <button type="button" class="pm-player-btn pm-primary" data-play-key="${esc(key)}" data-play-id="${esc(item.id ?? '')}">
            ▶ Riproduci
          </button>
          <button type="button" class="pm-player-btn" data-detail-key="${esc(key)}" data-detail-id="${esc(item.id ?? '')}">
            ℹ Altre info
          </button>
        </div>
      </div>
    </article>
  `.trim();
}

export function renderCardHtml(item, isFav = false, esc = defaultEsc, options = {}) {
  if (!item) return "";
  const key = compositeKey ? compositeKey(item) : `${item.source || "locale"}:${item.id ?? ""}`;
  const badge = sourceBadge ? sourceBadge(item.source) : null;
  const badgeLabel = badge?.label || item.source_label || item.source || "Locale";
  const badgeIcon = badge?.icon ? `${badge.icon} ` : "";
  const poster = safeMediaUrl(item.poster);
  const seen = isSeen(item);
  const title = item.title || "";
  const dur = item.duration ? formatDuration(item.duration) : "";
  let meta = "";
  if (item.kind === "episodio" || (item.series && (item.season != null || item.episode != null))) {
    const epPrefix = (item.season != null || item.episode != null) ? `S${item.season ?? 1}E${item.episode ?? 1}` : "";
    meta = [item.series, epPrefix, dur].filter(Boolean).join(" · ");
  } else if (item.kind === "brano") {
    meta = [item.series || item.album, dur].filter(Boolean).join(" · ");
  } else {
    meta = [item.series, item.year, dur].filter(Boolean).join(" · ");
  }

  const defaultIcon = item.kind === "brano" ? "🎵" : (item.kind === "episodio" ? "📺" : "🎬");
  const isS4me = Boolean(isStream4meItem(item) || item.channel_id || options.showPin);
  const pinnedIds = options.pinnedIds instanceof Set ? options.pinnedIds : new Set(Array.isArray(options.pinnedIds) ? options.pinnedIds : []);
  const isPinned = Boolean(options.isPinned ?? (item.id != null && pinnedIds.has(String(item.id))));

  const wlMap = options.watchlistMap;
  const wlEntry = options.wlEntry || (wlMap instanceof Map ? (wlMap.get(key) || (item.id != null ? wlMap.get(String(item.id)) : null)) : null);
  const wlIcon = wlEntry ? (wlEntry.priority === "high" ? "🔥" : "📌") : "📋";

  return `
    <article class="pm-card ${seen ? 'pm-seen' : ''}" data-play-key="${esc(key)}" data-play-id="${esc(item.id)}" data-detail-key="${esc(key)}" data-detail-id="${esc(item.id)}" ${isS4me ? `data-s4me-open="${esc(item.id ?? '')}"` : ""}>
      <div class="pm-poster">
        ${poster ? `<img class="pm-poster-img" src="${esc(poster)}" alt="" loading="lazy">` : `<div class="pm-poster-placeholder">${defaultIcon}</div>`}
        <span class="pm-source-badge" style="position: absolute; top: 6px; right: 6px; z-index: 2;">${esc(badgeIcon)}${esc(badgeLabel)}</span>
        ${seen ? `<span class="pm-seen-badge pm-seen">✓</span>` : ""}
        <button type="button" class="pm-fav-btn" data-fav-key="${esc(key)}" data-fav-id="${esc(item.id)}" style="position: absolute; top: 6px; left: 6px; z-index: 3; background: var(--panel); border: 1px solid var(--line); border-radius: 999px; width: 24px; height: 24px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.8rem; cursor: pointer; color: ${isFav ? 'var(--accent)' : 'var(--muted)'};" title="${isFav ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}">${isFav ? '★' : '☆'}</button>
        <button type="button" class="pm-fav-btn" data-wl-toggle="${esc(key)}" data-wl-id="${esc(item.id ?? '')}" style="position: absolute; top: 6px; left: 34px; z-index: 3; background: var(--panel); border: 1px solid ${wlEntry ? 'var(--accent)' : 'var(--line)'}; border-radius: 999px; width: 24px; height: 24px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.72rem; cursor: pointer; color: ${wlEntry ? 'var(--accent)' : 'var(--muted)'};" title="Aggiungi/Modifica nella Watchlist">${wlIcon}</button>
        ${isS4me && item.id != null ? `
          <button type="button" class="pm-pin-btn ${isPinned ? 'pm-pinned' : ''}" data-pin-item="${esc(item.id)}" title="${isPinned ? 'Rimuovi dalla Libreria' : 'Aggiungi alla Libreria'}">
            ${isPinned ? '✓ In Libreria' : '＋ Libreria'}
          </button>
        ` : ""}
      </div>
      <div class="pm-card-body">
        <h4 class="pm-title" title="${esc(title)}">${esc(title)}</h4>
        ${meta ? `<div class="pm-meta">${esc(meta)}</div>` : ""}
      </div>
    </article>
  `.trim();
}

export function renderCarouselHtml(title, items, options = {}, esc = defaultEsc) {
  if (!items || !items.length) return "";
  const favs = options.favs || new Set();
  const pinnedIds = options.pinnedIds || new Set();
  const watchlistMap = options.watchlistMap || new Map();
  const type = options.type || "card";

  let cardsHtml = "";
  if (type === "resume") {
    cardsHtml = items.map((it) => {
      const pct = resumeOf(it);
      const poster = safeMediaUrl(it.backdrop || it.poster);
      const key = compositeKey ? compositeKey(it) : `${it.source || "locale"}:${it.id ?? ""}`;
      const badge = sourceBadge ? sourceBadge(it.source) : null;
      const badgeLabel = badge?.label || it.source || "Locale";
      const badgeIcon = badge?.icon ? `${badge.icon} ` : "";
      let sub = "";
      if (it.kind === "episodio") {
        sub = it.series ? `${it.series} · S${it.season ?? 1}E${it.episode ?? 1}` : `Episodio ${it.episode ?? 1}`;
      } else if (it.kind === "brano") {
        sub = it.series || it.album || "";
      } else if (it.year) {
        sub = String(it.year);
      }
      return `
        <article class="pm-resume-card" data-play-key="${esc(key)}" data-play-id="${esc(it.id)}" data-detail-key="${esc(key)}" data-detail-id="${esc(it.id)}">
          <div class="pm-backdrop">
            ${poster ? `<img class="pm-backdrop-img" src="${esc(poster)}" alt="" loading="lazy">` : `<div class="pm-poster-placeholder">▶</div>`}
            <span class="pm-source-badge" style="position: absolute; top: 6px; right: 6px; z-index: 2;">${esc(badgeIcon)}${esc(badgeLabel)}</span>
            <div class="pm-progress">
              <div class="pm-progress-bar" style="width: ${pct}%;"></div>
            </div>
          </div>
          <div class="pm-card-body">
            <h4 class="pm-title" title="${esc(it.title)}">${esc(it.title)}</h4>
            <div class="pm-meta">
              ${sub ? `<span>${esc(sub)}</span>` : ""}
              <span class="pm-progress-label">${pct}%${it.resume_pos ? ` · ${esc(formatDuration(it.resume_pos))}` : ""}</span>
            </div>
          </div>
        </article>
      `;
    }).join("");
  } else if (type === "series") {
    cardsHtml = items.map((s) => {
      const rep = s.repItem || {};
      const poster = safeMediaUrl(rep.poster);
      const isFav = s.isFav || favs.has("series:" + s.name);
      const sKey = `series:${s.name}`;
      const wlEntry = watchlistMap instanceof Map ? (watchlistMap.get(sKey) || (rep.id != null ? watchlistMap.get(compositeKey(rep)) : null)) : null;
      const wlIcon = wlEntry ? (wlEntry.priority === "high" ? "🔥" : "📌") : "📋";
      const meta = `${s.seasonsCount || 1} stagion${(s.seasonsCount || 1) === 1 ? 'e' : 'i'} · ${s.count || 1} episod${(s.count || 1) === 1 ? 'o' : 'i'}`;
      const badge = sourceBadge ? sourceBadge(rep.source) : null;
      const badgeLabel = badge?.label || rep.source || "Locale";
      const badgeIcon = badge?.icon ? `${badge.icon} ` : "";
      return `
        <article class="pm-card ${s.allSeen ? 'pm-seen' : ''}" data-series-name="${esc(s.name)}">
          <div class="pm-poster">
            ${poster ? `<img class="pm-poster-img" src="${esc(poster)}" alt="" loading="lazy">` : `<div class="pm-poster-placeholder">📺</div>`}
            <span class="pm-source-badge" style="position: absolute; top: 6px; right: 6px; z-index: 2;">${esc(badgeIcon)}${esc(badgeLabel)}</span>
            ${s.allSeen ? `<span class="pm-seen-badge pm-seen">✓ Vista</span>` : ""}
            <button type="button" class="pm-fav-btn" data-fav-id="series:${esc(s.name)}" style="position: absolute; top: 6px; left: 6px; z-index: 3; background: var(--panel); border: 1px solid var(--line); border-radius: 999px; width: 24px; height: 24px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.8rem; cursor: pointer; color: ${isFav ? 'var(--accent)' : 'var(--muted)'};" title="${isFav ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}">${isFav ? '★' : '☆'}</button>
            <button type="button" class="pm-fav-btn" data-wl-toggle="series:${esc(s.name)}" style="position: absolute; top: 6px; left: 34px; z-index: 3; background: var(--panel); border: 1px solid ${wlEntry ? 'var(--accent)' : 'var(--line)'}; border-radius: 999px; width: 24px; height: 24px; display: inline-flex; align-items: center; justify-content: center; font-size: 0.72rem; cursor: pointer; color: ${wlEntry ? 'var(--accent)' : 'var(--muted)'};" title="Aggiungi/Modifica nella Watchlist">${wlIcon}</button>
          </div>
          <div class="pm-card-body">
            <h4 class="pm-title" title="${esc(s.name)}">${esc(s.name)}</h4>
            <div class="pm-meta">${esc(meta)}</div>
          </div>
        </article>
      `;
    }).join("");
  } else {
    cardsHtml = items.map((it) => {
      const key = compositeKey ? compositeKey(it) : String(it.id);
      const isFav = favs.has(key) || favs.has(String(it.id));
      return renderCardHtml(it, isFav, esc, { pinnedIds, watchlistMap });
    }).join("");
  }

  const countLabel = `${items.length} ${items.length === 1 ? 'titolo' : 'titoli'}`;

  return `
    <section class="pm-carousel">
      <div class="pm-carousel-header">
        <h3 class="pm-carousel-title">${esc(title)}</h3>
        <div class="pm-carousel-controls" style="display: flex; align-items: center; gap: 6px;">
          <span class="pm-carousel-count">${esc(countLabel)}</span>
          <button type="button" class="pm-carousel-btn" data-carousel-scroll="-1" title="Scorri a sinistra" aria-label="Scorri a sinistra">‹</button>
          <button type="button" class="pm-carousel-btn" data-carousel-scroll="1" title="Scorri a destra" aria-label="Scorri a destra">›</button>
        </div>
      </div>
      <div class="pm-carousel-row" data-carousel-row>
        ${cardsHtml}
      </div>
    </section>
  `.trim();
}

export function renderListHtml(items = [], options = {}, esc = defaultEsc) {
  if (!items || !items.length) {
    return `<p class="muted" style="padding: 32px 0; text-align: center;">Nessun elemento da mostrare.</p>`;
  }
  const favs = options.favs || new Set();
  const watchlistMap = options.watchlistMap || new Map();
  return `
    <div class="pm-list">
      ${items.map((it) => {
        const key = compositeKey ? compositeKey(it) : String(it.id ?? "");
        const isFav = favs.has(key) || favs.has(String(it.id));
        const wlEntry = watchlistMap instanceof Map ? (watchlistMap.get(key) || (it.id != null ? watchlistMap.get(String(it.id)) : null)) : null;
        const wlIcon = wlEntry ? (wlEntry.priority === "high" ? "🔥" : "📌") : "📋";
        const badge = sourceBadge ? sourceBadge(it.source) : null;
        const badgeLabel = badge?.label || it.source || "Locale";
        const badgeIcon = badge?.icon ? `${badge.icon} ` : "";
        const poster = safeMediaUrl(it.poster || it.backdrop);
        const dur = it.duration ? formatDuration(it.duration) : "";
        let metaParts = [badgeIcon + badgeLabel, it.year, dur].filter(Boolean);
        if (it.kind === "episodio" && it.series) {
          const ep = (it.season != null || it.episode != null) ? `S${it.season ?? 1}E${it.episode ?? 1}` : "";
          metaParts = [it.series, ep, dur].filter(Boolean);
        }
        const defaultIcon = it.kind === "brano" ? "🎵" : (it.kind === "episodio" ? "📺" : "🎬");
        return `
          <div class="pm-list-row" data-play-key="${esc(key)}" data-play-id="${esc(it.id ?? '')}" data-detail-key="${esc(key)}" data-detail-id="${esc(it.id ?? '')}">
            <div class="pm-list-thumb">
              ${poster ? `<img class="pm-list-thumb-img" src="${esc(poster)}" alt="" loading="lazy">` : defaultIcon}
            </div>
            <div class="pm-list-info">
              <h4 class="pm-list-title" title="${esc(it.title)}">${esc(it.title)}</h4>
              <div class="pm-list-meta">
                ${metaParts.map((m) => `<span>${esc(m)}</span>`).join(" · ")}
              </div>
            </div>
            <div class="pm-list-actions">
              <button type="button" class="pm-fav-btn" data-wl-toggle="${esc(key)}" style="background: transparent; border: none; font-size: 1rem; cursor: pointer; color: ${wlEntry ? 'var(--accent)' : 'var(--muted)'}; padding: 6px;" title="Aggiungi/Modifica nella Watchlist">${wlIcon}</button>
              <button type="button" class="pm-fav-btn" data-fav-key="${esc(key)}" data-fav-id="${esc(it.id ?? '')}" style="background: transparent; border: none; font-size: 1.1rem; cursor: pointer; color: ${isFav ? 'var(--accent)' : 'var(--muted)'}; padding: 6px;" title="${isFav ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}">${isFav ? '★' : '☆'}</button>
              <button type="button" class="pm-player-btn pm-primary" data-play-key="${esc(key)}" data-play-id="${esc(it.id ?? '')}" style="padding: 4px 10px; font-size: .8rem;">▶ Riproduci</button>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `.trim();
}

export function renderMediaContextMenuHtml(item, options = {}, esc = defaultEsc) {
  if (!item) return "";
  const k = options.key || (item.key || (typeof compositeKey === "function" ? compositeKey(item) : ""));
  const id = options.id != null ? String(options.id) : String(item.id ?? "");
  const isContinueItem = Boolean(options.isContinueItem);
  const isS4me = Boolean(options.isS4me);
  const isPinnedS4me = Boolean(options.isPinnedS4me);
  const isFav = Boolean(options.isFav);

  const itemsHtml = [];
  itemsHtml.push(`<button type="button" class="pm-ctx-item" data-ctx-play="${esc(k)}" data-ctx-id="${esc(id)}">▶ Riproduci</button>`);
  itemsHtml.push(`<button type="button" class="pm-ctx-item" data-ctx-detail="${esc(k)}" data-ctx-id="${esc(id)}">ℹ Informazioni</button>`);
  itemsHtml.push(`<button type="button" class="pm-ctx-item" data-ctx-fav="${esc(k)}" data-ctx-id="${esc(id)}">${isFav ? "★ Rimuovi dai preferiti" : "☆ Aggiungi ai preferiti"}</button>`);

  if (isContinueItem) {
    itemsHtml.push(`<button type="button" class="pm-ctx-item pm-ctx-danger" data-ctx-remove-continue="${esc(k)}" data-ctx-item-id="${esc(id)}">✕ Rimuovi da «Continua a guardare»</button>`);
  }

  if (isS4me && id) {
    if (isPinnedS4me) {
      itemsHtml.push(`<button type="button" class="pm-ctx-item pm-ctx-danger" data-ctx-unpin-s4me="${esc(id)}">🗑 Rimuovi dalla Libreria Stream4me</button>`);
    } else {
      itemsHtml.push(`<button type="button" class="pm-ctx-item" data-ctx-pin-s4me="${esc(id)}">＋ Aggiungi alla Libreria</button>`);
    }
  }

  return itemsHtml.join("");
}

export function renderDetailModal(target, groups = {}, options = {}, esc = defaultEsc) {
  if (!target) return "";
  const favs = options.favs || new Set();
  const pinnedIds = options.pinnedIds instanceof Set ? options.pinnedIds : new Set(Array.isArray(options.pinnedIds) ? options.pinnedIds : []);
  const watchlistMap = options.watchlistMap || new Map();
  const detailLoading = Boolean(options.loadingDetail);
  const isSeries = Boolean(!detailLoading && (typeof target === "string" || target.series || groups[target.title || target.name || target]));
  const seriesName = typeof target === "string" ? target : (target.series || target.title || target.name || "");
  const seasons = groups[seriesName] || null;

  if (isSeries && seasons) {
    const seasonKeys = Object.keys(seasons).sort((a, b) => Number(a) - Number(b));
    let currentSeason = options.selectedSeason != null ? String(options.selectedSeason) : seasonKeys[0];
    if (!seasonKeys.includes(currentSeason)) currentSeason = seasonKeys[0] || "1";

    const allEps = seasonKeys.flatMap((k) => seasons[k] || []);
    const repEp = allEps.find((e) => e.poster || e.backdrop) || allEps[0] || (typeof target === "object" ? target : {});
    const backdrop = safeMediaUrl(repEp.backdrop || repEp.poster);
    const overview = repEp.overview || (typeof target === "object" ? target.overview : "") || "";
    const currentEps = seasons[currentSeason] || [];

    const lastWatched = allEps.filter(isSeen).pop();
    const nextToWatch = (lastWatched ? nextEpisode(allEps, lastWatched.id) : null) || allEps.find((e) => !isSeen(e)) || allEps[0];
    const isSeriesFav = favs.has("series:" + seriesName);
    const badge = sourceBadge ? sourceBadge(repEp.source) : null;
    const badgeLabel = badge?.label || repEp.source || "Locale";
    const badgeIcon = badge?.icon ? `${badge.icon} ` : "";
    const pinTargetId = (typeof target === "object" && target?.id) ? target.id : repEp.id;
    const isS4meSeries = Boolean(isStream4meItem(repEp) || repEp.channel_id || (typeof target === "object" && (isStream4meItem(target) || target.channel_id)));
    const isPinnedSeries = Boolean(pinTargetId != null && pinnedIds.has(String(pinTargetId)));
    const wlKey = (typeof target === "object" && target?.id) ? (compositeKey(target) || `series:${seriesName}`) : `series:${seriesName}`;
    const wlEntry = options.wlEntry ?? (watchlistMap instanceof Map ? (watchlistMap.get(wlKey) || watchlistMap.get(`series:${seriesName}`) || (repEp.id != null ? watchlistMap.get(compositeKey(repEp)) : null)) : null);

    return `
      <div class="pm-modal-overlay" data-close-modal-backdrop>
        <div class="pm-modal-detail" role="dialog" aria-modal="true">
          <button type="button" class="pm-modal-close" data-close-modal title="Chiudi">✕</button>
          <div class="pm-modal-header">
            ${backdrop ? `<img class="pm-modal-backdrop" src="${esc(backdrop)}" alt="" loading="lazy">` : ""}
            <div class="pm-modal-gradient"></div>
            <div class="pm-modal-header-body">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="pm-source-badge">${esc(badgeIcon)}${esc(badgeLabel)}</span>
                <span class="pm-badge">${seasonKeys.length} stagion${seasonKeys.length === 1 ? 'e' : 'i'}</span>
                <span class="pm-badge">${allEps.length} episodi</span>
                ${repEp.genre ? `<span class="pm-badge">${esc(repEp.genre)}</span>` : ""}
              </div>
              <h2 class="pm-modal-title">${esc(seriesName)}</h2>
              ${overview ? `<p class="pm-hero-desc" style="-webkit-line-clamp: 4;">${esc(overview)}</p>` : ""}
              <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 6px;">
                ${nextToWatch ? `
                  <button type="button" class="pm-player-btn pm-primary" data-play-key="${esc(compositeKey ? compositeKey(nextToWatch) : nextToWatch.id)}" data-play-id="${esc(nextToWatch.id)}">
                    ▶ Riproduci: S${esc(nextToWatch.season ?? 1)}E${esc(nextToWatch.episode ?? 1)} · ${esc(nextToWatch.title)}
                  </button>
                ` : ""}
                <button type="button" class="pm-player-btn" data-fav-id="series:${esc(seriesName)}">
                  ${isSeriesFav ? '★ Preferita' : '☆ Aggiungi ai preferiti'}
                </button>
                ${isS4meSeries && pinTargetId != null ? `
                  <button type="button" class="pm-player-btn ${isPinnedSeries ? 'pm-primary' : ''}" data-pin-item="${esc(pinTargetId)}">
                    ${isPinnedSeries ? '✓ In Libreria' : '＋ Libreria'}
                  </button>
                ` : ""}
              </div>
              ${renderWatchlistControlsHtml(wlKey, wlEntry, esc)}
            </div>
          </div>
          <div class="pm-modal-body">
            <div class="pm-season-tabs" role="tablist">
              ${seasonKeys.map((s) => `
                <button type="button" role="tab" class="pm-season-tab ${String(s) === String(currentSeason) ? 'pm-active' : ''}" data-modal-season="${esc(s)}">
                  Stagione ${esc(s)}
                </button>
              `).join("")}
            </div>
            <div class="pm-episode-list">
              ${currentEps.map((ep) => {
                const epPoster = safeMediaUrl(ep.poster || repEp.poster || backdrop);
                const seen = isSeen(ep);
                const pct = resumeOf(ep);
                const key = compositeKey ? compositeKey(ep) : String(ep.id);
                const isFav = favs.has(key) || favs.has(String(ep.id));
                return `
                  <article class="pm-episode-card ${seen ? 'pm-seen' : ''}" data-play-key="${esc(key)}" data-play-id="${esc(ep.id)}">
                    <div class="pm-episode-thumb">
                      ${epPoster ? `<img class="pm-episode-thumb-img" src="${esc(epPoster)}" alt="" loading="lazy">` : `<div class="pm-poster-placeholder">▶</div>`}
                      ${seen ? `<span class="pm-seen-badge pm-seen">✓</span>` : ""}
                    </div>
                    <div class="pm-episode-info">
                      <div class="pm-episode-num">Episodio ${ep.episode != null ? esc(ep.episode) : ""}</div>
                      <h4 class="pm-episode-title" title="${esc(ep.title)}">${esc(ep.title)}</h4>
                      ${ep.overview ? `<p class="pm-episode-desc">${esc(ep.overview)}</p>` : ""}
                      <div class="pm-meta">
                        ${ep.duration ? `<span>${esc(formatDuration(ep.duration))}</span>` : ""}
                        ${pct > 0 && !seen ? `<span class="pm-progress-label">${pct}%</span>` : ""}
                      </div>
                    </div>
                    <button type="button" class="pm-fav-btn" data-fav-key="${esc(key)}" data-fav-id="${esc(ep.id)}" style="background: transparent; border: none; font-size: 1.1rem; cursor: pointer; color: ${isFav ? 'var(--accent)' : 'var(--muted)'}; padding: 6px;" title="${isFav ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}">${isFav ? '★' : '☆'}</button>
                  </article>
                `;
              }).join("")}
            </div>
          </div>
        </div>
      </div>
    `.trim();
  }

  // Standalone item (Film, Brano, Stream4me item, etc.)
  const item = target;
  const key = compositeKey ? compositeKey(item) : `${item.source || "locale"}:${item.id ?? ""}`;
  const badge = sourceBadge ? sourceBadge(item.source) : null;
  const badgeLabel = badge?.label || item.source_label || item.source || "Locale";
  const badgeIcon = badge?.icon ? `${badge.icon} ` : "";
  const bg = safeMediaUrl(item.backdrop || item.poster);
  const dur = item.duration ? formatDuration(item.duration) : "";
  const isFav = favs.has(key) || favs.has(String(item.id));
  const isS4me = Boolean(isStream4meItem(item) || item.channel_id || options.showPin);
  const isPinned = Boolean(options.isPinned ?? (item.id != null && pinnedIds.has(String(item.id))));
  const detailEpisodes = Array.isArray(options.episodes) ? options.episodes : (Array.isArray(item.episodes) ? item.episodes : []);
  const wlEntry = options.wlEntry ?? (watchlistMap instanceof Map ? (watchlistMap.get(key) || (item.id != null ? watchlistMap.get(String(item.id)) : null)) : null);

  return `
    <div class="pm-modal-overlay" data-close-modal-backdrop>
      <div class="pm-modal-detail" role="dialog" aria-modal="true">
        <button type="button" class="pm-modal-close" data-close-modal title="Chiudi">✕</button>
        <div class="pm-modal-header">
          ${bg ? `<img class="pm-modal-backdrop" src="${esc(bg)}" alt="" loading="lazy">` : ""}
          <div class="pm-modal-gradient"></div>
          <div class="pm-modal-header-body">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="pm-source-badge">${esc(badgeIcon)}${esc(badgeLabel)}</span>
              ${item.year ? `<span class="pm-badge">${esc(item.year)}</span>` : ""}
              ${item.genre ? `<span class="pm-badge">${esc(item.genre)}</span>` : ""}
              <span class="pm-badge">HD</span>
              ${dur ? `<span class="pm-badge">${esc(dur)}</span>` : ""}
            </div>
            <h2 class="pm-modal-title">${esc(item.title || "")}</h2>
            ${item.overview ? `<p class="pm-hero-desc" style="-webkit-line-clamp: 5;">${esc(item.overview)}</p>` : ""}
            <div style="display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 8px;">
              <button type="button" class="pm-player-btn pm-primary" data-play-key="${esc(key)}" data-play-id="${esc(item.id ?? '')}">
                ▶ Riproduci
              </button>
              <button type="button" class="pm-player-btn" data-fav-key="${esc(key)}" data-fav-id="${esc(item.id ?? '')}">
                ${isFav ? '★ Preferito' : '☆ Aggiungi ai preferiti'}
              </button>
              ${isS4me && item.id != null ? `
                <button type="button" class="pm-player-btn ${isPinned ? 'pm-primary' : ''}" data-pin-item="${esc(item.id)}">
                  ${isPinned ? '✓ In Libreria' : '＋ Libreria'}
                </button>
              ` : ""}
            </div>
            ${renderWatchlistControlsHtml(key, wlEntry, esc)}
          </div>
        </div>
        ${detailLoading || detailEpisodes.length ? `
          <div class="pm-modal-body">
            ${detailLoading ? `<p class="muted" style="margin: 0; font-size: 0.88rem;">Caricamento episodi e flussi da Stream4me…</p>` : ""}
            ${detailEpisodes.length ? `
              <h4 style="margin: 0; font-size: 0.95rem; color: var(--text);">Episodi / Flussi disponibili (${detailEpisodes.length})</h4>
              <div class="pm-episode-list">
                ${detailEpisodes.map((ep, idx) => {
                  const epKey = compositeKey ? compositeKey(ep) : `${ep.source || item.source || "stream4me"}:${ep.id ?? idx}`;
                  const epPoster = safeMediaUrl(ep.poster || item.poster || bg);
                  return `
                    <article class="pm-episode-card" data-play-key="${esc(epKey)}" data-play-id="${esc(ep.id ?? '')}">
                      <div class="pm-episode-thumb">
                        ${epPoster ? `<img class="pm-episode-thumb-img" src="${esc(epPoster)}" alt="" loading="lazy">` : `<div class="pm-poster-placeholder">▶</div>`}
                      </div>
                      <div class="pm-episode-info">
                        <div class="pm-episode-num">${ep.episode != null ? `Episodio ${esc(ep.episode)}` : `Flusso ${idx + 1}`}</div>
                        <h4 class="pm-episode-title" title="${esc(ep.title || item.title || '')}">${esc(ep.title || item.title || '')}</h4>
                        ${ep.overview ? `<p class="pm-episode-desc">${esc(ep.overview)}</p>` : ""}
                      </div>
                      <button type="button" class="pm-player-btn pm-primary" data-play-key="${esc(epKey)}" data-play-id="${esc(ep.id ?? '')}" style="padding: 5px 12px; font-size: 0.8rem;">▶ Riproduci</button>
                    </article>
                  `;
                }).join("")}
              </div>
            ` : ""}
          </div>
        ` : ""}
      </div>
    </div>
  `.trim();
}

export function renderStream4meBrowserHtml(state = {}, esc = defaultEsc) {
  const {
    installed = false,
    providers = [],
    activeProvider = null,
    activePath = "",
    query = "",
    browsedItems = [],
    pinnedIds = new Set(),
    favs = new Set(),
    watchlistMap = new Map(),
    loading = false,
    error = "",
  } = state || {};

  const pinSet = pinnedIds instanceof Set ? pinnedIds : new Set(Array.isArray(pinnedIds) ? pinnedIds.map(String) : []);
  const favSet = favs instanceof Set ? favs : new Set(Array.isArray(favs) ? favs.map(String) : []);
  const provList = Array.isArray(providers) ? providers : [];
  const itemsList = Array.isArray(browsedItems) ? browsedItems : [];

  if (!activeProvider) {
    if (!installed && !provList.length) {
      return `
        <div class="pm-empty-banner" style="text-align: center; padding: 48px 24px; background: var(--bg-2); border: 1px solid var(--line); border-radius: 8px; margin-top: 16px;">
          <div style="font-size: 2.6rem; margin-bottom: 10px;">🧩</div>
          <h3 style="margin: 0 0 8px 0; font-size: 1.2rem; color: var(--text);">Stream4me non ancora installato</h3>
          <p class="muted" style="max-width: 520px; margin: 0 auto 18px auto; font-size: 0.88rem; line-height: 1.5;">
            Installa Stream4me per sfogliare e guardare canali in streaming, film, serie TV e anime direttamente da Pozzo Launcher.
          </p>
          <button type="button" class="pm-player-btn pm-primary" data-install-stream4me style="font-size: 0.95rem; padding: 8px 20px;">
            ⬇ Installa Stream4me con 1 clic
          </button>
        </div>
      `.trim();
    }

    return `
      <div class="pm-s4me-browser">
        <div class="pm-provider-header">
          <div style="display: flex; flex-direction: column; gap: 4px;">
            <h3 style="margin: 0; font-size: 1.25rem; color: var(--text);">🧩 Navigatore Canali Stream4me (Kodi)</h3>
            <p class="muted" style="margin: 0; font-size: 0.84rem;">Seleziona un provider per sfogliare il catalogo in tempo reale o cerca un titolo in tutti i canali e aggiungilo alla tua Libreria. Clicca con il tasto destro su un provider per rimuoverlo.</p>
          </div>
          <div class="pm-provider-search-bar">
            <input type="search" class="pm-provider-search-input" data-provider-search-input value="${esc(query)}" placeholder="Cerca film, serie TV o anime nei provider…">
            <button type="button" class="pm-player-btn pm-primary" data-provider-search-btn>🔍 Cerca nei provider</button>
          </div>
        </div>
        ${loading ? `
          <div class="pm-provider-status">
            <p class="muted">Ricerca nei provider Stream4me in corso…</p>
          </div>
        ` : ""}
        ${error ? `
          <div class="pm-provider-status">
            <p style="color: var(--accent); margin: 0 0 8px 0;">${esc(error)}</p>
            <button type="button" class="pm-player-btn" data-provider-retry>↻ Riprova</button>
          </div>
        ` : ""}
        ${query && itemsList.length ? `
          <div style="margin-bottom: 24px;">
            <h4 style="margin: 0 0 12px 0; font-size: 1.05rem; color: var(--text);">Risultati in streaming per "${esc(query)}" (${itemsList.length})</h4>
            <div class="pm-grid">
              ${itemsList.map((it) => {
                const sIt = { ...it, source: it.source || "stream4me", source_label: it.source_label || it.channel_name || "Stream4me" };
                const ck = compositeKey ? compositeKey(sIt) : String(sIt.id ?? "");
                const isFav = favSet.has(ck) || favSet.has(String(sIt.id ?? ""));
                return renderCardHtml(sIt, isFav, esc, { showPin: true, pinnedIds: pinSet, watchlistMap });
              }).join("")}
            </div>
          </div>
        ` : ""}
        <div class="pm-provider-grid">
          ${provList.map((p) => {
            const pId = p.id || p.channel || p.name || "";
            const pName = p.name || p.title || pId;
            const cats = Array.isArray(p.categories) ? p.categories : (p.category ? [p.category] : []);
            return `
              <article class="pm-provider-card" data-open-provider="${esc(pId)}">
                <div class="pm-provider-card-top">
                  <span class="pm-provider-icon">🧩</span>
                  <div style="min-width: 0; flex: 1;">
                    <h4 class="pm-provider-title" title="${esc(pName)}">${esc(pName)}</h4>
                    ${p.language ? `<span class="pm-badge">${esc(p.language)}</span>` : ""}
                  </div>
                </div>
                ${cats.length ? `
                  <div class="pm-provider-tags">
                    ${cats.map((c) => `<span class="pm-badge">${esc(c)}</span>`).join("")}
                  </div>
                ` : ""}
                <div class="pm-provider-card-footer">
                  <button type="button" class="pm-player-btn pm-primary" data-open-provider="${esc(pId)}" style="width: 100%; justify-content: center;">
                    Apri catalogo →
                  </button>
                </div>
              </article>
            `;
          }).join("")}
        </div>
      </div>
    `.trim();
  }

  const provName = activeProvider.name || activeProvider.title || activeProvider.id || "Provider";
  const menus = Array.isArray(activeProvider.menus) ? activeProvider.menus : [];

  return `
    <div class="pm-s4me-browser">
      <div class="pm-provider-nav">
        <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
          <button type="button" class="pm-player-btn" data-close-provider>← Tutti i provider</button>
          <h3 style="margin: 0; font-size: 1.2rem; color: var(--text);">🧩 ${esc(provName)}</h3>
        </div>
        <div class="pm-provider-search-bar">
          <input type="search" class="pm-provider-search-input" data-provider-search-input value="${esc(query)}" placeholder="Cerca in ${esc(provName)}…">
          <button type="button" class="pm-player-btn pm-primary" data-provider-search-btn>🔍 Cerca</button>
        </div>
      </div>
      ${menus.length ? `
        <div class="pm-season-tabs" role="tablist" style="margin-bottom: 14px;">
          ${menus.map((m) => {
            const mPath = m.path ?? m.id ?? m.action ?? "";
            const mLabel = m.label || m.title || m.name || mPath || "Catalogo";
            const isAct = !query && (String(mPath) === String(activePath));
            return `
              <button type="button" role="tab" class="pm-season-tab ${isAct ? 'pm-active' : ''}" data-provider-path="${esc(mPath)}">
                ${esc(mLabel)}
              </button>
            `;
          }).join("")}
        </div>
      ` : ""}
      ${loading ? `
        <div class="pm-provider-status">
          <p class="muted">Esplorazione catalogo ${esc(provName)} in corso…</p>
        </div>
      ` : error ? `
        <div class="pm-provider-status">
          <p style="color: var(--accent); margin: 0 0 10px 0;">${esc(error)}</p>
          <button type="button" class="pm-player-btn" data-provider-retry>↻ Riprova</button>
        </div>
      ` : itemsList.length ? `
        <div class="pm-grid">
          ${itemsList.map((it) => {
            const sIt = { ...it, source: it.source || "stream4me", source_label: it.source_label || provName };
            const ck = compositeKey ? compositeKey(sIt) : String(sIt.id ?? "");
            const isFav = favSet.has(ck) || favSet.has(String(sIt.id ?? ""));
            return renderCardHtml(sIt, isFav, esc, { showPin: true, pinnedIds: pinSet, watchlistMap });
          }).join("")}
        </div>
      ` : `
        <div class="pm-provider-status">
          <p class="muted">Nessun elemento trovato in questa sezione. Prova una categoria diversa o usa la barra di ricerca.</p>
        </div>
      `}
    </div>
  `.trim();
}

export function renderSettingsModal(data = {}, esc = defaultEsc) {
  const activeTab = data.activeTab || "cartelle";
  const roots = data.roots || [];
  const scanning = Boolean(data.scanning);
  const canPick = Boolean(typeof window !== "undefined" && window.pywebview?.api?.pick_folder);
  const installedAddons = data.installedAddons || [];
  const activeRecipes = data.activeRecipes || [];
  const providers = Array.isArray(data.providers) ? data.providers : [];
  const availableInactiveProviders = Array.isArray(data.availableInactiveProviders) ? data.availableInactiveProviders : [];
  const stream4meInstalled = installedAddons.some((a) => (a.name || a.id || "").toLowerCase().includes("stream4me")) || Boolean(data.stream4meStatus) || providers.length > 0;

  return `
    <div class="pm-settings-overlay" data-close-settings-backdrop>
      <div class="pm-settings-modal" role="dialog" aria-modal="true">
        <div class="pm-settings-header">
          <h3 class="pm-settings-title">⚙ Impostazioni Media Center</h3>
          <button type="button" class="pm-modal-close" data-close-settings style="position: static;" title="Chiudi">✕</button>
        </div>
        <div class="pm-settings-tabs" role="tablist">
          <button type="button" role="tab" class="pm-settings-tab ${activeTab === 'cartelle' ? 'pm-active' : ''}" data-settings-tab="cartelle">📁 Cartelle locali</button>
          <button type="button" role="tab" class="pm-settings-tab ${activeTab === 'stream4me' ? 'pm-active' : ''}" data-settings-tab="stream4me">🧩 Kodi & Stream4me</button>
          <button type="button" role="tab" class="pm-settings-tab ${activeTab === 'server' ? 'pm-active' : ''}" data-settings-tab="server">🌐 Server Jellyfin / Plex</button>
          <button type="button" role="tab" class="pm-settings-tab ${activeTab === 'metadati' ? 'pm-active' : ''}" data-settings-tab="metadati">🔍 Metadati</button>
        </div>
        <div class="pm-settings-content">
          ${activeTab === "cartelle" ? `
            <div class="pm-settings-section">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <strong style="font-size: 0.95rem;">Cartelle Multimediali Locali</strong>
                <button type="button" class="pm-player-btn" data-scan-now ${scanning ? "disabled" : ""}>
                  ${scanning ? "⟳ Scansione…" : "↻ Scansiona ora"}
                </button>
              </div>
              <p class="muted" style="margin: 0; font-size: 0.82rem;">Aggiungi cartelle contenenti film, serie TV, anime o musica per l'indicizzazione locale automatica.</p>
              <div style="display: flex; gap: 6px;">
                <input type="text" class="pm-root-input" placeholder="Percorso cartella sul computer…" style="flex: 1; min-width: 0; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg-2); color: var(--text); font: inherit; font-size: 0.84rem;">
                ${canPick ? `<button type="button" class="pm-player-btn" data-pick-root>Sfoglia…</button>` : ""}
                <button type="button" class="pm-player-btn pm-primary" data-add-root>＋ Aggiungi</button>
              </div>
              <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 8px;">
                ${roots.length ? roots.map((r) => `
                  <div style="display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; border-radius: 6px; background: var(--bg-2); border: 1px solid var(--line); font-size: 0.82rem;">
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;" title="${esc(r.path)}">📁 ${esc(r.path)}</span>
                    <button type="button" class="pm-player-btn" data-remove-root="${esc(r.path)}" style="padding: 2px 8px; font-size: 0.74rem;">✕ Rimuovi</button>
                  </div>
                `).join("") : `<p class="muted" style="margin: 8px 0; font-size: 0.82rem;">Nessuna cartella configurata.</p>`}
              </div>
            </div>
          ` : ""}

          ${activeTab === "stream4me" ? `
            <div class="pm-settings-section">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <strong style="font-size: 0.95rem;">Integrazione Kodi & Stream4me</strong>
                <span class="pm-badge" style="background: ${stream4meInstalled ? 'var(--accent)' : 'var(--bg-3)'}; color: ${stream4meInstalled ? 'var(--bg)' : 'var(--text)'};">
                  ${stream4meInstalled ? '✓ Stream4me Installato' : 'Non installato'}
                </span>
              </div>
              <p class="muted" style="margin: 0; font-size: 0.82rem;">Guarda serie TV, film e canali in streaming direttamente su Pozzo Launcher tramite Stream4me e gli addon di Kodi.</p>
              <div>
                <button type="button" class="pm-player-btn pm-primary" data-install-stream4me>
                  ${stream4meInstalled ? '↻ Aggiorna Stream4me' : '⬇ Installa Stream4me'}
                </button>
                <button type="button" class="pm-player-btn" data-cleanup-stream4me title="Toglie i titoli dei provider eliminati e riscansiona quelli attivi">
                  🧹 Aggiorna e pulisci librerie
                </button>
              </div>

              <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line); display: flex; flex-direction: column; gap: 8px;">
                <strong style="font-size: 0.88rem;">Aggiungi o Gestisci Provider Stream4me</strong>
                <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                  <input type="text" id="pm-prov-name" placeholder="Nome provider (es. MioSito)…" style="flex: 1; min-width: 140px; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg-2); color: var(--text); font: inherit; font-size: 0.84rem;">
                  <input type="text" id="pm-prov-host" placeholder="URL Host (es. https://miosito.it)…" style="flex: 1; min-width: 180px; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg-2); color: var(--text); font: inherit; font-size: 0.84rem;">
                  <select id="pm-prov-cat" class="pm-source-select">
                    <option value="movie,tvshow">Film & Serie TV</option>
                    <option value="anime">Anime</option>
                    <option value="movie">Solo Film</option>
                    <option value="tvshow">Solo Serie TV</option>
                    <option value="live">Canali Live</option>
                  </select>
                  <button type="button" class="pm-player-btn pm-primary" data-add-provider>＋ Aggiungi Provider</button>
                </div>

                ${availableInactiveProviders.length ? `
                  <div style="display: flex; gap: 6px; align-items: center; margin-top: 4px;">
                    <select id="pm-prov-enable" class="pm-source-select" style="flex: 1;">
                      ${availableInactiveProviders.map((ip) => `<option value="${esc(ip.id || ip.channel || ip.name)}">${esc(ip.name || ip.title || ip.id)}</option>`).join("")}
                    </select>
                    <button type="button" class="pm-player-btn" data-enable-provider>Attiva canale Stream4me</button>
                  </div>
                ` : ""}

                ${providers.length ? `
                  <div style="display: flex; flex-direction: column; gap: 5px; margin-top: 6px;">
                    <span class="muted" style="font-size: 0.8rem;">Provider attivi (${providers.length}):</span>
                    ${providers.map((p) => {
                      const pid = p.id || p.channel || p.name || "";
                      const pname = p.name || p.title || pid;
                      return `
                        <div style="display: flex; align-items: center; justify-content: space-between; padding: 5px 10px; border-radius: 6px; background: var(--bg-2); border: 1px solid var(--line); font-size: 0.82rem;">
                          <span>🧩 <strong>${esc(pname)}</strong> ${p.host ? `<span class="muted">(${esc(p.host)})</span>` : ""}</span>
                          <button type="button" class="pm-player-btn" data-remove-provider="${esc(pid)}" style="padding: 2px 8px; font-size: 0.74rem;">🗑 Rimuovi</button>
                        </div>
                      `;
                    }).join("")}
                  </div>
                ` : ""}
              </div>

              <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line);">
                <strong style="font-size: 0.86rem;">Installa Addon Custom da URL / Zip</strong>
                <div style="display: flex; gap: 6px; margin-top: 6px;">
                  <input type="text" id="pm-addon-input" placeholder="URL GitHub o percorso file .zip…" style="flex: 1; min-width: 0; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg-2); color: var(--text); font: inherit; font-size: 0.84rem;">
                  <button type="button" class="pm-player-btn" data-install-addon>Installa Addon</button>
                </div>
              </div>
              <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 8px;">
                <strong style="font-size: 0.84rem;">Addon e sorgenti attive:</strong>
                ${installedAddons.length ? installedAddons.map((a) => `
                  <div style="display: flex; align-items: center; justify-content: space-between; padding: 4px 8px; border-radius: 6px; background: var(--bg-2); font-size: 0.8rem;">
                    <span>🧩 ${esc(a.name || a.id)}</span>
                    <span class="muted">${esc(a.version || "")}</span>
                  </div>
                `).join("") : ""}
                ${activeRecipes.length ? activeRecipes.map((r) => `
                  <div style="display: flex; align-items: center; justify-content: space-between; padding: 4px 8px; border-radius: 6px; background: var(--bg-2); font-size: 0.8rem;">
                    <span>📜 ${esc(r.title || r.name || r.id)}</span>
                    <span class="muted">ricetta</span>
                  </div>
                `).join("") : ""}
                ${!installedAddons.length && !activeRecipes.length ? `<span class="muted" style="font-size: 0.8rem;">Nessun addon aggiuntivo trovato.</span>` : ""}
              </div>
            </div>
          ` : ""}

          ${activeTab === "server" ? `
            <div class="pm-settings-section">
              <strong style="font-size: 0.95rem;">Server Multimediale Remoto (Jellyfin / Plex)</strong>
              <p class="muted" style="margin: 0; font-size: 0.82rem;">Connetti la tua istanza Jellyfin o Plex per accedere alle tue librerie remote e sincronizzare la visione.</p>
              <div style="display: flex; gap: 8px;">
                <select id="pm-server-type" class="pm-source-select" style="min-width: 120px;">
                  <option value="jellyfin">Jellyfin</option>
                  <option value="plex">Plex</option>
                </select>
                <input type="text" id="pm-server-url" placeholder="http://192.168.1.100:8096" style="flex: 1; min-width: 0; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg-2); color: var(--text); font: inherit; font-size: 0.84rem;">
              </div>
              <input type="password" id="pm-server-token" placeholder="API Key / User Token…" style="padding: 7px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg-2); color: var(--text); font: inherit; font-size: 0.84rem;">
              <div style="display: flex; gap: 8px; align-items: center;">
                <button type="button" class="pm-player-btn pm-primary" data-save-server>Salva configurazione</button>
                <button type="button" class="pm-player-btn" data-test-server>Test connessione</button>
                <span class="pm-server-status muted" style="font-size: 0.82rem;"></span>
              </div>
            </div>
          ` : ""}

          ${activeTab === "metadati" ? `
            <div class="pm-settings-section">
              <strong style="font-size: 0.95rem;">Arricchimento Metadati e Locandine</strong>
              <p class="muted" style="margin: 0; font-size: 0.82rem;">Scarica automaticamente locandine ad alta risoluzione, trame, date di rilascio, generi e sfondi cinematografici da TMDb, TVDb e SteamGridDB per tutti i tuoi film e serie TV.</p>
              <div style="margin-top: 6px;">
                <button type="button" class="pm-player-btn pm-primary" data-enrich-metadata>
                  🔍 Arricchisci locandine e trame online
                </button>
              </div>
              <div class="pm-enrich-status muted" style="margin-top: 8px; font-size: 0.82rem;"></div>
            </div>
          ` : ""}
        </div>
      </div>
    </div>
  `.trim();
}

export { attachPlay, play, loadContinueCache };

/** Renderizza l'HTML del widget dashboard Media Locale (vuoto o card con avanzamento). */
export function renderMediaWidgetHtml(item, esc = defaultEsc) {
  if (!item || isSeen(item) || !(resumeOf(item) > 0 || Number(item.resume_pos || item.pos || 0) > 0)) {
    return `
      <div class="gs-empty-widget" style="display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 20px 14px; gap: 10px; min-height: 120px;">
        <div style="font-size: 2rem; color: var(--muted); line-height: 1;">🎬</div>
        <div style="display: flex; flex-direction: column; gap: 2px;">
          <p style="margin: 0; font-size: 0.95rem; font-weight: 500; color: var(--text);">Nessun video in corso di riproduzione</p>
          <p style="margin: 0; font-size: 0.8rem; color: var(--muted);">Guarda film o serie TV con Media locale</p>
        </div>
        <button type="button" class="btn primary gs-media-open-btn" style="background: var(--accent); color: var(--bg); border: none; padding: 6px 14px; border-radius: 6px; font-weight: 500; cursor: pointer; margin-top: 4px;">
          Apri Media locale
        </button>
      </div>
    `.trim();
  }

  const title = item.title || "Contenuto multimediale";
  const pos = Number(item.resume_pos ?? item.pos ?? 0);
  const dur = Number(item.duration ?? 0);
  let percent = resumeOf(item);
  if (percent <= 0 && pos > 0 && dur > 0) {
    percent = Math.min(100, Math.max(1, Math.round((pos / dur) * 100)));
  }

  const imgUrl = safeMediaUrl(item.backdrop || item.poster);

  let subtitle = "";
  if (item.kind === "episodio" || item.series) {
    const epPart = (item.season != null || item.episode != null) ? `S${item.season ?? 1}E${item.episode ?? 1}` : "";
    subtitle = [item.series, epPart].filter(Boolean).join(" · ");
  } else if (item.year) {
    subtitle = String(item.year);
  }

  let timeInfo = "";
  if (dur > 0 && pos > 0) {
    const rem = Math.max(0, dur - pos);
    timeInfo = `${formatDuration(pos)} / ${formatDuration(dur)} · ${formatDuration(rem)} rimasti`;
  } else if (pos > 0) {
    timeInfo = formatDuration(pos);
  } else if (dur > 0) {
    timeInfo = formatDuration(dur);
  }

  const key = compositeKey ? compositeKey(item) : `${item.source || "locale"}:${item.id ?? ""}`;
  const badge = sourceBadge ? sourceBadge(item.source) : null;
  const badgeLabel = badge?.label || item.source_label || item.source || "Locale";

  return `
    <div class="gs-resume-card" style="display: flex; gap: 14px; align-items: center; width: 100%;">
      <div class="gs-resume-cover" style="width: 140px; height: 85px; flex-shrink: 0; border-radius: 6px; overflow: hidden; background: var(--panel); border: 1px solid var(--line); position: relative; display: flex; align-items: center; justify-content: center;">
        ${imgUrl ? `<img class="pm-poster-img" src="${esc(imgUrl)}" alt="" style="width: 100%; height: 100%; object-fit: cover; display: block;" loading="lazy">` : `<div style="font-size: 2rem; color: var(--muted);">🎬</div>`}
        <span class="pm-source-badge" style="position: absolute; top: 4px; right: 4px; font-size: 0.7rem; padding: 2px 5px; border-radius: 4px; background: var(--panel); border: 1px solid var(--line); color: var(--text);">${esc(badgeLabel)}</span>
      </div>
      <div class="gs-resume-info" style="display: flex; flex-direction: column; gap: 6px; min-width: 0; flex: 1;">
        <div style="min-width: 0;">
          <h3 class="gs-resume-title" style="margin: 0; font-size: 1rem; font-weight: 600; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${esc(title)}">${esc(title)}</h3>
          ${subtitle ? `<div class="gs-resume-meta" style="font-size: 0.8rem; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${esc(subtitle)}</div>` : ""}
        </div>
        <div style="display: flex; flex-direction: column; gap: 3px; width: 100%;">
          <div class="gs-progress-bar" style="height: 6px; border-radius: 999px; background: var(--line); overflow: hidden; width: 100%;">
            <div style="width: ${percent}%; height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.3s ease;"></div>
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: var(--muted);">
            <span>${esc(timeInfo)}</span>
            <span style="font-variant-numeric: tabular-nums;">${percent}%</span>
          </div>
        </div>
        <div style="display: flex; gap: 8px; margin-top: 2px;">
          <button type="button" class="btn primary gs-media-play-btn" data-play-key="${esc(key)}" data-play-id="${esc(item.id ?? '')}" style="background: var(--accent); color: var(--bg); border: none; padding: 5px 14px; border-radius: 6px; font-weight: 600; font-size: 0.84rem; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;">
            ▶ Riproduci
          </button>
          <button type="button" class="btn gs-media-open-btn" style="background: var(--panel); color: var(--text); border: 1px solid var(--line); padding: 5px 10px; border-radius: 6px; font-size: 0.84rem; cursor: pointer;">
            Apri Media
          </button>
        </div>
      </div>
    </div>
  `.trim();
}

/** Genera la definizione del widget dashboard per Media locale. */
export function createMediaWidgetDef(gsInstance, ctxInstance) {
  const pluginId = ctxInstance?.id || "media-locale";
  const sidebarId = ctxInstance?.id || "media";

  const widgetDef = {
    id: "media:continue",
    title: "Continua a guardare (Media)",
    description: "Ultimo film o serie tv in riproduzione",
    category: "extensions",
    defaultSpan: 2,
    async render(container, context) {
      if (!container) return;
      const gsRef = context?.gs || gsInstance || (typeof window !== "undefined" ? window.GS : null);
      const esc = (s) => (gsRef?.esc ? gsRef.esc(s) : defaultEsc(s));

      container.innerHTML = `<div style="padding: 16px; text-align: center; color: var(--muted); font-size: 0.85rem;">Caricamento in corso…</div>`;

      // 1. Lettura cache locale di riproduzione
      let cached = [];
      try {
        cached = typeof loadContinueCache === "function" ? loadContinueCache() : [];
      } catch {}

      let targetItem = null;
      if (Array.isArray(cached) && cached.length > 0) {
        targetItem = cached.find((it) => it && !isSeen(it) && (resumeOf(it) > 0 || Number(it.resume_pos || 0) > 0));
      }

      // 2. Lettura live da backend se disponibile
      const api = gsRef?.api || context?.api || (typeof window !== "undefined" ? window.api : null);
      if (api) {
        try {
          let apiItems = null;
          try {
            const res = await api(`/plugin-api/${pluginId}/list?limit=50`);
            apiItems = Array.isArray(res) ? res : (Array.isArray(res?.items) ? res.items : null);
          } catch {
            try {
              const res = await api("/api/ext/media-locale/library");
              apiItems = Array.isArray(res) ? res : (Array.isArray(res?.items) ? res.items : null);
            } catch {}
          }

          if (Array.isArray(apiItems) && apiItems.length > 0) {
            if (typeof mergeContinueWatching === "function") {
              const merged = mergeContinueWatching(apiItems, cached);
              if (merged && merged.length > 0) {
                targetItem = merged[0];
              }
            } else {
              const liveActive = apiItems.find((it) => it && !isSeen(it) && (resumeOf(it) > 0 || Number(it.resume_pos || 0) > 0));
              if (liveActive) targetItem = liveActive;
            }
          }
        } catch {}
      }

      // 3. Render HTML
      container.innerHTML = renderMediaWidgetHtml(targetItem, esc);

      // 4. Navigazione verso Media locale
      const openMedia = () => {
        const tid = sidebarId || "media";
        if (typeof context?.setView === "function") {
          context.setView({ type: "plugin", id: tid });
        } else if (typeof window !== "undefined" && typeof window.setView === "function") {
          window.setView({ type: "plugin", id: tid });
        } else if (typeof document !== "undefined") {
          const btn = document.querySelector(`[data-plugin-item="${tid}"]`)
            || document.querySelector('[data-plugin-item="media"]')
            || document.querySelector('[data-plugin-item="media-locale"]');
          if (btn) btn.click();
        }
      };

      container.querySelectorAll(".gs-media-open-btn").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          openMedia();
        });
      });

      // 5. Avvio riproduzione
      const playBtn = container.querySelector(".gs-media-play-btn");
      if (playBtn && targetItem) {
        playBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          const onDone = () => {
            widgetDef.render(container, context);
          };
          const playItem = normalizePlayItem(targetItem);
          if (typeof window !== "undefined" && typeof window.__pmPlay === "function") {
            window.__pmPlay(playItem, onDone);
          } else if (typeof play === "function") {
            try {
              play(gsRef, playItem, onDone);
            } catch {
              play(playItem, gsRef, onDone);
            }
          } else if (typeof gsRef?.toast === "function") {
            gsRef.toast("Player non pronto");
          }
        });
      }
    }
  };

  return widgetDef;
}

const safeCall = (fn, fb) => { try { return fn() ?? fb; } catch { return fb; } };
const widgetEmpty = (msg) => `<div class="gs-empty-widget pm-widget-empty">${defaultEsc(msg)}</div>`;
const widgetLane = (items, esc, isFav = false) => `<div class="pm-widget-lane">${items.map((it) => renderCardHtml(it, isFav, esc)).join("")}</div>`;

/** Definizioni dei widget extra (spotlight, watchlist, prossimo episodio, preferiti). Render sincroni: ritornano HTML. */
export function createExtraMediaWidgetDefs(gsInstance) {
  const ctxOf = (context) => {
    const gs = context?.gs || gsInstance || (typeof window !== "undefined" ? window.GS : null);
    return { gs, esc: (s) => (gs?.esc ? gs.esc(s) : defaultEsc(s)), known: safeCall(() => loadContinueCache(), []) };
  };
  const def = (id, title, description, defaultSpan, build) => ({
    id, title, description, category: "media", defaultSpan,
    render(arg1, arg2) {
      const isContainer = Boolean(arg1 && ("innerHTML" in arg1 || arg1.nodeType === 1));
      const container = isContainer ? arg1 : null;
      const ctx = isContainer ? arg2 : arg1;
      const c = ctxOf(ctx);
      const html = safeCall(() => build(c), widgetEmpty("Nessun contenuto disponibile"));
      if (container) container.innerHTML = html;
      return html;
    },
  });
  return [
    def("media:spotlight", "In evidenza (Media)", "Titolo in primo piano dalla libreria", 2, ({ esc, known }) => {
      const it = pickHeroItem(known, []);
      if (!it) return widgetEmpty("Nessun titolo in evidenza");
      const img = safeMediaUrl(it.backdrop || it.poster);
      const badges = [sourceBadge?.(it.source)?.label || it.source, it.year, it.kind].filter(Boolean)
        .map((b) => `<span class="pm-source-badge">${esc(b)}</span>`).join("");
      return `<div class="pm-widget-spotlight">${img ? `<img class="pm-poster-img" src="${esc(img)}" alt="" loading="lazy">` : ""}
        <div class="pm-widget-spotlight-body"><h3>${esc(it.title || "Senza titolo")}</h3><div>${badges}</div>
        <button type="button" class="btn primary gs-media-play-btn" data-play-key="${esc(compositeKey(it))}" data-play-id="${esc(it.id ?? "")}">▶ Riproduci</button></div></div>`;
    }),
    def("media:watchlist", "Watchlist (Media)", "Titoli da guardare", 2, ({ gs, esc }) => {
      const list = sortAndFilterWatchlist(safeCall(() => loadWatchlistLocal(gs), []), { status: "all" }).slice(0, 12);
      return list.length ? widgetLane(list, esc) : widgetEmpty("La Watchlist è vuota");
    }),
    def("media:next_episode", "Prossimo episodio (Media)", "Episodio successivo dell'ultima serie", 1, ({ esc, known }) => {
      const last = known.find((it) => it && (it.series || it.kind === "episodio"));
      const eps = last ? Object.values(groupEpisodes(known)[String(last.series || last.show || last.title || "Varie").trim()] || {}).flat() : [];
      const next = last && nextEpisode(eps, last.id);
      return next ? widgetLane([next], esc) : widgetEmpty("Nessun prossimo episodio");
    }),
    def("media:favorites", "Preferiti (Media)", "I tuoi titoli preferiti", 2, ({ gs, esc, known }) => {
      const favs = loadFavs(gs);
      // shortcut: only favorites present in the continue cache are shown, upgrade if the widget gets a library fetch
      const list = known.filter((it) => it && (favs.has(compositeKey(it)) || favs.has(String(it.id)))).slice(0, 12);
      return list.length ? widgetLane(list, esc, true) : widgetEmpty("Nessun preferito");
    }),
  ];
}

/** Registra il widget "media:continue" nel registro della Dashboard modulare. */
export function registerMediaWidget(gsInstance, ctxInstance) {
  const widgetDef = createMediaWidgetDef(gsInstance, ctxInstance);
  const reg = gsInstance?.ui?.registerWidget
    || (typeof window !== "undefined" ? window.GS?.ui?.registerWidget : null);
  if (typeof reg === "function") {
    createExtraMediaWidgetDefs(gsInstance).forEach((w) => reg(w));
    reg(widgetDef);
    return true;
  }
  if (typeof window !== "undefined") {
    window.__gs_pending_widgets = window.__gs_pending_widgets || [];
    window.__gs_pending_widgets.push(...createExtraMediaWidgetDefs(gsInstance), widgetDef);
    if (gsInstance?.on) {
      gsInstance.on("dashboardReady", () => {
        const r = gsInstance?.ui?.registerWidget || window.GS?.ui?.registerWidget;
        if (typeof r === "function") [...createExtraMediaWidgetDefs(gsInstance), widgetDef].forEach((w) => r(w));
      });
    }
  }
  return false;
}

const TAB_KINDS = { tutti: "", film: "film", serie: "episodio", anime: "episodio", musica: "brano", stream4me: "web", web: "web", watchlist: "watchlist" };

const WATCHLIST_STORAGE_KEY = "pm_watchlist";

function loadWatchlistLocal(gs) {
  try {
    const raw = gs?.store?.get
      ? gs.store.get(WATCHLIST_STORAGE_KEY, null)
      : JSON.parse(localStorage.getItem("gs." + WATCHLIST_STORAGE_KEY) || "[]");
    if (Array.isArray(raw) && raw.length) return raw.map((x) => normalizeWatchlistEntry(x));
    const ls = JSON.parse(localStorage.getItem("gs." + WATCHLIST_STORAGE_KEY) || "[]");
    return Array.isArray(ls) ? ls.map((x) => normalizeWatchlistEntry(x)) : [];
  } catch {
    return [];
  }
}

function saveWatchlistLocal(gs, entries) {
  const arr = Array.isArray(entries) ? entries.map((x) => normalizeWatchlistEntry(x)) : [];
  try { if (gs?.store?.set) gs.store.set(WATCHLIST_STORAGE_KEY, arr); } catch {}
  try { localStorage.setItem("gs." + WATCHLIST_STORAGE_KEY, JSON.stringify(arr)); } catch {}
}

export default function (gs, ctx) {
  const pluginId = ctx?.id || "media-locale";
  const apiBase = `/plugin-api/${pluginId}`;
  const esc = (s) => (gs?.esc ? gs.esc(s) : defaultEsc(s));
  const favs = loadFavs(gs);
  attachPlay(gs);

  const sidebarId = ctx?.id || "media";
  gs.addSidebarItem({ id: sidebarId, label: "Media", icon: "🎬", view: sidebarId });
  registerMediaWidget(gs, ctx);
  if (typeof gs?.on === "function") {
    gs.on("dashboardReady", () => registerMediaWidget(gs, ctx));
  }

  if (typeof gs?.addSettingsTab === "function") {
    gs.addSettingsTab({
      id: "media-stream4me",
      label: "Media & Stream4me",
      category: "streaming",
      async render(el) {
        if (!el) return;
        let provs = [];
        let inactive = [];
        const refreshGlobalSettings = async () => {
          try {
            const pRes = await gs.api("/plugin-api/ricette-web/stream4me/providers");
            provs = Array.isArray(pRes?.providers) ? pRes.providers : (Array.isArray(pRes) ? pRes : []);
            inactive = Array.isArray(pRes?.availableInactiveProviders) ? pRes.availableInactiveProviders : [];
          } catch {}
          el.innerHTML = `
            <div class="pm-settings-section">
              <strong style="font-size: 0.95rem;">Aggiungi o Gestisci Provider Stream4me</strong>
              <p class="muted" style="margin: 0; font-size: 0.82rem;">Aggiungi provider personalizzati o rimuovi quelli esistenti da Stream4me.</p>
              <div style="display: flex; flex-wrap: wrap; gap: 6px;">
                <input type="text" id="pm-prov-name" placeholder="Nome provider (es. MioSito)…" style="flex: 1; min-width: 140px; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg-2); color: var(--text); font: inherit; font-size: 0.84rem;">
                <input type="text" id="pm-prov-host" placeholder="URL Host (es. https://miosito.it)…" style="flex: 1; min-width: 180px; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg-2); color: var(--text); font: inherit; font-size: 0.84rem;">
                <select id="pm-prov-cat" class="pm-source-select">
                  <option value="movie,tvshow">Film & Serie TV</option>
                  <option value="anime">Anime</option>
                  <option value="movie">Solo Film</option>
                  <option value="tvshow">Solo Serie TV</option>
                  <option value="live">Canali Live</option>
                </select>
                <button type="button" class="pm-player-btn pm-primary" data-add-provider>＋ Aggiungi Provider</button>
              </div>
              ${inactive.length ? `
                <div style="display: flex; gap: 6px; align-items: center; margin-top: 4px;">
                  <select id="pm-prov-enable" class="pm-source-select" style="flex: 1;">
                    ${inactive.map((ip) => `<option value="${esc(ip.id || ip.channel || ip.name)}">${esc(ip.name || ip.title || ip.id)}</option>`).join("")}
                  </select>
                  <button type="button" class="pm-player-btn" data-enable-provider>Attiva canale Stream4me</button>
                </div>
              ` : ""}
              <div style="display: flex; flex-direction: column; gap: 5px; margin-top: 8px;">
                ${provs.map((p) => {
                  const pid = p.id || p.channel || p.name || "";
                  const pname = p.name || p.title || pid;
                  return `
                    <div style="display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; border-radius: 6px; background: var(--bg-2); border: 1px solid var(--line); font-size: 0.82rem;">
                      <span>🧩 <strong>${esc(pname)}</strong> ${p.host ? `<span class="muted">(${esc(p.host)})</span>` : ""}</span>
                      <button type="button" class="pm-player-btn" data-remove-provider="${esc(pid)}" style="padding: 2px 8px; font-size: 0.74rem;">🗑 Rimuovi</button>
                    </div>
                  `;
                }).join("")}
              </div>
            </div>
          `;
        };
        el.onclick = async (ev) => {
          const addBtn = ev.target.closest("[data-add-provider]");
          if (addBtn) {
            const name = el.querySelector("#pm-prov-name")?.value?.trim() || "";
            const host = el.querySelector("#pm-prov-host")?.value?.trim() || "";
            const cat = el.querySelector("#pm-prov-cat")?.value || "movie,tvshow";
            if (!name) return;
            try {
              await gs.api("/plugin-api/ricette-web/stream4me/providers", {
                method: "POST",
                body: { name, host, categories: cat.split(",").map((s) => s.trim()).filter(Boolean) },
              });
              gs?.toast?.("Provider aggiunto");
            } catch {}
            await refreshGlobalSettings();
            return;
          }
          const enBtn = ev.target.closest("[data-enable-provider]");
          if (enBtn) {
            const pid = el.querySelector("#pm-prov-enable")?.value || "";
            if (!pid) return;
            try {
              await gs.api("/plugin-api/ricette-web/stream4me/providers", { method: "POST", body: { id: pid, enable: true } });
              gs?.toast?.("Canale Stream4me attivato");
            } catch {}
            await refreshGlobalSettings();
            return;
          }
          const remBtn = ev.target.closest("[data-remove-provider]");
          if (remBtn) {
            const pid = remBtn.dataset.removeProvider;
            if (!pid) return;
            try {
              await gs.api("/plugin-api/ricette-web/stream4me/providers/remove", { method: "POST", body: { id: pid } });
              gs?.toast?.("Provider rimosso");
            } catch {}
            await refreshGlobalSettings();
          }
        };
        await refreshGlobalSettings();
      },
    });
  }

  function executePlay(item, onClose) {
    const playItem = normalizePlayItem(item);
    if (typeof window !== "undefined" && typeof window.__pmPlay === "function") {
      window.__pmPlay(playItem, onClose);
    } else if (typeof play === "function") {
      try {
        play(gs, playItem, onClose);
      } catch {
        play(playItem, gs, onClose);
      }
    } else if (typeof gs?.toast === "function") {
      gs.toast("Player non pronto");
    }
  }

  let pmActiveKeyDown = null;

  const viewDef = {
    title: "Media",
    async render(root) {
      if (!root) return;
      let currentTab = "tutti";
      let currentSource = "all";
      let currentQuery = "";
      let filterOnlyFavs = false;
      let showSettings = false;
      let settingsTab = "cartelle";
      let selectedDetailTarget = null;
      let selectedDetailSeason = null;
      let viewMode = (typeof localStorage !== "undefined" && localStorage.getItem("gs.pm_view_mode")) || "netflix";
      let roots = [];
      let scanning = false;
      let items = [];
      let catalogItems = [];
      let pinnedItems = [];
      const pinnedIds = new Set();
      let watchlistEntries = loadWatchlistLocal(gs);
      const watchlistMap = new Map();
      let wlFilterStatus = "all";
      let wlFilterPriority = "all";
      let wlSortBy = "priority";
      let s4mInstalled = false;
      let s4mProviders = [];
      let s4mInactiveProviders = [];
      let activeS4mProvider = null;
      let activeS4mPath = "";
      let s4mBrowsedItems = [];
      let s4mLoading = false;
      let s4mError = "";
      let detailEpisodes = [];
      let detailLoading = false;
      let installedAddons = [];
      let activeRecipes = [];
      const itemsByKey = new Map();
      const itemsById = new Map();

      function syncWatchlistMap() {
        watchlistMap.clear();
        for (const raw of watchlistEntries) {
          if (!raw) continue;
          const e = normalizeWatchlistEntry(raw);
          if (e.item_key) watchlistMap.set(e.item_key, e);
          if (e.item_id) watchlistMap.set(String(e.item_id), e);
          if (e.series) watchlistMap.set(`series:${e.series}`, e);
        }
      }
      syncWatchlistMap();

      root.innerHTML = "";
      root.classList.add("pm-view");

      const toolbar = document.createElement("div");
      toolbar.className = "pm-toolbar";
      toolbar.style.cssText = "display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 20px;";
      toolbar.innerHTML = `
        <div class="pm-season-tabs pm-main-tabs" role="tablist">
          <button type="button" role="tab" class="pm-season-tab pm-active" data-tab="tutti">✨ Tutti</button>
          <button type="button" role="tab" class="pm-season-tab" data-tab="film">🎬 Film</button>
          <button type="button" role="tab" class="pm-season-tab" data-tab="serie">📺 Serie TV</button>
          <button type="button" role="tab" class="pm-season-tab" data-tab="anime">🇯🇵 Anime</button>
          <button type="button" role="tab" class="pm-season-tab" data-tab="watchlist">📋 Watchlist</button>
          <button type="button" role="tab" class="pm-season-tab" data-tab="stream4me">🧩 Stream4me</button>
          <button type="button" role="tab" class="pm-season-tab" data-tab="musica">🎵 Musica</button>
        </div>
        <select class="pm-source-select" aria-label="Filtra sorgente">
          <option value="all">🌐 Tutte le sorgenti</option>
          <option value="locale">📁 Solo locale</option>
          <option value="server">🖥️ Server Jellyfin / Plex</option>
          <option value="web">📡 Web & Stream4me</option>
        </select>
        <div class="pm-view-mode-tabs" role="group" aria-label="Modalità vista">
          <button type="button" class="pm-view-mode-btn ${viewMode === 'netflix' ? 'pm-active' : ''}" data-view-mode="netflix" title="Vista Panoramica a Caroselli">🍿 Panoramica</button>
          <button type="button" class="pm-view-mode-btn ${viewMode === 'grid' ? 'pm-active' : ''}" data-view-mode="grid" title="Vista Locandine">⊞ Locandine</button>
          <button type="button" class="pm-view-mode-btn ${viewMode === 'list' ? 'pm-active' : ''}" data-view-mode="list" title="Vista Elenco">☰ Elenco</button>
        </div>
        <div style="flex: 1; min-width: 150px;">
          <input type="search" class="pm-search" placeholder="Cerca film, serie, anime…" style="width: 100%; max-width: 260px; padding: 6px 14px; border-radius: 999px; border: 1px solid var(--line); background: var(--bg-2); color: var(--text); font: inherit; font-size: 0.84rem;" aria-label="Cerca">
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
          <button type="button" class="pm-season-tab pm-primary" data-open-add-dialog title="Aggiungi cartella locale, Stream4me o flussi">＋ Aggiungi</button>
          <button type="button" class="pm-season-tab pm-favs-toggle" data-toggle-favs>☆ Solo preferiti</button>
          <button type="button" class="pm-season-tab" data-quick-enrich title="Scarica metadati e locandine online (TMDb / AniList)">🔍 Scarica locandine</button>
          <button type="button" class="pm-season-tab pm-settings-btn" data-open-settings>⚙ Impostazioni Media</button>
        </div>
      `;

      const content = document.createElement("div");
      content.className = "pm-content";

      const modalHost = document.createElement("div");
      modalHost.className = "pm-modal-host";

      const ctxMenuHost = document.createElement("div");
      ctxMenuHost.className = "pm-ctx-menu-host";

      root.append(toolbar, content, modalHost, ctxMenuHost);

      const searchInput = toolbar.querySelector(".pm-search");
      const favsToggle = toolbar.querySelector(".pm-favs-toggle");
      const sourceSelect = toolbar.querySelector(".pm-source-select");
      const tabBtns = toolbar.querySelectorAll("[data-tab]");

      function closeCtxMenu() {
        ctxMenuHost.innerHTML = "";
      }

      function attachWheelListeners() {
        const rows = content.querySelectorAll("[data-carousel-row]");
        rows.forEach((row) => {
          row.addEventListener("wheel", (e) => {
            if (e.shiftKey && e.deltaY !== 0) {
              e.preventDefault();
              row.scrollLeft += e.deltaY;
            }
          }, { passive: false });
        });
      }

      function enrichStream4meItemForLibrary(itemObj) {
        if (!itemObj) return null;
        const copy = { ...itemObj, source: itemObj.source || "stream4me", source_label: itemObj.source_label || itemObj.channel_name || activeS4mProvider?.name || "Stream4me" };
        const provCats = Array.isArray(activeS4mProvider?.categories) ? activeS4mProvider.categories : [];
        const isAnimeProv = provCats.some((c) => String(c).toLowerCase().includes("anime")) || String(activeS4mPath).toLowerCase().includes("anime") || isAnimeItem(copy);
        const isTvProv = provCats.some((c) => String(c).toLowerCase().includes("tv") || String(c).toLowerCase().includes("serie")) || String(activeS4mPath).toLowerCase().includes("serie") || copy.kind === "serie" || copy.kind === "episodio" || Boolean(copy.series);

        if (isAnimeProv) {
          copy.kind = "episodio";
          copy.series = copy.series || copy.title;
          if (!copy.genre || !String(copy.genre).toLowerCase().includes("anime")) {
            copy.genre = copy.genre ? `${copy.genre}, Anime` : "Anime";
          }
        } else if (isTvProv) {
          copy.kind = "episodio";
          copy.series = copy.series || copy.title;
        } else if (!copy.kind) {
          copy.kind = "film";
        }
        return copy;
      }

      async function pinStream4meItem(itemObj, pid) {
        const targetId = String(pid || itemObj?.id || "");
        if (!targetId) return null;
        const enriched = enrichStream4meItemForLibrary(itemObj || { id: targetId, title: targetId, source: "stream4me" });
        try {
          await gs.api("/plugin-api/ricette-web/stream4me/pin", { method: "POST", body: { item: enriched, id: targetId } });
        } catch {}
        pinnedIds.add(targetId);
        const existingIdx = pinnedItems.findIndex((x) => String(x.id) === targetId);
        if (existingIdx >= 0) {
          pinnedItems[existingIdx] = { ...pinnedItems[existingIdx], ...enriched };
        } else if (enriched) {
          pinnedItems.unshift(enriched);
        }
        syncItemsIndex();
        return enriched;
      }

      async function loadWatchlist() {
        try {
          const res = await gs.api(`/plugin-api/media-locale/watchlist`);
          const arr = Array.isArray(res?.entries) ? res.entries : (Array.isArray(res?.items) ? res.items : (Array.isArray(res) ? res : null));
          if (Array.isArray(arr)) {
            watchlistEntries = arr.map((x) => normalizeWatchlistEntry(x));
            saveWatchlistLocal(gs, watchlistEntries);
          }
        } catch {
          watchlistEntries = loadWatchlistLocal(gs);
        }
        syncWatchlistMap();
      }

      async function upsertWatchlistEntry(itemKey, patch = {}, itemFallback = null) {
        const existing = watchlistMap.get(itemKey) || null;
        const fb = itemFallback || itemsByKey.get(itemKey) || itemsById.get(itemKey) || (itemKey.startsWith("series:") ? { id: itemKey, title: itemKey.slice(7), series: itemKey.slice(7), kind: "episodio", source: "locale" } : { id: itemKey, item_key: itemKey });
        const now = Math.floor(Date.now() / 1000);
        const merged = normalizeWatchlistEntry({
          ...(existing || {}),
          ...patch,
          item_key: itemKey,
          added_at: existing?.added_at || now,
          updated_at: now,
        }, fb);

        const idx = watchlistEntries.findIndex((e) => e.item_key === merged.item_key || (e.item_id && e.item_id === merged.item_id));
        if (idx >= 0) {
          watchlistEntries[idx] = merged;
        } else {
          watchlistEntries.unshift(merged);
        }
        syncWatchlistMap();
        saveWatchlistLocal(gs, watchlistEntries);

        try {
          await gs.api("/plugin-api/media-locale/watchlist", {
            method: "POST",
            body: { action: "upsert", entry: merged, entries: watchlistEntries },
          });
        } catch {}

        // If Stream4me item not in library yet, pin it so the user never loses it
        if (fb && isStream4meItem(fb) && fb.id != null && !pinnedIds.has(String(fb.id))) {
          await pinStream4meItem(fb, fb.id);
        }
        return merged;
      }

      async function removeWatchlistEntry(itemKey) {
        watchlistEntries = watchlistEntries.filter((e) => e.item_key !== itemKey && String(e.item_id) !== itemKey && `series:${e.series}` !== itemKey);
        syncWatchlistMap();
        saveWatchlistLocal(gs, watchlistEntries);
        try {
          await gs.api("/plugin-api/media-locale/watchlist", {
            method: "POST",
            body: { action: "remove", item_key: itemKey, entries: watchlistEntries },
          });
        } catch {}
      }

      async function loadRoots() {
        try {
          const res = await gs.api(`${apiBase}/roots`);
          roots = Array.isArray(res?.roots) ? res.roots : [];
        } catch {
          roots = [];
        }
      }

      async function loadAddonsAndRecipes() {
        try {
          const res = await gs.api("/plugin-api/ricette-web/kodi_addons");
          installedAddons = Array.isArray(res?.addons) ? res.addons : (Array.isArray(res) ? res : []);
        } catch {}
        try {
          const res = await gs.api("/plugin-api/ricette-web/recipes");
          activeRecipes = Array.isArray(res?.recipes) ? res.recipes : (Array.isArray(res) ? res : []);
        } catch {}
      }

      function syncItemsIndex() {
        const merged = [];
        const seen = new Set();
        for (const it of [...catalogItems, ...pinnedItems, ...detailEpisodes]) {
          if (!it) continue;
          const k = compositeKey ? compositeKey(it) : `${it.source || "locale"}:${it.id ?? ""}`;
          if (k && seen.has(k)) continue;
          if (k) seen.add(k);
          merged.push(it);
        }
        items = merged;

        itemsByKey.clear();
        itemsById.clear();
        for (const it of [...items, ...s4mBrowsedItems, ...watchlistEntries]) {
          if (it) {
            const k = it.item_key || (compositeKey ? compositeKey(it) : `${it.source || "locale"}:${it.id ?? ""}`);
            if (k) itemsByKey.set(k, it);
            if (it.id != null) itemsById.set(String(it.id), it);
          }
        }
      }

      async function loadStream4meMeta() {
        try {
          const pRes = await gs.api("/plugin-api/ricette-web/stream4me/providers");
          const pArr = Array.isArray(pRes?.providers) ? pRes.providers : (Array.isArray(pRes) ? pRes : []);
          s4mProviders = pArr;
          s4mInactiveProviders = Array.isArray(pRes?.availableInactiveProviders) ? pRes.availableInactiveProviders : [];
          s4mInstalled = Boolean(pRes?.installed ?? pArr.length > 0);
        } catch {
          s4mProviders = [];
        }
        try {
          const pinRes = await gs.api("/plugin-api/ricette-web/stream4me/pinned");
          const pinArr = Array.isArray(pinRes?.items) ? pinRes.items : (Array.isArray(pinRes) ? pinRes : []);
          pinnedItems = pinArr.map((x) => ({
            ...x,
            source: x.source || "stream4me",
            source_label: x.source_label || x.channel_name || "Stream4me",
          }));
          pinnedIds.clear();
          for (const p of pinnedItems) {
            if (p && p.id != null) pinnedIds.add(String(p.id));
          }
        } catch {
          pinnedItems = [];
        }
      }

      async function browseStream4meProvider(providerObj, pathStr = "", queryStr = "") {
        activeS4mProvider = providerObj || null;
        activeS4mPath = pathStr || "";
        s4mLoading = true;
        s4mError = "";
        renderContent();
        try {
          const chId = providerObj?.id || providerObj?.channel || "all";
          const qp = new URLSearchParams();
          qp.set("channel", chId);
          if (pathStr) qp.set("path", pathStr);
          if (queryStr) qp.set("query", queryStr);
          const res = await gs.api(`/plugin-api/ricette-web/stream4me/browse?${qp.toString()}`);
          const arr = Array.isArray(res?.items) ? res.items : (Array.isArray(res) ? res : []);
          s4mBrowsedItems = arr.map((x) => ({
            ...x,
            source: x.source || "stream4me",
            source_label: x.source_label || providerObj?.name || "Stream4me",
          }));
          if (res?.error) s4mError = String(res.error);
        } catch (err) {
          s4mError = err?.message || "Errore durante l'esplorazione del provider";
          s4mBrowsedItems = [];
        } finally {
          s4mLoading = false;
          syncItemsIndex();
          renderContent();
        }
      }

      async function searchStream4meOnline(q) {
        if (!q || q.length < 2) return;
        s4mLoading = true;
        s4mError = "";
        renderContent();
        try {
          const chId = activeS4mProvider?.id || activeS4mProvider?.channel || "all";
          const res = await gs.api(`/plugin-api/ricette-web/stream4me/browse?channel=${encodeURIComponent(chId)}&query=${encodeURIComponent(q)}`);
          const arr = Array.isArray(res?.items) ? res.items : (Array.isArray(res) ? res : []);
          s4mBrowsedItems = arr.map((x) => ({
            ...x,
            source: x.source || "stream4me",
            source_label: x.source_label || activeS4mProvider?.name || "Stream4me",
          }));
        } catch (err) {
          s4mError = err?.message || "Errore ricerca online Stream4me";
        } finally {
          s4mLoading = false;
          syncItemsIndex();
          renderContent();
        }
      }

      async function loadData() {
        if (!catalogItems.length) {
          content.innerHTML = `<p class="muted" style="padding: 32px 0; text-align: center;">Caricamento catalogo multimediale…</p>`;
        }
        try {
          if (typeof federatedList === "function") {
            const res = await federatedList(gs, { kind: "", query: "" });
            catalogItems = Array.isArray(res?.items) ? res.items : (Array.isArray(res) ? res : []);
          } else {
            const res = await gs.api(`${apiBase}/list?limit=500`);
            catalogItems = Array.isArray(res) ? res : (Array.isArray(res?.items) ? res.items : []);
          }
        } catch {
          catalogItems = [];
        }

        await Promise.all([loadStream4meMeta(), loadWatchlist()]);
        syncItemsIndex();
        renderContent();
      }

      function getVisibleItems() {
        const base = typeof filterHubItems === "function"
          ? filterHubItems(items, {
              tab: currentTab === "anime" ? "serie" : (currentTab === "stream4me" ? "web" : (currentTab === "watchlist" ? "tutti" : currentTab)),
              sourceFilter: currentSource,
              query: currentQuery,
              onlyFavs: filterOnlyFavs,
              favs,
            })
          : items.filter((it) => {
              if (filterOnlyFavs) {
                const k = compositeKey ? compositeKey(it) : String(it.id);
                if (!favs.has(k) && !favs.has(String(it.id))) return false;
              }
              if (currentSource !== "all") {
                const s = String(it.source || "").toLowerCase();
                if (currentSource === "locale" && s !== "locale" && s !== "media-locale") return false;
                if (currentSource === "server" && s !== "jellyfin" && s !== "plex" && s !== "server") return false;
                if (currentSource === "web" && s !== "web" && s !== "ricette-web" && s !== "kodi" && s !== "stream4me") return false;
              }
              return true;
            });

        if (currentTab === "anime") {
          return items.filter((it) => {
            if (!isAnimeItem(it)) return false;
            if (currentQuery) {
              const q = currentQuery.toLowerCase();
              const match = String(it.title || "").toLowerCase().includes(q) || String(it.series || "").toLowerCase().includes(q);
              if (!match) return false;
            }
            if (filterOnlyFavs) {
              const k = compositeKey ? compositeKey(it) : String(it.id);
              if (!favs.has(k) && !favs.has(String(it.id)) && !(it.series && favs.has("series:" + it.series))) return false;
            }
            return true;
          });
        }
        return base;
      }

      function renderSettings() {
        modalHost.innerHTML = renderSettingsModal({
          activeTab: settingsTab,
          roots,
          scanning,
          installedAddons,
          activeRecipes,
          providers: s4mProviders,
          availableInactiveProviders: s4mInactiveProviders,
          stream4meStatus: s4mInstalled || s4mProviders.length > 0,
        }, esc);
      }

      function resolveStream4meTarget(target) {
        if (typeof target === "object" && target !== null) {
          if (isStream4meItem(target) || target.channel_id || String(target.source || "").includes("ricette")) {
            return target;
          }
          return null;
        }
        if (typeof target === "string") {
          const allGrouped = groupEpisodes(items);
          const sGroup = allGrouped[target];
          const sEps = sGroup ? Object.values(sGroup).flat() : [];
          return sEps.find((e) => isStream4meItem(e) || String(e.id || "").startsWith("s4me:") || String(e.id || "").startsWith("stream4me:") || String(e.id || "").startsWith("s4m:")) || null;
        }
        return null;
      }

      async function openItemDetail(target, selectedSeason = null) {
        selectedDetailTarget = target;
        selectedDetailSeason = selectedSeason;
        detailEpisodes = [];
        detailLoading = false;

        const s4mTarget = resolveStream4meTarget(target);

        if (s4mTarget && s4mTarget.id != null) {
          detailLoading = true;
          renderDetail(target, selectedSeason);
          try {
            const res = await gs.api(`/plugin-api/ricette-web/detail?id=${encodeURIComponent(s4mTarget.id)}`);
            if (res && typeof res === "object") {
              if (res.overview && !s4mTarget.overview) s4mTarget.overview = res.overview;
              if (res.poster && !s4mTarget.poster) s4mTarget.poster = res.poster;
              if (res.backdrop && !s4mTarget.backdrop) s4mTarget.backdrop = res.backdrop;
              const eps = Array.isArray(res.episodes) ? res.episodes : (Array.isArray(res.items) ? res.items : []);
              const seriesTitle = typeof target === "string" ? target : (s4mTarget.series || s4mTarget.title || "");
              detailEpisodes = deduplicateStream4meEpisodes(eps, s4mTarget, seriesTitle);
            }
          } catch {}
          detailLoading = false;
          for (const ep of detailEpisodes) {
            const k = compositeKey ? compositeKey(ep) : `${ep.source || "stream4me"}:${ep.id ?? ""}`;
            if (k) itemsByKey.set(k, ep);
            if (ep.id != null) itemsById.set(String(ep.id), ep);
          }
          syncItemsIndex();
          if (detailEpisodes.length === 0) {
            selectedDetailTarget = s4mTarget;
          }
        }
        renderDetail(selectedDetailTarget, selectedDetailSeason);
      }

      function renderDetail(target, selectedSeason = null) {
        const s4mTarget = resolveStream4meTarget(target);
        let groups;
        let modalTarget = target;
        if (s4mTarget) {
          if (detailEpisodes.length > 0) {
            groups = groupEpisodes(detailEpisodes);
          } else {
            groups = {};
            modalTarget = s4mTarget;
          }
        } else {
          const vis = getVisibleItems();
          groups = groupEpisodes([...items, ...vis]);
        }
        modalHost.innerHTML = renderDetailModal(modalTarget, groups, {
          favs,
          pinnedIds,
          watchlistMap,
          selectedSeason,
          episodes: detailEpisodes,
          loadingDetail: detailLoading,
        }, esc);
      }

      function renderContent() {
        tabBtns.forEach((b) => b.classList.toggle("pm-active", b.dataset.tab === currentTab));
        favsToggle.classList.toggle("pm-active", filterOnlyFavs);
        favsToggle.textContent = filterOnlyFavs ? "★ Solo preferiti" : "☆ Solo preferiti";
        sourceSelect.value = currentSource;

        if (currentTab === "watchlist") {
          content.innerHTML = renderWatchlistViewHtml(watchlistEntries, {
            status: wlFilterStatus,
            priority: wlFilterPriority,
            sortBy: wlSortBy,
            query: currentQuery,
          }, esc);
          return;
        }

        if (currentTab === "stream4me" || currentTab === "web") {
          const pinnedCarousel = !activeS4mProvider && !currentQuery && pinnedItems.length
            ? renderCarouselHtml("📌 I tuoi titoli salvati in Libreria da Stream4me", pinnedItems, { favs, pinnedIds, watchlistMap }, esc)
            : "";
          const browserHtml = renderStream4meBrowserHtml({
            installed: s4mInstalled || installedAddons.some((a) => (a.name || a.id || "").toLowerCase().includes("stream4me")),
            providers: s4mProviders,
            activeProvider: activeS4mProvider,
            activePath: activeS4mPath,
            query: currentQuery,
            browsedItems: s4mBrowsedItems,
            pinnedIds,
            favs,
            watchlistMap,
            loading: s4mLoading,
            error: s4mError,
          }, esc);
          content.innerHTML = `
            <div class="pm-netflix-home">
              ${pinnedCarousel}
              ${browserHtml}
            </div>
          `;
          attachWheelListeners();
          return;
        }

        const vis = getVisibleItems();

        if (filterOnlyFavs || currentQuery) {
          const onlineSearchBanner = currentQuery.length >= 2 ? `
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; padding: 12px 16px; margin-bottom: 14px; border-radius: 10px; background: var(--bg-2); border: 1px solid var(--line);">
              <span style="font-size: 0.88rem; color: var(--text);">Vuoi cercare <strong>"${esc(currentQuery)}"</strong> anche nei canali streaming di Stream4me?</span>
              <button type="button" class="pm-player-btn pm-primary" data-search-s4me-online="${esc(currentQuery)}">🔍 Cerca "${esc(currentQuery)}" anche in streaming su Stream4me</button>
            </div>
          ` : "";

          if (!vis.length) {
            content.innerHTML = `
              ${onlineSearchBanner}
              <p class="muted" style="padding: 40px 0; text-align: center;">Nessun contenuto locale trovato per i filtri selezionati.</p>
            `;
            return;
          }
          if (viewMode === "list") {
            content.innerHTML = `${onlineSearchBanner}${renderListHtml(vis, { favs, watchlistMap }, esc)}`;
          } else {
            content.innerHTML = `
              ${onlineSearchBanner}
              <div class="pm-grid" style="margin-top: 10px;">
                ${vis.map((it) => {
                  const key = compositeKey ? compositeKey(it) : String(it.id);
                  const isFav = favs.has(key) || favs.has(String(it.id));
                  return renderCardHtml(it, isFav, esc, { pinnedIds, watchlistMap });
                }).join("")}
              </div>
            `;
          }
          return;
        }

        const cached = typeof loadContinueCache === "function" ? loadContinueCache() : [];
        const continueItems = typeof mergeContinueWatching === "function"
          ? mergeContinueWatching(items, cached)
          : items.filter((it) => { const p = resumeOf(it); return p > 0 && !isSeen(it); });

        const heroItem = typeof pickHeroItem === "function"
          ? pickHeroItem(vis, continueItems)
          : (continueItems[0] || vis[0] || null);

        const heroHtml = heroItem ? renderHeroHtml(heroItem, esc) : "";

        if (viewMode === "list") {
          content.innerHTML = `
            <div class="pm-list-view">
              ${heroHtml}
              ${renderListHtml(vis, { favs, watchlistMap }, esc)}
            </div>
          `;
          return;
        }

        if (viewMode === "grid") {
          content.innerHTML = `
            <div class="pm-grid-view">
              ${heroHtml}
              ${vis.length ? `<div class="pm-grid" style="margin-top: 14px;">${vis.map((it) => {
                const key = compositeKey ? compositeKey(it) : String(it.id);
                const isFav = favs.has(key) || favs.has(String(it.id));
                return renderCardHtml(it, isFav, esc, { pinnedIds, watchlistMap });
              }).join("")}</div>` : `<p class="muted" style="padding: 40px 0; text-align: center;">Nessun contenuto disponibile.</p>`}
            </div>
          `;
          return;
        }

        // 1. Continua a guardare
        const resumeHtml = continueItems.length
          ? renderCarouselHtml("🍿 Continua a guardare", continueItems, { type: "resume", favs, pinnedIds, watchlistMap }, esc)
          : "";

        // 1b. Watchlist Carousel (Active items: plan_to_watch or watching, sorted by Priority Alta first)
        const activeWatchlist = sortAndFilterWatchlist(watchlistEntries, { status: "active", sortBy: "priority" })
          .filter((e) => e.status === "plan_to_watch" || e.status === "watching");
        const watchlistCarouselHtml = activeWatchlist.length
          ? renderCarouselHtml("📋 La tua Watchlist (Priorità Alta)", activeWatchlist, { favs, pinnedIds, watchlistMap }, esc)
          : "";

        // 2. Stream4me (Pinned + eventuali web items)
        const stream4mePool = pinnedItems.length
          ? pinnedItems
          : vis.filter(isStream4meItem);
        const stream4meHtml = stream4mePool.length
          ? renderCarouselHtml("🧩 In evidenza da Stream4me", stream4mePool, { favs, pinnedIds, watchlistMap }, esc)
          : "";

        // 3. Film
        const filmItems = vis.filter((it) => it.kind === "film" || (!it.series && it.kind !== "episodio" && it.kind !== "brano" && !isAnimeItem(it)));
        const filmHtml = filmItems.length
          ? renderCarouselHtml("🎬 Film", filmItems, { favs, pinnedIds, watchlistMap }, esc)
          : "";

        // 4. Serie TV (non anime)
        const tvAll = vis.filter((it) => (it.kind === "episodio" || it.kind === "serie" || it.series) && !isAnimeItem(it));
        const tvEpisodes = tvAll.filter((it) => it.series || it.kind === "episodio");
        const tvGroups = groupEpisodes(tvEpisodes);
        const tvSummaries = Object.keys(tvGroups).map((name) => {
          const seasons = tvGroups[name];
          const sKeys = Object.keys(seasons);
          const eps = sKeys.flatMap((k) => seasons[k]);
          return {
            name,
            count: eps.length,
            seasonsCount: sKeys.length,
            repItem: eps.find((e) => e.poster) || eps[0],
            allSeen: eps.length > 0 && eps.every(isSeen),
            isFav: favs.has("series:" + name),
          };
        });
        const tvStandalone = tvAll.filter((it) => !it.series && it.kind === "serie");
        const tvHtml = tvSummaries.length
          ? renderCarouselHtml("📺 Serie TV", tvSummaries, { type: "series", favs, pinnedIds, watchlistMap }, esc)
          : (tvStandalone.length ? renderCarouselHtml("📺 Serie TV", tvStandalone, { favs, pinnedIds, watchlistMap }, esc) : "");

        // 5. Anime
        const animeAll = vis.filter((it) => isAnimeItem(it));
        const animeSeries = animeAll.filter((it) => it.series || it.kind === "episodio");
        const animeGroups = groupEpisodes(animeSeries);
        const animeSummaries = Object.keys(animeGroups).map((name) => {
          const seasons = animeGroups[name];
          const sKeys = Object.keys(seasons);
          const eps = sKeys.flatMap((k) => seasons[k]);
          return {
            name,
            count: eps.length,
            seasonsCount: sKeys.length,
            repItem: eps.find((e) => e.poster) || eps[0],
            allSeen: eps.length > 0 && eps.every(isSeen),
            isFav: favs.has("series:" + name),
          };
        });
        const animeStandalone = animeAll.filter((it) => !it.series && it.kind !== "episodio");
        const animePool = animeSummaries.length ? animeSummaries : animeStandalone;
        const animeHtml = animePool.length
          ? renderCarouselHtml("🇯🇵 Anime", animePool, { type: animeSummaries.length ? "series" : "card", favs, pinnedIds, watchlistMap }, esc)
          : "";

        // 6. Musica
        const musicItems = vis.filter((it) => it.kind === "brano");
        const musicHtml = musicItems.length
          ? renderCarouselHtml("🎵 Musica", musicItems, { favs, pinnedIds, watchlistMap }, esc)
          : "";

        if (currentTab === "film") {
          content.innerHTML = `
            <div class="pm-netflix-home">
              ${heroHtml}
              ${filmHtml}
              ${filmItems.length ? `<div class="pm-grid" style="margin-top: 14px;">${filmItems.map((it) => renderCardHtml(it, favs.has(compositeKey ? compositeKey(it) : String(it.id)), esc, { pinnedIds, watchlistMap })).join("")}</div>` : ""}
            </div>
          `;
        } else if (currentTab === "serie") {
          content.innerHTML = `
            <div class="pm-netflix-home">
              ${heroHtml}
              ${tvHtml}
            </div>
          `;
        } else if (currentTab === "anime") {
          content.innerHTML = `
            <div class="pm-netflix-home">
              ${heroHtml}
              ${animeHtml}
            </div>
          `;
        } else if (currentTab === "musica") {
          content.innerHTML = `
            <div class="pm-netflix-home">
              ${musicHtml}
              ${musicItems.length ? `<div class="pm-grid" style="margin-top: 14px;">${musicItems.map((it) => renderCardHtml(it, favs.has(compositeKey ? compositeKey(it) : String(it.id)), esc, { pinnedIds, watchlistMap })).join("")}</div>` : ""}
            </div>
          `;
        } else {
          // Home Netflix completa
          content.innerHTML = `
            <div class="pm-netflix-home">
              ${heroHtml}
              ${resumeHtml}
              ${watchlistCarouselHtml}
              ${stream4meHtml}
              ${filmHtml}
              ${tvHtml}
              ${animeHtml}
              ${musicHtml}
              ${!resumeHtml && !watchlistCarouselHtml && !stream4meHtml && !filmHtml && !tvHtml && !animeHtml && !musicHtml ? `<p class="muted" style="padding: 40px 0; text-align: center;">Nessun contenuto multimediale disponibile. Clicca su ⚙ Impostazioni Media per aggiungere cartelle o configurare server e addon.</p>` : ""}
            </div>
          `;
        }

        attachWheelListeners();
      }

      root.oncontextmenu = (e) => {
        // 1. Caso provider Stream4me
        const provCard = e.target.closest(".pm-provider-card[data-open-provider]");
        if (provCard) {
          e.preventDefault();
          e.stopPropagation();
          const pid = provCard.dataset.openProvider || "";
          if (!pid) return;
          const x = Math.min(Number(e.clientX || 120), (window?.innerWidth || 1000) - 200);
          const y = Math.min(Number(e.clientY || 120), (window?.innerHeight || 800) - 150);
          ctxMenuHost.innerHTML = `
            <div class="pm-ctx-menu" style="position: fixed; left: ${x}px; top: ${y}px; z-index: 10000;">
              <button type="button" class="pm-ctx-item" data-open-provider="${esc(pid)}">📂 Apri provider</button>
              <button type="button" class="pm-ctx-item" data-remove-provider="${esc(pid)}">🗑 Rimuovi provider</button>
            </div>
          `;
          return;
        }

        // 2. Caso Media Card (locandina, continua a guardare, riga, watchlist, hero)
        const mediaCard = e.target.closest(".pm-card, .pm-resume-card, .pm-list-row, .pm-wl-card, .pm-hero, [data-play-key], [data-detail-key]");
        if (!mediaCard) {
          closeCtxMenu();
          return;
        }

        e.preventDefault();
        e.stopPropagation();

        const k = mediaCard.dataset.detailKey || mediaCard.dataset.playKey || mediaCard.dataset.wlCard || "";
        const id = mediaCard.dataset.detailId || mediaCard.dataset.playId || "";
        const item = (k ? itemsByKey.get(k) : null) || (id ? itemsById.get(id) : null) || { id, title: mediaCard.querySelector(".pm-title, .pm-list-title, .pm-hero-title")?.textContent || "Media", key: k };

        const isContinueItem = Boolean(mediaCard.closest(".pm-resume-card") || (item && (item.resume_pos > 0 || (typeof loadContinueCache === "function" && loadContinueCache().some((c) => (k && compositeKey(c) === k) || (id && String(c.id) === String(id)))))));
        const isS4me = Boolean(isStream4meItem(item) || (id && String(id).startsWith("s4me:")) || (item?.source === "stream4me"));
        const isPinnedS4me = Boolean(isS4me && id && pinnedIds.has(String(id)));
        const isFav = favs.has(k) || (id && favs.has(String(id)));

        const x = Math.min(Number(e.clientX || 120), (window?.innerWidth || 1000) - 240);
        const y = Math.min(Number(e.clientY || 120), (window?.innerHeight || 800) - 200);

        ctxMenuHost.innerHTML = `
          <div class="pm-ctx-menu" style="position: fixed; left: ${x}px; top: ${y}px; z-index: 10000;">
            ${renderMediaContextMenuHtml(item, { key: k, id, isContinueItem, isS4me, isPinnedS4me, isFav }, esc)}
          </div>
        `;
      };

      root.onchange = async (e) => {
        const wlStatusSel = e.target.closest("[data-wl-status]");
        if (wlStatusSel) {
          const itemKey = wlStatusSel.dataset.wlStatus;
          await upsertWatchlistEntry(itemKey, { status: wlStatusSel.value });
          if (modalHost.innerHTML && selectedDetailTarget) renderDetail(selectedDetailTarget, selectedDetailSeason);
          renderContent();
          return;
        }
        const wlPrioSel = e.target.closest("[data-wl-priority]");
        if (wlPrioSel) {
          const itemKey = wlPrioSel.dataset.wlPriority;
          await upsertWatchlistEntry(itemKey, { priority: wlPrioSel.value });
          if (modalHost.innerHTML && selectedDetailTarget) renderDetail(selectedDetailTarget, selectedDetailSeason);
          renderContent();
          return;
        }
        const wlRatingSel = e.target.closest("[data-wl-rating]");
        if (wlRatingSel) {
          const itemKey = wlRatingSel.dataset.wlRating;
          await upsertWatchlistEntry(itemKey, { rating: Number(wlRatingSel.value || 0) });
          if (modalHost.innerHTML && selectedDetailTarget) renderDetail(selectedDetailTarget, selectedDetailSeason);
          renderContent();
          return;
        }
        const wlFilterPrioSel = e.target.closest("[data-wl-filter-priority]");
        if (wlFilterPrioSel) {
          wlFilterPriority = wlFilterPrioSel.value || "all";
          renderContent();
          return;
        }
        const wlSortSel = e.target.closest("[data-wl-sort]");
        if (wlSortSel) {
          wlSortBy = wlSortSel.value || "priority";
          renderContent();
          return;
        }
      };

      root.onclick = async (e) => {
        if (!e.target.closest(".pm-ctx-menu")) {
          closeCtxMenu();
        }

        // 1. Azioni del menu contestuale
        const remContBtn = e.target.closest("[data-ctx-remove-continue]");
        if (remContBtn) {
          e.stopPropagation();
          closeCtxMenu();
          const k = remContBtn.dataset.ctxRemoveContinue;
          const id = remContBtn.dataset.ctxItemId;
          removeFromContinueCache(k || id);
          if (id) {
            try { await gs.api(`${apiBase}/pos`, { method: "POST", body: { id, pos: 0, seen: true } }); } catch {}
          }
          gs?.toast?.("Rimosso da «Continua a guardare»");
          renderContent();
          return;
        }

        const unpinS4meBtn = e.target.closest("[data-ctx-unpin-s4me]");
        if (unpinS4meBtn) {
          e.stopPropagation();
          closeCtxMenu();
          const pid = String(unpinS4meBtn.dataset.ctxUnpinS4me || "");
          if (pid) {
            try { await gs.api("/plugin-api/ricette-web/stream4me/unpin", { method: "POST", body: { id: pid } }); } catch {}
            pinnedIds.delete(pid);
            pinnedItems = pinnedItems.filter((x) => String(x.id) !== pid);
            syncItemsIndex();
            gs?.toast?.("Rimosso dalla Libreria");
            renderContent();
          }
          return;
        }

        const pinS4meBtn = e.target.closest("[data-ctx-pin-s4me]");
        if (pinS4meBtn) {
          e.stopPropagation();
          closeCtxMenu();
          const pid = String(pinS4meBtn.dataset.ctxPinS4me || "");
          if (pid) {
            const itemObj = itemsById.get(pid) || { id: pid };
            try { await pinStream4meItem(itemObj, pid); } catch {}
            syncItemsIndex();
            gs?.toast?.("✓ Aggiunto alla tua Libreria!");
            renderContent();
          }
          return;
        }

        const ctxPlayBtn = e.target.closest("[data-ctx-play]");
        if (ctxPlayBtn) {
          e.stopPropagation();
          closeCtxMenu();
          const k = ctxPlayBtn.dataset.ctxPlay;
          const id = ctxPlayBtn.dataset.ctxId;
          const item = (k ? itemsByKey.get(k) : null) || (id ? itemsById.get(id) : null);
          if (item) {
            modalHost.innerHTML = "";
            executePlay(item, () => renderContent());
          }
          return;
        }

        const ctxDetailBtn = e.target.closest("[data-ctx-detail]");
        if (ctxDetailBtn) {
          e.stopPropagation();
          closeCtxMenu();
          const k = ctxDetailBtn.dataset.ctxDetail;
          const id = ctxDetailBtn.dataset.ctxId;
          const item = (k ? itemsByKey.get(k) : null) || (id ? itemsById.get(id) : null);
          if (item) {
            const target = (item.series && !isStream4meItem(item)) ? item.series : item;
            const season = item.season != null ? String(item.season) : null;
            await openItemDetail(target, season);
          }
          return;
        }

        const ctxFavBtn = e.target.closest("[data-ctx-fav]");
        if (ctxFavBtn) {
          e.stopPropagation();
          closeCtxMenu();
          const k = ctxFavBtn.dataset.ctxFav;
          const id = ctxFavBtn.dataset.ctxId;
          const target = k || id;
          if (target) {
            if (favs.has(target)) favs.delete(target); else favs.add(target);
            if (id && target !== id) {
              if (favs.has(target)) favs.add(id); else favs.delete(id);
            }
            saveFavs(gs, favs);
            renderContent();
          }
          return;
        }

        // Scorrimento caroselli con pulsanti frecce ‹ ›
        const scrollBtn = e.target.closest("[data-carousel-scroll]");
        if (scrollBtn) {
          e.stopPropagation();
          const dir = Number(scrollBtn.dataset.carouselScroll) || 1;
          const car = scrollBtn.closest(".pm-carousel");
          const row = car?.querySelector("[data-carousel-row]");
          if (row && typeof row.scrollBy === "function") {
            row.scrollBy({ left: dir * 600, behavior: "smooth" });
          } else if (row) {
            row.scrollLeft += dir * 600;
          }
          return;
        }

        // Modalità di visualizzazione (Panoramica / Locandine / Elenco)
        const viewModeBtn = e.target.closest("[data-view-mode]");
        if (viewModeBtn) {
          e.stopPropagation();
          viewMode = viewModeBtn.dataset.viewMode;
          try { localStorage.setItem("gs.pm_view_mode", viewMode); } catch {}
          toolbar.querySelectorAll("[data-view-mode]").forEach((b) => {
            b.classList.toggle("pm-active", b.dataset.viewMode === viewMode);
          });
          renderContent();
          return;
        }

        // Watchlist: Quick toggle sulle card
        const wlToggleBtn = e.target.closest("[data-wl-toggle]");
        if (wlToggleBtn) {
          e.stopPropagation();
          e.preventDefault();
          const k = wlToggleBtn.dataset.wlToggle;
          const id = wlToggleBtn.dataset.wlId;
          if (!k) return;
          const itemObj = itemsByKey.get(k) || (id ? itemsById.get(id) : null);
          if (watchlistMap.has(k)) {
            await removeWatchlistEntry(k);
            gs?.toast?.("Rimosso dalla Watchlist");
          } else {
            await upsertWatchlistEntry(k, { status: "plan_to_watch", priority: "medium" }, itemObj);
            gs?.toast?.("📋 Aggiunto alla Watchlist!");
          }
          if (modalHost.innerHTML && selectedDetailTarget) renderDetail(selectedDetailTarget, selectedDetailSeason);
          renderContent();
          return;
        }

        // Watchlist: Aggiungi da modal dettaglio
        const wlAddBtn = e.target.closest("[data-wl-add]");
        if (wlAddBtn) {
          e.stopPropagation();
          const k = wlAddBtn.dataset.wlAdd;
          const prio = wlAddBtn.dataset.wlAddPriority || "medium";
          const itemObj = itemsByKey.get(k) || (typeof selectedDetailTarget === "object" ? selectedDetailTarget : null);
          await upsertWatchlistEntry(k, { status: "plan_to_watch", priority: prio }, itemObj);
          gs?.toast?.("📋 Aggiunto alla Watchlist!");
          if (modalHost.innerHTML && selectedDetailTarget) renderDetail(selectedDetailTarget, selectedDetailSeason);
          renderContent();
          return;
        }

        // Watchlist: Salva nota
        const wlSaveNoteBtn = e.target.closest("[data-wl-save-note]");
        if (wlSaveNoteBtn) {
          e.stopPropagation();
          const k = wlSaveNoteBtn.dataset.wlSaveNote;
          const scope = wlSaveNoteBtn.closest(".pm-wl-controls") || root;
          const inp = scope.querySelector(`[data-wl-note-input="${CSS?.escape ? CSS.escape(k) : k}"]`) || scope.querySelector("[data-wl-note-input]");
          const notes = inp ? inp.value.trim() : "";
          await upsertWatchlistEntry(k, { notes });
          gs?.toast?.("Nota salvata ✓");
          if (modalHost.innerHTML && selectedDetailTarget) renderDetail(selectedDetailTarget, selectedDetailSeason);
          renderContent();
          return;
        }

        // Watchlist: Rimuovi
        const wlRemoveBtn = e.target.closest("[data-wl-remove]");
        if (wlRemoveBtn) {
          e.stopPropagation();
          const k = wlRemoveBtn.dataset.wlRemove;
          await removeWatchlistEntry(k);
          gs?.toast?.("Rimosso dalla Watchlist");
          if (modalHost.innerHTML && selectedDetailTarget) renderDetail(selectedDetailTarget, selectedDetailSeason);
          renderContent();
          return;
        }

        // Watchlist: Filtro Stato (pill o tab)
        const wlFilterStBtn = e.target.closest("[data-wl-filter-status]");
        if (wlFilterStBtn) {
          e.stopPropagation();
          wlFilterStatus = wlFilterStBtn.dataset.wlFilterStatus || "all";
          if (wlFilterStBtn.dataset.wlStatPriority) {
            wlFilterPriority = wlFilterPriority === wlFilterStBtn.dataset.wlStatPriority ? "all" : wlFilterStBtn.dataset.wlStatPriority;
          } else if (wlFilterStBtn.classList.contains("pm-wl-stat-pill") && wlFilterStatus === "all") {
            wlFilterPriority = "all";
          }
          renderContent();
          return;
        }

        // Pin / Unpin elemento Stream4me nella Libreria ("come se fosse mia")
        const pinBtn = e.target.closest("[data-pin-item]");
        if (pinBtn) {
          e.stopPropagation();
          e.preventDefault();
          const pid = String(pinBtn.dataset.pinItem || "");
          if (!pid) return;
          const itemObj = itemsById.get(pid) || (typeof selectedDetailTarget === "object" ? selectedDetailTarget : null);
          const alreadyPinned = pinnedIds.has(pid);
          try {
            if (alreadyPinned) {
              await gs.api("/plugin-api/ricette-web/stream4me/unpin", { method: "POST", body: { id: pid } });
              pinnedIds.delete(pid);
              pinnedItems = pinnedItems.filter((x) => String(x.id) !== pid);
              gs?.toast?.("Rimosso dalla Libreria");
            } else {
              await pinStream4meItem(itemObj, pid);
              gs?.toast?.("✓ Aggiunto alla tua Libreria!");
            }
          } catch {
            if (alreadyPinned) {
              pinnedIds.delete(pid);
              pinnedItems = pinnedItems.filter((x) => String(x.id) !== pid);
            } else {
              await pinStream4meItem(itemObj, pid);
            }
          }
          syncItemsIndex();
          if (modalHost.innerHTML && selectedDetailTarget) {
            renderDetail(selectedDetailTarget, selectedDetailSeason);
          }
          renderContent();
          return;
        }

        // Stream4me: Aggiungi Provider dalle Impostazioni
        const addProvBtn = e.target.closest("[data-add-provider]");
        if (addProvBtn) {
          e.stopPropagation();
          const nameInp = modalHost.querySelector("#pm-prov-name");
          const hostInp = modalHost.querySelector("#pm-prov-host");
          const catSel = modalHost.querySelector("#pm-prov-cat");
          const name = nameInp?.value?.trim() || "";
          const host = hostInp?.value?.trim() || "";
          const cats = (catSel?.value || "movie,tvshow").split(",").map((s) => s.trim()).filter(Boolean);
          if (!name) return;
          const newId = name.toLowerCase().replace(/[^a-z0-9_-]+/g, "");
          const newProv = { id: newId || name, name, host, categories: cats, menus: [{ label: "Catalogo", path: "main" }] };
          try {
            await gs.api("/plugin-api/ricette-web/stream4me/providers", { method: "POST", body: newProv });
          } catch {}
          if (!s4mProviders.some((p) => String(p.id || p.name) === String(newProv.id))) {
            s4mProviders.push(newProv);
          }
          gs?.toast?.("Provider aggiunto!");
          if (showSettings) renderSettings();
          renderContent();
          return;
        }

        // Stream4me: Attiva Provider Inattivo
        const enableProvBtn = e.target.closest("[data-enable-provider]");
        if (enableProvBtn) {
          e.stopPropagation();
          const sel = modalHost.querySelector("#pm-prov-enable");
          const pid = sel?.value || "";
          if (!pid) return;
          try {
            await gs.api("/plugin-api/ricette-web/stream4me/providers", { method: "POST", body: { id: pid, enable: true } });
          } catch {}
          const found = s4mInactiveProviders.find((p) => String(p.id || p.channel || p.name) === pid);
          if (found) {
            s4mProviders.push(found);
            s4mInactiveProviders = s4mInactiveProviders.filter((p) => String(p.id || p.channel || p.name) !== pid);
          }
          gs?.toast?.("Canale Stream4me attivato!");
          if (showSettings) renderSettings();
          renderContent();
          return;
        }

        // Stream4me: Rimuovi Provider (da impostazioni o menu contestuale tasto destro)
        const remProvBtn = e.target.closest("[data-remove-provider]");
        if (remProvBtn) {
          e.stopPropagation();
          const pid = remProvBtn.dataset.removeProvider;
          closeCtxMenu();
          if (!pid) return;
          try {
            await gs.api("/plugin-api/ricette-web/stream4me/providers/remove", { method: "POST", body: { id: pid } });
          } catch {}
          s4mProviders = s4mProviders.filter((p) => String(p.id || p.channel || p.name) !== String(pid));
          if (activeS4mProvider && String(activeS4mProvider.id || activeS4mProvider.channel || activeS4mProvider.name) === String(pid)) {
            activeS4mProvider = null;
            activeS4mPath = "";
            s4mBrowsedItems = [];
          }
          gs?.toast?.("Provider rimosso");
          if (showSettings) renderSettings();
          await loadData();
          renderContent();
          return;
        }

        // Navigazione Stream4me: Apri Provider
        const openProvBtn = e.target.closest("[data-open-provider]");
        if (openProvBtn) {
          e.stopPropagation();
          closeCtxMenu();
          const provId = openProvBtn.dataset.openProvider;
          const prov = s4mProviders.find((p) => String(p.id || p.channel || p.name) === String(provId)) || { id: provId, name: provId, menus: [] };
          const defaultPath = Array.isArray(prov.menus) && prov.menus[0] ? (prov.menus[0].path ?? prov.menus[0].id ?? "") : "";
          await browseStream4meProvider(prov, defaultPath, "");
          return;
        }

        // Navigazione Stream4me: Torna a tutti i provider
        const closeProvBtn = e.target.closest("[data-close-provider]");
        if (closeProvBtn) {
          e.stopPropagation();
          activeS4mProvider = null;
          activeS4mPath = "";
          s4mBrowsedItems = [];
          s4mError = "";
          renderContent();
          return;
        }

        // Navigazione Stream4me: Cambia categoria/menu del provider
        const provPathBtn = e.target.closest("[data-provider-path]");
        if (provPathBtn && activeS4mProvider) {
          e.stopPropagation();
          const pathVal = provPathBtn.dataset.providerPath || "";
          await browseStream4meProvider(activeS4mProvider, pathVal, "");
          return;
        }

        // Navigazione Stream4me: Ricerca interna nel provider o globale
        const provSearchBtn = e.target.closest("[data-provider-search-btn]");
        if (provSearchBtn) {
          e.stopPropagation();
          const inp = content.querySelector("[data-provider-search-input]");
          const qVal = inp ? inp.value.trim() : currentQuery;
          currentQuery = qVal;
          if (searchInput) searchInput.value = qVal;
          if (activeS4mProvider) {
            await browseStream4meProvider(activeS4mProvider, "", qVal);
          } else {
            await searchStream4meOnline(qVal);
          }
          return;
        }

        // Navigazione Stream4me: Riprova
        const provRetryBtn = e.target.closest("[data-provider-retry]");
        if (provRetryBtn) {
          e.stopPropagation();
          if (activeS4mProvider) {
            await browseStream4meProvider(activeS4mProvider, activeS4mPath, currentQuery);
          } else if (currentQuery) {
            await searchStream4meOnline(currentQuery);
          } else {
            await loadData();
          }
          return;
        }

        // Bottone "Cerca anche in streaming su Stream4me" dai risultati di ricerca
        const searchS4meOnlineBtn = e.target.closest("[data-search-s4me-online]");
        if (searchS4meOnlineBtn) {
          e.stopPropagation();
          const q = searchS4meOnlineBtn.dataset.searchS4meOnline || currentQuery;
          currentTab = "stream4me";
          currentQuery = q;
          if (searchInput) searchInput.value = q;
          await searchStream4meOnline(q);
          return;
        }

        // Tasto Apri Dialogo Aggiungi (Cartelle / Stream4me / Server)
        const addDialogBtn = e.target.closest("[data-open-add-dialog]");
        if (addDialogBtn) {
          e.stopPropagation();
          showSettings = true;
          settingsTab = "cartelle";
          await loadRoots();
          await loadAddonsAndRecipes();
          renderSettings();
          return;
        }

        // Preferiti
        const favBtn = e.target.closest("[data-fav-key], [data-fav-id]");
        if (favBtn) {
          e.stopPropagation();
          e.preventDefault();
          const fkey = favBtn.dataset.favKey;
          const fid = favBtn.dataset.favId;
          const target = fkey || fid;
          if (target) {
            if (favs.has(target)) favs.delete(target); else favs.add(target);
            if (fid && target !== fid) {
              if (favs.has(target)) favs.add(fid); else favs.delete(fid);
            }
            saveFavs(gs, favs);
            if (modalHost.innerHTML) {
              if (selectedDetailTarget) renderDetail(selectedDetailTarget, selectedDetailSeason);
            }
            renderContent();
          }
          return;
        }

        // Tasto Apri Impostazioni Media
        const openSettingsBtn = e.target.closest("[data-open-settings]");
        if (openSettingsBtn) {
          e.stopPropagation();
          showSettings = true;
          await loadRoots();
          await loadAddonsAndRecipes();
          renderSettings();
          return;
        }

        // Tasti Chiudi Modal o Impostazioni
        const closeSettingsBtn = e.target.closest("[data-close-settings]");
        if (closeSettingsBtn) {
          e.stopPropagation();
          showSettings = false;
          modalHost.innerHTML = "";
          return;
        }

        const closeModalBtn = e.target.closest("[data-close-modal]");
        if (closeModalBtn) {
          e.stopPropagation();
          selectedDetailTarget = null;
          selectedDetailSeason = null;
          modalHost.innerHTML = "";
          return;
        }

        // Click su backdrop overlay per chiudere
        if (e.target.hasAttribute("data-close-modal-backdrop")) {
          e.stopPropagation();
          selectedDetailTarget = null;
          selectedDetailSeason = null;
          modalHost.innerHTML = "";
          return;
        }
        if (e.target.hasAttribute("data-close-settings-backdrop")) {
          e.stopPropagation();
          showSettings = false;
          modalHost.innerHTML = "";
          return;
        }

        // Switch Tab Impostazioni
        const setTabBtn = e.target.closest("[data-settings-tab]");
        if (setTabBtn) {
          e.stopPropagation();
          settingsTab = setTabBtn.dataset.settingsTab;
          renderSettings();
          return;
        }

        // Quick Enrich dalla toolbar o dal pannello impostazioni
        const quickEnrichBtn = e.target.closest("[data-quick-enrich]");
        const enrichMetaBtn = e.target.closest("[data-enrich-metadata]");
        if (quickEnrichBtn || enrichMetaBtn) {
          e.stopPropagation();
          const stEl = modalHost.querySelector(".pm-enrich-status");
          if (stEl) stEl.textContent = "Arricchimento metadati in corso…";
          gs?.toast?.("Scaricamento locandine e metadati online avviato…");
          try {
            const res = await gs.api(`${apiBase}/enrich`, { method: "POST", body: {} });
            gs?.toast?.(res?.message || `Metadati aggiornati (${res?.enriched ?? 0} arricchiti)`);
            if (stEl) stEl.textContent = "Completato ✓";
            await loadData();
          } catch (err) {
            if (stEl) stEl.textContent = "Avviato in background ✓";
            gs?.toast?.("Arricchimento metadati in esecuzione in background");
          }
          return;
        }

        // Cartelle: Sfoglia con pywebview
        const pickBtn = e.target.closest("[data-pick-root]");
        if (pickBtn) {
          e.stopPropagation();
          try {
            const p = await window.pywebview?.api?.pick_folder?.();
            const inp = modalHost.querySelector(".pm-root-input");
            if (p && inp) inp.value = p;
          } catch {}
          return;
        }

        // Cartelle: Aggiungi
        const addRootBtn = e.target.closest("[data-add-root]");
        if (addRootBtn) {
          e.stopPropagation();
          const inp = modalHost.querySelector(".pm-root-input");
          const raw = inp ? inp.value.trim() : "";
          if (!raw) return;
          scanning = true;
          renderSettings();
          try {
            await gs.api(`${apiBase}/roots`, { body: { add: raw } });
            const res = await gs.api(`${apiBase}/scan`, { body: {} });
            roots = Array.isArray(res?.roots) ? res.roots : roots;
            gs?.toast?.(`Scansione completata (${res?.items ?? 0} contenuti)`);
            await loadData();
          } catch (err) {
            gs?.toast?.(err?.message || "Impossibile aggiungere la cartella", true);
          } finally {
            scanning = false;
            renderSettings();
          }
          return;
        }

        // Cartelle: Rimuovi
        const remRootBtn = e.target.closest("[data-remove-root]");
        if (remRootBtn) {
          e.stopPropagation();
          const rem = remRootBtn.dataset.removeRoot;
          if (!rem) return;
          try {
            const res = await gs.api(`${apiBase}/roots`, { body: { remove: rem } });
            roots = Array.isArray(res?.roots) ? res.roots : [];
            renderSettings();
            await loadData();
          } catch (err) {
            gs?.toast?.(err?.message || "Impossibile rimuovere la cartella", true);
          }
          return;
        }

        // Cartelle: Scansiona ora
        const scanNowBtn = e.target.closest("[data-scan-now]");
        if (scanNowBtn) {
          e.stopPropagation();
          if (scanning) return;
          scanning = true;
          renderSettings();
          try {
            const res = await gs.api(`${apiBase}/scan`, { body: {} });
            roots = Array.isArray(res?.roots) ? res.roots : roots;
            gs?.toast?.(`Scansione completata (${res?.items ?? 0} contenuti)`);
            await loadData();
          } catch (err) {
            gs?.toast?.(err?.message || "Errore durante la scansione", true);
          } finally {
            scanning = false;
            renderSettings();
          }
          return;
        }

        // Server: Salva
        const saveServerBtn = e.target.closest("[data-save-server]");
        if (saveServerBtn) {
          e.stopPropagation();
          const urlInp = modalHost.querySelector("#pm-server-url");
          const tokenInp = modalHost.querySelector("#pm-server-token");
          const typeSel = modalHost.querySelector("#pm-server-type");
          const stEl = modalHost.querySelector(".pm-server-status");
          try {
            await gs.api("/plugin-api/media-server/config", {
              body: { url: urlInp?.value?.trim() || "", token: tokenInp?.value?.trim() || "", type: typeSel?.value || "jellyfin" },
            });
            if (stEl) stEl.textContent = "Salvato ✓";
            gs?.toast?.("Configurazione server salvata");
            await loadData();
          } catch (err) {
            if (stEl) stEl.textContent = "Errore";
            gs?.toast?.(err?.message || "Errore salvataggio server", true);
          }
          return;
        }

        // Server: Test
        const testServerBtn = e.target.closest("[data-test-server]");
        if (testServerBtn) {
          e.stopPropagation();
          const stEl = modalHost.querySelector(".pm-server-status");
          if (stEl) stEl.textContent = "Verifica…";
          try {
            const res = await gs.api("/plugin-api/media-server/test");
            if (stEl) stEl.textContent = res?.ok ? "Online ✓" : "Non raggiungibile";
            gs?.toast?.(res?.ok ? "Server connesso con successo" : "Server non raggiungibile", !res?.ok);
          } catch (err) {
            if (stEl) stEl.textContent = "Offline ✕";
            gs?.toast?.(err?.message || "Test connessione fallito", true);
          }
          return;
        }

        // Stream4me: pulisce i provider eliminati e riscansiona quelli attivi
        const cleanS4mBtn = e.target.closest("[data-cleanup-stream4me]");
        if (cleanS4mBtn) {
          e.stopPropagation();
          cleanS4mBtn.disabled = true;
          gs?.toast?.("Pulizia e aggiornamento librerie in corso…");
          try {
            const r = await gs.api("/plugin-api/ricette-web/stream4me/cleanup", { method: "POST", body: {} });
            gs?.toast?.(`Librerie aggiornate: ${r?.removed ?? 0} rimossi, ${r?.refreshed ?? 0} titoli riscansionati`);
            await loadData();
            if (showSettings) renderSettings();
          } catch (err) {
            gs?.toast?.(err?.message || "Pulizia non riuscita", true);
            cleanS4mBtn.disabled = false;
          }
          return;
        }

        // Stream4me: Installa / Aggiorna
        const installS4mBtn = e.target.closest("[data-install-stream4me]");
        if (installS4mBtn) {
          e.stopPropagation();
          gs?.toast?.("Installazione Stream4me in corso…");
          try {
            try {
              await gs.api("/plugin-api/ricette-web/stream4me/install", { method: "POST", body: {} });
            } catch {
              await gs.api("/plugin-api/ricette-web/kodi_addons", {
                body: { url: "https://github.com/stream4me/stream4me" }
              });
            }
            gs?.toast?.("Stream4me pronto all'uso!");
            await loadAddonsAndRecipes();
            if (showSettings) renderSettings();
            await loadData();
          } catch (err) {
            gs?.toast?.(err?.message || "Impossibile installare Stream4me", true);
          }
          return;
        }

        // Addon: Installa da custom url / zip
        const installAddonBtn = e.target.closest("[data-install-addon]");
        if (installAddonBtn) {
          e.stopPropagation();
          const inp = modalHost.querySelector("#pm-addon-input");
          const val = inp?.value?.trim() || "";
          if (!val) return;
          try {
            const payload = val.startsWith("http") ? { url: val } : { path: val };
            await gs.api("/plugin-api/ricette-web/kodi_addons", { body: payload });
            gs?.toast?.("Addon installato con successo");
            if (inp) inp.value = "";
            await loadAddonsAndRecipes();
            renderSettings();
            await loadData();
          } catch (err) {
            gs?.toast?.(err?.message || "Impossibile installare addon", true);
          }
          return;
        }

        // Cambio Stagione dentro Modal Dettagli
        const modalSeasonBtn = e.target.closest("[data-modal-season]");
        if (modalSeasonBtn) {
          e.stopPropagation();
          selectedDetailSeason = modalSeasonBtn.dataset.modalSeason;
          if (selectedDetailTarget) renderDetail(selectedDetailTarget, selectedDetailSeason);
          return;
        }

        // Clic su serie o anime -> Apre Modal Dettagli Netflix (e carica episodi Stream4me se serie Stream4me)
        const seriesCard = e.target.closest("[data-series-name]");
        if (seriesCard) {
          e.stopPropagation();
          const sName = seriesCard.dataset.seriesName;
          await openItemDetail(sName, null);
          return;
        }

        // Clic su "ℹ Altre info" o card generica
        const detailBtn = e.target.closest("[data-detail-key], [data-detail-id], [data-s4me-open]");
        const playBtn = e.target.closest("[data-play-key], [data-play-id]");

        // Se clicca direttamente su Riproduci (o un episodio nella modale)
        if (playBtn && (!detailBtn || e.target.closest(".pm-player-btn.pm-primary") || e.target.closest(".pm-episode-card"))) {
          e.stopPropagation();
          const key = playBtn.dataset.playKey;
          const id = playBtn.dataset.playId;
          const item = (key ? itemsByKey.get(key) : null) || (id ? itemsById.get(id) : null);
          if (item) {
            modalHost.innerHTML = "";
            executePlay(item, () => renderContent());
          }
          return;
        }

        if (detailBtn) {
          e.stopPropagation();
          const key = detailBtn.dataset.detailKey;
          const id = detailBtn.dataset.detailId || detailBtn.dataset.s4meOpen;
          const item = (key ? itemsByKey.get(key) : null) || (id ? itemsById.get(id) : null);
          if (item) {
            const target = (item.series && !isStream4meItem(item)) ? item.series : item;
            const season = item.season != null ? String(item.season) : null;
            await openItemDetail(target, season);
          } else if (key && key.startsWith("series:")) {
            await openItemDetail(key.slice(7), null);
          }
          return;
        }

        // Switch Tab Barra Principale (0ms istantaneo in memoria!)
        const tabBtn = e.target.closest("[data-tab]");
        if (tabBtn) {
          e.stopPropagation();
          currentTab = tabBtn.dataset.tab;
          selectedDetailTarget = null;
          selectedDetailSeason = null;
          renderContent();
          if (currentTab === "stream4me" && currentQuery.length >= 2) {
            searchStream4meOnline(currentQuery);
          }
          return;
        }

        // Toggle Solo Preferiti
        const favToggleBtn = e.target.closest("[data-toggle-favs]");
        if (favToggleBtn) {
          e.stopPropagation();
          filterOnlyFavs = !filterOnlyFavs;
          renderContent();
          return;
        }
      };

      sourceSelect.onchange = () => {
        currentSource = sourceSelect.value;
        renderContent();
      };

      let searchTimer;
      let s4mSearchTimer;
      searchInput.oninput = () => {
        clearTimeout(searchTimer);
        clearTimeout(s4mSearchTimer);
        searchTimer = setTimeout(() => {
          currentQuery = searchInput.value.trim();
          renderContent();
        }, 120);
        s4mSearchTimer = setTimeout(() => {
          const q = searchInput.value.trim();
          if (currentTab === "stream4me" && q.length >= 2) {
            searchStream4meOnline(q);
          }
        }, 400);
      };

      root.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && e.target.matches("[data-provider-search-input]")) {
          e.preventDefault();
          const qVal = e.target.value.trim();
          currentQuery = qVal;
          if (searchInput) searchInput.value = qVal;
          if (activeS4mProvider) {
            browseStream4meProvider(activeS4mProvider, "", qVal);
          } else {
            searchStream4meOnline(qVal);
          }
        }
      });

      let activeHoverCard = null;
      root.addEventListener("mouseover", (e) => {
        const card = e.target.closest(".pm-card, .pm-resume-card, .pm-list-row, .pm-wl-card, [data-play-key], [data-detail-key]");
        if (card) activeHoverCard = card;
      });

      if (pmActiveKeyDown && typeof document !== "undefined") {
        document.removeEventListener("keydown", pmActiveKeyDown);
      }

      const onKeyDown = async (e) => {
        if (e.key === "Escape") {
          modalHost.innerHTML = "";
          closeCtxMenu();
          showSettings = false;
          selectedDetailTarget = null;
          selectedDetailSeason = null;
          return;
        }

        const activeTag = document.activeElement?.tagName?.toLowerCase();
        if (activeTag === "input" || activeTag === "textarea" || activeTag === "select" || document.activeElement?.isContentEditable) {
          return;
        }

        const targetCard = activeHoverCard || document.activeElement?.closest?.(".pm-card, .pm-resume-card, .pm-list-row, .pm-wl-card, [data-play-key], [data-detail-key]");
        if (!targetCard) return;

        const k = targetCard.dataset.detailKey || targetCard.dataset.playKey || targetCard.dataset.wlCard || "";
        const id = targetCard.dataset.detailId || targetCard.dataset.playId || "";
        const item = (k ? itemsByKey.get(k) : null) || (id ? itemsById.get(id) : null);

        if (e.key === "Delete" || e.key === "Backspace") {
          const isContinue = Boolean(targetCard.closest(".pm-resume-card") || (item && item.resume_pos > 0));
          const isPinned = Boolean(id && pinnedIds.has(String(id)));
          if (isContinue) {
            e.preventDefault();
            removeFromContinueCache(k || id);
            if (id) {
              try { await gs.api(`${apiBase}/pos`, { method: "POST", body: { id, pos: 0, seen: true } }); } catch {}
            }
            gs?.toast?.("Rimosso da «Continua a guardare»");
            renderContent();
          } else if (isPinned) {
            e.preventDefault();
            try { await gs.api("/plugin-api/ricette-web/stream4me/unpin", { method: "POST", body: { id } }); } catch {}
            pinnedIds.delete(String(id));
            pinnedItems = pinnedItems.filter((x) => String(x.id) !== String(id));
            syncItemsIndex();
            gs?.toast?.("Rimosso dalla Libreria");
            renderContent();
          }
        } else if (e.key === "f" || e.key === "F") {
          const target = k || id;
          if (target) {
            e.preventDefault();
            if (favs.has(target)) favs.delete(target); else favs.add(target);
            if (id && target !== id) {
              if (favs.has(target)) favs.add(id); else favs.delete(id);
            }
            saveFavs(gs, favs);
            renderContent();
          }
        }
      };
      pmActiveKeyDown = onKeyDown;
      if (typeof document !== "undefined") {
        document.addEventListener("keydown", onKeyDown);
      }

      await loadRoots();
      await loadData();
    },
  };

  gs.registerView(sidebarId, viewDef);
  if (sidebarId !== "media") gs.registerView("media", viewDef);
  if (sidebarId !== "media-locale") gs.registerView("media-locale", viewDef);
}

// Auto-registrazione nel dashboard globale se GS.ui.registerWidget e' gia' definito
if (typeof window !== "undefined" && typeof window.GS?.ui?.registerWidget === "function") {
  registerMediaWidget(window.GS);
}
