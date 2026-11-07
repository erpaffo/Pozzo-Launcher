import { compositeKey, isSeen, formatDuration, episodeSiblings } from "./logica.js";

export const CONTINUE_KEY = "gs.pm_continue_watching";
export const AUDIO_PREF_KEY = "gs.pm_audio_lang";
export const HANDOFF_KEY = "gs.pm_handoff"; // passaggio dell'episodio in corso alla finestra Media separata

const HANDOFF_FIELDS = ["id", "source", "kind", "title", "series", "season", "episode", "year", "poster", "provider",
  "seen", "resume_pos", "duration", "episode_count", "season_count"];
const slimItem = (e) => {
  const o = {};
  for (const k of HANDOFF_FIELDS) if (e && e[k] != null && e[k] !== "") o[k] = e[k];
  if (e && e.overview) o.overview = String(e.overview).slice(0, 200);
  return o;
};

/** Lascia alla finestra Media separata ciò che serve per riprendere: titolo, punto raggiunto e gli episodi per precedente/successivo. */
export function saveHandoff(item, episodes, pos, storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  if (!storage || !item) return false;
  const payload = { t: Date.now(), pos: Math.max(0, Number(pos) || 0), item: slimItem(item),
    episodes: (Array.isArray(episodes) ? episodes : []).slice(0, 3000).map(slimItem) };
  try { storage.setItem(HANDOFF_KEY, JSON.stringify(payload)); return true; } catch { return false; }
}

/** Legge e consuma il passaggio (una sola volta); null se manca, è illeggibile o più vecchio di `maxAgeMs`. */
export function takeHandoff(storage = (typeof localStorage !== "undefined" ? localStorage : null), maxAgeMs = 30000) {
  try {
    const raw = storage && storage.getItem(HANDOFF_KEY);
    if (!raw) return null;
    storage.removeItem(HANDOFF_KEY);
    const h = JSON.parse(raw);
    if (!h || !h.item || h.item.id == null || Date.now() - Number(h.t || 0) > maxAgeMs) return null;
    return h;
  } catch { return null; }
}
export const SUB_PREF_KEY = "gs.pm_sub_lang"; // codice lingua oppure "off"
export const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

/** Nuova posizione dopo un salto di `delta` secondi, dentro [0, durata]; durata ignota = nessun limite alto. */
export function seekTarget(cur, delta, dur) {
  const t = (Number(cur) || 0) + (Number(delta) || 0);
  return Math.max(0, Number.isFinite(dur) && dur > 0 ? Math.min(t, dur) : t);
}

const seasonOf = (ep) => (ep && ep.season != null && !Number.isNaN(Number(ep.season)) ? Number(ep.season) : 1);

/** «S1E3» (stagione 1 se manca). */
export function episodeLabel(ep) {
  return `S${seasonOf(ep)}E${ep?.episode != null ? ep.episode : "?"}`;
}

/** Pannello «Episodi» del lettore: schede stagione + elenco della stagione scelta. `cur` = indice dell'episodio in riproduzione in `list`. */
export function renderEpisodesPanel(list, cur, season, esc) {
  const seasons = [...new Set(list.map(seasonOf))].sort((a, b) => a - b);
  const tabs = seasons.length > 1
    ? `<div class="pm-eps-tabs" role="tablist">${seasons.map((n) => `<button type="button" role="tab" data-season="${n}" class="${n === season ? "pm-on" : ""}">Stagione ${n}</button>`).join("")}</div>`
    : "";
  const rows = list.map((ep, i) => ({ ep, i })).filter(({ ep }) => seasonOf(ep) === season).map(({ ep, i }) => `
    <li><button type="button" class="pm-eps-item${i === cur ? " pm-cur" : ""}${isSeen(ep) ? " pm-seen" : ""}" data-i="${i}" ${i === cur ? 'aria-current="true"' : ""}>
      <span class="pm-eps-num">${ep.episode != null ? esc(ep.episode) : "·"}</span>
      <span class="pm-eps-body"><b>${esc(ep.title || `Episodio ${ep.episode ?? i + 1}`)}</b>${ep.overview ? `<small>${esc(ep.overview)}</small>` : ""}</span>
      <span class="pm-eps-mark" aria-hidden="true">${i === cur ? "▶" : (isSeen(ep) ? "✓" : "")}</span>
    </button></li>`).join("");
  return `<div class="pm-eps-head"><strong>Episodi</strong><button type="button" class="pm-ctl-btn" data-eps-close aria-label="Chiudi elenco episodi">✕</button></div>${tabs}<ul class="pm-eps-list">${rows}</ul>`;
}

/** «1:05 / 42:10»; la durata ancora ignota (HLS in caricamento) resta «0:00». */
export function clockText(cur, dur) {
  return `${formatDuration(Math.max(0, Math.floor(cur || 0)))} / ${formatDuration(Number.isFinite(dur) && dur > 0 ? Math.floor(dur) : 0)}`;
}

const LANG_NAMES = { it: "Italiano", en: "Inglese", ja: "Giapponese", jp: "Giapponese", es: "Spagnolo", fr: "Francese", de: "Tedesco", pt: "Portoghese", ko: "Coreano", zh: "Cinese" };

/** Etichetta leggibile di una traccia audio HLS ({name, lang}). */
export function audioTrackLabel(t, i = 0) {
  const code = String(t?.lang || "").toLowerCase().split("-")[0];
  return LANG_NAMES[code] || t?.name || (code ? code.toUpperCase() : `Traccia ${i + 1}`);
}

/** Indice della traccia con la lingua preferita; -1 se non c'è (si lascia la scelta del lettore). */
export function pickAudioIndex(tracks, pref) {
  const want = String(pref || "").toLowerCase();
  if (!want || !Array.isArray(tracks)) return -1;
  return tracks.findIndex((t) => String(t?.lang || "").toLowerCase().split("-")[0] === want);
}

/** Lingua audio scelta l'ultima volta ("" se nessuna); storage assente o bloccato = nessuna preferenza. */
export function loadAudioPref(storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  try { return (storage && storage.getItem(AUDIO_PREF_KEY)) || ""; } catch { return ""; }
}

/** Preferenza sottotitoli: "" = mai scelta (restano spenti), "off" = spenti per scelta, altrimenti la lingua. */
export function loadSubPref(storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  try { return (storage && storage.getItem(SUB_PREF_KEY)) || ""; } catch { return ""; }
}

export function saveSubPref(lang, storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  try { if (storage && lang) storage.setItem(SUB_PREF_KEY, String(lang)); } catch { /* storage bloccato: vale solo per questa visione */ }
}

export function saveAudioPref(lang, storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  try { if (storage && lang) storage.setItem(AUDIO_PREF_KEY, String(lang)); } catch { /* storage bloccato: la scelta vale solo per questa visione */ }
}

export const AUTONEXT_KEY = "gs.pm_autonext";
export const SKIP_INTRO_KEY = "gs.pm_skip_intro";
export const SKIP_SECS_KEY = "gs.pm_skip_secs";
const defStorage = () => (typeof localStorage !== "undefined" ? localStorage : null);

/** Preferenze del lettore (del dispositivo): auto-next (default sì), salta intro (default no), secondi da saltare 5..600 (default 85). */
export function loadPlayerPrefs(storage = defStorage()) {
  const get = (k) => { try { return storage ? storage.getItem(k) : null; } catch { return null; } };
  const secs = Math.round(Number(get(SKIP_SECS_KEY)));
  return {
    autonext: get(AUTONEXT_KEY) !== "0",
    skipIntro: get(SKIP_INTRO_KEY) === "1",
    skipSecs: Number.isFinite(secs) && secs > 0 ? Math.min(600, Math.max(5, secs)) : 85,
  };
}

/** Salva solo i campi presenti in `patch` ({autonext, skipIntro, skipSecs}); storage bloccato = vale per questa sessione. */
export function savePlayerPrefs(patch = {}, storage = defStorage()) {
  const set = (k, v) => { try { if (storage) storage.setItem(k, String(v)); } catch { /* storage bloccato */ } };
  if (patch.autonext != null) set(AUTONEXT_KEY, patch.autonext ? "1" : "0");
  if (patch.skipIntro != null) set(SKIP_INTRO_KEY, patch.skipIntro ? "1" : "0");
  if (patch.skipSecs != null) set(SKIP_SECS_KEY, Math.min(600, Math.max(5, Math.round(Number(patch.skipSecs)) || 85)));
}

/** Passo del conto alla rovescia «Prossimo episodio»: secondi rimasti dopo un tick e se è scaduto. */
export function nextCountdown(secs) {
  const left = Math.max(0, (Number(secs) || 0) - 1);
  return { secs: left, done: left <= 0 };
}

/** Pre-caricamento del successivo: a 30 s di visione, o al 25% se la durata è nota (vale il primo dei due). */
export function prefetchDue(pos, dur) {
  const limit = Number.isFinite(dur) && dur > 0 ? Math.min(30, dur * 0.25) : 30;
  return (Number(pos) || 0) >= limit;
}

/** Profilo attivo del launcher ("default" se il frontend non lo espone). */
function activeProfile() {
  try {
    const w = typeof window !== "undefined" ? window : globalThis;
    return String(w.GS?.library?.()?.profiles?.active || "default");
  } catch { return "default"; }
}
/** Chiave «Continua a guardare» del profilo attivo. */
export const continueKey = () => `${CONTINUE_KEY}:${activeProfile()}`;

const BROWSER_EXTS = new Set([".mp4", ".webm", ".mp3", ".flac", ".ogg", ".m4a", ".ogv", ".opus", ".wav", ".m4v", ".m3u8"]);
const AUDIO_EXTS = new Set([".mp3", ".flac", ".ogg", ".m4a", ".opus", ".wav"]);

/** Carica la lista degli elementi da continuare dallo storage (localStorage di default). */
export function loadContinueCache(storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  if (!storage || typeof storage.getItem !== "function") return [];
  try {
    const key = continueKey();
    let raw = storage.getItem(key);
    if (!raw) {
      // migrazione: la vecchia chiave globale passa al profilo attivo alla prima lettura (poi sparisce, così non si copia negli altri profili)
      raw = storage.getItem(CONTINUE_KEY);
      if (!raw) return [];
      try { storage.setItem(key, raw); storage.removeItem(CONTINUE_KEY); } catch {}
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Salva o aggiorna un elemento nella cache di visione continua. */
export function saveContinueCache(item, pos, seen, duration, storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  const current = loadContinueCache(storage);
  if (!hasValidId(item)) return current;
  const key = compositeKey(item);
  if (!key) return current;

  const p = Number(pos != null && Number.isFinite(pos) ? pos : (item.resume_pos ?? item.pos ?? 0));
  const dur = Number(duration != null && Number.isFinite(duration) ? duration : (item.duration || 0));
  const isWatched = seen === true || isSeen({ resume_pos: p, duration: dur, seen: item.seen });

  const filtered = current.filter((it) => compositeKey(it) !== key);

  if (!isWatched && p > 0) {
    const entry = {
      ...item,
      resume_pos: Math.round(p * 10) / 10,
      seen: false,
      ...(dur > 0 ? { duration: Math.round(dur * 10) / 10 } : {}),
    };
    filtered.unshift(entry);
  }

  const updated = filtered.slice(0, 20);
  if (storage && typeof storage.setItem === "function") {
    try {
      storage.setItem(continueKey(), JSON.stringify(updated));
    } catch {}
  }
  return updated;
}

/** Rimuove un elemento dalla cache di visione continua per chiave o id. */
export function removeFromContinueCache(itemOrKey, storage = (typeof localStorage !== "undefined" ? localStorage : null)) {
  const current = loadContinueCache(storage);
  const targetKey = typeof itemOrKey === "string" ? itemOrKey : (itemOrKey ? compositeKey(itemOrKey) : null);
  const targetId = typeof itemOrKey === "object" && itemOrKey ? String(itemOrKey.id ?? "") : (typeof itemOrKey === "string" ? itemOrKey : "");
  const filtered = current.filter((it) => {
    const k = compositeKey(it);
    if (targetKey && k === targetKey) return false;
    if (targetId && String(it.id) === targetId) return false;
    return true;
  });
  if (storage && typeof storage.setItem === "function") {
    try {
      storage.setItem(continueKey(), JSON.stringify(filtered));
    } catch {}
  }
  return filtered;
}

/** Vero se la sorgente o il file può essere riprodotto direttamente nel browser (<video> o <audio>). */
export function isBrowserPlayable(target) {
  if (!target) return false;
  if (target.external === true) return false;
  const path = String(target.path || "");
  const url = String(target.url || "");
  const mime = String(target.mime || "").toLowerCase();

  if (target.external === false && (url || path)) return true;
  if (mime.startsWith("video/mp4") || mime.startsWith("video/webm") || mime.startsWith("video/ogg") || mime.startsWith("audio/")) {
    return true;
  }
  const ext = (path || url).split(/[?#]/)[0].toLowerCase().match(/\.[a-z0-9]+$/);
  return Boolean(ext && BROWSER_EXTS.has(ext[0]));
}

function hasValidId(it) {
  if (!it || it.id == null) return false;
  const s = String(it.id).trim();
  return s.length > 0 && s !== "undefined" && s !== "null";
}

let _hlsLoading = null;
/** Carica hls.js (vendorizzato accanto a questo file) al primo uso; null se non disponibile. */
function loadHls() {
  const w = typeof window !== "undefined" ? window : globalThis;
  if (w.Hls) return Promise.resolve(w.Hls);
  if (typeof document === "undefined") return Promise.resolve(null);
  _hlsLoading ||= new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = new URL("./hls.min.js", import.meta.url).href;
    s.onload = () => resolve(w.Hls || null);
    s.onerror = () => { _hlsLoading = null; resolve(null); };
    document.head.appendChild(s);
  });
  return _hlsLoading;
}

const CONTROLS_HTML = `
  <div class="pm-ctl" id="pm-ctl">
    <input type="range" class="pm-ctl-seek" id="pm-seek" min="0" max="1000" value="0" step="1" aria-label="Posizione">
    <div class="pm-ctl-row">
      <button type="button" class="pm-ctl-btn" id="pm-c-prev" aria-label="Episodio precedente" title="Episodio precedente (P)" hidden>⏮</button>
      <button type="button" class="pm-ctl-btn" id="pm-c-play" aria-label="Riproduci" title="Riproduci / pausa (spazio)">▶</button>
      <button type="button" class="pm-ctl-btn" id="pm-c-next" aria-label="Episodio successivo" title="Episodio successivo (N)" hidden>⏭</button>
      <button type="button" class="pm-ctl-btn" id="pm-c-back" aria-label="Indietro di 10 secondi" title="-10 s (←)">⟲</button>
      <button type="button" class="pm-ctl-btn" id="pm-c-fwd" aria-label="Avanti di 10 secondi" title="+10 s (→)">⟳</button>
      <button type="button" class="pm-ctl-btn" id="pm-c-mute" aria-label="Volume" title="Muto (M)">🔊</button>
      <input type="range" class="pm-ctl-vol" id="pm-vol" min="0" max="100" value="100" aria-label="Volume">
      <span class="pm-ctl-time" id="pm-time">0:00 / 0:00</span>
      <span class="pm-ctl-spacer"></span>
      <button type="button" class="pm-ctl-btn pm-ctl-text" id="pm-c-skip" aria-label="Salta intro" title="Salta intro (I)" hidden>⏭ Salta intro</button>
      <button type="button" class="pm-ctl-btn pm-ctl-text" id="pm-c-eps" aria-label="Tutti gli episodi" title="Tutti gli episodi (E)" hidden>☰ Episodi</button>
      <div class="pm-ctl-menuwrap" id="pm-sub-wrap" hidden>
        <button type="button" class="pm-ctl-btn pm-ctl-text" id="pm-c-sub" aria-haspopup="menu" aria-label="Sottotitoli" title="Sottotitoli">CC</button>
        <div class="pm-ctl-menu" role="menu" hidden></div>
      </div>
      <div class="pm-ctl-menuwrap" id="pm-audio-wrap" hidden>
        <button type="button" class="pm-ctl-btn pm-ctl-text" id="pm-c-audio" aria-haspopup="menu" aria-label="Lingua audio" title="Lingua audio">🌐 Audio</button>
        <div class="pm-ctl-menu" role="menu" hidden></div>
      </div>
      <div class="pm-ctl-menuwrap" id="pm-speed-wrap">
        <button type="button" class="pm-ctl-btn pm-ctl-text" id="pm-c-speed" aria-haspopup="menu" aria-label="Velocità" title="Velocità">1×</button>
        <div class="pm-ctl-menu" role="menu" hidden></div>
      </div>
      <button type="button" class="pm-ctl-btn" id="pm-c-fs" aria-label="Schermo intero" title="Schermo intero (F)">⛶</button>
    </div>
  </div>
  <aside class="pm-eps" id="pm-eps" aria-label="Episodi" hidden></aside>`;

/** Tenta di aprire il file o l'url nel lettore esterno. */
export async function openExternal(gs, item, target, apiPrefix = "/plugin-api/media-locale") {
  const isHttpOnly = !target?.path && (target?.url?.startsWith("http://") || target?.url?.startsWith("https://"));
  try {
    if (isHttpOnly) {
      try {
        await gs.api(`${apiPrefix}/external`, { body: { id: item?.id, lang: loadAudioPref() } });
        return;
      } catch {
        await gs.api("/api/open", { body: { url: target.url } });
        return;
      }
    }
    await gs.api(`${apiPrefix}/external`, { body: { id: item?.id } });
  } catch (err) {
    gs?.toast?.(err?.message || "Impossibile aprire su internet", true);
  }
}

/** Riproduce un MediaItem: verifica id, chiede play_target, apre l'overlay adatto e gestisce il progresso. */
/** Schermata di attesa mostrata appena si preme Riproduci; Esc o Annulla la chiudono (`cancelled`). */
function showLoadingOverlay(doc, item, gs) {
  const esc = gs?.esc || ((v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));
  const el = doc.createElement("div");
  el.className = "pm-player-overlay pm-loading";
  el.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.85);display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;";
  const label = item.series ? `${item.series} — ${item.title || ""}` : (item.title || "Riproduzione");
  el.innerHTML = `<div class="pm-loading-box" role="status" aria-live="polite">
    <div class="pm-loading-spin" aria-hidden="true"></div>
    <div class="pm-loading-title">${esc(label)}</div>
    <div class="pm-loading-sub">Apertura in corso…</div>
    <button type="button" class="pm-player-btn" data-loading-cancel>Annulla</button>
  </div>`;
  const state = {
    cancelled: false,
    remove() { doc.removeEventListener("keydown", onKey); el.remove(); },
  };
  const cancel = () => { state.cancelled = true; state.remove(); };
  function onKey(e) { if (e.key === "Escape") { e.preventDefault(); cancel(); } }
  el.querySelector("[data-loading-cancel]").addEventListener("click", cancel);
  doc.addEventListener("keydown", onKey);
  doc.body.appendChild(el);
  animateSpinners(el);
  return state;
}

/** Fa girare le rotelle `.pm-loading-spin` dentro `root` (una sola volta ciascuna). */
export function animateSpinners(root) {
  const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  root?.querySelectorAll?.(".pm-loading-spin").forEach((el) => {
    if (el._pmSpin) return;
    el._pmSpin = true;
    el.animate?.([{ transform: "rotate(0)" }, { transform: "rotate(360deg)" }], { duration: reduce ? 2400 : 800, iterations: Infinity });
  });
}

export async function play(gs, item, onClose, opts = {}) {
  if (!hasValidId(item)) {
    gs?.toast?.("Elemento non valido", true);
    return null;
  }

  const doc = typeof document !== "undefined" ? document : null;
  if (doc) {
    const prev = doc.querySelector(".pm-player-overlay");
    if (prev && typeof prev._pmClose === "function") prev._pmClose();
  }

  const src = item.source || "media-locale";
  const isSrv = src === "jellyfin" || src === "plex";
  const apiPrefix = isSrv
    ? "/plugin-api/media-server"
    : (src !== "locale" && src !== "media-locale" ? `/plugin-api/${src}` : "/plugin-api/media-locale");
  const srcQuery = isSrv ? `&source=${encodeURIComponent(src)}` : "";

  // il lettore si apre subito con un'attesa visibile: risolvere il flusso dei provider richiede qualche secondo di rete
  const loading = doc ? showLoadingOverlay(doc, item, gs) : null;

  let target;
  try {
    target = await gs.api(`${apiPrefix}/play_target?id=${encodeURIComponent(item.id)}${srcQuery}`);
  } catch (err) {
    loading?.remove();
    if (!loading?.cancelled) gs?.toast?.(err?.message || "Errore nel caricamento del file", true);
    return null;
  }
  if (loading?.cancelled) return null; // l'utente ha annullato mentre si risolveva il flusso
  loading?.remove();

  if (!target) {
    gs?.toast?.("Sorgente non trovata", true);
    return null;
  }

  const browserPlayable = isBrowserPlayable(target);
  if (!doc) return { item, target, browserPlayable };

  return openOverlay(gs, item, target, browserPlayable, apiPrefix, onClose, opts);
}

/** Barra comandi del lettore video: play, posizione, volume, velocità, audio, sottotitoli, schermo intero. */
function setupControls(overlay, video, esc, toggleFullscreen, eps = { list: [], index: -1 }) {
  const $ = (sel) => overlay.querySelector(sel);
  const box = $(".pm-player"), seek = $("#pm-seek"), vol = $("#pm-vol");
  const playBtn = $("#pm-c-play"), muteBtn = $("#pm-c-mute"), timeEl = $("#pm-time");
  const audioWrap = $("#pm-audio-wrap"), speedWrap = $("#pm-speed-wrap"), subWrap = $("#pm-sub-wrap");
  const menus = [audioWrap, speedWrap, subWrap];
  let idleTimer = null, scrubbing = false;

  const menuOf = (w) => w.querySelector(".pm-ctl-menu");
  const closeMenus = () => menus.forEach((w) => { menuOf(w).hidden = true; });
  const panel = $("#pm-eps");
  const menuOpen = () => !panel.hidden || menus.some((w) => !menuOf(w).hidden);

  function wake() {
    box.classList.remove("pm-idle");
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { if (!video.paused && !menuOpen() && !scrubbing) box.classList.add("pm-idle"); }, 3000);
  }

  /** Menu a scelta singola: items = [{label, value}], cur = value attivo; onPick(value). */
  function fillMenu(wrap, items, cur, onPick) {
    const menu = menuOf(wrap);
    menu.innerHTML = items.map((it, i) =>
      `<button type="button" role="menuitemradio" aria-checked="${it.value === cur}" data-i="${i}" class="${it.value === cur ? "pm-on" : ""}">${esc(it.label)}</button>`).join("");
    menu.onclick = (e) => {
      const b = e.target.closest("button[data-i]");
      if (!b) return;
      const it = items[Number(b.dataset.i)];
      menu.hidden = true;
      fillMenu(wrap, items, it.value, onPick);
      onPick(it.value);
    };
  }
  menus.forEach((w) => w.querySelector("button").addEventListener("click", (e) => {
    e.stopPropagation();
    const m = menuOf(w), wasHidden = m.hidden;
    closeMenus();
    m.hidden = !wasHidden;
  }));
  overlay.addEventListener("click", (e) => { if (!e.target.closest(".pm-ctl-menuwrap")) closeMenus(); });

  // episodi: precedente/successivo e pannello con tutta la serie (visibili solo con almeno due episodi)
  const has = eps.list.length > 1 && eps.index >= 0;
  const prevBtn = $("#pm-c-prev"), nextBtn = $("#pm-c-next"), epsBtn = $("#pm-c-eps");
  let panelSeason = has ? seasonOf(eps.list[eps.index]) : 1;
  const go = (d) => { const t = eps.list[eps.index + d]; if (t && eps.onPick) eps.onPick(t); };
  const drawPanel = () => {
    panel.innerHTML = renderEpisodesPanel(eps.list, eps.index, panelSeason, esc);
    panel.querySelector(".pm-cur")?.scrollIntoView?.({ block: "nearest" });
  };
  const togglePanel = () => { panel.hidden = !panel.hidden; if (!panel.hidden) { closeMenus(); drawPanel(); } };
  if (has) {
    prevBtn.hidden = nextBtn.hidden = epsBtn.hidden = false;
    prevBtn.disabled = eps.index === 0;
    nextBtn.disabled = eps.index === eps.list.length - 1;
    prevBtn.addEventListener("click", () => go(-1));
    nextBtn.addEventListener("click", () => go(1));
    epsBtn.addEventListener("click", (e) => { e.stopPropagation(); togglePanel(); });
    panel.addEventListener("click", (e) => {
      if (e.target.closest("[data-eps-close]")) { panel.hidden = true; return; }
      const tab = e.target.closest("[data-season]");
      if (tab) { panelSeason = Number(tab.dataset.season); drawPanel(); return; }
      const it = e.target.closest(".pm-eps-item");
      if (it && eps.onPick) eps.onPick(eps.list[Number(it.dataset.i)]);
    });
  }

  const setSpeed = (v) => { video.playbackRate = v; $("#pm-c-speed").textContent = `${v}×`; };
  fillMenu(speedWrap, SPEEDS.map((v) => ({ value: v, label: v === 1 ? "Normale" : `${v}×` })), 1, setSpeed);

  const toggle = () => { if (video.paused) video.play().catch(() => {}); else video.pause(); };
  const jump = (d) => { video.currentTime = seekTarget(video.currentTime, d, video.duration); };
  const syncVol = () => {
    vol.value = video.muted ? 0 : Math.round(video.volume * 100);
    muteBtn.textContent = video.muted || video.volume === 0 ? "🔇" : "🔊";
  };
  const syncTime = () => {
    timeEl.textContent = clockText(video.currentTime, video.duration);
    if (!scrubbing && video.duration > 0) seek.value = String(Math.round((video.currentTime / video.duration) * 1000));
  };

  const skipBtn = $("#pm-c-skip");
  const skip = () => jump(loadPlayerPrefs().skipSecs);
  if (skipBtn) { skipBtn.hidden = !loadPlayerPrefs().skipIntro; skipBtn.addEventListener("click", skip); }

  playBtn.addEventListener("click", toggle);
  video.addEventListener("click", toggle);
  $("#pm-c-back").addEventListener("click", () => jump(-10));
  $("#pm-c-fwd").addEventListener("click", () => jump(10));
  muteBtn.addEventListener("click", () => { video.muted = !video.muted; });
  vol.addEventListener("input", () => { video.muted = false; video.volume = Number(vol.value) / 100; });
  $("#pm-c-fs").addEventListener("click", () => toggleFullscreen());
  seek.addEventListener("input", () => { scrubbing = true; if (video.duration > 0) video.currentTime = (Number(seek.value) / 1000) * video.duration; });
  seek.addEventListener("change", () => { scrubbing = false; });
  video.addEventListener("play", () => { playBtn.textContent = "⏸"; playBtn.setAttribute("aria-label", "Pausa"); wake(); });
  video.addEventListener("pause", () => { playBtn.textContent = "▶"; playBtn.setAttribute("aria-label", "Riproduci"); box.classList.remove("pm-idle"); });
  video.addEventListener("timeupdate", syncTime);
  video.addEventListener("durationchange", syncTime);
  video.addEventListener("volumechange", syncVol);
  ["mousemove", "touchstart", "keydown"].forEach((ev) => box.addEventListener(ev, wake, { passive: true }));
  syncVol();
  wake();

  return {
    setAudio(tracks, cur, onPick) {
      fillMenu(audioWrap, tracks.map((t, i) => ({ value: i, label: audioTrackLabel(t, i) })), cur, onPick);
      audioWrap.hidden = false;
    },
    /** Sottotitoli: voce «Disattivati» (-1) più le tracce; compare solo se ce n'è almeno una. */
    setSubs(tracks, cur, onPick) {
      const items = [{ value: -1, label: "Disattivati" }, ...tracks.map((t, i) => ({ value: i, label: audioTrackLabel(t, i) }))];
      fillMenu(subWrap, items, cur, onPick);
      subWrap.hidden = false;
    },
    /** Scorciatoie del lettore; true se il tasto è stato gestito. */
    key(e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return false;
      switch (e.key) {
        case " ": case "k": case "K": toggle(); break;
        case "ArrowLeft": jump(-10); break;
        case "ArrowRight": jump(10); break;
        case "ArrowUp": video.muted = false; video.volume = Math.min(1, video.volume + 0.05); break;
        case "ArrowDown": video.volume = Math.max(0, video.volume - 0.05); break;
        case "m": case "M": video.muted = !video.muted; break;
        case "n": case "N": if (!has) return false; go(1); break;
        case "p": case "P": if (!has) return false; go(-1); break;
        case "e": case "E": if (!has) return false; togglePanel(); break;
        case "i": case "I": if (!loadPlayerPrefs().skipIntro) return false; skip(); break;
        default: return false;
      }
      wake();
      return true;
    },
    /** Escape chiude prima l'elenco episodi; true se c'era qualcosa da chiudere. */
    closePanel() { if (panel.hidden) return false; panel.hidden = true; return true; },
    destroy() { clearTimeout(idleTimer); },
    toggle, jump, skip, go, togglePanel, has,
    hasPrev: has && eps.index > 0,
    hasNext: has && eps.index < eps.list.length - 1,
  };
}

function openOverlay(gs, item, target, browserPlayable, apiPrefix, onClose, opts = {}) {
  const doc = document;
  const esc = gs?.esc || ((s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])));

  let titleText = item.title || "Riproduzione";
  if (item.series) {
    const s = item.season != null ? `S${item.season}` : "";
    const e = item.episode != null ? `E${item.episode}` : "";
    const ep = (s || e) ? ` — ${s}${e}` : "";
    titleText = `${item.series}${ep}: ${item.title || ""}`;
  } else if (item.album) {
    titleText = `${item.title || "Brano"} — ${item.album}`;
  }

  const overlay = doc.createElement("div");
  overlay.className = "pm-player-overlay";
  overlay.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.85);display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box;";

  let closed = false;
  let saveTimer = null;
  let resumeApplied = false;
  let mediaEl = null;
  let hls = null;
  let ctl = null; // comandi del lettore (solo video): vedi setupControls

  const resumePos = Number(opts.resumeAt ?? target.resume_pos ?? item.resume_pos ?? 0);

  async function saveProgress(overridePos) {
    if (closed || !hasValidId(item)) return;

    const rawPos = mediaEl ? Number(mediaEl.currentTime) : 0;
    const curPos = (overridePos != null && Number.isFinite(overridePos))
      ? overridePos
      : (Number.isFinite(rawPos) && rawPos > 0 ? rawPos : 0);

    const rawDur = mediaEl ? Number(mediaEl.duration) : 0;
    const curDur = (Number.isFinite(rawDur) && rawDur > 0) ? rawDur : Number(item.duration || 0);

    const isWatched = isSeen({ resume_pos: curPos, duration: curDur, seen: item.seen });

    saveContinueCache(item, curPos, isWatched, curDur);

    const payload = {
      id: String(item.id),
      pos: Math.round(curPos * 10) / 10,
      seen: isWatched,
    };
    if (item.source === "jellyfin" || item.source === "plex") {
      payload.source = item.source;
    }
    if (curDur > 0) {
      payload.duration = Math.round(curDur * 10) / 10;
    }

    item.resume_pos = isWatched ? 0 : payload.pos;
    item.seen = isWatched;
    if (curDur > 0 && !item.duration) {
      item.duration = payload.duration;
    }

    try {
      await gs.api(`${apiPrefix}/set_progress`, { body: payload });
    } catch {}
  }

  let isFullscreen = false;

  async function setWindowFullscreen(on) {
    const shouldBeFs = Boolean(on);
    try {
      const pw = (typeof window !== "undefined" ? window : globalThis)?.pywebview?.api;
      if (pw && typeof pw.set_fullscreen === "function") {
        await pw.set_fullscreen(shouldBeFs);
      }
    } catch {}

    try {
      if (shouldBeFs) {
        if (!doc.fullscreenElement && !doc.webkitFullscreenElement) {
          if (overlay.requestFullscreen) {
            await overlay.requestFullscreen({ navigationUI: "hide" });
          } else if (doc.documentElement.requestFullscreen) {
            await doc.documentElement.requestFullscreen({ navigationUI: "hide" });
          } else if (mediaEl && mediaEl.webkitEnterFullscreen) {
            mediaEl.webkitEnterFullscreen();
          }
        }
      } else {
        if (doc.fullscreenElement || doc.webkitFullscreenElement) {
          if (doc.exitFullscreen) {
            await doc.exitFullscreen();
          } else if (doc.webkitExitFullscreen) {
            await doc.webkitExitFullscreen();
          }
        }
      }
    } catch {}
  }

  function updateFullscreenUI(on) {
    isFullscreen = Boolean(on);
    if (isFullscreen) {
      overlay.classList.add("pm-fullscreen-mode");
    } else {
      overlay.classList.remove("pm-fullscreen-mode");
    }
    const fsBtn = overlay.querySelector("#pm-c-fs");
    if (fsBtn) {
      fsBtn.innerHTML = isFullscreen ? "🗗" : "⛶";
      fsBtn.title = isFullscreen ? "Esci da schermo intero (F)" : "Schermo intero (F)";
    }
  }

  async function toggleFullscreen(force) {
    const target = typeof force === "boolean" ? force : !isFullscreen;
    updateFullscreenUI(target);
    await setWindowFullscreen(target);
  }

  function onFullscreenChange() {
    const active = Boolean(doc.fullscreenElement || doc.webkitFullscreenElement);
    if (active !== isFullscreen) {
      updateFullscreenUI(active);
      try {
        const pw = (typeof window !== "undefined" ? window : globalThis)?.pywebview?.api;
        if (pw && typeof pw.set_fullscreen === "function") {
          pw.set_fullscreen(active);
        }
      } catch {}
    }
  }

  doc.addEventListener("fullscreenchange", onFullscreenChange);
  doc.addEventListener("webkitfullscreenchange", onFullscreenChange);

  function closeOverlay() {
    if (closed) return;
    if (browserPlayable && mediaEl) {
      saveProgress();
    }
    closed = true;
    if (!overlay._pmKeepFs && (isFullscreen || doc.fullscreenElement || doc.webkitFullscreenElement)) {
      setWindowFullscreen(false);
    }
    if (saveTimer) {
      clearInterval(saveTimer);
      saveTimer = null;
    }
    if (hls) {
      try { hls.destroy(); } catch {}
      hls = null;
    }
    if (mediaEl) {
      try {
        mediaEl.pause();
        mediaEl.removeAttribute("src");
        mediaEl.load();
      } catch {}
    }
    ctl?.destroy();
    cancelNext();
    teardownExtras();
    overlay.remove();
    doc.removeEventListener("keydown", onKeyDown);
    doc.removeEventListener("fullscreenchange", onFullscreenChange);
    doc.removeEventListener("webkitfullscreenchange", onFullscreenChange);
    if (typeof onClose === "function") {
      try { onClose(item); } catch {}
    }
  }

  /** Continua in una finestra Media separata (stesso episodio, stesso punto): qui il lettore si chiude e il launcher resta libero. */
  async function popOut() {
    const pos = mediaEl && Number.isFinite(mediaEl.currentTime) ? mediaEl.currentTime : 0;
    saveHandoff(item, opts.episodes, pos);
    closeOverlay(); // salva la posizione e ferma la riproduzione qui
    try {
      const w = typeof window !== "undefined" ? window : globalThis;
      if (w.pywebview?.api?.open_media) await w.pywebview.api.open_media();
      else w.open("/#media-window", "pozzo-media", "popup,width=1280,height=820");
    } catch (err) {
      gs?.toast?.(`Finestra Media non aperta (${err?.message || "errore"})`, true);
    }
  }

  /** Passa a un altro episodio della stessa serie: salva la posizione, chiude questo lettore e ne apre uno nuovo. */
  function switchEpisode(ep) {
    if (!ep || closed || String(ep.id) === String(item.id)) return;
    cancelNext();
    overlay._pmKeepFs = isFullscreen;
    const { resumeAt, ...rest } = opts; // il punto di ripresa era di questo episodio, non del prossimo
    play(gs, ep, onClose, { ...rest, startFullscreen: isFullscreen });
  }

  // ---- episodio successivo automatico, pre-caricamento, Media Session, oggetto di controllo (solo video)
  let nextTimer = null, nextCard = null, nextEp = null, prevEp = null, prefetched = false, lastEmit = 0, myCtl = null;
  const win = typeof window !== "undefined" ? window : globalThis;

  function cancelNext() {
    if (nextTimer) { clearInterval(nextTimer); nextTimer = null; }
    if (nextCard) { nextCard.remove(); nextCard = null; }
  }

  function startNext() {
    if (closed || nextTimer || !nextEp || !loadPlayerPrefs().autonext) return;
    const target = nextEp;
    let secs = 5;
    nextCard = doc.createElement("div");
    nextCard.className = "pm-nextup";
    nextCard.setAttribute?.("role", "status");
    nextCard.innerHTML = `<div class="pm-nextup-title">Prossimo episodio tra <b data-nu-secs>${secs}</b> s</div>
      <div class="pm-nextup-ep">${esc(episodeLabel(target))} · ${esc(target.title || "")}</div>
      <div class="pm-nextup-btns"><button type="button" class="pm-player-btn pm-primary" data-nu-now>Riproduci ora</button><button type="button" class="pm-player-btn" data-nu-cancel>Annulla</button></div>`;
    nextCard.querySelector("[data-nu-now]")?.addEventListener("click", () => switchEpisode(target));
    nextCard.querySelector("[data-nu-cancel]")?.addEventListener("click", cancelNext);
    (overlay.querySelector(".pm-player") || overlay).appendChild(nextCard);
    nextTimer = setInterval(() => {
      const r = nextCountdown(secs);
      secs = r.secs;
      const el = nextCard?.querySelector("[data-nu-secs]");
      if (el) el.textContent = String(secs);
      if (r.done) { cancelNext(); switchEpisode(target); }
    }, 1000);
  }

  function getState() {
    const v = mediaEl, p = loadPlayerPrefs();
    const num = (x) => (Number.isFinite(x) ? x : 0);
    return {
      active: true, id: item.id, source: item.source || "media-locale", title: item.title || "", series: item.series || "",
      season: item.season ?? null, episode: item.episode ?? null,
      paused: !!v.paused, pos: num(v.currentTime), duration: num(v.duration), volume: num(v.volume), muted: !!v.muted,
      fullscreen: isFullscreen, hasPrev: !!prevEp, hasNext: !!nextEp,
      skipIntro: p.skipIntro, skipSecs: p.skipSecs, autonext: p.autonext,
    };
  }
  function emitState(detail) {
    try { win.dispatchEvent?.(new CustomEvent("pm:state", { detail: detail || getState() })); } catch {}
  }

  function command(name, arg) {
    try {
      const v = mediaEl;
      switch (name) {
        case "play": v.play()?.catch?.(() => {}); return true;
        case "pause": v.pause(); return true;
        case "toggle": ctl.toggle(); return true;
        case "jump": ctl.jump(Number(arg) || 0); return true;
        case "seek": v.currentTime = seekTarget(0, Number(arg) || 0, v.duration); return true;
        case "next": if (!nextEp) return false; switchEpisode(nextEp); return true;
        case "prev": if (!prevEp) return false; switchEpisode(prevEp); return true;
        case "volume": v.muted = false; v.volume = Math.min(1, Math.max(0, Number(arg) || 0)); return true;
        case "mute": v.muted = !v.muted; return true;
        case "fullscreen": toggleFullscreen(); return true;
        case "skip": ctl.skip(); return true;
        case "episodes": if (!ctl.has) return false; ctl.togglePanel(); return true;
        case "close": closeOverlay(); return true;
        default: return false;
      }
    } catch { return false; }
  }

  function setupMediaSession() {
    try {
      const ms = typeof navigator !== "undefined" ? navigator.mediaSession : null;
      if (!ms) return;
      if (typeof MediaMetadata === "function") {
        const poster = String(item.poster || "");
        ms.metadata = new MediaMetadata({
          title: item.title || "", artist: item.series || "", album: item.series ? `Stagione ${item.season ?? 1}` : (item.album || ""),
          artwork: /^https?:\/\//i.test(poster) || /^\/(?!\/)/.test(poster) ? [{ src: poster }] : [],
        });
      }
      const h = (a, f) => { try { ms.setActionHandler(a, f); } catch {} };
      h("play", () => command("play")); h("pause", () => command("pause"));
      h("previoustrack", prevEp ? () => command("prev") : null);
      h("nexttrack", nextEp ? () => command("next") : null);
      h("seekbackward", () => command("jump", -10)); h("seekforward", () => command("jump", 10));
      h("seekto", (d) => command("seek", d?.seekTime));
    } catch {}
  }
  function teardownExtras() {
    if (!myCtl) return;
    if (win.__pmCtl === myCtl) { delete win.__pmCtl; emitState({ active: false }); }
    try {
      const ms = typeof navigator !== "undefined" ? navigator.mediaSession : null;
      if (!ms) return;
      for (const a of ["play", "pause", "previoustrack", "nexttrack", "seekbackward", "seekforward", "seekto"]) { try { ms.setActionHandler(a, null); } catch {} }
      ms.metadata = null;
      ms.playbackState = "none";
    } catch {}
  }
  function setupExtras(sib) {
    nextEp = sib.list[sib.index + 1] || null;
    prevEp = sib.index > 0 ? sib.list[sib.index - 1] : null;
    myCtl = { getState, command };
    win.__pmCtl = myCtl;
    setupMediaSession();
    const ps = (s) => { try { navigator.mediaSession.playbackState = s; } catch {} };
    mediaEl.addEventListener("play", () => { cancelNext(); ps("playing"); emitState(); });
    mediaEl.addEventListener("pause", () => { ps("paused"); emitState(); });
    mediaEl.addEventListener("volumechange", () => emitState());
    mediaEl.addEventListener("ended", startNext);
    mediaEl.addEventListener("timeupdate", () => {
      if (closed) return;
      if (!prefetched && nextEp && (item.source === "ricette-web" || apiPrefix === "/plugin-api/ricette-web") && prefetchDue(mediaEl.currentTime, mediaEl.duration)) {
        prefetched = true;
        try { Promise.resolve(gs.api("/plugin-api/ricette-web/prefetch", { body: { id: nextEp.id } })).catch(() => {}); } catch {}
      }
      const now = Date.now();
      if (now - lastEmit >= 1000) { lastEmit = now; emitState(); }
    });
    emitState();
  }

  function onKeyDown(e) {
    const targetTag = (e.target?.tagName || "").toLowerCase();
    if (targetTag === "input" || targetTag === "textarea" || targetTag === "select") {
      return;
    }
    if (e.key === "f" || e.key === "F") {
      e.preventDefault();
      toggleFullscreen();
      return;
    }
    if (ctl && ctl.key(e)) { e.preventDefault(); return; }
    if (e.key === "Escape") {
      e.preventDefault();
      if (ctl && ctl.closePanel()) return;
      if (isFullscreen || doc.fullscreenElement || doc.webkitFullscreenElement) {
        toggleFullscreen(false);
      } else {
        closeOverlay();
      }
    }
  }
  doc.addEventListener("keydown", onKeyDown);
  overlay._pmClose = closeOverlay;

  if (!browserPlayable) {
    overlay.innerHTML = `
      <div class="pm-player-modal" style="width:100%;max-width:640px;background:var(--panel,#18181b);border:1px solid var(--line,#27272a);border-radius:12px;padding:20px;box-sizing:border-box;display:flex;flex-direction:column;gap:14px;box-shadow:0 20px 40px rgba(0,0,0,0.6);">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line,#27272a);padding-bottom:10px;">
          <h3 class="pm-title" style="margin:0;font-size:1.05rem;font-weight:600;">${esc(titleText)}</h3>
          <button type="button" class="pm-player-btn" id="pm-close-x" aria-label="Chiudi" style="padding:4px 8px;font-size:1rem;line-height:1;">✕</button>
        </div>
        <div class="pm-player-fallback">
          <p class="pm-player-fallback-text">Questo formato non può essere riprodotto direttamente nel browser.</p>
          <button type="button" class="pm-player-external" id="pm-open-ext" title="Apre il flusso fuori dal launcher: nel lettore del sistema (mpv, VLC) o nel browser">🌐 Apri su internet</button>
        </div>
        <div class="pm-player-actions" style="justify-content:flex-end;">
          <button type="button" class="pm-player-btn" id="pm-close-btn">Chiudi</button>
        </div>
      </div>
    `;

    overlay.querySelector("#pm-open-ext")?.addEventListener("click", () => openExternal(gs, item, target, apiPrefix));
    overlay.querySelector("#pm-close-x")?.addEventListener("click", closeOverlay);
    overlay.querySelector("#pm-close-btn")?.addEventListener("click", closeOverlay);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) closeOverlay(); });

    doc.body.appendChild(overlay);
    return { overlay, close: closeOverlay, browserPlayable: false };
  }

  const cleanExt = (target.path || target.url || "").split(/[?#]/)[0].toLowerCase().match(/\.[a-z0-9]+$/);
  const isAudio = item.kind === "brano" ||
    Boolean(target.mime && target.mime.startsWith("audio/")) ||
    Boolean(cleanExt && AUDIO_EXTS.has(cleanExt[0]));

  const mediaTag = isAudio ? "audio" : "video";

  overlay.innerHTML = `
    <div class="pm-player-modal" style="width:100%;max-width:960px;background:var(--panel,#18181b);border:1px solid var(--line,#27272a);border-radius:12px;padding:16px;box-sizing:border-box;display:flex;flex-direction:column;gap:12px;box-shadow:0 20px 40px rgba(0,0,0,0.6);">
      <div class="pm-player-header" style="display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line,#27272a);padding-bottom:8px;">
        <h3 class="pm-title" style="margin:0;font-size:1.05rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(titleText)}</h3>
        <div style="display:flex;align-items:center;gap:8px;">
          <button type="button" class="pm-player-btn" id="pm-close-x" aria-label="Chiudi" style="padding:4px 8px;font-size:1rem;line-height:1;">✕</button>
        </div>
      </div>
      <div class="pm-player" style="${isAudio ? 'aspect-ratio:auto;padding:28px 16px;display:flex;align-items:center;justify-content:center;background:var(--bg-2,#111);' : ''}">
        <${mediaTag} class="pm-player-video" ${isAudio ? "controls" : ""} autoplay playsinline style="${isAudio ? 'width:100%;max-width:600px;height:54px;' : ''}"></${mediaTag}>
        ${isAudio ? "" : CONTROLS_HTML}
      </div>
      <div class="pm-player-actions">
        <div class="pm-player-actions-left">
          ${typeof document !== "undefined" && document.body?.classList.contains("media-window") ? "" : `<button type="button" class="pm-player-external" id="pm-open-window" title="Continua questo episodio in una finestra separata: il launcher resta libero (anche per giocare)">⧉ Apri in una nuova finestra</button>`}
          <button type="button" class="pm-player-external" id="pm-open-ext" title="Apre il flusso fuori dal launcher: nel lettore del sistema (mpv, VLC) o nel browser">🌐 Apri su internet</button>
        </div>
        <button type="button" class="pm-player-btn pm-primary" id="pm-close-btn">Chiudi</button>
      </div>
    </div>
  `;

  mediaEl = overlay.querySelector(mediaTag);
  if (!isAudio && mediaEl) {
    mediaEl.addEventListener("dblclick", (e) => {
      e.preventDefault();
      toggleFullscreen();
    });
  }

  if (!isAudio) {
    const sib = Array.isArray(opts.episodes) && opts.episodes.length > 1 ? episodeSiblings(opts.episodes, item.id) : { list: [], index: -1 };
    ctl = setupControls(overlay, mediaEl, esc, toggleFullscreen, { ...sib, onPick: switchEpisode });
    // shortcut: il nuovo lettore chiede lo schermo intero da solo; il browser lo accetta solo dopo un clic (non all'avvio automatico)
    if (opts.startFullscreen) toggleFullscreen(true);
    setupExtras(sib);
  }

  const streamSrc = target.url || (target.path ? `${apiPrefix}/stream?id=${encodeURIComponent(item.id)}` : "");
  const isHls = /\.m3u8$/i.test(streamSrc.split(/[?#]/)[0]);

  /** Errore fatale: niente spinner/player bloccato, solo messaggio e il pulsante del lettore esterno. */
  function showPlayError(msg) {
    if (closed) return;
    try { mediaEl.pause(); } catch {}
    const box = overlay.querySelector(".pm-player");
    if (box) box.innerHTML = `<p class="pm-player-fallback-text" style="padding:24px;margin:0;">${esc(msg)}</p>`;
  }

  if (isHls) {
    loadHls().then((Hls) => {
      if (closed) return;
      if (Hls && Hls.isSupported()) {
        hls = new Hls();
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (data?.fatal) showPlayError("Impossibile riprodurre questo flusso (HLS). Prova «Apri su internet».");
        });
        // menu «Audio» e «Sottotitoli» nei controlli: compaiono solo se la playlist offre le tracce
        hls.on(Hls.Events.AUDIO_TRACKS_UPDATED, () => {
          const tracks = hls.audioTracks || [];
          if (!ctl || tracks.length < 2) return;
          const want = pickAudioIndex(tracks, loadAudioPref());
          if (want >= 0) hls.audioTrack = want;
          ctl.setAudio(tracks, hls.audioTrack >= 0 ? hls.audioTrack : 0, (i) => {
            hls.audioTrack = i;
            saveAudioPref(String(tracks[i]?.lang || "").toLowerCase().split("-")[0]);
          });
        });
        hls.on(Hls.Events.SUBTITLE_TRACKS_UPDATED, () => {
          const tracks = hls.subtitleTracks || [];
          if (!ctl || !tracks.length) return;
          const pref = loadSubPref();
          const want = pref && pref !== "off" ? pickAudioIndex(tracks, pref) : -1; // stessa ricerca per lingua
          hls.subtitleDisplay = want >= 0;
          hls.subtitleTrack = want;
          ctl.setSubs(tracks, want, (i) => {
            hls.subtitleDisplay = i >= 0;
            hls.subtitleTrack = i;
            saveSubPref(i >= 0 ? String(tracks[i]?.lang || "").toLowerCase().split("-")[0] || "on" : "off");
          });
        });
        hls.loadSource(streamSrc);
        hls.attachMedia(mediaEl);
      } else if (mediaEl.canPlayType("application/vnd.apple.mpegurl")) {
        mediaEl.src = streamSrc;
      } else {
        showPlayError("Il flusso HLS non è riproducibile qui. Usa «Apri su internet».");
      }
    });
  } else if (streamSrc) {
    mediaEl.src = streamSrc;
  }
  mediaEl.addEventListener("error", () => { if (!isHls || !hls) showPlayError("Impossibile riprodurre questo file. Prova «Apri su internet»."); });

  function applyResume() {
    if (resumeApplied) return;
    if (Number.isFinite(resumePos) && resumePos > 0) {
      try {
        mediaEl.currentTime = resumePos;
        resumeApplied = true;
      } catch {}
    } else {
      resumeApplied = true;
    }
  }

  mediaEl.addEventListener("loadedmetadata", () => {
    if (!resumeApplied) applyResume();
  });
  mediaEl.addEventListener("canplay", () => {
    if (!resumeApplied) applyResume();
  });
  if (!isHls) applyResume(); // con HLS la posizione si applica a loadedmetadata, a manifest caricato

  saveTimer = setInterval(() => {
    if (closed) {
      clearInterval(saveTimer);
      return;
    }
    if (mediaEl && !mediaEl.paused && !mediaEl.ended) {
      saveProgress();
    }
  }, 10000);

  mediaEl.addEventListener("pause", () => {
    if (!closed) saveProgress();
  });
  mediaEl.addEventListener("ended", () => {
    if (!closed) {
      const dur = Number(mediaEl.duration || item.duration || 0);
      saveProgress(dur > 0 ? dur : undefined);
    }
  });

  overlay.querySelector("#pm-open-ext")?.addEventListener("click", () => {
    try { mediaEl?.pause(); } catch {}
    openExternal(gs, item, target, apiPrefix);
  });
  overlay.querySelector("#pm-open-window")?.addEventListener("click", popOut);
  overlay.querySelector("#pm-close-x")?.addEventListener("click", closeOverlay);
  overlay.querySelector("#pm-close-btn")?.addEventListener("click", closeOverlay);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeOverlay(); });

  doc.body.appendChild(overlay);
  return { overlay, mediaEl, close: closeOverlay, saveProgress, browserPlayable: true };
}

/** Registra window.__pmPlay(item) usando gs. */
export function attachPlay(gs) {
  const win = typeof window !== "undefined" ? window : globalThis;
  win.__pmPlay = (item, onClose, opts) => play(gs, item, onClose, opts);
  return win.__pmPlay;
}
