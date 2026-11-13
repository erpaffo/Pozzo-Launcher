"use strict";
/* Pozzo Launcher - frontend: toast e impostazioni (info, salute, backup, profili, sync, scansione). Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ------------------------------------------------------------------ toast, impostazioni, splash */
let toastTimer = 0;
/* Annuncio per i lettori di schermo: #toast-live resta nel DOM (sr-only), il box visivo #toast viene nascosto con hidden e non e' una regione live. */
function toastLive(msg, err) {
  const live = $("#toast-live");
  if (live.parentElement !== overlayHost()) overlayHost().appendChild(live);
  live.setAttribute("role", err ? "alert" : "status");
  live.textContent = "";
  live.textContent = msg;
}

function toast(msg, err = false) {
  const t = $("#toast");
  if (t.parentElement !== overlayHost()) overlayHost().appendChild(t);
  t.textContent = msg;
  toastLive(msg, err);
  t.className = err ? "err" : "";
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), err ? 7000 : 3500);
}

function savedToast(undo, label = window.t("e.toast.saved")) {
  const t = $("#toast");
  if (t.parentElement !== overlayHost()) overlayHost().appendChild(t);
  t.className = "";
  toastLive(label, false);
  t.replaceChildren(document.createTextNode(label));
  if (undo) {
    t.append(" · ");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-undo";
    button.textContent = window.t("e.toast.undo");
    button.onclick = async () => {
      t.hidden = true;
      try { await undo(); } catch (e) { toast(e.message, true); }
    };
    t.appendChild(button);
  }
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 4000);
}

/* @errors-begin: codice d'errore -> messaggio e azione che lo risolve (le azioni usano le pagine di impostazioni gia' esistenti).
   Un nuovo codice del server si aggiunge qui; ERROR_PATTERNS lo riconosce anche dal solo testo di risposte senza `code`. */
const ERROR_ACTIONS = {
  emulator_missing: { text: "e.err.emulatorMissing", label: "e.err.setupEmulators", run: () => openSettings("emu") },
  rom_folder_missing: { text: "e.err.romFolderMissing",
    label: "e.err.relinkFolders", run: () => openSettings("scan") },
};
const ERROR_PATTERNS = [
  [/^Nessun emulatore configurato/, "emulator_missing"],
  [/^File del gioco non trovato|^Nessun file avviabile nella cartella/, "rom_folder_missing"],
];

/** Codice dell'errore: quello esplicito (`err.code`) se la tabella lo conosce, altrimenti dedotto dal testo; "" se non ce n'e'. */
function errorCode(err) {
  if (err && ERROR_ACTIONS[err.code]) return err.code;
  const msg = String((err && err.message) || err || "");
  const hit = ERROR_PATTERNS.find(([re]) => re.test(msg));
  return hit ? hit[1] : "";
}
/* @errors-end */

/** Toast d'errore che resta finche' non lo si chiude (role=alert), con il bottone dell'azione che risolve il problema. */
function failToast(code, details = {}) {
  const entry = ERROR_ACTIONS[code];
  const t = $("#toast");
  if (t.parentElement !== overlayHost()) overlayHost().appendChild(t);
  t.className = "err";
  t.setAttribute("role", "alert");
  t.replaceChildren(document.createTextNode(details.message || (entry && window.t(entry.text)) || window.t("e.err.failed")));
  const add = (label, onclick) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "toast-undo";
    b.textContent = label;
    b.onclick = onclick;
    t.append(" · ", b);
  };
  if (entry) add(window.t(entry.label), () => { t.hidden = true; entry.run(details); });
  add(window.t("e.toast.close"), () => { t.hidden = true; });
  t.hidden = false;
  clearTimeout(toastTimer);
}
if (window.GS) GS.fail = failToast;

/** Mostra un errore: persistente e con azione se il codice e' noto, altrimenti il toast normale. */
function toastError(err) {
  const code = errorCode(err);
  return code ? failToast(code, { message: err.message, ...(err.details || {}) }) : toast(err.message, true);
}

function autosaveControl(element, save) {
  if (!element) return;
  const read = () => element.type === "checkbox" ? element.checked : element.value;
  const write = (value) => { if (element.type === "checkbox") element.checked = value; else element.value = value; };
  let saved = read();
  element.addEventListener("focus", () => { saved = read(); });
  element.addEventListener("change", async () => {
    const previous = saved, next = read();
    try {
      await save(next);
      saved = next;
      savedToast(async () => { write(previous); await save(previous); saved = previous; });
    } catch (e) {
      write(previous);
      toast(e.message, true);
    }
  });
}

/* ------------------------------------------------------------------ impostazioni */
const SETTINGS_CATS = [
  ["generale", "Generale", "sliders"], ["aspetto", "Aspetto", "palette"], ["libreria", "Libreria", "books"],
  ["fonti", "Fonti dati", "database"], ["store", "Store e account", "store"], ["download", "Download", "download"], ["emulatori", "Emulatori e avvio", "gamepad"],
  ["controller", "Controller e telefono", "phone"], ["streaming", "Streaming", "wifi"],
  ["integrazioni", "Integrazioni", "link"], ["estensioni", "Estensioni", "puzzle"],
  ["dati", "Dati e backup", "backup"], ["sistema", "Sistema", "monitor"],
];
const SETTINGS_ICONS = {
  sliders: '<path d="M4 6h6m4 0h6M4 12h2m4 0h10M4 18h10m4 0h2"/><circle cx="12" cy="6" r="2"/><circle cx="8" cy="12" r="2"/><circle cx="16" cy="18" r="2"/>',
  palette: '<path d="M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1.4-3.4 1.5 1.5 0 0 1 1.1-2.6H18a3 3 0 0 0 3-3c0-5-4-9-9-9Z"/><circle cx="7.5" cy="11" r=".8"/><circle cx="10" cy="7.5" r=".8"/><circle cx="15" cy="8" r=".8"/>',
  books: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21V5.5Z"/><path d="M4 6h12v13M8 7v9m4-9v9"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/>',
  store: '<path d="M4 9h16l-1 12H5L4 9Z"/><path d="M8 9V6a4 4 0 0 1 8 0v3"/>',
  gamepad: '<path d="M7 8h10a4 4 0 0 1 3.8 5l-1 3.5a2 2 0 0 1-3.2 1L14 15h-4l-2.6 2.5a2 2 0 0 1-3.2-1L3.2 13A4 4 0 0 1 7 8Z"/><path d="M7 11v4m-2-2h4m6-1h.01M17 14h.01"/>',
  phone: '<rect x="6" y="2.5" width="12" height="19" rx="2"/><path d="M10 18.5h4"/>',
  wifi: '<path d="M3 9a14 14 0 0 1 18 0M6.5 12.5a9 9 0 0 1 11 0M10 16a4 4 0 0 1 4 0"/><circle cx="12" cy="19" r=".8"/>',
  link: '<path d="M10 13.5 8.5 15a3.5 3.5 0 0 1-5-5l3-3a3.5 3.5 0 0 1 5 0"/><path d="m14 10.5 1.5-1.5a3.5 3.5 0 0 1 5 5l-3 3a3.5 3.5 0 0 1-5 0"/><path d="m8.5 15 7-7"/>',
  puzzle: '<path d="M9 4a2.5 2.5 0 1 1 5 0v2h5v5h-2a2.5 2.5 0 1 0 0 5h2v4H8v-4H6a2.5 2.5 0 1 1 0-5h2V6h1V4Z"/>',
  backup: '<path d="M4 8h16v12H4zM7 8V5h10v3m-7 4h4"/><path d="m9 15 3 3 3-3m-3 3v-6"/>',
  download: '<path d="M12 4v11m-4.5-4.5L12 15l4.5-4.5"/><path d="M5 19h14"/>',
  monitor: '<rect x="3" y="3" width="18" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/><circle cx="12" cy="10" r="3"/><path d="M12 8.5v2"/>',
};

function settingsIcon(name) {
  return `<svg class="snav-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${SETTINGS_ICONS[name] || SETTINGS_ICONS.monitor}</svg>`;
}
const SETTINGS_ALIASES = {
  health: "sistema", about: "sistema", info: "sistema", scan: "libreria", src: "fonti",
  acc: "store", emu: "emulatori", remote: "controller", integ: "integrazioni",
  look: "aspetto", lib: "dati", downloads: "download",
};
const SET = { tab: "generale", emu: null, preview: null, platforms: null, extraEmus: [], lastStatus: null };

function settingsCategory(id) {
  id = SETTINGS_ALIASES[id] || id;
  return SETTINGS_CATS.find(([key]) => key === id) || null;
}

async function loadSettingsMarkup() {
  const body = $("#settings-body");
  await Promise.all(SETTINGS_CATS.map(async ([id]) => {
    const pane = document.createElement("section");
    pane.className = "settings-pane";
    pane.dataset.pane = id;
    pane.hidden = true;
    body.appendChild(pane);
    const response = await fetch(`/static/settings/${id}.html?v=${encodeURIComponent(document.documentElement.dataset.v || "")}`);
    if (!response.ok) throw new Error(t("e.settings.loadFailed", { id, status: response.status }));
    pane.innerHTML = await response.text();
  }));
  const test = $("#pads-test-btn"), slot = $("#pads-test-setting");
  if (test && slot) slot.replaceWith(settingsRow(
    t("e.pads.title"),
    t("e.pads.desc"),
    test,
  ));
  renderSettingsNav();
}

function settingsRow(title, description, control, status) {
  const row = document.createElement("div");
  row.className = "srow";
  const text = document.createElement("div");
  text.className = "srow-txt";
  const heading = document.createElement("div");
  heading.className = "srow-title";
  heading.textContent = title;
  const detail = document.createElement("div");
  detail.className = "srow-desc";
  detail.textContent = description;
  text.append(heading, detail);
  row.append(text, control);
  if (status) row.append(status);
  return row;
}

function renderSettingsNav() {
  const nav = $("#settings-nav");
  const pluginTabs = GS.ui.settingsTabs || [];
  nav.innerHTML = SETTINGS_CATS.map(([id, label, icon]) => {
    const children = pluginTabs.filter((t) => (settingsCategory(t.category)?.[0] || "estensioni") === id);
    const badge = id === "sistema" ? `<i class="dot-issue" id="settings-alert" hidden></i>` : "";
    return `<button type="button" class="snav-item" data-category="${id}"><span class="ico">${settingsIcon(icon)}</span>`
      + `<span class="lbl">${t("e.cat." + id)}</span>${badge}</button>`
      + (children.length ? `<div class="snav-kids">${children.map((t) => `<button type="button" class="snav-item kid" data-category="ext:${esc(t.id)}">`
        + `<span class="ico">${settingsIcon("puzzle")}</span><span class="lbl">${esc(t.label)}</span></button>`).join("")}</div>` : "");
  }).join("");
  for (const t of pluginTabs) {
    const id = `ext:${t.id}`;
    if (document.querySelector(`[data-pane="${CSS.escape(id)}"]`)) continue;
    const pane = document.createElement("section");
    pane.className = "settings-pane";
    pane.dataset.pane = id;
    pane.hidden = true;
    $("#settings-body").appendChild(pane);
  }
}

function settingsOpen() {
  const page = $("#settings-page");
  return !!page && !page.hidden;
}

function settingsActive(id) {
  return settingsOpen() && SET.tab === id && !!document.querySelector(`#settings-body [data-pane="${CSS.escape(id)}"]`);
}

function openSettings(tab) {
  const id = settingsCategory(typeof tab === "string" ? tab : SET.tab)?.[0]
    || (typeof tab === "string" && tab.startsWith("ext:") ? tab : "generale");
  if (!settingsOpen() || SET.tab !== id) history.pushState({ settings: id }, "", `#settings/${id}`);
  showTab(id);
}

function closeSettings() {
  uiPreviewOff();
  $("#settings-page").hidden = true;
  document.body.classList.remove("settings-open");
  stopPadTest();
  watchStatusStop();
  if (location.hash.startsWith("#settings")) history.replaceState(null, "", location.pathname + location.search);
}

function showTab(tab) {
  stopPadTest();
  uiPreviewOff(); // anteprime di temi e colori non salvate: si annullano uscendo da Aspetto
  watchStatusStop();
  const id = settingsCategory(tab)?.[0] || (tab.startsWith("ext:") ? tab : "generale");
  renderSettingsNav();
  const page = $("#settings-page");
  page.hidden = false;
  document.body.classList.add("settings-open");
  setDrawer(false, false);
  SET.tab = id;
  $("#settings-search").value = "";
  $("#settings-results").hidden = true;
  $("#settings-body").hidden = false;
  document.querySelectorAll("#settings-nav [data-category]").forEach((b) => {
    const active = b.dataset.category === id;
    b.classList.toggle("active", active);
    if (active) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  document.querySelectorAll("#settings-body [data-pane]").forEach((p) => { p.hidden = p.dataset.pane !== id; });
  const pane = document.querySelector(`#settings-body [data-pane="${CSS.escape(id)}"]`);
  if (id.startsWith("ext:")) {
    const ext = GS.ui.settingsTabs.find((x) => `ext:${x.id}` === id);
    if (ext && pane) {
      pane.innerHTML = "";
      Promise.resolve(ext.render(pane, GS)).catch((e) => { pane.textContent = e.message; });
    }
  }
  $("#settings-title").textContent = id.startsWith("ext:")
    ? (GS.ui.settingsTabs.find((x) => `ext:${x.id}` === id)?.label || t("e.settings.extension"))
    : t("e.cat." + id);
  $("#settings-body").scrollTop = 0;
  if (id === "generale") { loadPower(); loadNotify(); loadWebhooks(); loadGlobalScripts(); loadProfilesSettings(); loadHints(); loadTour(); }
  else if (id === "download") loadDownloadSettings();
  else if (id === "sistema") { loadHealth(); loadAbout(); loadSystemErrors(); }
  else if (id === "libreria") { loadScan(); loadSources(); renderCustomConsoles(); watchStatusStart(); api("/api/status").then(showStatus); }
  else if (id === "fonti") { loadSources(); pollHltb(); pollCollart(); }
  else if (id === "store") { loadAccounts(); loadPcStores(); loadSteamExport(); }
  else if (id === "emulatori") loadEmu();
  else if (id === "controller" || id === "streaming") { loadRemote(); if (id === "controller") loadLibShare(); }
  else if (id === "integrazioni") loadIntegrations();
  else if (id === "aspetto" || id === "estensioni") { loadAppearance(); if (id === "aspetto") initUiPrefs(); }
  else if (id === "dati") { loadBackups(); loadSync(); loadSaveDir(); loadMaintenance(); }
  else if (id.startsWith("ext:")) stopPadTest();
  refreshSettingsHealth();
}

/* ------------------------------------------------------------------ Aspetto: zoom, densita', salvaschermo, editor del tema
 * Logica pura in GSUi (core.js). Valori in localStorage "gs.ui" / "gs.userTheme" (dispositivo): vedi il commento in core.js. */
const UI_TOKEN_LABELS = { bg: "e.token.bg", "bg-2": "e.token.bg2", "bg-3": "e.token.bg3", panel: "e.token.panel", line: "e.token.line", text: "e.token.text",
  muted: "e.token.muted", accent: "e.token.accent", "accent-2": "e.token.accent2", fav: "e.token.fav" };
const UI_ED = { name: "Il mio tema", tokens: null, themes: null };

function uiSavePrefs(part) {
  const next = { ...GSUi.prefs(GSUi.saved()), ...part };
  store.set("ui", next);
  if (JSON.stringify(GSUi.saved()) !== JSON.stringify(next)) throw new Error(t("e.prefs.saveFailed"));
  GSUi.applyPrefs(document, next);
  window.dispatchEvent(new Event("gs-ui-change"));
}

/** Toglie le anteprime (editor colori e tema al passaggio del mouse) e rimette il tema utente salvato. */
function uiHoverOff() {
  document.getElementById("gs-theme-hover")?.remove();
  const mine = document.getElementById("gs-user-theme");
  if (mine) mine.media = "all";
}
function uiPreviewOff() {
  GSUi.setStyle(document, "gs-user-theme-preview", "");
  uiHoverOff();
}

function uiEditorTokens() {
  if (UI_ED.tokens) return UI_ED.tokens;
  const saved = GSUi.savedTheme();
  const cs = getComputedStyle(document.documentElement);
  UI_ED.tokens = saved ? { ...saved.tokens } : Object.fromEntries(GSUi.TOKENS.map((k) => [k, GSUi.toHex(cs.getPropertyValue("--" + k)) || "#808080"]));
  if (saved) UI_ED.name = saved.name;
  return UI_ED.tokens;
}

function uiEditorPaint(preview = true) {
  const t = UI_ED.tokens;
  if (preview) GSUi.setStyle(document, "gs-user-theme-preview", GSUi.themeCss(t));
  $("#te-contrast").innerHTML = GSUi.contrastReport(t).map((c) => `<li class="${c.ok ? "status-ok" : "status-bad"}">`
    + `${c.ok ? "?" : "?"} ${window.t("e.contrast.item", { fg: esc(window.t(UI_TOKEN_LABELS[c.fg])), bg: esc(window.t(UI_TOKEN_LABELS[c.bg])), ratio: c.ratio, min: c.min })}</li>`).join("");
}

function uiEditorBuild() {
  const t = uiEditorTokens();
  $("#te-name").value = UI_ED.name;
  $("#te-tokens").innerHTML = GSUi.TOKENS.map((k) => {
    const [h, s, l] = GSUi.hexToHsl(t[k]);
    const range = (n, max, v, lbl) => `<label class="small">${lbl} <input type="range" data-hsl="${n}" min="0" max="${max}" value="${v}" aria-label="${esc(window.t(UI_TOKEN_LABELS[k]))} ${lbl}"></label>`;
    return `<div class="srow" data-token="${k}"><span class="sw" style="width:28px;height:28px;border-radius:6px;border:1px solid var(--line);background:${t[k]}"></span>`
      + `<div class="srow-txt"><div class="srow-title">${esc(window.t(UI_TOKEN_LABELS[k]))}</div></div>`
      + `<div class="row">${range(0, 360, h, "H")}${range(1, 100, s, "S")}${range(2, 100, l, "L")}</div></div>`;
  }).join("");
  uiEditorPaint(false); // aprire l'editor non cambia l'aspetto: l'anteprima parte alla prima modifica o importazione
}

async function uiThemeHover(card, on) {
  const id = card?.querySelector("input")?.value;
  if (!on || !id) return uiHoverOff();
  try { UI_ED.themes = UI_ED.themes || (await api("/api/extensions")).themes; } catch { return; }
  if (!card.matches(":hover, :focus-within")) return; // nel frattempo il puntatore e' uscito
  const css = UI_ED.themes.find((x) => x.id === id)?.desktop;
  uiHoverOff();
  if (!css) return;
  const link = document.createElement("link");
  link.id = "gs-theme-hover"; link.rel = "stylesheet"; link.href = css;
  document.head.appendChild(link);
  const mine = document.getElementById("gs-user-theme");
  if (mine) mine.media = "not all"; // il tema utente coprirebbe l'anteprima
}

function initUiPrefs() {
  const p = GSUi.prefs(GSUi.saved());
  const fill = (id, opts, value, save) => {
    const el = $(id);
    el.innerHTML = opts.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("");
    el.value = String(value);
    if (!el.dataset.bound) { el.dataset.bound = "1"; autosaveControl(el, save); }
  };
  const zoom = $("#ui-zoom"), zoomOut = $("#ui-zoom-out");
  zoom.value = p.zoom; zoomOut.textContent = `${p.zoom}%`;
  if (!zoom.dataset.bound) {
    zoom.dataset.bound = "1";
    zoom.addEventListener("input", () => { zoomOut.textContent = `${zoom.value}%`; });
    autosaveControl(zoom, (v) => uiSavePrefs({ zoom: +v })); // salva al rilascio (change) e permette di annullare
    zoom.addEventListener("change", () => { zoomOut.textContent = `${zoom.value}%`; });
  }
  const ca = $("#ui-cover-accent");
  ca.checked = p.coverAccent;
  if (!ca.dataset.bound) { ca.dataset.bound = "1"; autosaveControl(ca, (v) => uiSavePrefs({ coverAccent: !!v })); }
  const vs = $("#ui-video-snap");
  if (!vs.dataset.bound) {
    vs.dataset.bound = "1";
    api("/api/app/video-snap").then((r) => { vs.checked = !!r.enabled; }).catch(() => {});
    autosaveControl(vs, async (v) => { await api("/api/app/video-snap", { body: { enabled: !!v } }); GSVideo.reset(); });
  }
  fill("#ui-density", [["comfortable", t("e.density.comfortable")], ["compact", t("e.density.compact")]], p.density, (v) => uiSavePrefs({ density: v }));
  const dlList = $("#detail-layout-list");
  if (dlList) {
    const dlOpts = [
      ["cockpit", t("e.detailLayout.cockpit"), `<div class="dl-preview dl-preview--cockpit" aria-hidden="true">
        <div class="dl-pv-rail"><span class="dl-pv-cov"></span><span class="dl-pv-cta"></span><span class="dl-pv-box"></span></div>
        <div class="dl-pv-main"><span class="dl-pv-top"></span><span class="dl-pv-tabs"><i></i><i></i><i></i></span><span class="dl-pv-body"></span></div>
      </div>`],
      ["editorial", t("e.detailLayout.editorial"), `<div class="dl-preview dl-preview--editorial" aria-hidden="true">
        <div class="dl-pv-main"><span class="dl-pv-top"></span><span class="dl-pv-acc"></span><span class="dl-pv-acc"></span><span class="dl-pv-acc"></span></div>
        <div class="dl-pv-aside"><span class="dl-pv-cta"></span><span class="dl-pv-box"></span><span class="dl-pv-box"></span></div>
      </div>`],
      ["classic", t("e.detailLayout.classic"), `<div class="dl-preview dl-preview--classic" aria-hidden="true">
        <div class="dl-pv-main"><span class="dl-pv-top"></span><span class="dl-pv-pills"><i></i><i></i><i></i><i></i></span><span class="dl-pv-body"></span></div>
      </div>`],
    ];
    dlList.innerHTML = dlOpts.map(([val, label, preview]) => `<label class="experience-choice">
      <span><input type="radio" name="detailLayout" value="${esc(val)}" ${p.detailLayout === val ? "checked" : ""}><b>${esc(label)}</b></span>
      ${preview}</label>`).join("");
    if (!dlList.dataset.bound) {
      dlList.dataset.bound = "1";
      dlList.addEventListener("change", (e) => {
        if (e.target.name === "detailLayout") uiSavePrefs({ detailLayout: e.target.value });
      });
    }
  }
  fill("#ui-idle", GSUi.IDLE.map((m) => [m, m ? t("e.idle.minutes", { m }) : t("e.idle.off")]), p.idle, (v) => uiSavePrefs({ idle: +v }));

  const msg = (s, err) => { const m = $("#te-msg"); m.textContent = s; m.className = err ? "status-bad small" : "muted small"; };
  const enabled = $("#te-enabled");
  enabled.checked = !!GSUi.savedTheme()?.enabled;
  enabled.disabled = !GSUi.savedTheme();
  uiEditorBuild();
  if ($("#te-save").dataset.bound) return;
  $("#te-save").dataset.bound = "1";

  const persist = (theme) => {
    store.set("userTheme", theme);
    if (JSON.stringify(GSUi.savedTheme()) !== JSON.stringify(theme && { enabled: theme.enabled, name: theme.name, tokens: theme.tokens })) throw new Error(t("e.theme.saveFailed"));
    uiPreviewOff();
    GSUi.applyTheme(document);
    enabled.checked = !!theme?.enabled; enabled.disabled = !theme;
  };
  $("#te-tokens").addEventListener("input", (e) => {
    const row = e.target.closest("[data-token]");
    if (!row || !e.target.dataset.hsl) return;
    const [h, s, l] = [...row.querySelectorAll("input")].map((i) => +i.value);
    const hex = GSUi.hslToHex(h, s, l);
    UI_ED.tokens[row.dataset.token] = hex;
    row.querySelector(".sw").style.background = hex;
    uiEditorPaint();
  });
  $("#te-name").addEventListener("input", (e) => { UI_ED.name = e.target.value; });
  $("#te-revert").onclick = () => { UI_ED.tokens = null; uiPreviewOff(); uiEditorBuild(); msg(t("e.theme.previewCanceled")); };
  $("#te-save").onclick = () => {
    try {
      const theme = GSUi.checkTheme({ format: "pozzo-theme", version: 1, name: UI_ED.name, tokens: UI_ED.tokens });
      const bad = GSUi.contrastReport(theme.tokens).filter((c) => !c.ok);
      if (bad.length) throw new Error(t("e.theme.lowContrast"));
      persist({ enabled: true, ...theme });
      msg(t("e.theme.saved", { name: theme.name }));
    } catch (err) { msg(err.message, true); }
  };
  $("#te-export").onclick = () => {
    try {
      const theme = GSUi.checkTheme({ format: "pozzo-theme", version: 1, name: UI_ED.name, tokens: UI_ED.tokens });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([GSUi.serializeTheme(theme.name, theme.tokens)], { type: "application/json" }));
      a.download = `${theme.name.replace(/[^\w-]+/g, "_")}.pozzo-theme.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (err) { msg(err.message, true); }
  };
  $("#te-import").onchange = async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    try {
      if (f.size > 4096) throw new Error(t("e.theme.fileInvalid"));
      const theme = GSUi.parseTheme(await f.text());
      UI_ED.name = theme.name; UI_ED.tokens = theme.tokens;
      uiEditorBuild();
      uiEditorPaint();
      msg(t("e.theme.imported", { name: theme.name }));
    } catch (err) { msg(err.message, true); }
  };
  $("#te-remove").onclick = () => { try { persist(null); UI_ED.tokens = null; uiEditorBuild(); msg(t("e.theme.removed")); } catch (err) { msg(err.message, true); } };
  autosaveControl(enabled, (on) => { const t = GSUi.savedTheme(); if (!t) throw new Error(window.t("e.theme.noneSaved")); persist({ ...t, enabled: on }); });
  const list = $("#theme-list");
  list.addEventListener("mouseover", (e) => { const c = e.target.closest(".theme-card"); if (c) uiThemeHover(c, true); });
  list.addEventListener("focusin", (e) => { const c = e.target.closest(".theme-card"); if (c) uiThemeHover(c, true); });
  list.addEventListener("mouseleave", uiHoverOff);
  list.addEventListener("focusout", uiHoverOff);
  list.addEventListener("click", (e) => { if (e.target.closest(".theme-card")) uiHoverOff(); });
}

function initSettingsLayout() {
  $("#settings-back").onclick = closeSettings;
  $("#settings-nav").addEventListener("click", (e) => {
    const button = e.target.closest("[data-category]");
    if (button) {
      const id = button.dataset.category;
      history.pushState({ settings: id }, "", `#settings/${id}`);
      showTab(id);
    }
  });
  $("#settings-search").addEventListener("input", (e) => searchSettings(e.target.value));
  $("#settings-results").addEventListener("click", (e) => {
    const result = e.target.closest("[data-settings-category]");
    if (!result) return;
    const category = result.dataset.settingsCategory;
    history.pushState({ settings: category }, "", `#settings/${category}`);
    showTab(category);
    const target = document.getElementById(result.dataset.settingsTarget);
    target?.scrollIntoView({ block: "center" });
    target?.classList.add("flash");
    setTimeout(() => target?.classList.remove("flash"), 1200);
  });
  $("#settings-page").addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if ($("#settings-search").value) {
        $("#settings-search").value = "";
        $("#settings-results").hidden = true;
        $("#settings-body").hidden = false;
      } else closeSettings();
    }
  });
  window.addEventListener("popstate", () => {
    const match = location.hash.match(/^#settings(?:\/([a-z0-9:_-]+))?$/i);
    if (match) showTab(match[1] || "generale");
    else closeSettings();
  });
  bindSystemErrorButtons();
}

function searchSettings(query) {
  const results = $("#settings-results");
  query = query.trim().toLocaleLowerCase(GSI18n.lang);
  if (!query) {
    results.hidden = true;
    $("#settings-body").hidden = false;
    results.innerHTML = "";
    return;
  }
  const found = [];
  for (const [id, label] of SETTINGS_CATS) {
    const pane = document.querySelector(`#settings-body [data-pane="${CSS.escape(id)}"]`);
    if (!pane) continue;
    for (const el of pane.querySelectorAll("h3, h4, label, .srow-title")) {
      const text = el.textContent.replace(/\s+/g, " ").trim();
      if (!text.toLocaleLowerCase(GSI18n.lang).includes(query)) continue;
      let target = el.id || el.querySelector("input,select,textarea")?.id;
      if (!target) {
        target = `settings-search-${found.length}`;
        el.id = target;
      }
      found.push({ id, label, text, target });
    }
  }
  results.innerHTML = found.length ? found.map((x) => `<button class="sres" type="button" data-settings-category="${x.id}" data-settings-target="${esc(x.target)}">`
    + `<span class="sres-cat">${esc(t("e.cat." + x.id))}</span>${esc(x.text)}</button>`).join("") : `<p class="muted">${t("e.search.none")}</p>`;
  results.hidden = false;
  $("#settings-body").hidden = true;
}

function refreshSettingsHealth() {
  const dot = $("#settings-alert");
  if (!dot) return;
  api("/api/health").then((d) => {
    const count = (d.items || []).filter((x) => x.level === "warn" || x.level === "error").length;
    dot.hidden = !count;
    dot.title = count ? t("e.health.issues", { n: count }) : "";
  }).catch((e) => console.warn("Stato salute non disponibile:", e));
}

/* ---- impostazioni › integrazioni (Discord) */
function renderIntegrations(d) {
  const dc = (d && d.discord) || {};
  $("#dc-on").checked = !!dc.enabled;
  $("#dc-time").checked = dc.show_time !== false;
  if (dc.client_id) $("#dc-id").value = dc.client_id;
  let html;
  if (!dc.enabled) html = `<span class="muted">${t("e.discord.off")}</span>`;
  else if (!dc.client_id) html = `<span class="status-bad">${t("e.discord.noId")}</span>`;
  else if (dc.connected) html = `✅ <b>${t("e.discord.connected")}</b>${dc.playing ? ` · ${t("e.discord.playing", { game: esc(dc.playing) })}` : ""}`;
  else {
    html = `<span class="status-bad">${t("e.discord.notConnected", { error: esc(dc.error || t("e.discord.noResponse")) })}</span>`
      + ` <span class="muted small">${t("e.discord.openClient")}</span>`;
  }
  if (d && d.log_file) html += `<br><span class="muted small">${t("e.discord.logFile", { file: esc(d.log_file) })}</span>`;
  $("#dc-state").innerHTML = html;
}

async function loadIntegrations() {
  try { renderIntegrations(await api("/api/integrations")); } catch (e) { toast(e.message, true); }
}

function loadHints() {
  const sel = $("#hint-mode"), h = GS.hints?.settings;
  if (!sel || !h) return;
  sel.value = h.mode();
  if (sel.dataset.bound) return;
  sel.dataset.bound = "1";
  sel.addEventListener("change", () => h.setMode(sel.value));
  $("#hint-reset").addEventListener("click", () => { h.resetSeen(); toast(t("e.hints.reset")); });
}

function loadTour() {
  const auto = $("#tour-auto"), t = GS.tour;
  if (!auto || !t) return;
  auto.checked = t.settings.auto();
  if (auto.dataset.bound) return;
  auto.dataset.bound = "1";
  auto.addEventListener("change", () => t.settings.setAuto(auto.checked));
  $("#tour-start").addEventListener("click", () => {
    if (settingsOpen()) closeSettings();
    setTimeout(() => t.start({ manual: true }), 150);
  });
}

async function loadNotify() {
  try {
    const n = await api("/api/app/notify");
    $("#nt-on").checked = !!n.enabled;
    $("#bp-start").checked = !!(await api("/api/app/start-bigpicture")).enabled;
    const rss = $("#resume-session-start");
    if (rss) rss.checked = store.get("resumeSession", true);
    $("#nt-state").textContent = n.available ? "" : t("e.notify.windowsOnly");
  } catch (e) { toast(e.message, true); }
}

/* ---- webhook in uscita: una riga per webhook, salvate tutte insieme */
const WH_EVENTS = [["gioco_avviato", "e.wh.gameStarted"], ["gioco_chiuso", "e.wh.gameClosed"],
  ["download_finito", "e.wh.downloadDone"], ["prezzo_sceso", "e.wh.priceDrop"]];
function whRow(h = {}) {
  const row = document.createElement("div");
  row.className = "wh-row";
  row.dataset.orig = h.url || "";  // il server ritrova il segreto salvato da qui: non arriva mai al browser
  row.innerHTML = `<div class="row wrap">
      <input type="url" class="wh-url" placeholder="https://..." aria-label="${t("e.wh.urlAria")}" value="${esc(h.url || "")}">
      <label class="chk"><input type="checkbox" class="wh-on"${h.enabled === false ? "" : " checked"}> ${t("e.wh.active")}</label></div>
    <div class="row wrap">${WH_EVENTS.map(([id, label]) => `<label class="chk"><input type="checkbox" class="wh-ev" value="${id}"${(h.events || []).includes(id) ? " checked" : ""}> ${t(label)}</label>`).join("")}</div>
    <div class="row wrap"><input type="password" class="wh-secret" placeholder="${h.has_secret ? t("e.wh.secretSet") : t("e.wh.secretOptional")}" aria-label="${t("e.wh.secretAria")}" autocomplete="new-password">
      ${h.has_secret ? `<label class="chk"><input type="checkbox" class="wh-clear"> ${t("e.wh.clearSecret")}</label>` : ""}
      <button class="btn wh-test" type="button">${t("e.wh.test")}</button> <button class="btn wh-del" type="button">${t("e.wh.remove")}</button></div>`;
  return row;
}
function whSecret(row) {  // campo vuoto = il server tiene il segreto salvato
  return { orig: row.dataset.orig, secret: row.querySelector(".wh-secret").value, clear_secret: !!row.querySelector(".wh-clear")?.checked };
}
function whCollect() {
  return [...document.querySelectorAll("#wh-list .wh-row")].map((row) => ({
    url: row.querySelector(".wh-url").value.trim(),
    events: [...row.querySelectorAll(".wh-ev:checked")].map((c) => c.value),
    ...whSecret(row),
    enabled: row.querySelector(".wh-on").checked,
  }));
}
async function loadWebhooks() {
  const list = $("#wh-list");
  if (!list) return;
  if (!list.dataset.bound) {
    list.dataset.bound = "1";
    $("#wh-add").addEventListener("click", () => {
      const row = whRow();
      list.appendChild(row);
      row.querySelector(".wh-url").focus();
    });
    $("#wh-save").addEventListener("click", async () => {
      try {
        const r = await api("/api/webhooks", { body: { webhooks: whCollect() } });
        list.innerHTML = "";
        r.webhooks.forEach((h) => list.appendChild(whRow(h)));  // indirizzi originali e «segreto impostato» aggiornati
        $("#wh-state").textContent = t("e.wh.saved", { n: r.webhooks.length });
        toast(t("e.wh.savedToast"));
      } catch (e) { toast(e.message, true); }
    });
    list.addEventListener("click", async (e) => {
      const row = e.target.closest(".wh-row");
      if (!row) return;
      if (e.target.closest(".wh-del")) return row.remove();
      if (!e.target.closest(".wh-test")) return;
      const btn = e.target.closest(".wh-test");
      btn.disabled = true;
      try {
        const r = await api("/api/webhooks/test", { body: { url: row.querySelector(".wh-url").value.trim(), ...whSecret(row) } });
        toast(r.msg, !r.ok);
      } catch (err) { toast(err.message, true); }
      finally { btn.disabled = false; }
    });
  }
  try {
    const d = await api("/api/webhooks");
    list.innerHTML = "";
    d.webhooks.forEach((h) => list.appendChild(whRow(h)));
  } catch (e) { toast(e.message, true); }
}

/* ---- script globali: un comando per evento */
const GS_EVENTS = ["game_started", "game_stopped", "download_finished"];
async function loadGlobalScripts() {
  if (!$("#gs-save")) return;
  if (!$("#gs-save").dataset.bound) {
    $("#gs-save").dataset.bound = "1";
    $("#gs-save").addEventListener("click", async () => {
      try {
        await api("/api/app/scripts", { body: Object.fromEntries(GS_EVENTS.map((e) => [e, $(`#gs-${e}`).value])) });
        toast(t("e.gs.saved"));
      } catch (e) { toast(e.message, true); }
    });
  }
  try {
    const d = await api("/api/app/scripts");
    GS_EVENTS.forEach((e) => { $(`#gs-${e}`).value = d[e] || ""; });
  } catch (e) { toast(e.message, true); }
}

/* ---- prova controller: ultimo stato ricevuto da ogni telefono (la scheda «Telefono e streaming») */
let padTestT = 0;
function stopPadTest() { clearTimeout(padTestT); padTestT = 0; }
function startPadTest() {
  stopPadTest();
  const tick = async () => {
    const box = $("#pads-test");
    if (!box || box.hidden || !settingsActive("controller")) return stopPadTest();
    try { renderPads(await api("/api/phone/pads")); } catch (e) { box.textContent = e.message; }
    padTestT = setTimeout(tick, 400);
  };
  tick();
}
const PAD_BTN_LABEL = { a: "A", b: "B", x: "X", y: "Y", lb: "LB", rb: "RB", ls: "L3", rs: "R3",
  up: "▲", down: "▼", left: "◀", right: "▶", start: "Start", back: "Select", guide: "Guide" };
function renderPads(d) {
  const box = $("#pads-test");
  if (!box) return;
  const pads = d.pads || [];
  if (!pads.length) { box.innerHTML = `<p class="muted small">${t("e.pads.none")}</p>`; return; }
  const dot = (x, y) => `<i style="left:${50 + x * 45}%;top:${50 - y * 45}%"></i>`;
  box.innerHTML = pads.map((p) => `<div class="pad-t" style="--pc:${esc(p.color)}">
    <div><b>${t("e.pads.player", { n: p.player })}</b> <span class="muted small">${esc(p.name)}${p.motion ? " · 🌀" : ""}${p.connected ? "" : ` · ${t("e.pads.notActive")}`}</span></div>
    <div class="pad-k">${Object.entries(PAD_BTN_LABEL).map(([k, l]) => `<i class="${p.buttons.includes(k) ? "on" : ""}">${l}</i>`).join("")}</div>
    <div class="pad-x"><span class="stick">${dot(p.lx, p.ly)}</span><span class="stick">${dot(p.rx, p.ry)}</span>
      <label class="trig">LT<i><b style="width:${Math.round(p.lt * 100)}%"></b></i></label>
      <label class="trig">RT<i><b style="width:${Math.round(p.rt * 100)}%"></b></i></label>
      <button class="btn" type="button" data-pad-rumble="${p.slot}">${t("e.pads.rumble")}</button></div>
  </div>`).join("");
}

/* ---- al termine delle operazioni: sospendi o spegni il PC */
async function loadPower() {
  try {
    const p = await api("/api/app/power");
    $("#pw-after").value = p.after_jobs || "none";
    $("#pw-abort").hidden = !p.seconds;
    $("#pw-state").textContent = p.seconds ? t("e.power.countdown", { mode: p.mode === "sleep" ? t("e.power.sleep") : t("e.power.shutdown"), s: p.seconds }) : "";
  } catch { /* niente */ }
}

/* ---- info: versione, aggiornamenti, novita' */
/** Markdown minimo del changelog (titoli, elenchi, grassetto, codice). Il testo e' sempre passato da esc() prima. */
function miniMd(md) {
  const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  let html = "", list = false;
  for (const raw of md.split("\n")) {
    const l = raw.trimEnd();
    const li = /^\s*- (.*)/.exec(l), cont = list && /^\s{2,}\S/.test(l);
    if (cont) { html = html.replace(/<\/li>$/, " " + inline(l.trim()) + "</li>"); continue; }
    if (list && !li) { html += "</ul>"; list = false; }
    if (li) { if (!list) { html += "<ul>"; list = true; } html += `<li>${inline(li[1])}</li>`; }
    else if (l.startsWith("### ")) html += `<h5>${inline(l.slice(4))}</h5>`;
    else if (l.startsWith("## ")) html += `<h4>${inline(l.slice(3))}</h4>`;
    else if (l.startsWith("# ")) continue;
    else if (l) html += `<p>${inline(l)}</p>`;
  }
  return html + (list ? "</ul>" : "");
}

async function loadStorage(force = false) {
  const box = $("#storage-box");
  box.innerHTML = `<span class="muted">${t("e.storage.computing")}</span>`;
  try {
    const d = await api(`/api/storage${force ? "?force=1" : ""}`);
    const tbl = (head, rows) => `<table class="tbl"><thead><tr>${head.map((h, i) => `<th${i ? ' style="text-align:right"' : ""}>${h}</th>`).join("")}</tr></thead>`
      + `<tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i ? ' style="text-align:right"' : ""}>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    const n = (x) => x.toLocaleString(GSI18n.lang);
    box.innerHTML = `<p>${t("e.storage.folder")} <code>${esc(d.path)}</code> · <b>${esc(fmtSize(d.total))}</b></p>`
      + `<h5>${t("e.storage.perFolder")}</h5>` + tbl([t("e.col.folder"), t("e.col.file"), t("e.col.size")], d.folders.map((f) => [esc(f.name), n(f.files), esc(fmtSize(f.bytes))]))
      + `<h5>${t("e.storage.perConsole")}</h5>` + tbl([t("e.col.console"), t("e.storage.media"), t("e.storage.db"), t("e.storage.catalog"), t("e.storage.total")],
          d.platforms.map((p) => [esc(platName(p.id)), `${esc(fmtSize(p.media))} · ${t("e.storage.fileCount", { n: n(p.files) })}`,
            `${esc(fmtSize(p.db))} · ${t("e.storage.entryCount", { n: n(p.rows) })}`, p.entries ? `${esc(fmtSize(p.catalog))} · ${t("e.storage.listCount", { n: n(p.entries) })}` : "—", esc(fmtSize(p.total))]))
      + `<h5>${t("e.storage.perSource")}</h5>` + tbl([t("e.col.source"), t("e.col.entries"), t("e.col.size")], d.sources.map((s) => [esc(s.source), n(s.rows), esc(fmtSize(s.bytes))]))
      + `<h5>${t("e.storage.storeAndOther")}</h5>` + tbl([t("e.storage.data"), t("e.col.entries"), t("e.col.size")], d.kv.map((k) => [esc(k.label), n(k.rows), esc(fmtSize(k.bytes))]))
      + `<h5>${t("e.storage.database")}</h5>` + tbl([t("e.col.file"), t("e.col.size")], Object.entries(d.files).map(([k, v]) => [esc(k), esc(fmtSize(v))]));
  } catch (e) { box.innerHTML = ""; toast(e.message, true); }
}

async function loadCacheSources() {
  const box = $("#csrc-box");
  try {
    const d = (await api("/api/cache/sources")).sources;
    const day = (t) => (t ? new Date(t * 1000).toLocaleDateString(GSI18n.lang) : "—");
    const row = ([id, s]) => `<tr><td>${esc(id === "launchbox" ? t("e.cache.launchbox") : id === "hltb" ? "HowLongToBeat" : id)}</td>`
      + `<td style="text-align:right">${s.rows.toLocaleString(GSI18n.lang)}</td><td style="text-align:right">${esc(fmtSize(s.bytes))}</td>`
      + `<td style="text-align:right">${id === "launchbox" ? (s.rows || s.bytes ? t("e.cache.updated", { date: day(s.updated), days: s.days_left }) : t("e.cache.notDownloaded")) : t("e.cache.expired", { n: s.expired })}</td>`
      + `<td><button class="btn" data-csrc="${esc(id)}">${t("e.cache.clear")}</button></td></tr>`;
    box.innerHTML = `<table class="tbl"><thead><tr><th>${t("e.col.source")}</th><th style="text-align:right">${t("e.col.entries")}</th><th style="text-align:right">${t("e.col.size")}</th><th style="text-align:right">${t("e.col.status")}</th><th></th></tr></thead><tbody>`
      + Object.entries(d).map(row).join("") + `</tbody></table>`;
    box.querySelectorAll("[data-csrc]").forEach((b) => { b.onclick = () => clearCacheSource(b.dataset.csrc); });
  } catch (e) { box.innerHTML = ""; toast(e.message, true); }
}

async function clearCacheSource(source) {
  try {
    const r = await api("/api/cache/sources/clear", { body: source ? { source } : {} });
    toast(t("e.cache.cleared", { n: r.removed }));
    loadCacheSources();
  } catch (e) { toast(e.message, true); }
}

async function loadAbout() {
  try {
    const a = await api("/api/about");
    $("#about-ver").textContent = a.version;
    $("#about-data").textContent = t("e.about.dataIn", { dir: a.data_dir });
    $("#about-log").innerHTML = a.changelog ? miniMd(a.changelog) : `<p class="muted">${t("e.about.noChangelog")}</p>`;
  } catch (e) { toast(e.message, true); }
  try {
    const t = await api("/api/api-token");
    $("#api-token").value = t.token;
    $("#api-url").textContent = window.t("e.about.apiUrl", { url: t.url, file: t.file });
  } catch { /* niente: la scheda Info funziona lo stesso */ }
  checkUpdate(false, true);
}

async function checkUpdate(force = false, show = false) {
  let u;
  try { u = await api(`/api/update${force ? "?force=1" : ""}`); } catch (e) { if (show) $("#about-update").textContent = e.message; return; }
  const txt = u.newer ? t("e.update.available", { latest: u.latest, current: u.current })
    : u.error && !u.latest ? t("e.update.checkFailed", { error: u.error })
    : u.latest ? t("e.update.latest", { current: u.current }) : t("e.update.noRelease");
  if (show) {
    $("#about-update").innerHTML = esc(txt) + (u.newer && u.url ? ` <a href="#" data-open="${esc(u.url)}">${t("e.update.download")}</a>` : "")
      + (u.newer && u.install_kind ? ` <button class="btn primary" id="about-install">${t("e.update.install")}</button>` : "");
    if ($("#about-install")) $("#about-install").onclick = installUpdate;
  } else if (u.newer && store.get("updateSeen", "") !== u.latest) {
    updatePopup(u); // "visto" solo dopo un clic: se non lo noti o non c'e' rete, riappare
  } else if (u.error && !u.latest) {
    setTimeout(() => checkUpdate(false, false), 60000); // controllo fallito (es. rete non ancora pronta): riprova
  }
}

/** Piccolo pop-up cliccabile: installa la nuova versione (o apre la pagina di download se non si puo' installare dall'app). */
function updatePopup(u) {
  document.querySelector("#update-pop")?.remove();
  const p = document.createElement("button");
  p.id = "update-pop";
  p.type = "button";
  p.innerHTML = `<b>${t("e.update.newVersion", { v: esc(u.latest) })}</b><span>${u.install_kind ? t("e.update.clickInstall") : t("e.update.clickDownload")}</span><i title="${t("e.toast.close")}">✕</i>`;
  p.onclick = (e) => {
    p.remove();
    store.set("updateSeen", u.latest); // un solo avviso per versione, dopo che l'hai chiuso o cliccato
    if (e.target.tagName === "I") return;
    if (!u.install_kind) return api("/api/open", { body: { url: u.url } });
    openSettings("about");
    installUpdate();
  };
  overlayHost().appendChild(p);
}

/** Scarica e installa la nuova versione (dal server); alla fine l'app si chiude e si riapre aggiornata. */
async function installUpdate() {
  const box = $("#about-update");
  let st;
  try { st = await api("/api/update/install", { body: {} }); } catch (e) { return toast(e.message, true); }
  while (st.status === "running") {
    const pct = st.total ? ` ${Math.floor((100 * st.done) / st.total)}%` : "";
    box.innerHTML = `${esc(st.phase)}${pct}<div class="loadbar-track"><i></i></div>`;
    await new Promise((r) => setTimeout(r, 700));
    try { st = await api("/api/update/install"); } catch { st = { status: "done", phase: t("e.update.restarting") }; } // server gia' chiuso
  }
  box.textContent = st.phase;
  if (st.status === "error") toast(st.phase, true);
}

/* ---- salute */
async function loadHealth() {
  $("#health-list").innerHTML = `<p class="muted">${t("e.health.checking")}</p>`;
  let d;
  try { d = await api("/api/health"); } catch (e) { $("#health-list").innerHTML = `<p class="status-bad">${esc(e.message)}</p>`; return; }
  const ico = { ok: "✓", warn: "⚠", error: "✖" };
  SET.health = d.items;
  $("#health-list").innerHTML = `<div class="health">` + d.items.map((x, i) => `<div class="hl-row hl-${x.level}">`
    + `<span class="hl-ico">${ico[x.level]}</span><div class="hl-txt"><b>${esc(x.title)}</b>${x.detail ? `<div class="muted small">${esc(x.detail)}</div>` : ""}</div>`
    + (x.fix ? `<button class="btn hl-fix" data-i="${i}">${esc(x.fix.label)}</button>` : "") + `</div>`).join("") + `</div>`;
}

async function healthFix(fix) {
  if (fix.tab) return showTab(fix.tab);
  if (fix.backup) { await backupNow(); return loadHealth(); }
  if (fix.sunshine) {
    try { await api("/api/sunshine/start", { body: {} }); } catch (e) { return toast(e.message, true); }
    toast(t("e.sunshine.starting"));
    return setTimeout(loadHealth, 5000);
  }
  if (fix.scan) {
    try { await api("/api/scan", { body: { mode: fix.scan } }); } catch (e) { return toast(e.message, true); }
    SET.lastStatus = "running";
    setScanRunning(true);
    showTab("scan");
  }
}

/* ---- registro diagnostico locale (nessun invio) */
function bindSystemErrorButtons() {
  const ref = $("#sys-errors-refresh");
  if (ref && !ref.dataset.bound) {
    ref.dataset.bound = "1";
    ref.onclick = () => loadSystemErrors();
  }
  const cp = $("#sys-errors-copy");
  if (cp && !cp.dataset.bound) {
    cp.dataset.bound = "1";
    cp.onclick = async () => {
      let text = "";
      try {
        const r = await fetch("/api/system/errors/export");
        if (r.ok) text = await r.text();
      } catch {}
      if (!text && SET.recentErrors) text = JSON.stringify(SET.recentErrors, null, 2);
      if (!text || text.trim() === "[]" || !text.trim()) return toast(t("e.sys.nothingToCopy"));
      try {
        await navigator.clipboard.writeText(text);
        toast(t("e.sys.copied"));
      } catch {
        toast(t("e.sys.copyFailed"), true);
      }
    };
  }
  const clr = $("#sys-errors-clear");
  if (clr && !clr.dataset.bound) {
    clr.dataset.bound = "1";
    clr.onclick = async () => {
      try {
        await api("/api/system/errors/clear", { body: {} });
        toast(t("e.sys.cleared"));
        loadSystemErrors();
      } catch (e) {
        toast(e.message, true);
      }
    };
  }
}

async function loadSystemErrors() {
  bindSystemErrorButtons();
  const box = $("#sys-errors-box");
  if (!box) return;
  box.innerHTML = `<p class="muted">${t("e.sys.loading")}</p>`;
  try {
    const res = await api("/api/system/errors");
    const list = res.errors || [];
    SET.recentErrors = list;
    if (!list.length) {
      box.innerHTML = `<p class="muted">${t("e.sys.none")}</p>`;
      return;
    }
    const rows = list.slice().reverse().map((e) => `<tr>`
      + `<td style="white-space:nowrap" class="muted">${esc(e.time || "")}</td>`
      + `<td><b>${esc(e.module || "app")}</b></td>`
      + `<td>${esc(e.message || "")}${e.traceback ? `<details><summary class="muted">${t("e.sys.details")}</summary><pre class="small" style="max-height:100px;overflow:auto;margin:4px 0">${esc(e.traceback)}</pre></details>` : ""}</td>`
      + `</tr>`).join("");
    box.innerHTML = `<div style="max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:6px;padding:4px"><table class="emu"><thead><tr><th style="width:130px">${t("e.sys.time")}</th><th style="width:100px">${t("e.sys.module")}</th><th>${t("e.sys.message")}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  } catch (err) {
    box.innerHTML = `<p class="status-bad">${t("e.sys.readFailed", { msg: esc(err.message) })}</p>`;
  }
}

/* ---- copie di sicurezza dei dati utente */
async function loadBackups() {
  let d;
  try { d = await api("/api/backups"); } catch (e) { return toast(e.message, true); }
  $("#backup-list").innerHTML = d.items.length
    ? `<table class="emu"><tr><th>${t("e.backup.copy")}</th><th style="width:150px">${t("e.col.date")}</th><th style="width:80px" class="num">${t("e.backup.size")}</th><th style="width:110px"></th></tr>`
      + d.items.map((b) => `<tr><td class="small">${esc(b.name)}</td><td>${esc(fmtDate(b.time))}</td><td class="num">${esc(fmtSize(b.size))}</td>`
        + `<td><button class="btn bk-restore" data-name="${esc(b.name)}">${t("e.backup.restore")}</button></td></tr>`).join("") + `</table>`
      + `<p class="muted small">${t("e.storage.folder")} <code>${esc(d.folder)}</code></p>`
    : `<p class="muted small">${t("e.backup.none")}</p>`;
  loadBackupOpts();
}

/* opzioni della copia: automatica (spenta di default), quante tenerne, credenziali incluse */
async function loadBackupOpts() {
  let o;
  try { o = await api("/api/backups/settings"); } catch { return; }
  $("#bk-auto").checked = o.auto;
  $("#bk-keep").value = o.keep;
  $("#bk-secrets").checked = o.secrets;
  const save = async () => {
    try { await api("/api/backups/settings", { body: { auto: $("#bk-auto").checked, keep: +$("#bk-keep").value || 10, secrets: $("#bk-secrets").checked } }); }
    catch (e) { toast(e.message, true); }
  };
  $("#bk-auto").onchange = $("#bk-keep").onchange = $("#bk-secrets").onchange = save;
}

/* testo dell'anteprima di ripristino (puro: nessun accesso alla pagina) */
function backupPreviewText(p) {
  const lines = [t("e.backup.previewTitle", { name: p.name, date: fmtDate(p.created) }), ""];
  for (const it of p.items) {
    lines.push(`- ${it.file}: ${t(it.action === "overwrite" ? "e.backup.previewOverwrite" : "e.backup.previewCreate")}`);
    for (const c of it.counts || []) lines.push(`    ${t(c.label)}: ${c.now} → ${c.backup}`);
  }
  if (!p.secrets) lines.push("", t("e.backup.previewNoSecrets"));
  if (p.scripts_warning) lines.push("", p.scripts_warning);
  lines.push("", t("e.backup.previewAsk"));
  return lines.join("\n");
}

/* ---- manutenzione programmata (pannello in settings/dati.html; API /api/maintenance) */
/* pure:maintenance:start -- formattazione del rapporto, testata da tests/test_maintenance_ui.js (usa esc e fmtSize di core.js) */
const MAINT_LIST_MAX = 20;
function maintName(x) { return x && typeof x === "object" ? String(x.game ?? x.name ?? "") : String(x ?? ""); }
function maintList(items) {
  const list = items || [];
  const rows = list.slice(0, MAINT_LIST_MAX).map((x) => `<li>${esc(maintName(x))}`
    + (x && typeof x === "object" && x.path ? ` <span class="muted small">${esc(x.path)}</span>` : "") + "</li>").join("");
  const more = list.length > MAINT_LIST_MAX ? `<li class="muted">e altre ${list.length - MAINT_LIST_MAX}</li>` : "";
  return list.length ? `<ul class="maint-list">${rows}${more}</ul>` : `<p class="muted small">Nessuno.</p>`;
}
function maintDiffLines(diff) {
  if (!diff) return [];
  const short = (arr) => arr.slice(0, 5).map(maintName).join(", ") + (arr.length > 5 ? ` e altre ${arr.length - 5}` : "");
  const nuove = diff.rom_nuove_mancanti || [], ripr = diff.rom_ripristinate || [], bios = diff.bios_nuovi_invalidi || [];
  const out = [];
  if (nuove.length) out.push({ cls: "maint-bad", text: `${nuove.length} ROM nuove mancanti: ${short(nuove)}` });
  if (ripr.length) out.push({ cls: "maint-good", text: `${ripr.length} ROM ripristinate: ${short(ripr)}` });
  if (bios.length) out.push({ cls: "maint-bad", text: `${bios.length} BIOS nuovi non validi: ${short(bios)}` });
  const cd = diff.covers_delta || 0;
  if (cd) out.push({ cls: cd > 0 ? "maint-bad" : "maint-good", text: `Copertine mancanti: ${cd > 0 ? "+" : ""}${cd}` });
  const fd = diff.freeable_delta || 0; // più spazio da liberare = peggio
  if (fd) out.push({ cls: fd > 0 ? "maint-bad" : "maint-good", text: `Spazio liberabile: ${fd > 0 ? "+" : "-"}${fmtSize(Math.abs(fd))}` });
  return out;
}
function maintRenderReport(r, diff) {
  const steps = (r.steps || []).map((s) => `<li class="${s.ok ? "maint-good" : "maint-bad"}"><span aria-label="${s.ok ? "riuscito" : "fallito"}">${s.ok ? "✓" : "✗"}</span>`
    + ` ${esc(s.nome)}${s.note ? ` <span class="muted small">${esc(s.note)}</span>` : ""}</li>`).join("");
  const lines = maintDiffLines(diff);
  const diffHtml = diff ? `<h5>Rispetto all'ultima volta:</h5>` + (lines.length
    ? `<ul class="maint-diff">${lines.map((l) => `<li class="${l.cls}">${esc(l.text)}</li>`).join("")}</ul>`
    : `<p class="muted small">Nessuna differenza.</p>`) : "";
  return `<h5>Passaggi</h5>${steps ? `<ul class="maint-steps">${steps}</ul>` : `<p class="muted small">Nessun passaggio registrato.</p>`}`
    + `<h5>ROM sparite (${(r.rom_missing || []).length})</h5>${maintList(r.rom_missing)}`
    + `<h5>BIOS non validi (${(r.bios_invalid || []).length})</h5>${maintList(r.bios_invalid)}`
    + `<h5>Copertine mancanti</h5><p class="small">${esc(r.covers_missing ?? 0)}</p>`
    + `<h5>Spazio liberabile</h5><p class="small">${r.freeable_bytes == null ? "non calcolato" : esc(fmtSize(r.freeable_bytes) || "0 B")}</p>`
    + diffHtml;
}
/* pure:maintenance:end */

let MAINT_TIMER = 0;
function maintTime(t) {
  if (t == null || t === "") return "";
  return typeof t === "number" ? fmtDate(t) : new Date(t).toLocaleString(GSI18n.lang, { dateStyle: "medium", timeStyle: "short" });
}
function maintPaint(d) {
  const run = $("#mt-run");
  run.disabled = !!d.running;
  run.textContent = d.running ? t("e.running") : t("e.maint.run");
  $("#mt-state").textContent = d.running ? t("e.maint.running") : "";
  const latest = d.latest || {}, rep = latest.report;
  const peggiora = !!(latest.diff && latest.diff.peggiora);
  $("#mt-last").textContent = rep ? `${t("e.maint.last", { time: maintTime(rep.time) })}${peggiora ? ` · ${t("e.maint.worse")}` : ""}` : t("e.maint.noReport");
  $("#mt-last").classList.toggle("maint-bad", peggiora);
  $("#mt-detail").innerHTML = rep ? maintRenderReport(rep, latest.diff) : "";
}
async function maintPoll() {
  clearTimeout(MAINT_TIMER);
  if (SET.tab !== "dati" || !$("#mt-box")) return;
  let d;
  try { d = await api("/api/maintenance"); } catch (e) { $("#mt-state").textContent = e.message; return; }
  maintPaint(d);
  if (d.running) MAINT_TIMER = setTimeout(maintPoll, 2000);
}
async function loadMaintenance() {
  clearTimeout(MAINT_TIMER);
  const box = $("#mt-box");
  if (!box) return;
  if (!box.dataset.bound) {
    box.dataset.bound = "1";
    // il salvataggio rilegge tutti e tre i campi: l'annulla di autosaveControl riscrive prima il valore precedente
    const save = () => api("/api/maintenance/settings", { body: { enabled: $("#mt-on").checked, day: Number($("#mt-day").value), time: $("#mt-time").value } });
    autosaveControl($("#mt-on"), save);
    autosaveControl($("#mt-day"), save);
    autosaveControl($("#mt-time"), save);
    $("#mt-run").addEventListener("click", async () => {
      try { await api("/api/maintenance/run", { method: "POST" }); } catch (e) { return toast(e.message, true); }
      MAINT_TIMER = setTimeout(maintPoll, 1000);
    });
  }
  try {
    const d = await api("/api/maintenance");
    const s = d.settings || {};
    $("#mt-on").checked = !!s.enabled;
    $("#mt-day").value = String(s.day ?? 0);
    $("#mt-time").value = s.time || "03:00";
    maintPaint(d);
    if (d.running) MAINT_TIMER = setTimeout(maintPoll, 2000);
  } catch (e) { $("#mt-state").textContent = e.message; }
}

/* ---- profili utente: dati personali separati (preferiti, tempo di gioco, collezioni...), libreria comune */
function paintProfile() {
  const cur = S.profiles?.profiles?.find((x) => x.id === S.profiles.active) || { name: t("e.profile.main") };
  $("#profile-name").textContent = cur.name;
  const ico = $("#profile-ico");
  ico.textContent = cur.avatar || "👤";
  ico.style.background = cur.color || "";
  // lo stesso utente nella barra dei menu (c'e' in ogni grafica, la barra laterale puo' essere nascosta)
  const mbName = $("#mb-profile-name"), mbIco = $("#mb-profile-ico");
  if (mbName) mbName.textContent = cur.name;
  if (mbIco) { mbIco.textContent = cur.avatar || "👤"; mbIco.style.background = cur.color || ""; }
}

async function loadProfile() {
  try { S.profiles = await api("/api/profiles"); } catch { return; }
  paintProfile();
}

// profilo protetto da PIN: il PIN si chiede solo quando lo sblocchi (o lo modifichi) dal menu
async function unlockProfile(anchor, p) {
  const pin = await askText(anchor, t("e.profile.pinOf", { name: p.name }));
  if (!pin) return false;
  S.profiles = await api(`/api/profiles/${encodeURIComponent(p.id)}/unlock`, { body: { pin } });
  return true;
}

/** Dopo un cambio di profilo: libreria comune a tutti, si rilegge solo cio' che il server restituisce per il profilo attivo. */
async function applyProfile() {
  await loadProfile();
  let ps = null;
  try { ps = await api("/api/profile/settings"); } catch { /* route assente: restano tema ed esperienza comuni */ }
  if (ps?.experience && ps.experience !== GS.experience?.id) {
    store.set("view", GS.experiences.get(ps.experience)?.home ? { type: "home" } : { type: "all" });
    location.reload();
    return;
  }
  if (ps?.theme && ps.theme !== GS.extensions?.active_theme) await loadExtensions();
  await reload(true);
  toast(t("e.profile.toast", { name: $("#profile-name").textContent }));
}

/** Impostazioni > Generale: elenco profili (modifica, PIN, elimina) e «Chi gioca?» all'avvio. */
async function loadProfilesSettings() {
  const box = $("#prof-list");
  if (!box) return;
  await loadProfile();
  const st = S.profiles;
  $("#prof-section").hidden = !st;
  if (!st) return;
  box.innerHTML = st.profiles.map((x) => `<div class="row wrap" data-pid="${esc(x.id)}"><span class="ico" style="background:${esc(x.color || "")}">${esc(x.avatar || "👤")}</span>`
    + `<span>${esc(x.name)}${x.locked ? " 🔒" : ""}${x.id === st.active ? ` <span class="muted small">${t("e.profile.inUse")}</span>` : ""}</span>`
    + `<button class="btn" type="button" data-pf="edit">${t("e.profile.edit")}</button></div>`).join("");
  $("#prof-ask").checked = !!st.ask;
  $("#prof-active").textContent = (st.profiles.find((x) => x.id === st.active) || {}).name || "";
  $("#prof-remember").checked = !!st.remembered;
}

function bindProfilesSettings() {
  $("#prof-list")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-pf]");
    const p = b && S.profiles.profiles.find((x) => x.id === b.closest("[data-pid]").dataset.pid);
    if (p) GSProfilePicker.edit(p, { toast, onDone: async () => { await loadProfilesSettings(); if (S.profiles.active !== p.id && !S.profiles.profiles.some((x) => x.id === S.profiles.active)) await applyProfile(); } });
  });
  $("#prof-new")?.addEventListener("click", () => GSProfilePicker.edit(null, { toast, onDone: loadProfilesSettings }));
  $("#prof-ask")?.addEventListener("change", async (e) => {
    try { await api("/api/profiles/ask", { body: { ask: e.target.checked } }); } catch (err) { e.target.checked = !e.target.checked; toast(err.message, true); }
  });
  $("#prof-switch")?.addEventListener("click", () => GSProfilePicker.open({ onChange: async () => { await applyProfile(); await loadProfilesSettings(); }, toast }));
  $("#prof-remember")?.addEventListener("change", async (e) => {
    try {
      await api("/api/profiles/remember", { body: { remember: e.target.checked } });
      toast(e.target.checked ? t("e.profile.rememberOn") : t("e.profile.rememberOff"));
    } catch (err) { e.target.checked = !e.target.checked; toast(err.message, true); }
  });
}

async function switchProfile(id) {
  S.profiles = await api("/api/profiles/active", { body: { id } });
  await loadProfile();
  await reload(true);
  toast(t("e.profile.toast", { name: $("#profile-name").textContent }));
}

function profileMenu(anchor) {
  const st = S.profiles || { profiles: [], active: "default" };
  const cur = st.profiles.find((x) => x.id === st.active) || { name: "" };
  const p = $("#popover");
  p.innerHTML = `<div class="opts">${st.profiles.map((x) => `<div class="opt${x.id === st.active ? " hl" : ""}" data-pid="${esc(x.id)}">`
      + `<span>${x.id === st.active ? "✓ " : ""}${x.color ? `<i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${esc(x.color)}"></i> ` : ""}`
      + `${esc(x.avatar ? `${x.avatar} ` : "")}${esc(x.name)}${x.locked ? " 🔒" : ""}</span></div>`).join("")}
    <div class="opt" data-act="switch"><span>${t("e.profile.switch")}</span></div>
    <div class="opt" data-act="new"><span>${t("e.profile.new")}</span></div>
    <div class="opt" data-act="rename"><span>${t("e.profile.rename", { name: esc(cur.name) })}</span></div>
    <div class="opt" data-act="edit"><span>${t("e.profile.appearance")}</span></div>
    ${st.active !== "default" ? `<div class="opt" data-act="delete"><span>${t("e.profile.delete", { name: esc(cur.name) })}</span></div>` : ""}</div>`;
  placePopover(anchor);
  p.onclick = async (e) => {
    const o = e.target.closest(".opt");
    if (!o) return;
    closePopover();
    try {
      if (o.dataset.pid) {
        const t = st.profiles.find((x) => x.id === o.dataset.pid);
        if (t.id !== st.active && (!t.locked || await unlockProfile(anchor, t))) await switchProfile(t.id);
      } else if (o.dataset.act === "switch") {
        await GSProfilePicker.open({ onChange: applyProfile, toast });
      } else if (o.dataset.act === "edit") {
        if (cur.locked && !(await unlockProfile(anchor, cur))) return;
        // invio vuoto = non cambiare; «-» = togli
        const body = {};
        const avatar = await askText(anchor, t("e.profile.askAvatar"), cur.avatar);
        if (avatar !== null) body.avatar = avatar === "-" ? "" : avatar;
        const color = await askText(anchor, t("e.profile.askColor"), cur.color);
        if (color !== null) body.color = color === "-" ? "" : color;
        const pin = await askText(anchor, t("e.profile.askPin"), "");
        if (pin !== null) body.pin = pin === "-" ? "" : pin;
        if (Object.keys(body).length) { S.profiles = await api(`/api/profiles/${encodeURIComponent(st.active)}`, { method: "PATCH", body }); paintProfile(); toast(t("e.profile.updated")); }
      } else if (o.dataset.act === "new") {
        const name = await askText(anchor, t("e.profile.askName"));
        if (name) await switchProfile((await api("/api/profiles", { body: { name } })).created.id);
      } else if (o.dataset.act === "rename") {
        const name = await askText(anchor, t("e.profile.askRename"), cur.name);
        if (name) { await api(`/api/profiles/${encodeURIComponent(st.active)}`, { method: "PATCH", body: { name } }); await loadProfile(); }
      } else if (o.dataset.act === "delete" && confirm(t("e.profile.deleteConfirm", { name: cur.name }))) {
        await api(`/api/profiles/${encodeURIComponent(st.active)}`, { method: "DELETE" });
        await loadProfile();
        await reload(true);
        toast(t("e.profile.deleted"));
      }
    } catch (err) { toast(err.message, true); }
  };
}

/* ---- sincronizzazione tra PC (cartella condivisa e rete locale) */
async function loadSync(st) {
  try { st = st || await api("/api/sync"); } catch (e) { $("#sync-last").textContent = e.message; return; }
  $("#sync-folder").value = st.folder;
  document.querySelectorAll('[name="sync-what"]').forEach((r) => { r.checked = r.value === st.what; });
  const rows = [...st.peers.map((p) => ({ name: p.name, sub: p.url, del: `peer:${p.id}`, res: st.last?.peers?.[p.id] })),
    ...st.pcs.map((d) => ({ name: d.name, sub: t("e.sync.thisPc"), del: `pc:${d.id}` }))];
  $("#sync-peers").innerHTML = rows.length ? `<table class="emu">${rows.map((r) => `<tr><td>💻 ${esc(r.name)} <span class="muted small">${esc(r.sub)}</span>`
    + (r.res ? ` <span class="small ${r.res.error ? "status-bad" : "status-ok"}">${esc(r.res.error || t("e.sync.synced"))}</span>` : "")
    + `</td><td style="width:100px"><button class="btn" data-sync-del="${esc(r.del)}">${t("e.sync.unlink")}</button></td></tr>`).join("")}</table>` : "";
  const l = st.last || {};
  const folder = l.folder ? (l.folder.error ? ` · ${t("e.sync.folderError", { error: l.folder.error })}` : ` · ${t("e.sync.folderOk", { n: l.folder.from })}`) : "";
  $("#sync-last").textContent = st.busy ? t("e.sync.busy")
    : l.time ? `${t("e.sync.last", { time: new Date(l.time * 1000).toLocaleTimeString(GSI18n.lang, { hour: "2-digit", minute: "2-digit" }) })}${folder}`
    : t("e.sync.never");
  const sv = st.saves || {};
  if (!$("#sync-saves")) return;
  $("#sync-saves").checked = !!sv.enabled;
  if (!loadSync.games) {  // i giochi con salvataggi si chiedono una volta, quando la sezione si apre
    try { loadSync.games = (await api("/api/sync/saves")).games || []; } catch (e) { loadSync.games = []; }
  }
  const inc = new Set(sv.games || []);
  $("#sync-saves-list").innerHTML = loadSync.games.map((g) => `<label class="chk"><input type="checkbox" data-save-key="${esc(g.key)}"${inc.has(g.key) ? " checked" : ""}> ${esc(g.title)} `
    + `<span class="muted small">${t("e.sync.gameFiles", { n: g.files, size: fmtSize(g.size) || "0 B" })}</span></label>`).join("");
  const conflicts = (st.last?.saves?.conflicts) || [];
  $("#sync-saves-info").textContent = conflicts.length ? t("e.sync.conflicts", { list: conflicts.join(" · ") })
    : loadSync.games.length ? t("e.sync.picked", { picked: loadSync.games.filter((g) => inc.has(g.key)).length, total: loadSync.games.length })
      : t("e.sync.noSaves");
}

function bindSync() {
  const save = async (body) => { try { await loadSync(await api("/api/sync", { body })); toast(t("e.toast.saved")); } catch (e) { toast(e.message, true); } };
  $("#sync-folder-save").onclick = () => save({ folder: $("#sync-folder").value.trim() });
  $("#sync-folder-pick").onclick = async () => { const p = window.pywebview?.api ? await pickPath("folder") : null; if (p) { $("#sync-folder").value = p; save({ folder: p }); } };
  document.querySelectorAll('[name="sync-what"]').forEach((r) => { r.onchange = () => save({ what: r.value }); });
  $("#sync-code").onclick = async () => {
    try {
      const r = await api("/api/sync/code", { body: {} });
      $("#sync-code-out").innerHTML = t("e.sync.code", { code: esc(r.code), minutes: r.minutes })
        + (r.urls.map((u) => `<code>${esc(u.replace("https://", ""))}</code>`).join(` ${t("e.sync.or")} `) || t("e.sync.notFound"));
    } catch (e) { toast(e.message, true); }
  };
  $("#sync-peer-add").onclick = async () => {
    const btn = $("#sync-peer-add");
    btn.disabled = true;
    try {
      await loadSync(await api("/api/sync/peer", { body: { url: $("#sync-peer-url").value.trim(), code: $("#sync-peer-code").value.trim() } }));
      $("#sync-peer-code").value = "";
      toast(t("e.sync.paired"));
    } catch (e) { toast(e.message, true); } finally { btn.disabled = false; }
  };
  $("#sync-peers").onclick = async (e) => {
    const b = e.target.closest("[data-sync-del]");
    if (!b) return;
    const [kind, id] = b.dataset.syncDel.split(":");
    try { await loadSync(await api(kind === "peer" ? `/api/sync/peer/${id}` : `/api/sync/pcs/${id}`, { method: "DELETE" })); } catch (err) { toast(err.message, true); }
  };
  $("#sync-now").onclick = async () => {
    const btn = $("#sync-now");
    btn.disabled = true;
    $("#sync-last").textContent = t("e.sync.busy");
    try { await loadSync(await api("/api/sync/now", { body: {} })); await reload(true); } catch (e) { toast(e.message, true); } finally { btn.disabled = false; }
  };
  if ($("#sync-saves")) {
    $("#sync-saves").onchange = (e) => save({ saves: e.target.checked });
    $("#sync-saves-list").onchange = () => save({
      saves_games: [...document.querySelectorAll("[data-save-key]")].filter((x) => x.checked).map((x) => x.dataset.saveKey),
    });
  }
}

/** Cartella delle copie dei salvataggi dei giochi (formato Ludusavi). */
async function loadSaveDir(r) {
  try { r = r || await api("/api/app/save-dir"); } catch { return; }
  $("#save-dir").value = r.save_dir;
  $("#save-dir").placeholder = t("e.saveDir.default", { dir: r.default });
}

async function backupNow() {
  try { const r = await api("/api/backups", { body: {} }); toast(t("e.backup.created", { name: r.name })); } catch (e) { return toast(e.message, true); }
  loadBackups();
}

async function restoreBackup(name) {
  let p;
  try { p = await api("/api/backups/preview", { body: { name } }); } catch (e) { return toast(e.message, true); }
  if (!confirm(backupPreviewText(p))) return;
  let r;
  try { r = await api("/api/backups/restore", { body: { name, confirm: true } }); } catch (e) { return toast(e.message, true); }
  toast(t("e.backup.restored", { list: r.restored.join(", "), copy: r.safety_copy }));
  if (r.scripts_warning) toast(r.scripts_warning, true);
  await reload(true);
  loadBackups();
}

async function pickPath(kind) {
  const a = window.pywebview && window.pywebview.api;
  if (!a) { toast(t("e.pick.desktopOnly"), true); return null; }
  try { return await (kind === "folder" ? a.pick_folder() : a.pick_file()); } catch (e) { toast(String(e), true); return null; }
}

/* ---- scraping di nuovi giochi e console */
async function loadScan() {
  $("#scan-table").innerHTML = `<p class="muted">${t("e.scan.checking")}</p>`;
  const [pv, js] = await Promise.all([api("/api/scan/preview").catch((e) => ({ error: e.message })), api("/api/scan")]);
  if (!SET.platforms) SET.platforms = await api("/api/platforms");
  SET.preview = pv;
  renderScan(pv, js);
  if (js.status === "running") pollScan();
  else loadRenamed();
}

/* ---- altre cartelle ROM (altri dischi) */
function renderExtraRoots(extra) {
  $("#scan-extra").innerHTML = `<div class="muted small extra-roots">${t("e.scan.extraRoots")} `
    + (extra.length ? extra.map((x) => `<span class="xr${x.online ? "" : " off"}" title="${x.online ? "" : t("e.scan.unreachable")}">`
      + `<code>${esc(x.path)}</code>${x.online ? "" : " ⚠"} <a href="#" class="xr-del" data-path="${esc(x.path)}" title="${t("e.scan.remove")}">✕</a></span>`).join(" ")
      : t("e.scan.none"))
    + ` <button class="btn" id="xr-add" type="button">${t("e.scan.add")}</button>`
    + ` <button class="btn" id="xr-paste" type="button" title="${t("e.scan.pasteTitle")}">${t("e.scan.paste")}</button></div>`;
}

async function extraRoot(action, path) {
  if (!path) return;
  try { await api("/api/roms/extra", { body: { action, path } }); } catch (e) { return toast(e.message, true); }
  toast(action === "add" ? t("e.scan.addedToast") : t("e.scan.removedToast"));
  loadScan();
}

/* ---- cartelle rinominate o spostate: i dati del gioco (metadati, tempo di gioco, collezioni) passano alla nuova cartella */
async function loadRenamed() {
  const box = $("#scan-renamed");
  box.innerHTML = `<p class="muted small">${t("e.scan.checkingRenamed")}</p>`;
  let d;
  try { d = await api("/api/relink/plan"); } catch { box.innerHTML = ""; return; }
  if (!d.pairs.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="renamed"><b>${t("e.renamed.title", { n: d.pairs.length })}</b>
    <div class="muted small">${t("e.renamed.desc")}</div>
    <div class="rn-list">${d.pairs.map((x) => `<label><input type="checkbox" class="rn-sel" data-new="${esc(x.new)}" checked>
      <span>${esc(x.title)}</span> <span class="muted small">→ ${esc(x.path.split(/[\\/]/).slice(-2).join("/"))}</span></label>`).join("")}</div>
    <button class="btn primary" id="relink-apply">${t("e.renamed.apply")}</button></div>`;
  $("#relink-apply").onclick = async () => {
    const sel = [...document.querySelectorAll(".rn-sel:checked")].map((c) => c.dataset.new);
    if (!sel.length) return;
    try { const r = await api("/api/relink/apply", { body: { new: sel } }); toast(t("e.renamed.applied", { n: r.applied })); }
    catch (e) { return toast(e.message, true); }
    box.innerHTML = "";
    const tick = async () => {
      const st = await api("/api/status");
      if (st.building) return setTimeout(tick, 1000);
      await reload(true);
      loadScan();
    };
    tick();
  };
}

function renderScan(pv, js) {
  if (pv.error) { $("#scan-table").innerHTML = `<p class="status-bad">${esc(pv.error)}</p>`; return; }
  $("#scan-root").textContent = pv.root;
  renderExtraRoots(pv.extra || []);
  const fmt = (n) => (n ? n.toLocaleString(GSI18n.lang) : "—");
  $("#scan-table").innerHTML = `<table class="emu"><tr><th style="width:28px"><input type="checkbox" id="scan-all" title="${t("e.scan.selectAll")}"></th>`
    + `<th>${t("e.col.console")}</th><th>${t("e.col.folder")}</th><th class="num">${t("e.scan.games")}</th><th class="num">${t("e.scan.new")}</th>`
    + `<th class="num" title="${t("e.scan.noDataTitle")}">${t("e.scan.noData")}</th>`
    + `<th class="num" title="${t("e.scan.partialTitle")}">${t("e.scan.partial")}</th>`
    + `<th title="${t("e.scan.pasteConsoleTitle")}"></th></tr>`
    + pv.platforms.map((r) => `<tr class="${r.new ? "new" : ""}"><td><input type="checkbox" class="scan-sel" data-p="${esc(r.platform)}"></td>`
      + `<td>${esc(r.name)}</td><td class="muted small">${esc(r.folder)}</td><td class="num">${r.games.toLocaleString(GSI18n.lang)}</td>`
      + `<td class="num n">${fmt(r.new)}</td><td class="num warn">${fmt(r.nodata)}</td><td class="num">${fmt(r.partial)}</td>`
      + `<td><button class="btn paste-dir" data-platform="${esc(r.platform)}" title="${t("e.scan.pasteFolderOf", { name: esc(r.name) })}">📋</button></td></tr>`).join("") + `</table>`;
  applyScanMode();
  const opts = `<option value="">${t("e.scan.whichConsole")}</option>` + SET.platforms.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  $("#scan-unknown").innerHTML = pv.unknown.length
    ? `<div class="unknown"><b>${t("e.scan.unknownHead")}</b> <span class="muted small">${t("e.scan.unknownHint")}</span>`
      + pv.unknown.map((u) => `<div class="u"><code>${esc(u)}</code><select class="field map-folder" data-folder="${esc(u)}">${opts}</select></div>`).join("") + `</div>`
    : "";
  if (js) { setScanRunning(js.status === "running"); renderScanJob(js); }
}

// testo del pulsante: conta i giochi delle console spuntate (nessuna spunta = tutte le console).
// Nessuna console viene spuntata in automatico.
function applyScanMode() {
  const pv = SET.preview;
  if (!pv || pv.error) return;
  const mode = $("#scan-mode").value;
  const need = (r) => (mode === "new" ? r.new : mode === "missing" ? r.nodata + r.partial : r.games);
  const sel = new Set([...document.querySelectorAll(".scan-sel:checked")].map((c) => c.dataset.p));
  const rows = sel.size ? pv.platforms.filter((r) => sel.has(r.platform)) : pv.platforms;
  const tot = rows.reduce((a, r) => a + need(r), 0);
  const n = tot.toLocaleString(GSI18n.lang);
  const where = sel.size ? ` · ${t("e.scan.selected", { n: sel.size })}` : ` · ${t("e.scan.allConsoles")}`;
  $("#scan-start").textContent = (mode === "new" ? (tot ? t("e.scan.startNewN", { n }) : t("e.scan.startNew"))
    : mode === "missing" ? (tot ? t("e.scan.startMissingN", { n }) : t("e.scan.startMissing")) : t("e.scan.startAll")) + where;
}

function renderScanJob(js) {
  const label = { running: t("e.running"), done: t("e.scan.done"), cancelled: t("e.scan.cancelled"), error: t("e.scan.error") }[js.status] || "";
  const bars = (js.tasks || []).filter((t) => t.total > 0).map((t) => {
    const pct = Math.min(100, Math.round((100 * t.done) / t.total));
    return `<div class="bar"><span>${esc(t.name)}</span><div class="track"><div class="fill" style="width:${pct}%"></div></div>`
      + `<span class="n">${Math.round(t.done).toLocaleString(GSI18n.lang)} / ${Math.round(t.total).toLocaleString(GSI18n.lang)}</span></div>`;
  }).join("");
  $("#scan-progress").innerHTML = js.status === "idle" ? "" : `<div class="phase">${esc(js.phase || label)}</div><div class="bars">${bars}</div>`;
  const log = $("#scan-log");
  log.textContent = (js.log || []).join("\n");
  log.scrollTop = log.scrollHeight;
}

function setScanRunning(on) {
  $("#scan-start").hidden = on;
  $("#scan-cancel").hidden = !on;
  $("#scan-btn").classList.toggle("busy", on);
  $("#scan-btn").textContent = on ? t("e.scan.scraping") : t("e.scan.newGames");
}

let scanTimer = 0;
async function pollScan() {
  clearTimeout(scanTimer);
  let js;
  try { js = await api("/api/scan"); } catch { return; }
  setScanRunning(js.status === "running");
  if (settingsActive("libreria")) renderScanJob(js);
  // scansione finita: i file trovati compaiono subito, i metadati arrivano dopo senza bloccare
  if (js.status === "running" && js.phase === "Scraping" && SET.shownFor !== js.started) { SET.shownFor = js.started; reload(true); }
  if (js.status === "running") scanTimer = setTimeout(pollScan, 1000);
  else if (SET.lastStatus === "running") { // appena terminato
    if (js.status === "done") {
      await reload(true);
      toast(js.title ? t("e.scan.doneTitle", { title: js.title }) : t("e.scan.finished"));
      if (S.detail) openDetail(S.detail.id);
    }
    else if (js.status === "error") toast(js.phase, true);
    else if (js.status === "cancelled") toast(t("e.scan.interrupted"));
    if (settingsActive("libreria")) loadScan();
  }
  SET.lastStatus = js.status;
}

async function startScan() {
  const sel = [...new Set([...document.querySelectorAll(".scan-sel:checked")].map((c) => c.dataset.p))];
  const mode = $("#scan-mode").value;
  if (mode === "all" && !confirm(t("e.scan.confirmAll"))) return;
  try { await api("/api/scan", { body: { platforms: sel, mode } }); }
  catch (e) { return toast(e.message, true); }
  SET.lastStatus = "running";
  setScanRunning(true);
  pollScan();
}
