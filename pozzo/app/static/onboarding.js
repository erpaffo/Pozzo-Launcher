"use strict";
/* Pozzo Launcher - procedura guidata di primo avvio in 4 passi (tutti facoltativi e riprendibili):
 * 1 cartella ROM, 2 console (emulatore consigliato, BIOS), 3 store PC, 4 tema ed esperienza.
 * Sostituisce SETUP.open (setup.js): app.js, il pulsante «Configurazione guidata» e «Rifai la procedura»
 * aprono questa e non la vecchia. Riusa /api/setup, /api/setup/check-roms, /api/emulators/*, /api/accounts
 * e /api/app/theme|experience. La libreria, i metadati e le copertine sono unici e condivisi da tutti i
 * profili: qui non si salva nulla per profilo. Lo stato dei passi resta in localStorage (gs.onboarding). */

(() => {
  const KEY = "gs.onboarding";
  const STEPS = ["Cartella ROM", "Console", "Store", "Aspetto"];
  const DEFAULT = { step: 0, roms: "", stores: null, theme: "", experience: "", skipped: [] };

  const clean = (raw) => {
    const s = { ...DEFAULT, skipped: [] };
    if (!raw || typeof raw !== "object") return s;
    if (Number.isInteger(raw.step)) s.step = Math.min(STEPS.length - 1, Math.max(0, raw.step));
    for (const k of ["roms", "theme", "experience"]) if (typeof raw[k] === "string") s[k] = raw[k];
    if (raw.stores && typeof raw.stores === "object" && !Array.isArray(raw.stores)) {
      s.stores = Object.fromEntries(Object.entries(raw.stores).map(([k, v]) => [k, !!v]));
    }
    if (Array.isArray(raw.skipped)) s.skipped = raw.skipped.filter((n) => Number.isInteger(n) && n >= 0 && n < STEPS.length);
    return s;
  };
  const load = (store) => {
    try { return clean(JSON.parse(store.getItem(KEY) || "null")); } catch { return clean(null); }
  };
  const save = (store, s) => { try { store.setItem(KEY, JSON.stringify(s)); } catch { /* storage non disponibile */ } };
  // console da mostrare al passo 2: quelle trovate nelle ROM, senza duplicati, con un tetto
  const consoles = (platforms, max = 12) => {
    const seen = new Set();
    return (Array.isArray(platforms) ? platforms : []).filter((p) => p && p.id && !seen.has(p.id) && seen.add(p.id)).slice(0, max);
  };
  const biosMissing = (b) => !!b && Array.isArray(b.items) && b.items.some((i) => i.required && !i.ok);

  const api = { clean, load, save, consoles, biosMissing, STEPS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document === "undefined" || typeof window === "undefined") return;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const call = async (path, body) => {
    const init = { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json" } };
    if (body !== undefined) init.body = JSON.stringify(body);
    const r = await fetch(path, init);
    if (!r.ok) {
      let m = r.status === 404 ? "Funzione non disponibile in questa versione" : r.statusText;
      try { m = (await r.json()).detail || m; } catch { /* risposta non JSON */ }
      throw new Error(m);
    }
    return r.json();
  };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  if (!document.querySelector("link[data-onboarding]")) {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "/static/onboarding.css"; l.dataset.onboarding = "1";
    document.head.appendChild(l);
  }

  let root = null, st = DEFAULT, srv = null, running = null, resolveOpen = null, opener = null;
  const ui = { found: null, romsMsg: "", rows: {}, stores: [], ext: null, origTheme: "", origExp: "", msg: "" };

  const body = () => root.querySelector(".onb-body");
  const persist = () => save(localStorage, st);
  const live = (m) => { const e = root && root.querySelector(".onb-live"); if (e) e.textContent = m || ""; };

  function finishStep(skip) {
    if (skip && !st.skipped.includes(st.step)) st.skipped.push(st.step);
    if (!skip) st.skipped = st.skipped.filter((n) => n !== st.step);
    if (st.step === 3 && skip) restoreLook();
    if (st.step < STEPS.length - 1) { st.step++; persist(); render(); } else { persist(); conclude(); }
  }

  function render() {
    const i = st.step;
    root.querySelector(".onb-steps").innerHTML = STEPS.map((n, k) =>
      `<li class="${k === i ? "on" : ""}${st.skipped.includes(k) ? " skip" : ""}" ${k === i ? 'aria-current="step"' : ""}>${k + 1}. ${n}${st.skipped.includes(k) ? " (saltato)" : ""}</li>`).join("");
    root.querySelector("#onb-title").textContent = `Passo ${i + 1} di ${STEPS.length}: ${STEPS[i]}`;
    [stepRoms, stepConsoles, stepStores, stepLook][i]();
    root.querySelector(".onb-nav").innerHTML = `<button class="btn" data-a="back" ${i === 0 ? "disabled" : ""}>Indietro</button>
      <button class="btn" data-a="skip">Salta questo passo</button>
      <button class="btn primary" data-a="next">${i === STEPS.length - 1 ? "Fine" : "Avanti"}</button>`;
    focusFirst();
  }

  function focusFirst() {
    const t = body().querySelector("input,select,button:not([disabled])") || root.querySelector("[data-a=next]");
    if (t) t.focus({ preventScroll: true });
  }

  // 1 - cartella ROM: percorso incollato o scelto (se l'app lo permette) e anteprima delle console
  function stepRoms() {
    const list = ui.found ? ui.found.map((p) => `<li>${esc(p.name)}</li>`).join("") : "";
    body().innerHTML = `<p>Dove tieni le ROM? La libreria è una sola e vale per tutti i profili.</p>
      <label for="onb-roms">Percorso della cartella</label>
      <div class="onb-row"><input id="onb-roms" type="text" value="${esc(st.roms)}" placeholder="D:\\Giochi\\ROM" spellcheck="false" autocomplete="off">
      <button class="btn" data-a="pick" ${window.pywebview?.api?.pick_folder ? "" : "hidden"}>Sfoglia…</button>
      <button class="btn" data-a="check">Verifica</button></div>
      <p class="onb-msg" role="status">${esc(ui.romsMsg)}</p>
      ${list ? `<p>Console trovate: ${ui.found.length}</p><ul class="onb-list">${list}</ul>` : ""}`;
  }

  async function checkRoms() {
    const v = body().querySelector("#onb-roms").value.trim();
    st.roms = v; persist();
    if (!v) { ui.found = null; ui.romsMsg = "Scrivi o incolla un percorso, oppure salta il passo."; return stepRoms(); }
    ui.romsMsg = "Controllo in corso…"; live(ui.romsMsg);
    try {
      const r = await call("/api/setup/check-roms", { path: v });
      ui.found = r.platforms; st.roms = r.path; persist();
      ui.romsMsg = r.platforms.length ? `Trovate ${r.platforms.length} console.` : "Cartella valida, ma nessuna console riconosciuta.";
    } catch (e) { ui.found = null; ui.romsMsg = `${e.message}. Puoi andare avanti comunque.`; }
    stepRoms(); live(ui.romsMsg);
    body().querySelector("#onb-roms").focus();
  }

  async function pickFolder() {
    try {
      const p = await window.pywebview.api.pick_folder();
      if (p) { body().querySelector("#onb-roms").value = p; await checkRoms(); }
    } catch { ui.romsMsg = "Selezione cartella non disponibile: incolla il percorso."; stepRoms(); }
  }

  // anteprima silenziosa del percorso già salvato, per mostrare le console senza chiedere di nuovo
  async function previewSaved() {
    try { const r = await call("/api/setup/check-roms", { path: st.roms }); ui.found = r.platforms; ui.romsMsg = `Trovate ${r.platforms.length} console.`; } catch { ui.found = null; }
    if (root && st.step <= 1) render();
  }

  // 2 - console: emulatore consigliato, installazione con avanzamento e controllo BIOS
  async function loadConsole(id) {
    const row = ui.rows[id] = ui.rows[id] || {};
    const q = encodeURIComponent(id);
    const [rec, bios] = await Promise.allSettled([call(`/api/emulators/recommend?console=${q}`), call(`/api/emulators/bios?console=${q}`)]);
    row.rec = rec.status === "fulfilled" ? rec.value : null;
    row.bios = bios.status === "fulfilled" ? bios.value : null;
    row.err = rec.status === "rejected" && bios.status === "rejected" ? rec.reason.message : "";
    row.loaded = true;
    if (root && st.step === 1) paintConsole(id);
  }

  function consoleRow(p) {
    const r = ui.rows[p.id] || {};
    let info = "Controllo…";
    if (r.loaded) {
      const parts = [];
      if (r.rec) parts.push(r.rec.supported ? `${esc(r.rec.emulator)}${r.rec.installed ? " (già installato)" : ""}` : "nessuna installazione automatica");
      if (r.bios) parts.push(biosMissing(r.bios) ? "BIOS mancanti" : r.bios.items.length ? "BIOS a posto" : "nessun BIOS richiesto");
      info = parts.join(" · ") || esc(r.err || "informazioni non disponibili");
    }
    const can = r.rec && r.rec.supported && !r.rec.installed;
    // perche' questo emulatore: una frase e tre motivi (fedeltà, prestazioni, controller) con il testo nel tooltip
    const m = r.rec && r.rec.reasons;
    const why = r.rec && r.rec.reason ? `<span class="onb-why">${esc(r.rec.reason)}</span>` : "";
    const chips = m ? [["fedelta", "Fedeltà"], ["prestazioni", "Prestazioni"], ["controller", "Controller"]]
      .filter(([k]) => m[k]).map(([k, t]) => `<span class="onb-chip" tabindex="0" title="${esc(m[k])}">${t}</span>`).join(" ") : "";
    return `<li data-id="${esc(p.id)}"><span class="onb-name">${esc(p.name)}</span> <span class="onb-info">${info}</span>
      ${can ? `<button class="btn" data-a="install" data-id="${esc(p.id)}" ${r.busy ? "disabled" : ""}>${r.busy ? "Installo…" : "Installa"}</button>` : ""}
      <span class="onb-prog" role="status">${esc(r.msg || "")}</span>
      ${why || chips ? `<div class="onb-motivi">${why} ${chips}</div>` : ""}</li>`;
  }

  function paintConsole(id) {
    const li = body().querySelector(`li[data-id="${CSS.escape(id)}"]`);
    const p = consoles(ui.found).find((x) => x.id === id);
    if (li && p) li.outerHTML = consoleRow(p);
  }

  function stepConsoles() {
    const list = consoles(ui.found);
    if (!list.length) {
      body().innerHTML = `<p>Nessuna console da configurare ora: torna al primo passo e verifica la cartella, oppure salta. Potrai installare gli emulatori anche dopo, da Impostazioni.</p>`;
      return;
    }
    body().innerHTML = `<p>Emulatori consigliati e BIOS per le console trovate. Installa solo ciò che ti serve.</p>
      <ul class="onb-list">${list.map(consoleRow).join("")}</ul>`;
    list.filter((p) => !(ui.rows[p.id] && ui.rows[p.id].loaded)).forEach((p) => loadConsole(p.id));
  }

  async function install(id) {
    const r = ui.rows[id]; if (!r || r.busy) return;
    r.busy = true; r.msg = "Avvio…"; paintConsole(id);
    let stop = false;
    const poll = (async () => {
      while (!stop) {
        await wait(1200);
        if (stop) break;
        try {
          const s = await call(`/api/emulators/install-recommended?console=${encodeURIComponent(id)}`);
          const cur = (s.steps || []).find((x) => x.state === "running") || (s.steps || [])[0];
          if (cur) r.msg = `${cur.label} (${Math.round((s.progress || 0) * 100)}%)`;
        } catch { /* l'avanzamento è solo informativo */ }
        if (root && st.step === 1) paintConsole(id);
      }
    })();
    try {
      const out = await call("/api/emulators/install-recommended", { console: id });
      r.msg = out.message || "Installato"; if (r.rec) r.rec.installed = true;
    } catch (e) { r.msg = `Non riuscito: ${e.message}`; }
    stop = true; await poll; r.busy = false;
    if (root && st.step === 1) { paintConsole(id); live(r.msg); }
  }

  // 3 - store: l'elenco viene da /api/accounts; le credenziali si inseriscono poi da Impostazioni
  async function stepStores() {
    body().innerHTML = `<p role="status">Cerco gli store installati…</p>`;
    try {
      ui.stores = (await call("/api/accounts")).stores.filter((s) => !["manual", "ports"].includes(s.id));
    } catch (e) {
      if (root && st.step === 2) body().innerHTML = `<p class="onb-msg" role="status">Elenco degli store non disponibile (${esc(e.message)}). Puoi saltare e collegarli da Impostazioni.</p>`;
      return;
    }
    if (!root || st.step !== 2) return;
    if (!st.stores) st.stores = Object.fromEntries(ui.stores.map((s) => [s.id, !!(s.detected && s.enabled)]));
    body().innerHTML = `<p>Importa i giochi degli store trovati su questo PC. Se serve un accesso, lo fai dopo da Impostazioni › Account.</p>
      <ul class="onb-list">${ui.stores.map((s) => `<li><label><input type="checkbox" data-store="${esc(s.id)}" ${st.stores[s.id] ? "checked" : ""}>
      ${esc(s.name)} <span class="onb-info">${s.detected ? "trovato" : s.login ? "accesso richiesto" : "non trovato"}</span></label></li>`).join("")}</ul>`;
    focusFirst();
  }

  // 4 - tema ed esperienza, applicati subito e annullati se si salta il passo
  async function stepLook() {
    body().innerHTML = `<p role="status">Carico temi ed esperienze…</p>`;
    try { ui.ext = ui.ext || await call("/api/extensions"); } catch (e) {
      if (root && st.step === 3) body().innerHTML = `<p class="onb-msg" role="status">Temi non disponibili (${esc(e.message)}). Puoi cambiarli da Impostazioni.</p>`;
      return;
    }
    if (!root || st.step !== 3) return;
    const x = ui.ext, themes = x.themes || [], exps = (x.experiences || []).filter((e) => e.available);
    if (!ui.origTheme) { ui.origTheme = x.active_theme || "default"; ui.origExp = x.active_experience || ""; }
    const radios = (name, items, cur) => items.map((t) => `<label class="onb-opt"><input type="radio" name="${name}" value="${esc(t.id)}" ${t.id === cur ? "checked" : ""}> ${esc(t.name || t.id)}</label>`).join("");
    body().innerHTML = `<fieldset><legend>Tema</legend>${radios("onb-theme", themes, st.theme || x.active_theme)}</fieldset>
      ${exps.length ? `<fieldset><legend>Esperienza</legend>${radios("onb-exp", exps, st.experience || x.active_experience)}</fieldset>` : ""}
      <p class="onb-info">Le animazioni seguono le impostazioni di movimento (Impostazioni › Aspetto) e il tuo sistema.</p>
      <p class="onb-msg" role="status">${esc(ui.msg)}</p>`;
    focusFirst();
  }

  async function applyLook(kind, id) {
    try {
      await call(kind === "theme" ? "/api/app/theme" : "/api/app/experience", kind === "theme" ? { theme: id } : { experience: id });
      st[kind] = id; persist();
      if (typeof loadExtensions === "function") await loadExtensions();
      ui.msg = "";
    } catch (e) { ui.msg = `Anteprima non riuscita: ${e.message}`; live(ui.msg); }
  }

  async function restoreLook() {
    if (ui.origTheme && st.theme && st.theme !== ui.origTheme) await applyLook("theme", ui.origTheme);
    if (ui.origExp && st.experience && st.experience !== ui.origExp) await applyLook("experience", ui.origExp);
    st.theme = st.experience = ""; persist();
  }

  // fine: /api/setup imposta app.setup_done e importa/crea la libreria, condivisa da tutti i profili
  async function conclude() {
    const romsOk = !!(ui.found || (srv && srv.roms && srv.roms === st.roms));
    body().innerHTML = `<p role="status">Preparo la libreria…</p>`;
    root.querySelector(".onb-nav").innerHTML = "";
    const payload = { start: true, scrape: true };
    if (st.roms && romsOk) payload.roms = st.roms;
    if (st.stores && !st.skipped.includes(2)) payload.stores = st.stores;
    try {
      await call("/api/setup", payload);
      for (let n = 0; n < 1800 && root; n++) {
        const s = (await call("/api/setup")).state;
        if (root) body().innerHTML = `<p role="status">${esc(s.phase || "Preparazione")}</p>`;
        if (s.status === "done") break;
        if (s.status === "error") throw new Error(s.phase);
        await wait(1000);
      }
      try { localStorage.removeItem(KEY); } catch { /* ignora */ }
      close();
    } catch (e) {
      if (!root) return;
      body().innerHTML = `<p class="onb-msg" role="alert">Non è stato possibile completare: ${esc(e.message)}</p>`;
      root.querySelector(".onb-nav").innerHTML = `<button class="btn primary" data-a="retry">Riprova</button><button class="btn" data-a="close">Chiudi comunque</button>`;
      focusFirst();
    }
  }

  function close() {
    if (root) { root.remove(); root = null; window.dispatchEvent(new CustomEvent("pozzo:onboarding-done")); }
    document.removeEventListener("keydown", onKey, true);
    if (opener && opener.isConnected) opener.focus();
    const f = resolveOpen; resolveOpen = running = null;
    if (f) f();
  }

  // Esc o «Salta tutto»: conclude con la configurazione minima così l'app si apre
  async function skipAll() { await restoreLook(); conclude(); }

  function onKey(e) {
    if (!root) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); skipAll(); return; }
    if (e.key !== "Tab") return;
    const f = [...root.querySelectorAll("button:not([disabled]):not([hidden]),input,select")];
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (!root.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function onClick(e) {
    const b = e.target.closest("[data-a]"); if (!b || b.disabled) return;
    const a = b.dataset.a;
    if (a === "next") finishStep(false);
    else if (a === "skip") finishStep(true);
    else if (a === "back") { st.step = Math.max(0, st.step - 1); persist(); render(); }
    else if (a === "check") checkRoms();
    else if (a === "pick") pickFolder();
    else if (a === "install") install(b.dataset.id);
    else if (a === "retry") conclude();
    else if (a === "close") close();
    else if (a === "all") skipAll();
  }

  function onChange(e) {
    const t = e.target;
    if (t.dataset.store) { st.stores[t.dataset.store] = t.checked; persist(); }
    else if (t.name === "onb-theme") applyLook("theme", t.value);
    else if (t.name === "onb-exp") applyLook("experience", t.value);
  }

  async function open(force = false) {
    if (running) return running;
    try { srv = await call("/api/setup"); } catch (e) { srv = null; console.warn("setup non disponibile", e); }
    if (srv && srv.done && !force) return;
    if (!srv && !force) return;  // server o rotta non raggiungibili: l'avvio non si blocca
    st = load(localStorage);
    if (!st.roms && srv && srv.roms) st.roms = srv.roms;
    ui.found = null; ui.rows = {}; ui.ext = null; ui.origTheme = ui.origExp = ""; ui.romsMsg = ""; ui.msg = "";
    opener = document.activeElement;
    root = document.createElement("div");
    root.className = "onb";
    root.setAttribute("role", "dialog"); root.setAttribute("aria-modal", "true"); root.setAttribute("aria-labelledby", "onb-title");
    root.innerHTML = `<div class="onb-card"><header><h2 id="onb-title"></h2><button class="btn" data-a="all">Salta tutto</button></header>
      <ol class="onb-steps" aria-label="Passi"></ol><div class="onb-body"></div><div class="onb-nav"></div>
      <div class="onb-live" role="status" aria-live="polite"></div></div>`;
    root.addEventListener("click", onClick);
    root.addEventListener("change", onChange);
    document.body.appendChild(root);
    document.addEventListener("keydown", onKey, true);
    running = new Promise((res) => { resolveOpen = res; });
    if (st.roms) previewSaved();
    render();
    return running;
  }

  window.ONBOARDING = { open };
  // evita la vecchia procedura: app.js, events.js e grid.js continuano a chiamare SETUP.open
  if (typeof SETUP !== "undefined" && SETUP) SETUP.open = open;
})();