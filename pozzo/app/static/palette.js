"use strict";
/* Palette comandi (Ctrl/Cmd+K): giochi, console, sezioni delle Impostazioni e azioni del registro scorciatoie.
 * Cerca solo nei dati già in memoria (nessuna rete). La logica di ricerca è pura ed esportata per i test Node;
 * l'interfaccia nasce solo se c'è un DOM. Movimento: solo transform/opacity, spento con html[data-motion="off"]. */
(function () {
  const root = typeof window !== "undefined" ? window : globalThis;
  const MAX_GAMES = 8, MAX_OTHER = 6, MIN_DEBOUNCE = 120;

  /** Minuscolo e senza accenti: "Pokémon" == "pokemon". */
  const normalize = (s) => String(s ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();

  /** 0 = prefisso, 1 = inizio di una parola, 2 = contenuto; -1 = nessuna corrispondenza (tutte le parole devono comparire). */
  function score(haystack, query) {
    const h = normalize(haystack), tokens = normalize(query).split(/\s+/).filter(Boolean);
    if (!tokens.length) return 0;
    let worst = 0;
    for (const t of tokens) {
      const i = h.indexOf(t);
      if (i < 0) return -1;
      worst = Math.max(worst, i === 0 ? 0 : /[\s\-_:.\/]/.test(h[i - 1]) ? 1 : 2);
    }
    return worst;
  }

  /** Filtra e ordina (per punteggio, poi per ordine di arrivo) al massimo `limit` voci; `text` dà il testo cercabile. */
  function rank(items, query, text, limit) {
    const out = [];
    items.forEach((item, order) => {
      const s = score(text(item), query);
      if (s >= 0) out.push({ item, s, order });
    });
    out.sort((a, b) => a.s - b.s || a.order - b.order);
    return out.slice(0, limit).map((x) => x.item);
  }

  /** Ritarda fn di almeno 120 ms; .cancel() annulla la chiamata in attesa. */
  function debounce(fn, ms = 140, timers = { set: (...a) => setTimeout(...a), clear: (id) => clearTimeout(id) }) {
    let id = null;
    const wrapped = (...args) => { timers.clear(id); id = timers.set(() => { id = null; fn(...args); }, Math.max(MIN_DEBOUNCE, ms)); };
    wrapped.cancel = () => { timers.clear(id); id = null; };
    return wrapped;
  }

  /** Gruppi di risultati: sources = { games, consoles, settings, actions }, ognuno un array di { label, hint?, ... }. */
  function search(sources, query) {
    const q = normalize(query);
    const lab = (x) => `${x.label} ${x.hint || ""}`;
    const groups = [
      { id: "games", label: t("b.palette.group.games"), items: q ? rank(sources.games || [], q, lab, MAX_GAMES) : [] },
      { id: "consoles", label: t("b.common.console"), items: rank(sources.consoles || [], q, lab, MAX_OTHER) },
      { id: "settings", label: t("b.common.settings"), items: rank(sources.settings || [], q, lab, MAX_OTHER) },
      { id: "actions", label: t("b.palette.group.actions"), items: rank(sources.actions || [], q, lab, q ? MAX_OTHER : 8) },
    ];
    return groups.filter((g) => g.items.length);
  }

  const api = { normalize, score, rank, debounce, search, MAX_GAMES, MIN_DEBOUNCE };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.GSPalette = api;
  if (typeof document === "undefined" || !document.body) return;

  /* ---- sorgenti dai dati in memoria */
  const SC = () => root.PozzoShortcuts;
  function sources() {
    const st = typeof S !== "undefined" ? S : null;
    const games = [];
    for (const g of st?.games || []) {
      if (g.grp && (g.id !== g.grp.primary || g.grp.hidden)) continue;
      games.push({ label: g.title, hint: st.plats?.get(g.platform)?.name || g.platform || "", run: () => GS.openGame(g.id) });
    }
    const consoles = [...(st?.plats?.values() || [])].map((p) => ({ label: p.name || p.id, hint: t("b.common.console"), run: () => { closeOverlays(); setView({ type: "platform", id: p.id }); } }));
    const settings = (typeof SETTINGS_CATS !== "undefined" ? SETTINGS_CATS : []).map(([id, label]) => ({ label, hint: t("b.common.settings"), run: () => openSettings(id) }));
    const actions = (SC()?.REGISTRY || []).filter((en) => (en.scope === "desktop" || en.scope === "both") && en.id !== "palette")
      .map((en) => ({ label: en.label, hint: SC().keyLabel(en.id), run: () => SC().run(en.id) }));
    return { games, consoles, settings, actions };
  }
  function closeOverlays() {
    if (typeof settingsOpen === "function" && settingsOpen()) closeSettings();
    if (typeof S !== "undefined" && S.detail) closeDetail();
  }

  /* ---- interfaccia */
  let box = null, input = null, list = null, opener = null, flat = [], active = 0, data = null;
  const esc2 = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function render() {
    const groups = search(data, input.value);
    flat = [];
    list.innerHTML = groups.map((g) => `<li role="presentation" class="pal-group"><span id="pal-g-${g.id}">${g.label}</span><ul role="group" aria-labelledby="pal-g-${g.id}">`
      + g.items.map((it) => { const i = flat.push(it) - 1; return `<li role="option" id="pal-o-${i}" data-i="${i}" aria-selected="false" class="pal-item"><span class="pal-l">${esc2(it.label)}</span>${it.hint ? `<kbd class="pal-h">${esc2(it.hint)}</kbd>` : ""}</li>`; }).join("")
      + "</ul></li>").join("") || '<li role="presentation" class="pal-empty">' + t("b.palette.empty") + '</li>';
    select(0);
  }
  function select(i) {
    active = flat.length ? (i + flat.length) % flat.length : 0;
    list.querySelectorAll('[role="option"]').forEach((el) => el.setAttribute("aria-selected", String(+el.dataset.i === active)));
    const el = $(`#pal-o-${active}`, list);
    input.setAttribute("aria-activedescendant", el ? el.id : "");
    el?.scrollIntoView({ block: "nearest" });
  }
  function choose(i) {
    const it = flat[i];
    if (!it) return;
    close(false);
    try { const r = it.run(); if (r instanceof Promise) r.catch((e) => GS.toast?.(e.message, true)); } catch (e) { GS.toast?.(e.message, true); }
  }
  let dirty = false;
  const onInput = debounce(() => { dirty = false; render(); });

  function open() {
    if (box) return true;
    opener = document.activeElement;
    data = sources();
    box = document.createElement("div");
    box.className = "pal-overlay";
    box.innerHTML = '<div class="pal" role="dialog" aria-modal="true" aria-label="' + t("b.palette.dialog") + '">'
      + '<input class="pal-input" type="text" role="combobox" aria-expanded="true" aria-controls="pal-list" aria-autocomplete="list" aria-activedescendant="" autocomplete="off" spellcheck="false" placeholder="' + t("b.palette.placeholder") + '" aria-label="' + t("b.palette.inputLabel") + '">'
      + '<ul class="pal-list" id="pal-list" role="listbox" aria-label="' + t("b.palette.results") + '"></ul>'
      + '<div class="pal-foot muted">' + t("b.palette.footer") + '</div></div>';
    document.body.appendChild(box);
    input = $(".pal-input", box);
    list = $(".pal-list", box);
    render();
    input.focus();
    box.addEventListener("mousedown", (e) => { if (e.target === box) { e.preventDefault(); close(); } });
    list.addEventListener("click", (e) => { const o = e.target.closest("[data-i]"); if (o) choose(+o.dataset.i); });
    list.addEventListener("mousemove", (e) => { const o = e.target.closest("[data-i]"); if (o && +o.dataset.i !== active) select(+o.dataset.i); });
    input.addEventListener("input", () => { dirty = true; onInput(); });
    box.addEventListener("keydown", (e) => {
      const k = e.key;
      if (k === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
      else if (k === "ArrowDown") { e.preventDefault(); select(active + 1); }
      else if (k === "ArrowUp") { e.preventDefault(); select(active - 1); }
      else if (k === "Enter") { e.preventDefault(); if (dirty) { onInput.cancel(); dirty = false; render(); } choose(active); }
      else if (k === "Tab") { e.preventDefault(); input.focus(); } // focus trap: l'unico elemento attivo è il campo
    });
    return true;
  }
  function close(restore = true) {
    if (!box) return;
    onInput.cancel();
    const b = box;
    box = null;
    b.remove();
    if (restore && opener && opener.isConnected) opener.focus();
  }
  const toggle = () => (box ? (close(), true) : open());
  Object.assign(api, { open, close, toggle, isOpen: () => !!box });
})();