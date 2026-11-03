"use strict";
/* Pozzo Launcher - nucleo condiviso tra interfaccia desktop e Big Picture.
 *
 * Espone window.GS: utilita', chiamate API, decodifica della libreria e il MODELLO DI ESTENSIONI.
 * I plugin (plugins/<id>/frontend.js) ricevono GS e si agganciano a punti stabili invece di
 * modificare la pagina, cosi' sopravvivono agli aggiornamenti dell'interfaccia:
 *
 *   export default function (gs) {
 *     gs.addGameAction({ id: "hltb", label: "Quanto dura?", run: (game) => ... });
 *     gs.addDetailSection({ id: "note", title: "Note", render: async (game) => "<p>...</p>" });
 *     gs.addTileBadge({ id: "new", render: (g) => g.year >= 2024 ? "NUOVO" : null });
 *     gs.addSidebarItem({ id: "stats", label: "Statistiche", icon: "📊", view: "stats" });
 *     gs.registerView("stats", { title: "Statistiche", render: async (el) => { el.innerHTML = "..." } });
 *     gs.on("gameStarted", (info) => ...);
 *   }
 */

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const collator = new Intl.Collator("it", { sensitivity: "base", numeric: true });
const store = {
  get(k, d) { try { const v = localStorage.getItem("gs." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("gs." + k, JSON.stringify(v)); } catch { /* storage non disponibile */ } },
};
/* ui-prefs:start - aspetto (zoom, densita', tema utente, salvaschermo di Big Picture). Funzioni pure: tests/test_ui_prefs.js.
 * Le preferenze stanno in localStorage "gs.ui" (valgono per il dispositivo, come gs.motion): il server non ha un campo
 * di profilo per questi valori e /api/profile/settings rifiuta le chiavi che non conosce. */
const GSUi = (() => {
  const ZOOMS = [90, 95, 100, 105, 110, 115, 120, 125];
  const DENSITIES = ["comfortable", "compact"];
  const IDLE = [0, 1, 2, 3, 5, 10, 15, 30]; // minuti prima del salvaschermo; 0 = disattivato
  const TOKENS = ["bg", "bg-2", "bg-3", "panel", "line", "text", "muted", "accent", "accent-2", "fav"];
  const HEX = /^#[0-9a-f]{6}$/i;
  const THEME_KEYS = ["format", "version", "name", "tokens"];
  const MAX_SLIDES = 60;

  const prefs = (raw) => {
    const o = raw && typeof raw === "object" ? raw : {};
    return { zoom: ZOOMS.includes(o.zoom) ? o.zoom : 100, density: DENSITIES.includes(o.density) ? o.density : "comfortable",
      idle: IDLE.includes(o.idle) ? o.idle : 3, coverAccent: typeof o.coverAccent === "boolean" ? o.coverAccent : true };
  };

  /** Colore CSS ("#abc", "#aabbcc", "rgb(a, b, c)") -> "#aabbcc"; null se non e' un colore semplice. */
  const toHex = (s) => {
    s = String(s || "").trim().toLowerCase();
    let m = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/.exec(s);
    if (m) return "#" + m[1] + m[1] + m[2] + m[2] + m[3] + m[3];
    if (HEX.test(s)) return s;
    m = /^rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})/.exec(s);
    return m && m.slice(1, 4).every((v) => +v <= 255) ? "#" + m.slice(1, 4).map((v) => (+v).toString(16).padStart(2, "0")).join("") : null;
  };
  const hexToHsl = (hex) => {
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min, l = (max + min) / 2;
    let h = 0;
    if (d) h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [Math.round((h * 60 + 360) % 360), Math.round(d ? d / (1 - Math.abs(2 * l - 1)) * 100 : 0), Math.round(l * 100)];
  };
  const hslToHex = (h, s, l) => {
    s /= 100; l /= 100;
    const a = s * Math.min(l, 1 - l);
    const f = (n) => { const k = (n + h / 30) % 12; return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))); };
    return "#" + [f(0), f(8), f(4)].map((v) => v.toString(16).padStart(2, "0")).join("");
  };
  /** Luminanza relativa WCAG 2.x. */
  const luminance = (hex) => {
    const [r, g, b] = [1, 3, 5].map((i) => { const c = parseInt(hex.slice(i, i + 2), 16) / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const contrastRatio = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
  // testo normale AA = 4.5, elementi grafici/secondari = 3
  const CHECKS = [["text", "bg", 4.5], ["text", "panel", 4.5], ["muted", "bg", 3], ["accent", "bg", 3]];
  const contrastReport = (tokens) => CHECKS.map(([fg, bg, min]) => {
    const ratio = Math.round(contrastRatio(tokens[fg], tokens[bg]) * 100) / 100;
    return { fg, bg, min, ratio, ok: ratio >= min };
  });

  /** Valida un tema utente: solo token noti con colori #rrggbb, nessun URL o CSS libero. Lancia Error in italiano. */
  const checkTheme = (o) => {
    if (!o || typeof o !== "object" || Array.isArray(o)) throw new Error("Tema non valido");
    if (Object.keys(o).some((k) => !THEME_KEYS.includes(k))) throw new Error("Il tema contiene campi sconosciuti");
    if (o.format !== "pozzo-theme" || o.version !== 1) throw new Error("Formato o versione del tema non supportati");
    const name = typeof o.name === "string" ? o.name.trim() : "";
    if (!name || name.length > 40 || /[\u0000-\u001f<>]/.test(name)) throw new Error("Nome del tema non valido");
    const t = o.tokens;
    if (!t || typeof t !== "object" || Array.isArray(t)) throw new Error("Colori mancanti");
    if (Object.keys(t).some((k) => !TOKENS.includes(k))) throw new Error("Il tema contiene colori sconosciuti");
    const tokens = {};
    for (const k of TOKENS) {
      if (typeof t[k] !== "string" || !HEX.test(t[k])) throw new Error(`Colore non valido: ${k}`);
      tokens[k] = t[k].toLowerCase();
    }
    return { name, tokens };
  };
  const parseTheme = (text) => {
    if (typeof text !== "string" || text.length > 4096) throw new Error("File non valido o troppo grande");
    let o;
    try { o = JSON.parse(text); } catch { throw new Error("Il file non e' JSON valido"); }
    return checkTheme(o);
  };
  const serializeTheme = (name, tokens) => JSON.stringify({ format: "pozzo-theme", version: 1, name, tokens }, null, 2);
  const themeCss = (tokens) => `html:root{${TOKENS.map((k) => `--${k}:${tokens[k]}`).join(";")}}`;

  /** Stile con id fisso nell'<head>: css vuoto lo toglie. Ritorna l'elemento (o null). */
  const setStyle = (doc, id, css) => {
    const old = doc.getElementById(id);
    if (old) old.remove();
    if (!css) return null;
    const el = doc.createElement("style");
    el.id = id; el.textContent = css;
    doc.head.appendChild(el);
    return el;
  };
  const saved = () => store.get("ui", null);
  const savedTheme = () => { // un valore rovinato o manomesso torna "nessun tema utente"
    const o = store.get("userTheme", null);
    if (!o || typeof o !== "object") return null;
    try { return { enabled: o.enabled === true, ...checkTheme({ format: "pozzo-theme", version: 1, name: o.name, tokens: o.tokens }) }; } catch { return null; }
  };
  const applyPrefs = (doc, p) => {
    const root = doc.documentElement;
    p = prefs(p);
    // 100% = nessun attributo: il layout in pixel resta identico a prima
    if (p.zoom === 100) delete root.dataset.uiZoom; else root.dataset.uiZoom = String(p.zoom);
    root.style.setProperty("--ui-zoom", String(p.zoom / 100));
    root.dataset.uiDensity = p.density;
    return p;
  };
  const applyTheme = (doc) => { const t = savedTheme(); return setStyle(doc, "gs-user-theme", t && t.enabled ? themeCss(t.tokens) : ""); };

  /** Foto da mostrare nel salvaschermo: solo giochi con copertina, ordine casuale, al massimo MAX_SLIDES. */
  const pickSlides = (games, rnd = Math.random, limit = MAX_SLIDES) => {
    const a = games.filter((g) => g && g.cover);
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a.slice(0, Math.min(limit, MAX_SLIDES));
  };
  /** "full" = dissolvenza + zoom lento, "fade" = solo dissolvenza, "none" = cambio immediato (data-motion di motion.js). */
  const attractMotion = (dataMotion, systemReduced) => (dataMotion === "off" ? "none" : dataMotion === "reduced" ? "fade"
    : dataMotion === "normal" ? "full" : systemReduced ? "fade" : "full");

  /** Inattivita': env = {minutes(), canRun(), start(), stop(), setT, clearT}. activity() torna true se ha chiuso il salvaschermo. */
  const createIdle = (env) => {
    let timer = null, active = false;
    const arm = () => {
      env.clearT(timer); timer = null;
      const m = env.minutes();
      if (m > 0) timer = env.setT(() => { timer = null; if (env.canRun()) { active = true; env.start(); } else arm(); }, m * 60000);
    };
    const close = () => { if (!active) return false; active = false; env.stop(); return true; };
    return { arm, close, isActive: () => active, activity() { const was = close(); arm(); return was; } };
  };
  return { ZOOMS, DENSITIES, IDLE, TOKENS, CHECKS, prefs, toHex, hexToHsl, hslToHex, contrastRatio, contrastReport, parseTheme, checkTheme,
    serializeTheme, themeCss, setStyle, saved, savedTheme, applyPrefs, applyTheme, pickSlides, attractMotion, createIdle };
})();
window.GSUi = GSUi;
// applicati subito (core.js e' il primo script): zoom, densita' e tema utente prima che la pagina si disegni
GSUi.applyPrefs(document, GSUi.saved());
GSUi.applyTheme(document);
/* ui-prefs:end */

const SHORT = { megadrive: "MD", mastersystem: "SMS", gamegear: "GG", psx: "PS1", ps2: "PS2", ps3: "PS3", psp: "PSP",
  psvita: "VITA", gamecube: "GC", gc: "GC", wiiu: "WII U", switch: "SWITCH", xbox360: "X360", dreamcast: "DC",
  saturn: "SAT", segacd: "MCD", sega32x: "32X", pcengine: "PCE", nds: "DS", "3ds": "3DS", n64: "N64", windows: "PC" };
const STORE_SHORT = { steam: "STEAM", epic: "EPIC", gog: "GOG", amazon: "AMAZON", battlenet: "BATTLE.NET", riot: "RIOT", xbox: "XBOX",
  minecraft: "MINECRAFT", ports: "APP", manual: "PC" };
const STORE_ICON = { steam: "◉", epic: "◆", gog: "◎", amazon: "◗", battlenet: "✦", riot: "✪", xbox: "⬢", minecraft: "▣", manual: "⌂" };

function fmtSize(n) {
  if (!n) return "";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i === 0 ? n.toFixed(0) : n < 10 ? n.toFixed(2) : n.toFixed(1)).replace(".", ",") + " " + u[i];
}

/* ---- Store: giochi installabili da tutti gli store importati (posseduti su Steam/Epic/GOG/… non
 * installati + giochi delle pagine "Store online" delle console). Esclusi i giochi gia' presenti in
 * un'altra versione installata/sul disco. */
const GB = 1024 ** 3;
const SHOP_SIZES = [
  { id: "", label: "Qualsiasi dimensione", ok: () => true },
  { id: "s", label: "Meno di 1 GB", ok: (g) => g.size > 0 && g.size < GB },
  { id: "m", label: "1 – 10 GB", ok: (g) => g.size >= GB && g.size < 10 * GB },
  { id: "l", label: "10 – 50 GB", ok: (g) => g.size >= 10 * GB && g.size < 50 * GB },
  { id: "xl", label: "Oltre 50 GB", ok: (g) => g.size >= 50 * GB },
  { id: "u", label: "Dimensione sconosciuta", ok: (g) => !g.size },
];
const SHOP_SORTS = [
  { id: "title", label: "Titolo A–Z", cmp: (a, b) => collator.compare(a.sort, b.sort) },
  { id: "-rating", label: "Valutazione", cmp: (a, b) => (b.rating ?? -1) - (a.rating ?? -1) || collator.compare(a.sort, b.sort) },
  { id: "-year", label: "Più recenti", cmp: (a, b) => (b.year || 0) - (a.year || 0) || collator.compare(a.sort, b.sort) },
  { id: "year", label: "Più vecchi", cmp: (a, b) => (a.year || 9999) - (b.year || 9999) || collator.compare(a.sort, b.sort) },
  { id: "size", label: "Più leggeri", cmp: (a, b) => (a.size || Infinity) - (b.size || Infinity) || collator.compare(a.sort, b.sort) },
  { id: "-size", label: "Più pesanti", cmp: (a, b) => (b.size || 0) - (a.size || 0) || collator.compare(a.sort, b.sort) },
  { id: "store", label: "Store", cmp: (a, b) => collator.compare(shopSource(a), shopSource(b)) || collator.compare(a.sort, b.sort) },
];
const shopSource = (g) => (g.store === "online" ? "online:" + g.platform : g.store);

function shopGames(games) {
  const owned = new Set(games.filter((g) => g.installed).map((g) => g.gi));
  return games.filter((g) => g.store && g.store !== "manual" && !g.installed && !owned.has(g.gi) && !g.grp.hidden);
}

/** Origini presenti (per il filtro): store PC e pagine online delle console. */
function shopSources(items, stores, platName) {
  const n = new Map();
  for (const g of items) n.set(shopSource(g), (n.get(shopSource(g)) || 0) + 1);
  const pc = stores.filter((s) => n.has(s.id)).map((s) => ({ id: s.id, label: s.name, n: n.get(s.id) }));
  const on = [...n.keys()].filter((k) => k.startsWith("online:"))
    .map((k) => ({ id: k, label: `Online · ${platName(k.slice(7))}`, n: n.get(k) }))
    .sort((a, b) => collator.compare(a.label, b.label));
  return pc.concat(on);
}

function shopFilter(items, f) {
  const size = SHOP_SIZES.find((s) => s.id === (f.size || "")) || SHOP_SIZES[0];
  let it = items.filter((g) => g.content !== "update" && (!f.hideDlc || g.content !== "dlc")
    && (!f.src || shopSource(g) === f.src) && (!f.plat || g.platform === f.plat) && size.ok(g));
  // una sola copia per gioco (la principale se rispetta i filtri)
  const one = new Map();
  for (const g of it) if (!one.has(g.gi) || g.id === g.grp.primary) one.set(g.gi, g);
  it = [...one.values()];
  if (f.q) {
    const toks = fold(f.q).split(/\s+/).filter(Boolean);
    it = it.filter((g) => toks.every((t) => g.q.includes(t)));
  }
  return it.sort((SHOP_SORTS.find((s) => s.id === f.sort) || SHOP_SORTS[0]).cmp);
}

/* ---- Scopri: filtri "intelligenti" su valutazioni, voti, anni, giocatori (validi per ogni vista) */
const THIS_YEAR = new Date().getFullYear();
const byScore = (f) => (a, b) => (f(b) ?? -1) - (f(a) ?? -1) || collator.compare(a.sort, b.sort);
const best = (g) => Math.max(g.critics ?? 0, g.votes >= 20 ? g.rating ?? 0 : 0);
const PRESETS = [
  { id: "", label: "Tutti i giochi" },
  { id: "critics", label: "🏆 Migliori per la critica", hint: "voto Metacritic (RAWG) o della critica (IGDB) almeno 75",
    ok: (g) => g.critics >= 0.75, cmp: byScore((g) => g.critics), score: "critics" },
  { id: "loved", label: "❤️ Più amati dal pubblico", hint: "voto dei giocatori almeno 75% con almeno 20 voti",
    ok: (g) => g.rating >= 0.75 && g.votes >= 20, cmp: byScore((g) => g.rating), score: "rating" },
  { id: "top", label: "⭐ Capolavori", hint: "critica almeno 90 oppure pubblico almeno 85% con almeno 50 voti",
    ok: (g) => g.critics >= 0.9 || (g.rating >= 0.85 && g.votes >= 50), cmp: byScore(best), score: "best" },
  { id: "popular", label: "🔥 Più votati", hint: "ordinati per numero di voti dei giocatori",
    ok: (g) => g.votes > 0, cmp: byScore((g) => g.votes), score: "votes" },
  { id: "gems", label: "💎 Gemme nascoste", hint: "voto alto (almeno 80%) ma pochi voti (da 5 a 200)",
    ok: (g) => g.rating >= 0.8 && g.votes >= 5 && g.votes < 200, cmp: byScore((g) => g.rating), score: "rating" },
  { id: "classics", label: "🕹 Grandi classici", hint: "usciti prima del 2000 con voto almeno 75%",
    ok: (g) => g.year && g.year < 2000 && Math.max(g.rating ?? 0, g.critics ?? 0) >= 0.75, cmp: byScore((g) => Math.max(g.rating ?? 0, g.critics ?? 0)), score: "best" },
  { id: "new", label: "🆕 Usciti negli ultimi 3 anni", ok: (g) => g.year >= THIS_YEAR - 3,
    cmp: (a, b) => (b.year || 0) - (a.year || 0) || collator.compare(a.sort, b.sort) },
  { id: "multi", label: "👥 Multigiocatore in locale", hint: "almeno 2 giocatori sullo stesso schermo", ok: (g) => g.players >= 2,
    cmp: byScore((g) => g.rating) },
  { id: "short", label: "⏱ Brevi (meno di 5 ore)", hint: "storia principale entro 5 ore (HowLongToBeat)",
    ok: (g) => g.hltb != null && g.hltb <= 5, cmp: (a, b) => a.hltb - b.hltb || collator.compare(a.sort, b.sort), score: "hltb" },
  { id: "long", label: "🏔 Lunghi (oltre 40 ore)", hint: "storia principale di almeno 40 ore (HowLongToBeat)",
    ok: (g) => g.hltb >= 40, cmp: (a, b) => b.hltb - a.hltb || collator.compare(a.sort, b.sort), score: "hltb" },
  { id: "unplayed", label: "⏳ Mai giocati", ok: (g) => !g.grp.last && !g.grp.playtime, cmp: byScore((g) => g.rating) },
  { id: "worst", label: "👎 Peggio valutati", hint: "voto sotto il 50% con almeno 10 voti",
    ok: (g) => g.rating != null && g.rating < 0.5 && g.votes >= 10, cmp: (a, b) => a.rating - b.rating || collator.compare(a.sort, b.sort), score: "rating" },
  { id: "unrated", label: "❔ Senza valutazione", ok: (g) => g.rating == null && g.critics == null },
];

/** Applica preset, genere e decennio; restituisce null come ordine se il preset non ne impone uno. */
function discover(items, f = {}) {
  const p = PRESETS.find((x) => x.id === (f.preset || "")) || PRESETS[0];
  let it = p.ok ? items.filter(p.ok) : items;
  if (f.genre) it = it.filter((g) => fold(g.genres).split(/\s*,\s*/).includes(f.genre));
  if (f.decade) it = it.filter((g) => g.year && Math.floor(g.year / 10) * 10 === +f.decade);
  return { items: it, cmp: p.cmp || null, preset: p };
}

/** Generi piu' comuni (normalizzati), per il filtro. */
function genreList(games, max = 40) {
  const n = new Map(), label = new Map();
  for (const g of games) {
    for (const x of String(g.genres || "").split(/\s*,\s*/)) {
      if (!x) continue;
      const k = fold(x);
      n.set(k, (n.get(k) || 0) + 1);
      if (!label.has(k)) label.set(k, x);
    }
  }
  return [...n.entries()].filter(([, c]) => c >= 3).sort((a, b) => b[1] - a[1]).slice(0, max)
    .map(([k, c]) => ({ id: k, label: label.get(k), n: c })).sort((a, b) => collator.compare(a.label, b.label));
}

function decadeList(games) {
  const s = new Set(games.filter((g) => g.year > 1950).map((g) => Math.floor(g.year / 10) * 10));
  return [...s].sort();
}

/** Testo del punteggio da mostrare sotto la copertina per il preset attivo. */
function scoreText(g, kind) {
  const pct = (v) => Math.round(v * 100);
  if (kind === "critics" && g.critics != null) return `Critica ${pct(g.critics)}`;
  if (kind === "rating" && g.rating != null) return `★ ${pct(g.rating)}%${g.votes ? ` (${g.votes.toLocaleString("it")})` : ""}`;
  if (kind === "votes") return `${g.votes.toLocaleString("it")} voti`;
  if (kind === "hltb") return g.hltb != null ? `⏱ ${fmtHours(g.hltb)}` : "";
  if (kind === "best") return g.critics != null ? `Critica ${pct(g.critics)}` : g.rating != null ? `★ ${pct(g.rating)}%` : "";
  return "";
}

/* ---- stato del gioco */
const STATUS = {
  backlog: { label: "Da giocare", icon: "📋" }, playing: { label: "In corso", icon: "▶" },
  done: { label: "Finito", icon: "✔" }, dropped: { label: "Abbandonato", icon: "✖" },
};
const fmtHours = (h) => (h == null ? "" : h < 1 ? `${Math.round(h * 60)} min` : `${String(Math.round(h * 10) / 10).replace(".", ",")} h`);

/* ---- collezioni intelligenti: regole salvate, valutate sui dati della libreria */
const SMART_RULES = ["platforms", "stores", "genres", "status", "minRating", "minCritics", "minPlayers", "yearFrom", "yearTo",
  "maxHours", "minHours", "installed", "favorites", "unplayed"];

function smartMatch(g, r = {}) {
  if (g.grp.hidden || (g.store === "online" && !r.includeOnline)) return false;
  if (r.platforms?.length && !r.platforms.includes(g.platform)) return false;
  if (r.stores?.length && !r.stores.includes(g.store || "rom")) return false;
  if (r.genres?.length) {  // generi normalizzati (Azione, Gioco di ruolo...), uguali tra fonti e lingue
    const gs = typeof RECO !== "undefined" ? RECO.canonGenres(g.genres) : [];
    if (!r.genres.some((x) => gs.includes(x))) return false;
  }
  if (r.status?.length && !r.status.includes(g.grp.status || "none")) return false;
  if (r.minRating && !(g.rating >= r.minRating / 100)) return false;
  if (r.minCritics && !(g.critics >= r.minCritics / 100)) return false;
  if (r.minPlayers && !(g.players >= r.minPlayers)) return false;
  if (r.yearFrom && !(g.year >= r.yearFrom)) return false;
  if (r.yearTo && !(g.year && g.year <= r.yearTo)) return false;
  if (r.maxHours && !(g.hltb != null && g.hltb <= r.maxHours)) return false;
  if (r.minHours && !(g.hltb >= r.minHours)) return false;
  if (r.installed && !(!g.store || g.installed)) return false;
  if (r.favorites && !g.grp.favorite) return false;
  if (r.unplayed && (g.grp.last || g.grp.playtime || g.splay)) return false;
  return true;
}

/** Giochi di una collezione intelligente (una versione per gioco). */
function smartGames(games, rules) {
  return games.filter((g) => g.id === g.grp.primary && smartMatch(g, rules));
}

/** Ogni link web (data-open o <a href="http…">) si apre nel browser di sistema, in una nuova scheda: nell'app un link normale
 *  porterebbe via la pagina o finirebbe sulla home. In cattura, cosi' vale anche dove manca un gestore proprio. */
document.addEventListener("click", (e) => {
  const el = e.target.closest?.("[data-open], a[href^='http']");
  const url = el && (el.dataset.open || el.getAttribute("href"));
  if (!url || !/^https?:\/\//i.test(url)) return;
  e.preventDefault(); e.stopPropagation();
  api("/api/open", { body: { url } }).catch((err) => typeof toast === "function" && toast(err.message, true));
}, true);

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: { "Content-Type": "application/json" } };
  if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.method = opts.method || "POST"; }
  const r = await fetch(path, init);
  if (!r.ok) {
    let m = r.statusText;
    try { m = (await r.json()).detail || m; } catch { /* risposta non JSON */ }
    throw new Error(m);
  }
  return r.json();
}

/** Decodifica la risposta compatta di /api/library in oggetti comodi da usare. */
function decodeLibrary(lib) {
  const plats = new Map(lib.platforms.map((p) => [p.id, p]));
  const colls = lib.collections.map((c, i) => ({ ...c, idx: i }));
  const groups = lib.groups.rows.map((r) => ({ primary: r[0], favorite: r[1], hidden: r[2], last: r[3], playtime: r[4],
    plays: r[5], colls: r[6], versions: r[7], status: r[8] || "" }));
  // JSON.parse crea una stringa per ogni valore: console, sviluppatori, generi... ripetuti in 150.000 giochi
  // diventano una copia sola (~12 MB in meno)
  const pool = new Map();
  const one = (s) => { const v = pool.get(s); if (v !== undefined) return v; pool.set(s, s); return s; };
  const games = lib.games.rows.map((r) => {
    const g = { id: r[0], title: r[1], sort: r[2], platform: one(r[3]), year: r[4], cover: r[5], gi: r[6], rating: r[7],
      dev: one(r[8]), genres: one(r[9]), found: r[10], region: one(r[11]), store: one(r[12]) || null, installed: r[13],
      size: r[14] || 0, votes: r[15] || 0, critics: r[16] ?? null, players: r[17] || 0, splay: r[18] || 0,
      hltb: r[19] ?? null, content: one(r[20]) || "game" };
    g.grp = groups[g.gi];
    g.q = fold(`${g.title} ${g.dev} ${plats.get(g.platform)?.name || ""} ${g.platform} ${g.store || ""}`);
    return g;
  });
  return { plats, colls, collBySlug: new Map(colls.map((c) => [c.slug, c])), groups, games,
    byId: new Map(games.map((g) => [g.id, g])), stores: lib.stores || [], builtAt: lib.built_at, smart: lib.smart || [] };
}

/* ------------------------------------------------------------------ estensioni */
const GS = (() => {
  const handlers = new Map();
  const experiences = new Map();
  experiences.set("catalog", { id: "catalog", name: "Catalogo", description: "Interfaccia classica con navigazione laterale.",
    nav: "sidebar", home: null, card: null, detail: "panel", onFocus: null });
  const ui = { gameActions: [], detailSections: [], tileBadges: [], sidebarItems: [], views: new Map(), settingsTabs: [] };
  const add = (list) => (item) => {
    if (!item || !item.id) throw new Error("serve un id");
    const i = list.findIndex((x) => x.id === item.id);
    if (i >= 0) list[i] = item; else list.push(item);
    GS.emit("uiChanged", { kind: list });
    return item;
  };
  const GS = {
    apiVersion: 1,
    mode: document.documentElement.dataset.mode || "desktop",
    _loadingExperience: null,
    experiences,
    experience: { id: "catalog", name: "Catalogo", description: "Interfaccia classica con navigazione laterale.",
      nav: "sidebar", home: null, card: null, detail: "panel", onFocus: null },
    api, esc, fold, store, ui, fmtSize,
    registerExperience(experience) {
      const navs = ["sidebar", "top", "none"], details = ["modal", "page", "panel"];
      if (!experience || !/^[a-z][a-z0-9_-]*$/.test(experience.id || "")
          || (GS._loadingExperience && experience.id !== GS._loadingExperience)
          || typeof experience.name !== "string" || !navs.includes(experience.nav)
          || !details.includes(experience.detail)
          || (experience.home != null && typeof experience.home !== "function")
          || (experience.card != null && typeof experience.card !== "function")
          || (experience.onFocus != null && typeof experience.onFocus !== "function")) {
        throw new Error("Contratto esperienza non valido");
      }
      const registered = {
        id: experience.id, name: experience.name, description: String(experience.description || ""),
        nav: experience.nav, home: experience.home || null, card: experience.card || null,
        detail: experience.detail, onFocus: experience.onFocus || null,
      };
      experiences.set(registered.id, registered);
      return registered;
    },
    on(ev, fn) { if (!handlers.has(ev)) handlers.set(ev, new Set()); handlers.get(ev).add(fn); return () => handlers.get(ev).delete(fn); },
    emit(ev, data) { for (const fn of handlers.get(ev) || []) { try { fn(data); } catch (e) { console.error(`[GS] ${ev}:`, e); } } },
    addGameAction: add(ui.gameActions), // {id, label, icon?, when?(game), run(game)}
    addDetailSection: add(ui.detailSections), // {id, title, render(game) -> html|Element|Promise}
    addTileBadge: add(ui.tileBadges), // {id, render(game) -> testo|null}
    addSidebarItem: add(ui.sidebarItems), // {id, label, icon?, view?, onClick?}
    addSettingsTab: add(ui.settingsTabs), // {id, label, category?, render(el)}
    registerView(id, view) { ui.views.set(id, view); GS.emit("uiChanged", { kind: "views" }); }, // {title, render(el)}
    // forniti dall'interfaccia attiva (desktop o Big Picture)
    toast: (m) => console.log(m),
    openGame: () => {},
    library: () => null,
    currentGame: () => null,
    plugins: [],
  };
  return GS;
})();
window.GS = GS;

/** Mostra la finestra nativa (una volta sola: le chiamate successive non cambiano nulla) con la barra
 *  del titolo e il bordo del colore di sfondo del tema. Nel browser non fa nulla. */
function showWindow() {
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  const send = () => window.pywebview?.api?.window_ready?.(bg);
  if (window.pywebview?.api) send(); else window.addEventListener("pywebviewready", send, { once: true });
}

/** Applica il tema attivo e carica i plugin abilitati. */
async function loadExtensions() {
  let ext;
  try { ext = await api("/api/extensions"); } catch (e) {
    console.warn("estensioni non disponibili", e);
    showWindow();  // senza estensioni si mostra lo stesso, col tema predefinito
    return;
  }
  const mode = GS.mode;
  document.querySelectorAll("link[data-ext]").forEach((l) => l.remove());
  if (mode === "desktop") {
    GS.experienceErrors = GS.experienceErrors || {};
    const loadExperience = async (experience) => {
      if (!experience.available || !experience.script) {
        if (experience.error) GS.experienceErrors[experience.id] = experience.error;
        return;
      }
      try {
        GS._loadingExperience = experience.id;
        await import(experience.script);
        if (!GS.experiences.has(experience.id)) throw new Error("Lo script non ha registrato l'esperienza");
      } catch (e) {
        GS.experienceErrors[experience.id] = `${e.name}: ${e.message}`;
        console.warn(`Esperienza ${experience.id}:`, e);
      } finally {
        GS._loadingExperience = null;
      }
    };
    // Solo l'esperienza attiva blocca l'avvio; le altre (servono a Impostazioni > Aspetto) si caricano dopo, una alla volta
    // perche' registerExperience valida l'id con _loadingExperience.
    const all = ext.experiences || [];
    if (!GS.experiencesReady) {
      await Promise.all(all.filter((x) => x.id === ext.active_experience).map(loadExperience));
      GS.experiencesReady = (async () => {
        for (const x of all) if (x.id !== ext.active_experience) await loadExperience(x);
      })();
    }
    GS.experience = GS.experiences.get(ext.active_experience) || GS.experiences.get("catalog")
      || { id: "catalog", name: "Catalogo", description: "Interfaccia classica con navigazione laterale.",
        nav: "sidebar", home: null, card: null, detail: "panel", onFocus: null };
    document.documentElement.dataset.experienceId = GS.experience.id;
    // Keep the legacy CSS selector stable so the Originale preset keeps its pre-registry layout.
    document.documentElement.dataset.experience = GS.experience.id === "original" ? "catalog" : GS.experience.id;
    document.documentElement.dataset.experienceNav = GS.experience.nav;
    document.documentElement.dataset.experienceDetail = GS.experience.detail;
    const topNav = GS.experience.nav === "top", drawer = GS.experience.nav !== "sidebar";
    const bar = $("#experience-bar"), nav = $("#experience-nav"), toggle = $("#drawer-toggle");
    if (bar) bar.hidden = !drawer;
    if (nav) { nav.hidden = !topNav; nav.style.display = topNav ? "" : "none"; }
    if (toggle) { toggle.hidden = !drawer; toggle.style.display = drawer ? "" : "none"; }
  }
  const theme = ext.themes.find((t) => t.id === ext.active_theme);
  const css = theme && (mode === "bigpicture" ? theme.bigpicture : theme.desktop);
  const styles = [];  // fogli di stile del tema e dell'esperienza: si aspetta che siano applicati
  const addStyle = (href, kind) => {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = href; l.dataset.ext = kind;
    document.head.appendChild(l);
    styles.push(l);
  };
  if (css) addStyle(css, "theme");
  GSUi.applyTheme(document); // il tema utente va dopo quello scelto: a parita' di peso vince l'ultimo foglio
  if (mode === "desktop") {
    const selected = (ext.experiences || []).find((item) => item.id === GS.experience.id);
    if (selected && selected.style) addStyle(selected.style, "experience");
  }
  // La finestra nativa si mostra solo qui, con barra del titolo e bordo del colore del tema: prima
  // l'utente vedrebbe per un attimo il tema predefinito, i colori di sistema e la disposizione sbagliata.
  Promise.all(styles.map((l) => new Promise((done) => {
    if (l.sheet) return done();
    l.addEventListener("load", done, { once: true });
    l.addEventListener("error", done, { once: true });
  }))).then(showWindow);
  document.documentElement.dataset.theme = ext.active_theme || "default";
  GS.plugins = ext.plugins;
  GS.extensions = ext;
  const prefetched = new Map(ext.plugins.filter((x) => x.enabled && x.frontend).map((p) => [p.id, import(p.frontend)]));
  prefetched.forEach((promise) => promise.catch(() => {}));
  for (const p of ext.plugins.filter((x) => x.enabled)) {
    if (p.style) {
      const l = document.createElement("link");
      l.rel = "stylesheet"; l.href = p.style; l.dataset.ext = "plugin";
      document.head.appendChild(l);
    }
    if (p.frontend) {
      try {
        const m = await prefetched.get(p.id);
        if (typeof m.default === "function") await m.default(GS, { id: p.id, settings: p.settings || {} });
      } catch (e) {
        console.error(`Plugin ${p.id}:`, e);
        GS.toast(`Il plugin «${p.name}» non si e' caricato: ${e.message}`, true);
      }
    }
  }
  GS.emit("extensionsLoaded", ext);
}
