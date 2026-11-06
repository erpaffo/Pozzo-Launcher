"use strict";
/* Pozzo Launcher - Dashboard modulare e widget predefiniti.
 * Script classico compatibile con l'ambito globale Pozzo e Node.js.
 */

(function () {
const root = typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : this);

root.GS = root.GS || {};
root.GS.ui = root.GS.ui || {};
root.GS.ui.widgets = root.GS.ui.widgets || new Map();
// testi dal catalogo: window.t esiste nel browser; senza, resta la chiave
const t = (k, p) => (typeof root.t === "function" ? root.t(k, p) : k);

/* ------------------------------------------------------------------ utilità di base */
const esc = (s) => {
  if (typeof root.esc === "function") return root.esc(s);
  if (root.GS && typeof root.GS.esc === "function") return root.GS.esc(s);
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
};

const hue = (s) => {
  if (typeof root.hue === "function") return root.hue(s);
  let h = 0;
  for (let i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
};

const platName = (p) => {
  if (typeof root.platName === "function") return root.platName(p);
  return p || "";
};

const getResumeLeft = (sec) => {
  if (typeof root.resumeLeftText === "function") return root.resumeLeftText(sec);
  if (!(sec > 0)) return "";
  const m = Math.round(sec / 60);
  if (m < 60) return t("g.dash.resume.left_min", { n: Math.max(1, m) });
  const h = Math.round(m / 60);
  return t(h === 1 ? "g.dash.resume.left_h_one" : "g.dash.resume.left_h_many", { n: h });
};

const getResumeSave = (save, now = Date.now() / 1000) => {
  if (typeof root.resumeSaveText === "function") return root.resumeSaveText(save, now);
  if (!save || !save.time) return "";
  const t = new Date(save.time * 1000), n = new Date(now * 1000);
  const day = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.round((day(n) - day(t)) / 86400000);
  const when = diff <= 0 ? root.t("g.dash.save.today") : diff === 1 ? root.t("g.dash.save.yesterday") : root.t("g.dash.save.days_ago", { n: diff });
  const hm = `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
  return root.t("g.dash.save.line", { when, hm });
};

const checkIsApp = (g) => {
  if (typeof root.isApp === "function") return root.isApp(g);
  if (g.is_app || g.content === "app") return true;
  return g.store === "manual" && String(g.genres || "").split(", ").includes("Applicazione");
};

const formatTime = (sec) => {
  if (typeof root.fmtTime === "function") return root.fmtTime(sec);
  if (!sec) return "0 min";
  const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
};

const renderShelfGame = (g) => {
  if (typeof root.shelfGame === "function") return root.shelfGame(g);
  const storeShort = typeof root.STORE_SHORT !== "undefined" ? root.STORE_SHORT[g.store] : "";
  const meta = [g.year, storeShort || platName(g.platform)].filter(Boolean).join(" · ");
  return `<button class="shelf-game" type="button" data-shelf-game="${esc(String(g.id))}" aria-label="${esc(t("g.dash.shelf.open", { title: g.title }))}">`
    + `<span class="shelf-cover" style="--h:${hue(g.title)}"><img src="/img/${encodeURIComponent(String(g.id))}/cover?w=300" alt="" loading="lazy"><span>${esc(g.title)}</span></span>`
    + `<span class="shelf-game-title">${esc(g.title)}</span><span class="shelf-game-meta">${esc(meta)}</span></button>`;
};

/* ------------------------------------------------------------------ storage */
function getStorage() {
  return typeof localStorage !== "undefined" ? localStorage : root.localStorage;
}

function getStorageItem(key) {
  try {
    const s = getStorage();
    if (!s) return null;
    return typeof s.getItem === "function" ? s.getItem(key) : s[key];
  } catch {
    return null;
  }
}

function setStorageItem(key, value) {
  try {
    const s = getStorage();
    if (!s) return;
    if (typeof s.setItem === "function") s.setItem(key, value);
    else s[key] = value;
  } catch { /* storage non disponibile */ }
}

function removeStorageItem(key) {
  try {
    const s = getStorage();
    if (!s) return;
    if (typeof s.removeItem === "function") s.removeItem(key);
    else delete s[key];
  } catch { /* storage non disponibile */ }
}

/* ------------------------------------------------------------------ registry */
function registerWidget(def) {
  if (!def || typeof def !== "object") {
    throw new Error("La definizione del widget deve essere un oggetto");
  }
  if (typeof def.id !== "string" || !def.id.trim()) {
    throw new Error("L'id del widget deve essere una stringa non vuota");
  }
  if (typeof def.title !== "string" || !def.title.trim()) {
    throw new Error("Il titolo del widget deve essere una stringa non vuota");
  }
  if (typeof def.render !== "function") {
    throw new Error("La funzione di render del widget è obbligatoria");
  }
  const span = def.defaultSpan === 2 || def.defaultSpan === "full" ? def.defaultSpan : 1;
  const widget = {
    id: def.id.trim(),
    title: def.title.trim(),
    description: typeof def.description === "string" ? def.description : "",
    category: typeof def.category === "string" ? def.category : "general",
    defaultSpan: span,
    render: def.render,
  };
  root.GS.ui.widgets.set(widget.id, widget);
  if (typeof root.GS.emit === "function") {
    root.GS.emit("uiChanged", { kind: "widgets", widget });
  }
  return widget;
}
root.GS.ui.registerWidget = registerWidget;

/* ------------------------------------------------------------------ layout */
function getDefaultDashboardLayout() {
  return [
    { instanceId: "resume-1", widgetId: "games:resume", span: 2 },
    { instanceId: "apps-1", widgetId: "apps:launcher", span: 1 },
    { instanceId: "stats-1", widgetId: "stats:overview", span: 1 },
    { instanceId: "favorites-1", widgetId: "games:favorites", span: 2 },
    { instanceId: "recent-1", widgetId: "games:recent", span: "full" },
  ];
}

function normalizeDashboardLayout(layout) {
  if (!Array.isArray(layout)) return getDefaultDashboardLayout();
  let count = 0;
  return layout
    .filter((item) => item && typeof item === "object" && typeof item.widgetId === "string" && item.widgetId.trim())
    .map((item) => {
      count++;
      const span = item.span === "full" ? "full" : Math.min(Math.max(Number(item.span) || 1, 1), 4);
      let height = null;
      if (typeof item.height === "number" && !isNaN(item.height) && item.height >= 120 && item.height <= 1600) {
        height = Math.round(item.height);
      } else if (typeof item.height === "string" && ["sm", "md", "lg", "xl"].includes(item.height)) {
        height = item.height;
      }
      const res = {
        instanceId: String(item.instanceId || `widget-${Date.now()}-${count}`),
        widgetId: item.widgetId.trim(),
        span: span === "full" || span === 2 || span === 3 || span === 4 ? span : 1,
      };
      if (height) res.height = height;
      return res;
    });
}

function getDashboardLayout(profileId) {
  const key = profileId ? "gs.dashboard.layout." + profileId : "gs.dashboard.layout";
  let raw = getStorageItem(key);
  if ((raw === null || raw === undefined) && profileId) {
    raw = getStorageItem("gs.dashboard.layout");
  }
  if (raw === null || raw === undefined || raw === "") {
    return getDefaultDashboardLayout();
  }
  try {
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!Array.isArray(parsed)) return getDefaultDashboardLayout();
    return normalizeDashboardLayout(parsed);
  } catch {
    return getDefaultDashboardLayout();
  }
}

function saveDashboardLayout(layout, profileId) {
  const normalized = normalizeDashboardLayout(layout);
  const key = profileId ? "gs.dashboard.layout." + profileId : "gs.dashboard.layout";
  setStorageItem(key, JSON.stringify(normalized));
  return normalized;
}

function resetDashboardLayout(profileId) {
  const def = getDefaultDashboardLayout();
  saveDashboardLayout(def, profileId);
  return def;
}

/* ------------------------------------------------------------------ widget integrati */
const libraryGames = (context) => {
  if (context && context._cachedLibraryGames) return context._cachedLibraryGames;
  const source = context?.state?.games || (typeof root.S !== "undefined" && root.S?.games) || [];
  const res = source.filter((g) => g && g.id != null && (!g.grp || g.grp.primary == null || String(g.id) === String(g.grp.primary)) && !g.grp?.hidden);
  if (context && typeof context === "object") context._cachedLibraryGames = res;
  return res;
};
const playtime = (g) => (g.grp?.playtime || 0) + (g.splay || 0) * 60;

const builtInWidgets = [
  {
    id: "games:resume",
    title: "g.dash.resume.title",
    description: "g.dash.resume.desc",
    category: "games",
    defaultSpan: 2,
    render: (context) => {
      const games = libraryGames(context);
      const recent = games
        .filter((g) => (g.grp?.last || g.last || 0) > 0)
        .sort((a, b) => (b.grp?.last || b.last || 0) - (a.grp?.last || a.last || 0));
      const top = recent[0];
      if (!top) {
        return `<div class="gs-widget-empty"><p class="muted">${t("g.dash.resume.empty")}</p></div>`;
      }
      const left = getResumeLeft(top.remaining_secs || (top.hltb ? Math.max(0, top.hltb * 3600 - (top.grp?.playtime || 0)) : 0));
      const save = getResumeSave(top.save || top.grp?.save);
      const pName = platName(top.platform);
      const metaParts = [pName, top.year].filter(Boolean).join(" · ");

      return `<div class="gs-resume-card" style="--h:${hue(top.title)}">
        <div class="gs-resume-cover">
          <img src="/img/${encodeURIComponent(String(top.id))}/cover?w=640" alt="" loading="lazy" decoding="async" onerror="this.remove()">
        </div>
        <div class="gs-resume-info">
          <div class="shelves-kicker">${t("g.dash.resume.title")}</div>
          <h3 class="gs-resume-title">${esc(top.title)}</h3>
          ${metaParts ? `<p class="gs-resume-meta muted">${esc(metaParts)}</p>` : ""}
          ${left ? `<p class="gs-resume-meta">${esc(left)}</p>` : ""}
          ${save ? `<p class="gs-resume-meta muted">${esc(save)}</p>` : ""}
          <div style="margin-top:8px;">
            <button class="btn primary" type="button" data-resume-play="${esc(String(top.id))}">▶ ${t("g.dash.resume.title")}</button>
          </div>
        </div>
      </div>`;
    },
  },
  {
    id: "apps:launcher",
    title: "g.dash.apps.title",
    description: "g.dash.apps.desc",
    category: "apps",
    defaultSpan: 1,
    render: (context) => {
      const apps = libraryGames(context).filter((g) => checkIsApp(g));
      const visibleApps = apps.slice(0, 16);

      const appsHtml = visibleApps.map((g) => {
        return `<button class="btn gs-app-tile" type="button" data-app-launch="${esc(String(g.id))}" data-shelf-game="${esc(String(g.id))}" title="${esc(g.title)}">
          <img class="gs-app-icon" src="/img/${encodeURIComponent(String(g.id))}/icon" alt="" loading="lazy" decoding="async" onerror="this.remove()">
          <span class="gs-app-title">${esc(g.title)}</span>
        </button>`;
      }).join("");

      return `<div class="gs-apps-widget">
        ${apps.length ? `<div class="gs-apps-grid">${appsHtml}</div>` : `<p class="muted">${t("g.dash.apps.empty")}</p>`}
        <div style="margin-top:12px;">
          <button class="btn" type="button" data-add-app="app">＋ ${t("g.dash.apps.add")}</button>
        </div>
      </div>`;
    },
  },
  {
    id: "games:favorites",
    title: "g.dash.favorites.title",
    description: "g.dash.favorites.desc",
    category: "games",
    defaultSpan: 2,
    render: (context) => {
      const favs = libraryGames(context).filter((g) => g.grp?.favorite || g.fav).slice(0, 20);

      if (!favs.length) {
        return `<div class="gs-shelf-empty"><p class="muted">${t("g.dash.favorites.empty")}</p></div>`;
      }

      return `<div class="shelf-section">
        <div class="shelf-lane">${favs.map(renderShelfGame).join("")}</div>
      </div>`;
    },
  },
  {
    id: "games:recent",
    title: "g.dash.recent.title",
    description: "g.dash.recent.desc",
    category: "games",
    defaultSpan: "full",
    render: (context) => {
      const recents = libraryGames(context)
        .filter((g) => (g.grp?.last || g.last || 0) > 0)
        .sort((a, b) => (b.grp?.last || b.last || 0) - (a.grp?.last || a.last || 0))
        .slice(0, 20);

      if (!recents.length) {
        return `<div class="gs-shelf-empty"><p class="muted">${t("g.dash.recent.empty")}</p></div>`;
      }

      return `<div class="shelf-section">
        <div class="shelf-lane">${recents.map(renderShelfGame).join("")}</div>
      </div>`;
    },
  },
  {
    id: "stats:overview",
    title: "g.dash.stats.title",
    description: "g.dash.stats.desc",
    category: "stats",
    defaultSpan: 1,
    render: (context) => {
      const games = libraryGames(context);
      const totalSecs = games.reduce((acc, g) => acc + (g.grp?.playtime || 0) + (g.splay || 0) * 60, 0);
      const timeStr = formatTime(totalSecs);
      const gamesCount = games.length;
      const completedCount = games.filter((g) => g.grp?.status === "done").length;

      return `<div class="gs-stats-grid">
        <div class="gs-stat-item">
          <span class="gs-stat-num">${esc(timeStr)}</span>
          <span class="gs-stat-lbl">${t("g.dash.stats.playtime")}</span>
        </div>
        <div class="gs-stat-item">
          <span class="gs-stat-num">${gamesCount}</span>
          <span class="gs-stat-lbl">${t("g.dash.label.games")}</span>
        </div>
        <div class="gs-stat-item">
          <span class="gs-stat-num">${completedCount}</span>
          <span class="gs-stat-lbl">${t("g.dash.stats.completed")}</span>
          <span class="gs-stat-lbl">${t("g.dash.label.games")}</span>
        </div>
        <div class="gs-stat-item">
          <span class="gs-stat-num">${completedCount}</span>
          <span class="gs-stat-lbl">${t("g.dash.stats.completed")}</span>
        </div>
      </div>`;
    },
  },
  {
    id: "games:roulette",
    title: "g.dash.roulette.title",
    description: "g.dash.roulette.desc",
    category: "games",
    defaultSpan: 1,
    render: (context) => {
      const games = libraryGames(context).filter((g) => !checkIsApp(g));
      let g = games.find((x) => String(x.id) === roulettePick);
      if (!g && games.length) { g = games[Math.floor(Math.random() * games.length)]; roulettePick = String(g.id); }
      if (!g) return `<div class="gs-widget-empty"><p class="muted">${t("g.dash.roulette.empty")}</p></div>`;
      return `<div class="gs-roulette-card" style="--h:${hue(g.title)}">
        ${renderShelfGame(g)}
        <div class="gs-roulette-actions">
          <button class="btn primary" type="button" data-resume-play="${esc(String(g.id))}">▶ ${t("g.dash.roulette.play")}</button>
          <button class="btn" type="button" data-roulette-reroll${games.length < 2 ? " disabled" : ""}>🎲 ${t("g.dash.roulette.reroll")}</button>
        </div>
      </div>`;
    },
  },
  {
    id: "games:most_played",
    title: "g.dash.most.title",
    description: "g.dash.most.desc",
    category: "games",
    defaultSpan: 1,
    render: (context) => {
      const top = libraryGames(context).map((g) => [g, playtime(g)]).filter(([, t]) => t > 0)
        .sort((a, b) => b[1] - a[1]).slice(0, 5);
      if (!top.length) return `<div class="gs-widget-empty"><p class="muted">${t("g.dash.most.empty")}</p></div>`;
      return `<div class="gs-ranking">${top.map(([g, t]) => `<button class="gs-ranking-item" type="button" data-shelf-game="${esc(String(g.id))}">
        <span class="gs-ranking-title">${esc(g.title)}</span><span class="gs-ranking-time muted">${esc(formatTime(t))}</span>
        <span class="gs-ranking-bar"><span style="width:${Math.round((t / top[0][1]) * 100)}%"></span></span>
      </button>`).join("")}</div>`;
    },
  },
  {
    id: "games:backlog",
    title: "g.dash.backlog.title",
    description: "g.dash.backlog.desc",
    category: "games",
    defaultSpan: 1,
    render: (context) => {
      const score = (g) => g.critics ?? g.rating ?? -1;
      const list = libraryGames(context).filter((g) => !checkIsApp(g) && playtime(g) === 0)
        .sort((a, b) => score(b) - score(a)).slice(0, 5);
      if (!list.length) return `<div class="gs-widget-empty"><p class="muted">${t("g.dash.backlog.empty")}</p></div>`;
      return `<div class="gs-ranking">${list.map((g) => `<button class="gs-ranking-item" type="button" data-shelf-game="${esc(String(g.id))}">
        <span class="gs-ranking-title">${esc(g.title)}</span>
        <span class="gs-ranking-time muted">${g.critics != null ? t("g.dash.backlog.critic", { n: Math.round(g.critics * 100) }) : ""}</span>
      </button>`).join("")}</div>`;
    },
  },
  {
    id: "tools:quick_actions",
    title: "g.dash.quick.title",
    description: "g.dash.quick.desc",
    category: "tools",
    defaultSpan: 1,
    render: () => `<div class="gs-quick-actions-grid">
      <button class="btn" type="button" data-quick-action="bigpicture">🖥 Big Picture</button>
      <button class="btn" type="button" data-quick-action="reload">⟳ ${t("g.dash.quick.reload")}</button>
      <button class="btn" type="button" data-quick-action="add">＋ ${t("g.dash.label.add")}</button>
      <button class="btn" type="button" data-quick-action="settings">⚙ ${t("g.dash.quick.settings")}</button>
    </div>`,
  },
  {
    id: "downloads:status",
    title: "g.dash.downloads.title",
    description: "g.dash.downloads.desc",
    category: "tools",
    defaultSpan: 1,
    render: () => {
      // DL è un const top-level di downloads.js (script classico): visibile solo via typeof
      const tasks = typeof DL !== "undefined" && Array.isArray(DL.tasks) ? DL.tasks : [];
      const live = tasks.filter((t) => t.status === "running" || t.status === "queued" || t.status === "paused").slice(0, 4);
      const rows = live.map((t) => {
        const pct = Math.round(Math.min(Math.max(t.progress || 0, 0), 1) * 100);
        return `<div class="gs-ranking-item"><span class="gs-ranking-title">${esc(t.name || t.source || "")}</span>
          <span class="gs-ranking-time muted">${pct}%</span><span class="gs-ranking-bar"><span style="width:${pct}%"></span></span></div>`;
      }).join("");
      return `<div class="gs-ranking">${rows || `<p class="muted">${t("g.dash.downloads.none")}</p>`}
        <button class="btn" type="button" data-quick-action="downloads">${t("g.dash.downloads.open")}</button></div>`;
    },
  },
];

// Scelta corrente della roulette, indipendente dall'elemento così sopravvive ai re-render
let roulettePick = null;
function rerollRoulette(context) {
  const pool = libraryGames(context).filter((g) => !checkIsApp(g) && String(g.id) !== roulettePick);
  if (pool.length) roulettePick = String(pool[Math.floor(Math.random() * pool.length)].id);
}

// Registrazione automatica dei widget integrati
builtInWidgets.forEach((w) => registerWidget(w));

/* ------------------------------------------------------------------ renderer */
function findClosest(target, sel) {
  if (!target) return null;
  if (typeof target.closest === "function") return target.closest(sel);
  let cur = target;
  while (cur) {
    if (cur.matches && cur.matches(sel)) return cur;
    if (cur.dataset) {
      if (sel.startsWith("[data-") && sel.endsWith("]")) {
        const attr = sel.slice(1, -1);
        if (attr.includes("=")) {
          const [k, v] = attr.split("=");
          const prop = k.replace(/^data-/, "").replace(/-([a-z])/g, (_, c) => c.toUpperCase());
          const cleanVal = v.replace(/^["']|["']$/g, "");
          if (cur.dataset[prop] === cleanVal) return cur;
        } else {
          const prop = attr.replace(/^data-/, "").replace(/-([a-z])/g, (_, c) => c.toUpperCase());
          if (prop in cur.dataset) return cur;
        }
      }
    }
    if (cur.classList && sel.startsWith(".")) {
      const cls = sel.slice(1);
      if (cur.classList.contains && cur.classList.contains(cls)) return cur;
    }
    cur = cur.parentElement;
  }
  return null;
}

const ADD_CATEGORIES = [["all", "g.dash.label.all"], ["media", "g.dash.label.media"], ["games", "g.dash.label.games"], ["tools", "g.dash.label.tools"], ["stats", "g.dash.stats.title"]];

function renderAddWidgetModal(category = "all", context = {}) {
  const options = [];
  for (const [id, def] of root.GS.ui.widgets.entries()) {
    if (category !== "all" && def.category !== category) continue;
    let previewHtml = "";
    try {
      if (typeof def.render === "function") {
        previewHtml = def.render(context, { instanceId: `preview-${id}`, span: def.defaultSpan || 1 });
      }
    } catch {
      previewHtml = `<div class="muted" style="padding:12px;font-size:var(--type-xs);">${t("g.dash.gallery.preview_na")}</div>`;
    }

    const spanLabel = def.defaultSpan === "full" ? t("g.dash.span.full") : `${def.defaultSpan || 1}x`;
    options.push(`<div class="gs-gallery-card gs-widget-option" data-widget-category="${esc(def.category)}" data-gallery-widget-id="${esc(id)}" draggable="true">
      <div class="gs-gallery-card-header">
        <div class="gs-gallery-card-info">
          <span class="gs-gallery-card-title gs-widget-option-title">${esc(t(def.title))}</span>
          <span class="gs-gallery-card-desc gs-widget-option-desc">${esc(t(def.description || ""))}</span>
        </div>
        <span class="gs-gallery-badge">${esc(spanLabel)}</span>
      </div>
      <div class="gs-gallery-preview" title="${esc(t("g.dash.gallery.preview_title"))}">
        ${previewHtml}
      </div>
      <div class="gs-gallery-card-actions">
        <span class="gs-gallery-drag-hint" title="${esc(t("g.dash.gallery.drag_title"))}">⋮⋮ ${t("g.dash.label.drag")}</span>
        <button class="btn primary gs-gallery-add-btn" type="button" data-add-widget-id="${esc(id)}">＋ ${t("g.dash.label.add")}</button>
      </div>
    </div>`);
  }
  return `<div class="gs-modal-backdrop gs-gallery-backdrop" role="dialog" aria-modal="true" aria-label="${esc(t("g.dash.gallery.aria"))}">
    <div class="gs-modal-box gs-gallery-modal">
      <div class="gs-gallery-modal-header">
        <div>
          <h2 style="margin:0;font-size:var(--type-xl);">${t("g.dash.gallery.title")}</h2>
          <p class="muted" style="margin:4px 0 0 0;font-size:var(--type-sm);">${t("g.dash.gallery.intro")}</p>
        </div>
        <button class="btn icon-btn" type="button" data-modal-close aria-label="${esc(t("g.dash.label.close"))}">✕</button>
      </div>
      <div class="gs-category-tabs" role="tablist">${ADD_CATEGORIES.map(([k, label]) =>
        `<button class="gs-category-tab${k === category ? " active" : ""}" type="button" role="tab" aria-selected="${k === category}" data-add-category="${k}">${t(label)}</button>`).join("")}</div>
      <div class="gs-gallery-grid gs-widget-options-list">
        ${options.join("") || `<p class="muted" style="grid-column: 1 / -1; padding: 24px; text-align: center;">${t("g.dash.gallery.empty_cat")}</p>`}
      </div>
    </div>
  </div>`;
}

function flipAnimate(container, changeFn) {
  if (!container || typeof container.querySelectorAll !== "function") {
    return changeFn();
  }
  const isReduced = typeof root !== "undefined"
    && root.dataset
    && (root.dataset.motion === "off" || root.dataset.motion === "reduced");
  if (isReduced) {
    return changeFn();
  }

  const cards = Array.from(container.querySelectorAll(".gs-widget-card"));
  const firsts = new Map();
  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];
    const id = card.getAttribute ? card.getAttribute("data-instance-id") : card.dataset?.instanceId;
    if (id && typeof card.getBoundingClientRect === "function") {
      firsts.set(id, card.getBoundingClientRect());
    }
  }

  changeFn();

  const newCards = Array.from(container.querySelectorAll(".gs-widget-card"));
  for (let i = 0; i < newCards.length; i++) {
    const card = newCards[i];
    const id = card.getAttribute ? card.getAttribute("data-instance-id") : card.dataset?.instanceId;
    const first = id ? firsts.get(id) : null;
    if (!first || typeof card.getBoundingClientRect !== "function") continue;
    const last = card.getBoundingClientRect();
    const dx = first.left - last.left;
    const dy = first.top - last.top;
    if ((dx !== 0 || dy !== 0) && card.style) {
      card.style.transform = `translate3d(${dx}px, ${dy}px, 0)`;
      card.style.transition = "none";
      if (typeof requestAnimationFrame === "function") {
        requestAnimationFrame(() => {
          card.style.transition = "transform 260ms cubic-bezier(0.2, 0, 0, 1)";
          card.style.transform = "translate3d(0, 0, 0)";
          const clean = () => {
            if (card.style) {
              card.style.transform = "";
              card.style.transition = "";
            }
            if (typeof card.removeEventListener === "function") {
              card.removeEventListener("transitionend", clean);
            }
          };
          if (typeof card.addEventListener === "function") {
            card.addEventListener("transitionend", clean, { once: true });
          }
          setTimeout(clean, 300);
        });
      }
    }
  }
}

function setupDashboardEvents(element, context) {
  element.onclick = (e) => {
    const find = (sel) => (e.target.closest ? e.target.closest(sel) : findClosest(e.target, sel));

    // 1. Alterna modalità modifica
    if (find("[data-dashboard-toggle-edit]")) {
      element._gsEditMode = !element._gsEditMode;
      element._gsShowAddModal = false;
      renderCustomDashboard(element, context);
      return;
    }

    // 2. Apri dialogo aggiungi widget
    if (find("[data-dashboard-add-widget]")) {
      element._gsShowAddModal = true;
      renderCustomDashboard(element, context);
      return;
    }

    // 3. Chiudi dialogo aggiungi widget
    const closeBtn = find("[data-modal-close]");
    const backdrop = find(".gs-modal-backdrop");
    if (closeBtn || (backdrop && e.target === backdrop)) {
      element._gsShowAddModal = false;
      renderCustomDashboard(element, context);
      return;
    }

    // 3b. Filtro categoria nel dialogo
    const catTab = find("[data-add-category]");
    if (catTab) {
      element._gsAddCategory = catTab.getAttribute ? catTab.getAttribute("data-add-category") : catTab.dataset.addCategory;
      renderCustomDashboard(element, context);
      return;
    }

    // 4. Aggiungi widget dal dialogo
    const addChoice = find("[data-add-widget-id]");
    if (addChoice) {
      const widgetId = addChoice.getAttribute ? addChoice.getAttribute("data-add-widget-id") : addChoice.dataset.addWidgetId;
      const widget = root.GS.ui.widgets.get(widgetId);
      const span = widget?.defaultSpan || 1;
      const layout = getDashboardLayout(context?.profileId);
      layout.push({
        instanceId: `w-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        widgetId,
        span,
      });
      saveDashboardLayout(layout, context?.profileId);
      element._gsShowAddModal = false;
      renderCustomDashboard(element, context);
      return;
    }

    // 5. Ripristina layout predefinito
    if (find("[data-dashboard-reset]")) {
      resetDashboardLayout(context?.profileId);
      renderCustomDashboard(element, context);
      return;
    }

    // 6. Controlli dei singoli widget in modalità modifica
    const card = find(".gs-widget-card");
    if (card && element._gsEditMode) {
      const instanceId = card.getAttribute ? card.getAttribute("data-instance-id") : card.dataset.instanceId;
      const layout = getDashboardLayout(context?.profileId);
      const index = layout.findIndex((item) => item.instanceId === instanceId);
      if (index !== -1) {
        if (find('[data-widget-move="prev"]')) {
          if (index > 0) {
            const grid = element.querySelector ? element.querySelector(".gs-dashboard-grid") : element;
            flipAnimate(grid, () => {
              const temp = layout[index - 1];
              layout[index - 1] = layout[index];
              layout[index] = temp;
              saveDashboardLayout(layout, context?.profileId);
              renderCustomDashboard(element, context);
            });
          }
          return;
        }
        if (find('[data-widget-move="next"]')) {
          if (index < layout.length - 1) {
            const grid = element.querySelector ? element.querySelector(".gs-dashboard-grid") : element;
            flipAnimate(grid, () => {
              const temp = layout[index + 1];
              layout[index + 1] = layout[index];
              layout[index] = temp;
              saveDashboardLayout(layout, context?.profileId);
              renderCustomDashboard(element, context);
            });
          }
          return;
        }
        const spanBtn = find('[data-widget-span]');
        if (spanBtn) {
          const rawSpan = spanBtn.getAttribute ? spanBtn.getAttribute("data-widget-span") : spanBtn.dataset.widgetSpan;
          layout[index].span = rawSpan === "full" ? "full" : (Number(rawSpan) || 1);
          saveDashboardLayout(layout, context?.profileId);
          renderCustomDashboard(element, context);
          return;
        }
        const heightBtn = find('[data-widget-height]');
        if (heightBtn) {
          const rawHeight = heightBtn.getAttribute ? heightBtn.getAttribute("data-widget-height") : heightBtn.dataset.widgetHeight;
          layout[index].height = rawHeight === "auto" ? null : rawHeight;
          saveDashboardLayout(layout, context?.profileId);
          renderCustomDashboard(element, context);
          return;
        }
        if (find('[data-widget-remove]')) {
          layout.splice(index, 1);
          saveDashboardLayout(layout, context?.profileId);
          renderCustomDashboard(element, context);
          return;
        }
      }
    }

    // 7. Interazioni in modalità normale
    if (!element._gsEditMode) {
      if (find("[data-roulette-reroll]")) {
        rerollRoulette(context);
        renderCustomDashboard(element, context);
        return;
      }
      const quick = find("[data-quick-action]");
      if (quick) {
        const act = quick.getAttribute ? quick.getAttribute("data-quick-action") : quick.dataset.quickAction;
        if (act === "bigpicture" && typeof root.enterBigPicture === "function") root.enterBigPicture();
        else if (act === "reload" && typeof root.GS.refresh === "function") root.GS.refresh();
        else if (act === "add" && typeof root.openAddGame === "function") root.openAddGame();
        else if (act === "settings" && typeof root.openSettings === "function") root.openSettings();
        else if (act === "downloads" && typeof root.setView === "function") root.setView({ type: "downloads" });
        return;
      }
      const resume = find("[data-resume-play]");
      if (resume) {
        const rawId = resume.getAttribute ? resume.getAttribute("data-resume-play") : resume.dataset.resumePlay;
        const id = Number(rawId);
        if (typeof root.play === "function") root.play(id);
        else if (root.GS && typeof root.GS.openGame === "function") root.GS.openGame(id);
        return;
      }
      const addApp = find("[data-add-app]");
      if (addApp) {
        if (typeof root.openAddGame === "function") root.openAddGame("app");
        return;
      }
      const appLaunch = find("[data-app-launch]");
      if (appLaunch) {
        const rawId = appLaunch.getAttribute ? appLaunch.getAttribute("data-app-launch") : appLaunch.dataset.appLaunch;
        const id = Number(rawId);
        if (typeof root.play === "function") root.play(id);
        else if (root.GS && typeof root.GS.openGame === "function") root.GS.openGame(id);
        return;
      }
      const shelfGameEl = find("[data-shelf-game]");
      if (shelfGameEl) {
        const rawId = shelfGameEl.getAttribute ? shelfGameEl.getAttribute("data-shelf-game") : shelfGameEl.dataset.shelfGame;
        const id = Number(rawId);
        if (typeof root.openDetail === "function") root.openDetail(id);
        else if (root.GS && typeof root.GS.openGame === "function") root.GS.openGame(id);
        return;
      }
    }
  };

  // 8. Riordino fluido tramite Drag & Drop e animazioni FLIP in modalità modifica
  element.ondragstart = (e) => {
    if (!element._gsEditMode) return;
    const find = (sel) => (e.target.closest ? e.target.closest(sel) : findClosest(e.target, sel));

    const galleryCard = find(".gs-gallery-card");
    const widgetId = galleryCard ? (galleryCard.getAttribute ? galleryCard.getAttribute("data-gallery-widget-id") : galleryCard.dataset?.galleryWidgetId) : null;
    const card = find(".gs-widget-card");
    const instanceId = card ? (card.getAttribute ? card.getAttribute("data-instance-id") : card.dataset?.instanceId) : null;

    // A. Drag dalla Galleria Widget per inserimento a schermo
    if (galleryCard && widgetId && !instanceId) {
      element._gsDraggedWidgetId = widgetId;
      element._gsDraggedId = null;
      if (galleryCard.classList && galleryCard.classList.add) galleryCard.classList.add("gs-dragging");
      const backdrop = element.querySelector ? element.querySelector(".gs-gallery-backdrop") : null;
      if (backdrop && backdrop.classList && backdrop.classList.add) backdrop.classList.add("gs-dragging-from-gallery");
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "copyMove";
        e.dataTransfer.setData("text/widget-id", widgetId);
        e.dataTransfer.setData("text/plain", widgetId);
      }
      return;
    }

    // B. Drag riordino scheda dashboard esistente
    if (!card || !instanceId) return;
    element._gsDraggedId = instanceId;
    element._gsDraggedWidgetId = null;
    element._gsLastTargetId = instanceId;
    if (card.classList && card.classList.add) card.classList.add("gs-dragging");
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", instanceId || "");
    }
  };

  element.ondragover = (e) => {
    if (!element._gsEditMode || (!element._gsDraggedId && !element._gsDraggedWidgetId)) return;
    if (e.preventDefault) e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = element._gsDraggedWidgetId ? "copy" : "move";

    const find = (sel) => (e.target.closest ? e.target.closest(sel) : findClosest(e.target, sel));
    const targetCard = find(".gs-widget-card");
    const targetId = targetCard ? (targetCard.getAttribute ? targetCard.getAttribute("data-instance-id") : targetCard.dataset?.instanceId) : null;

    // Se stiamo trascinando un nuovo widget dalla galleria:
    if (element._gsDraggedWidgetId) {
      if (targetCard && targetCard.classList && targetCard.classList.add) {
        targetCard.classList.add("gs-drag-over");
      }
      return;
    }

    if (!targetCard || !targetId || targetId === element._gsDraggedId) return;

    // Transizione FLIP solo quando il cursore entra in una scheda differente (throttled)
    if (targetId !== element._gsLastTargetId) {
      element._gsLastTargetId = targetId;
      const grid = element.querySelector ? element.querySelector(".gs-dashboard-grid") : element;
      flipAnimate(grid, () => {
        const layout = getDashboardLayout(context?.profileId);
        const fromIdx = layout.findIndex((it) => it.instanceId === element._gsDraggedId);
        const toIdx = layout.findIndex((it) => it.instanceId === targetId);
        if (fromIdx !== -1 && toIdx !== -1) {
          const [moved] = layout.splice(fromIdx, 1);
          layout.splice(toIdx, 0, moved);
          saveDashboardLayout(layout, context?.profileId);
          renderCustomDashboard(element, context);
        }
      });
    }
  };

  element.ondragenter = (e) => {
    if (!element._gsEditMode || (!element._gsDraggedId && !element._gsDraggedWidgetId)) return;
    const find = (sel) => (e.target.closest ? e.target.closest(sel) : findClosest(e.target, sel));
    const targetCard = find(".gs-widget-card");
    const targetId = targetCard ? (targetCard.getAttribute ? targetCard.getAttribute("data-instance-id") : targetCard.dataset?.instanceId) : null;
    if (targetCard && (element._gsDraggedWidgetId || (targetId && targetId !== element._gsDraggedId))) {
      if (targetCard.classList && targetCard.classList.add) targetCard.classList.add("gs-drag-over");
    }
  };

  element.ondragleave = (e) => {
    const find = (sel) => (e.target.closest ? e.target.closest(sel) : findClosest(e.target, sel));
    const targetCard = find(".gs-widget-card");
    if (targetCard && targetCard.classList && targetCard.classList.remove) {
      if (!e.relatedTarget || !targetCard.contains(e.relatedTarget)) {
        targetCard.classList.remove("gs-drag-over");
      }
    }
  };

  element.ondrop = (e) => {
    if (!element._gsEditMode) return;
    const find = (sel) => (e.target.closest ? e.target.closest(sel) : findClosest(e.target, sel));

    // A. Drop di un nuovo widget dalla galleria:
    const widgetIdToInsert = element._gsDraggedWidgetId || (e.dataTransfer && e.dataTransfer.getData && e.dataTransfer.getData("text/widget-id"));
    if (widgetIdToInsert) {
      if (e.preventDefault) e.preventDefault();
      const widget = root.GS.ui.widgets.get(widgetIdToInsert);
      const span = widget?.defaultSpan || 1;
      const layout = getDashboardLayout(context?.profileId);
      const newInstance = {
        instanceId: `w-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        widgetId: widgetIdToInsert,
        span,
      };

      const targetCard = find(".gs-widget-card");
      const targetId = targetCard ? (targetCard.getAttribute ? targetCard.getAttribute("data-instance-id") : targetCard.dataset?.instanceId) : null;
      const targetIdx = targetId ? layout.findIndex((it) => it.instanceId === targetId) : -1;

      if (targetIdx !== -1) {
        layout.splice(targetIdx, 0, newInstance);
      } else {
        layout.push(newInstance);
      }

      saveDashboardLayout(layout, context?.profileId);
      element._gsShowAddModal = false;
      element._gsDraggedWidgetId = null;
      renderCustomDashboard(element, context);
      return;
    }

    // B. Drop riordino scheda esistente
    if (!element._gsDraggedId) return;
    if (e.preventDefault) e.preventDefault();
    const targetCard = find(".gs-widget-card");
    const targetId = targetCard ? (targetCard.getAttribute ? targetCard.getAttribute("data-instance-id") : targetCard.dataset?.instanceId) : null;
    if (targetId && targetId !== element._gsDraggedId && targetId !== element._gsLastTargetId) {
      element._gsLastTargetId = targetId;
      const grid = element.querySelector ? element.querySelector(".gs-dashboard-grid") : element;
      flipAnimate(grid, () => {
        const layout = getDashboardLayout(context?.profileId);
        const fromIdx = layout.findIndex((it) => it.instanceId === element._gsDraggedId);
        const toIdx = layout.findIndex((it) => it.instanceId === targetId);
        if (fromIdx !== -1 && toIdx !== -1) {
          const [moved] = layout.splice(fromIdx, 1);
          layout.splice(toIdx, 0, moved);
          saveDashboardLayout(layout, context?.profileId);
          renderCustomDashboard(element, context);
        }
      });
    }
  };

  element.ondragend = () => {
    element._gsDraggedId = null;
    element._gsDraggedWidgetId = null;
    element._gsLastTargetId = null;
    const cards = element.querySelectorAll ? element.querySelectorAll(".gs-widget-card, .gs-gallery-card") : [];
    for (let i = 0; i < cards.length; i++) {
      if (cards[i].classList && cards[i].classList.remove) {
        cards[i].classList.remove("gs-dragging");
        cards[i].classList.remove("gs-drag-over");
      }
    }
    const backdrop = element.querySelector ? element.querySelector(".gs-gallery-backdrop") : null;
    if (backdrop && backdrop.classList && backdrop.classList.remove) {
      backdrop.classList.remove("gs-dragging-from-gallery");
    }
  };

  // Ridimensionamento interattivo libero tramite maniglia corner
  const handleResizeStart = (e) => {
    if (!element._gsEditMode) return;
    const handle = findClosest(e.target, ".gs-widget-resize-handle");
    if (!handle) return;
    if (e.button && e.button !== 0) return;
    if (e.preventDefault) e.preventDefault();
    if (e.stopPropagation) e.stopPropagation();

    const card = findClosest(handle, ".gs-widget-card");
    if (!card) return;
    const instanceId = card.getAttribute ? card.getAttribute("data-instance-id") : card.dataset.instanceId;
    const grid = (element.querySelector && element.querySelector(".gs-dashboard-grid")) || element;
    const gridRect = (grid.getBoundingClientRect && grid.getBoundingClientRect()) || { width: 1200, left: 0 };
    const cardRect = (card.getBoundingClientRect && card.getBoundingClientRect()) || { width: card.offsetWidth || 320, height: card.offsetHeight || 200, top: 0, left: 0 };

    const startX = e.clientX || 0;
    const startY = e.clientY || 0;
    const startWidth = cardRect.width || card.offsetWidth || 320;
    const startHeight = cardRect.height || card.offsetHeight || 200;
    const colWidth = Math.max(280, Math.floor(((gridRect.width || 1200) - 48) / 3));

    if (card.classList && card.classList.add) card.classList.add("gs-resizing");
    if (card.setAttribute) card.setAttribute("draggable", "false");

    let currentSpan = card.classList && card.classList.contains && card.classList.contains("span-full") ? "full" :
      (card.classList && card.classList.contains && card.classList.contains("span-3") ? 3 :
      (card.classList && card.classList.contains && card.classList.contains("span-2") ? 2 : 1));
    let currentHeight = startHeight;

    const onMove = (moveEvt) => {
      if (moveEvt.preventDefault) moveEvt.preventDefault();
      const clientX = moveEvt.clientX || 0;
      const clientY = moveEvt.clientY || 0;
      const dx = clientX - startX;
      const dy = clientY - startY;

      currentHeight = Math.max(140, Math.min(1400, Math.round(startHeight + dy)));
      if (card.style) card.style.minHeight = currentHeight + "px";

      const prospectiveWidth = Math.max(240, startWidth + dx);
      if (prospectiveWidth > (gridRect.width || 1200) * 0.75) {
        currentSpan = "full";
      } else if (prospectiveWidth > colWidth * 2.2) {
        currentSpan = 3;
      } else if (prospectiveWidth > colWidth * 1.2) {
        currentSpan = 2;
      } else {
        currentSpan = 1;
      }

      if (card.classList && card.classList.remove && card.classList.add) {
        card.classList.remove("span-1", "span-2", "span-3", "span-full");
        card.classList.add(currentSpan === "full" ? "span-full" : `span-${currentSpan}`);
      }
    };

    const onEnd = () => {
      if (typeof window !== "undefined") {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onEnd);
        window.removeEventListener("pointercancel", onEnd);
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onEnd);
      }
      if (card.classList && card.classList.remove) card.classList.remove("gs-resizing");
      if (card.setAttribute) card.setAttribute("draggable", "true");

      const layout = getDashboardLayout(context?.profileId);
      const index = layout.findIndex((item) => item.instanceId === instanceId);
      if (index !== -1) {
        layout[index].span = currentSpan;
        layout[index].height = currentHeight;
        saveDashboardLayout(layout, context?.profileId);
        renderCustomDashboard(element, context);
      }
    };

    if (typeof window !== "undefined") {
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onEnd);
      window.addEventListener("pointercancel", onEnd);
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onEnd);
    }
  };

  let lastResizeTime = 0;
  const guardedResizeStart = (e) => {
    const now = Date.now();
    if (now - lastResizeTime < 50) return;
    lastResizeTime = now;
    handleResizeStart(e);
  };
  element.onpointerdown = guardedResizeStart;
  element.onmousedown = guardedResizeStart;
}

function renderCustomDashboard(element, context = {}) {
  if (!element) return;
  const profileId = context.profileId || null;
  const isEditing = Boolean(element._gsEditMode);
  const layout = getDashboardLayout(profileId);

  // Intestazione con pulsante modifica
  const headerHtml = `<header class="gs-dashboard-header">
    <div>
      <h1 class="gs-dashboard-title">${t("g.dash.title")}</h1>
      <p class="gs-dashboard-subtitle">${t("g.dash.subtitle")}</p>
    </div>
    <button class="btn gs-edit-toggle" type="button" data-dashboard-toggle-edit>
      ${isEditing ? `✓ ${t("g.dash.edit.done")}` : `✏️ ${t("g.dash.edit.customize")}`}
    </button>
  </header>`;

  // Barra di modifica con aggiunta e ripristino
  const editBarHtml = isEditing ? `<div class="gs-edit-bar">
    <button class="btn" type="button" data-dashboard-add-widget>＋ ${t("g.dash.edit.add_widget")}</button>
    <button class="btn" type="button" data-dashboard-reset>${t("g.dash.edit.reset")}</button>
  </div>` : "";

  // Schede dei widget
  const cardsHtml = layout.map((item) => {
    const widget = root.GS.ui.widgets.get(item.widgetId);
    const span = item.span === "full" ? "full" : (Number(item.span) || 1);
    const spanClass = span === "full" ? "span-full" : (span === 3 ? "span-3" : (span === 2 ? "span-2" : "span-1"));
    const heightClass = typeof item.height === "string" && item.height !== "auto" ? ` height-${item.height}` : "";
    const styleAttr = typeof item.height === "number" ? ` style="min-height:${item.height}px;"` : "";

    const controlsHtml = isEditing ? `<div class="gs-widget-controls" aria-label="${esc(t("g.dash.edit.controls"))}">
      <span class="gs-drag-handle" title="${esc(t("g.dash.edit.drag_hint"))}" aria-hidden="true">⋮⋮</span>
      <button class="btn gs-ctrl-btn" type="button" data-widget-move="prev" title="${esc(t("g.dash.edit.move_prev"))}" aria-label="${esc(t("g.dash.edit.move_prev"))}">‹</button>
      <button class="btn gs-ctrl-btn" type="button" data-widget-move="next" title="${esc(t("g.dash.edit.move_next"))}" aria-label="${esc(t("g.dash.edit.move_next"))}">›</button>
      <div class="gs-ctrl-group" title="${esc(t("g.dash.edit.width"))}">
        <button class="btn gs-ctrl-btn${span === 1 ? " active" : ""}" type="button" data-widget-span="1" title="${esc(t("g.dash.edit.width1"))}">1x</button>
        <button class="btn gs-ctrl-btn${span === 2 ? " active" : ""}" type="button" data-widget-span="2" title="${esc(t("g.dash.edit.width2"))}">2x</button>
        <button class="btn gs-ctrl-btn${span === 3 ? " active" : ""}" type="button" data-widget-span="3" title="${esc(t("g.dash.edit.width3"))}">3x</button>
        <button class="btn gs-ctrl-btn${span === "full" ? " active" : ""}" type="button" data-widget-span="full" title="${esc(t("g.dash.edit.width_full"))}">Full</button>
      </div>
      <div class="gs-ctrl-group" title="${esc(t("g.dash.edit.height"))}">
        <button class="btn gs-ctrl-btn${item.height === "sm" ? " active" : ""}" type="button" data-widget-height="sm" title="${esc(t("g.dash.edit.h_sm"))}">S</button>
        <button class="btn gs-ctrl-btn${item.height === "md" ? " active" : ""}" type="button" data-widget-height="md" title="${esc(t("g.dash.edit.h_md"))}">M</button>
        <button class="btn gs-ctrl-btn${item.height === "lg" ? " active" : ""}" type="button" data-widget-height="lg" title="${esc(t("g.dash.edit.h_lg"))}">L</button>
        <button class="btn gs-ctrl-btn${!item.height || item.height === "auto" ? " active" : ""}" type="button" data-widget-height="auto" title="${esc(t("g.dash.edit.h_auto"))}">Auto</button>
      </div>
      <button class="btn gs-ctrl-btn" type="button" data-widget-remove title="${esc(t("g.dash.edit.remove"))}" aria-label="${esc(t("g.dash.edit.remove"))}">✕</button>
    </div>` : "";

    let contentHtml = "";
    if (!widget) {
      // Gestione widget non installati o sconosciuti senza errori
      contentHtml = `<div class="gs-widget-unknown"><p class="muted">${t("g.dash.widget.unknown", { id: esc(item.widgetId) })}</p></div>`;
    } else {
      try {
        contentHtml = widget.render(context, item);
      } catch (err) {
        contentHtml = `<div class="gs-widget-error"><p class="muted">${t("g.dash.widget.error", { msg: esc(err?.message || String(err)) })}</p></div>`;
      }
    }

    const isDragging = isEditing && element._gsDraggedId && item.instanceId === element._gsDraggedId;
    return `<div class="card gs-widget-card ${spanClass}${heightClass}${isDragging ? " gs-dragging" : ""}" data-instance-id="${esc(item.instanceId)}"${styleAttr}${isEditing ? ' draggable="true"' : ""}>
      ${controlsHtml}
      <div class="gs-widget-body">
        ${contentHtml}
      </div>
      ${isEditing ? `<span class="gs-widget-resize-handle" title="${esc(t("g.dash.edit.resize_hint"))}" aria-label="${esc(t("g.dash.edit.resize"))}">⤡</span>` : ""}
    </div>`;
  }).join("");

  const emptyHtml = `<div class="gs-widget-empty" style="grid-column: 1 / -1; padding: 24px; text-align: center;">
    <p class="muted">${t("g.dash.empty")}</p>
    ${!isEditing ? '<button class="btn" type="button" data-dashboard-toggle-edit>✏️ ' + t("g.dash.edit.customize") + '</button>' : ''}
  </div>`;

  const modalHtml = element._gsShowAddModal ? renderAddWidgetModal(element._gsAddCategory || "all", context) : "";

  element.innerHTML = `<div class="gs-dashboard${isEditing ? " editing gs-dashboard--editing" : ""}">
    ${headerHtml}
    ${editBarHtml}
    <div class="gs-dashboard-grid">
      ${cardsHtml || emptyHtml}
    </div>
    ${modalHtml}
  </div>`;

  setupDashboardEvents(element, context);
}

root.getDashboardLayout = getDashboardLayout;
root.saveDashboardLayout = saveDashboardLayout;
root.getDefaultDashboardLayout = getDefaultDashboardLayout;
root.resetDashboardLayout = resetDashboardLayout;
root.normalizeDashboardLayout = normalizeDashboardLayout;
root.renderCustomDashboard = renderCustomDashboard;
root.flipAnimate = flipAnimate;
if (root.GS) {
  root.GS.renderCustomDashboard = renderCustomDashboard;
  root.GS.ui = root.GS.ui || {};
  root.GS.ui.registerWidget = registerWidget;
  root.GS.flipAnimate = flipAnimate;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    registerWidget,
    getDashboardLayout,
    saveDashboardLayout,
    getDefaultDashboardLayout,
    resetDashboardLayout,
    normalizeDashboardLayout,
    renderCustomDashboard,
    flipAnimate,
    builtInWidgets,
    rerollRoulette,
    esc,
    hue,
    platName,
  };
}
})();
