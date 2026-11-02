"use strict";
/* Pozzo Launcher - suggerimenti al primo uso: un fumetto alla volta ancorato a un elemento.
 * GS.hints.register({id, target:'#sel', text, when?}) ; GS.hints.show(id) ; GS.hints.settings.
 * Stato in localStorage "gs.hints" ({seen:{id:true}, snoozeUntil:ms|0, off:bool}); semplice, non per profilo
 * (shortcut: i profili condividono i suggerimenti visti; per separarli basta prefissare la chiave col profilo). */
(() => {
  const KEY = "gs.hints", GAP = 3000, DAY = 86400000;

  // --- logica pura (testata con node) ---
  const load = (s) => {
    let o = {};
    try { o = JSON.parse(s.getItem(KEY)) || {}; } catch (e) { /* stato assente o corrotto */ }
    const seen = {};
    if (o.seen && typeof o.seen === "object") for (const k of Object.keys(o.seen)) if (o.seen[k] === true) seen[k] = true;
    const snooze = Number(o.snoozeUntil);
    return { seen, snoozeUntil: Number.isFinite(snooze) && snooze > 0 ? snooze : 0, off: o.off === true };
  };
  const save = (s, st) => { try { s.setItem(KEY, JSON.stringify(st)); } catch (e) { /* storage pieno: si perde solo la memoria */ } };
  const active = (st, now) => !st.off && now >= st.snoozeUntil;
  const canShow = (st, id, now) => active(st, now) && !st.seen[id];
  const mode = (st, now) => (st.off ? "off" : st.snoozeUntil > now ? "snooze" : "on");
  const setMode = (st, m, now) => {
    st.off = m === "off";
    st.snoozeUntil = m === "snooze" ? now + 7 * DAY : 0;
    return st;
  };
  const resetSeen = (st) => { st.seen = {}; return st; };
  const api = { KEY, GAP, load, save, active, canShow, mode, setMode, resetSeen };

  if (typeof window === "undefined") { module.exports = api; return; }

  // --- interfaccia ---
  const store = window.localStorage;
  const reg = new Map();
  const queue = [];
  let cur = null, lastClosed = 0, timer = 0, pop = null;

  const css = document.createElement("style");
  css.textContent = ".gs-hint{position:fixed;z-index:9000;max-width:280px;padding:12px 14px;background:var(--panel,#171a23);color:var(--text,#e6e8ef);"
    + "border:1px solid var(--accent,#5b8cff);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.45);font-size:13px;line-height:1.4;"
    + "opacity:0;transform:translateY(6px);transition:opacity var(--mo-fast,180ms) ease,transform var(--mo-fast,180ms) var(--mo-ease-out,ease)}"
    + ".gs-hint.in{opacity:1;transform:none}"
    + ".gs-hint .row{display:flex;gap:8px;margin-top:10px;justify-content:flex-end}"
    + "html[data-motion=\"off\"] .gs-hint,html[data-motion=\"reduced\"] .gs-hint{transition:none;transform:none}"
    + "@media (prefers-reduced-motion:reduce){html:not([data-motion=\"normal\"]) .gs-hint{transition:none;transform:none}}";
  document.head.appendChild(css);

  const state = () => load(store);
  const visible = (el) => !!el && el.getClientRects().length > 0;

  function onKey(e) { if (e.key === "Escape") { e.stopPropagation(); close(false); } }

  function close(markSeen) {
    if (!cur) return;
    const id = cur.id, el = pop;
    if (markSeen) { const st = state(); st.seen[id] = true; save(store, st); }
    cur = null; pop = null; lastClosed = Date.now();
    document.removeEventListener("keydown", onKey, true);
    if (el) { el.classList.remove("in"); setTimeout(() => el.remove(), 200); }
    pump();
  }

  function place(el, target) {
    const r = target.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight;
    el.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left)) + "px";
    el.style.top = Math.max(8, r.bottom + 8 + h < innerHeight ? r.bottom + 8 : r.top - h - 8) + "px";
  }

  function display(h, target) {
    cur = h;
    pop = document.createElement("div");
    pop.className = "gs-hint"; pop.setAttribute("role", "status");
    const p = document.createElement("div"); p.textContent = h.text;
    const row = document.createElement("div"); row.className = "row";
    const later = document.createElement("button"); later.className = "btn"; later.type = "button"; later.textContent = "Più tardi";
    const ok = document.createElement("button"); ok.className = "btn accent"; ok.type = "button"; ok.textContent = "Ho capito";
    later.onclick = () => close(false); ok.onclick = () => close(true);
    row.append(later, ok); pop.append(p, row);
    document.body.appendChild(pop);
    place(pop, target);
    document.addEventListener("keydown", onKey, true);
    requestAnimationFrame(() => { if (pop) pop.classList.add("in"); });
  }

  function pump() {
    clearTimeout(timer);
    if (cur || !queue.length) return;
    const wait = Math.max(0, lastClosed + GAP - Date.now());
    if (wait) { timer = setTimeout(pump, wait); return; }
    const id = queue.shift(), h = reg.get(id);
    const target = h && document.querySelector(h.target);
    if (!h || !canShow(state(), id, Date.now()) || !visible(target) || (h.when && !h.when())) { pump(); return; }
    display(h, target);
  }

  const hints = {
    register(h) {
      if (h && h.id && h.target && h.text) reg.set(h.id, h);
    },
    show(id) {
      if (!reg.has(id) || queue.includes(id) || (cur && cur.id === id)) return;
      queue.push(id); pump();
    },
    settings: {
      mode: () => mode(state(), Date.now()),
      setMode: (m) => { save(store, setMode(state(), m, Date.now())); if (m !== "on") close(false); },
      resetSeen: () => { save(store, resetSeen(state())); },
    },
  };
  window.GS = window.GS || {};
  window.GS.hints = hints;

  // suggerimenti reali, mostrati uno alla volta dopo l'avvio (se l'elemento non c'è, si salta)
  const REAL = [
    ["bigpicture", "#bp-btn", "Big Picture: la libreria a schermo intero, pensata per il controller."],
    ["search", "#search", "Cerca per titolo o sviluppatore. Premi / per saltare qui da ovunque."],
    ["settings", "#settings-btn", "Qui trovi cartelle ROM, emulatori, store e tutte le opzioni."],
    ["gamemenu", ".tile", "Clic destro su un gioco per preferiti, stato, collegamento sul desktop e altro."],
  ];
  REAL.forEach(([id, target, text]) => hints.register({ id, target, text }));
  const start = () => setTimeout(() => REAL.forEach((r) => hints.show(r[0])), 4000);
  if (document.readyState === "complete") start(); else addEventListener("load", start);
})();
