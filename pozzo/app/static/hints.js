"use strict";
/* Pozzo Launcher - suggerimenti: un fumetto alla volta ancorato a un elemento, per scoprire funzioni.
 * GS.hints.register({id, target:'#sel'|[...], text:str|()=>str, priority?, when?, done?}) ; GS.hints.show(id) ; GS.hints.settings.
 * Un suggerimento e' "visto" quando compare (mai ripetuto, salvo «Rivedi tutti»). Per sessione ne escono al massimo MAX:
 * il primo dopo FIRST ms dal caricamento, il secondo almeno SECOND ms dopo il primo. Si sceglie tra i non visti con
 * bersaglio visibile e `when` vera (priorita' piu' alta prima, poi a caso). `done`: selettore che, se presente, indica
 * che l'utente ha gia' scoperto la funzione (segnato visto in silenzio).
 * Stato in localStorage "gs.hints" ({seen:{id:true}, snoozeUntil:ms|0, off:bool}); semplice, non per profilo
 * (shortcut: i profili condividono i suggerimenti visti; per separarli basta prefissare la chiave col profilo). */
(() => {
  const KEY = "gs.hints", DAY = 86400000, MAX = 2, FIRST = 10000, SECOND = 60000, TICK = 2000;

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
  const mode = (st, now) => (st.off ? "off" : st.snoozeUntil > now + DAY ? "week" : st.snoozeUntil > now ? "day" : "on");
  const setMode = (st, m, now) => {
    st.off = m === "off";
    st.snoozeUntil = m === "day" ? now + DAY : m === "week" ? now + 7 * DAY : 0;
    return st;
  };
  const resetSeen = (st) => { st.seen = {}; return st; };
  /** Prima la priorita' piu' alta, a parita' a caso (rnd() in [0,1)). */
  const pick = (list, rnd = Math.random) => {
    const top = Math.max(...list.map((h) => h.priority));
    const best = list.filter((h) => h.priority === top);
    return best[Math.floor(rnd() * best.length)] || null;
  };

  /* Motore: tutta la logica, con l'ambiente iniettato (d) cosi' si prova con node senza browser.
   * d: store, now(), query(sel)->el|null, rect(el), vp()->{w,h}, inView(rect,vp), place(rect,size,vp), blocked()->bool,
   *    ui: {open(h, text)->void, measure()->{w,h}, apply(pos), close()}, rnd?  */
  function engine(d) {
    const reg = new Map(), t0 = d.now();
    let cur = null, shown = 0, last = 0, paused = false;
    const st = () => load(d.store);
    const find = (h) => {
      for (const sel of [].concat(h.target)) {
        const el = d.query(sel);
        if (el && d.inView(d.rect(el), d.vp())) return el;
      }
      return null;
    };
    const mark = (id, on) => { const s = st(); if (on) s.seen[id] = true; else delete s.seen[id]; save(d.store, s); };
    const ok = (h) => { try { return !h.when || !!h.when(); } catch (e) { return false; } };
    const layout = () => {
      const el = find(cur.h);
      if (!el) { drop(); return; }
      d.ui.apply(d.place(d.rect(el), d.ui.measure(), d.vp()));
    };
    function end() { cur = null; d.ui.close(); }
    /** chiusura normale: il suggerimento resta visto */
    function close() { if (cur) end(); }
    /** il bersaglio e' sparito o c'e' una pausa: si toglie il «visto», non e' stato letto */
    function drop() { if (!cur) return; mark(cur.h.id, false); shown = Math.max(0, shown - 1); end(); }
    function open(h) {
      mark(h.id, true); shown++; last = d.now();
      cur = { h };
      d.ui.open(h, typeof h.text === "function" ? h.text() : h.text);
      layout();
    }
    function tick() {
      const now = d.now();
      if (cur) { layout(); return; }
      const s = st();
      for (const h of reg.values()) if (h.done && !s.seen[h.id] && d.query(h.done)) mark(h.id, true);
      if (paused || shown >= MAX || !active(load(d.store), now) || d.blocked()) return;
      if (now - (shown ? last : t0) < (shown ? SECOND : FIRST)) return;
      const seen = load(d.store).seen;
      const list = [...reg.values()].filter((h) => !seen[h.id] && ok(h) && find(h));
      const h = list.length ? pick(list, d.rnd) : null;
      if (h) open(h);
    }
    return {
      register(h) {
        if (h && h.id && h.target && h.text) reg.set(h.id, { priority: 5, ...h });
      },
      show(id) { // a richiesta: subito, anche se gia' visto
        const h = reg.get(id);
        if (!h || cur || paused || !active(st(), d.now()) || d.blocked() || !find(h)) return false;
        open(h); return true;
      },
      tick, relayout() { if (cur) layout(); }, close, drop,
      pause() { paused = true; drop(); },
      setMode(m) { save(d.store, setMode(st(), m, d.now())); if (m !== "on") close(); },
      mode: () => mode(st(), d.now()),
      resetSeen() { save(d.store, resetSeen(st())); },
      current: () => cur && cur.h.id,
    };
  }
  const api = { KEY, DAY, MAX, FIRST, SECOND, load, save, active, canShow, mode, setMode, resetSeen, pick, engine };

  if (typeof window === "undefined") { module.exports = api; return; }

  // --- interfaccia ---
  const css = document.createElement("style");
  css.textContent = ".gs-hint{position:fixed;z-index:9000;box-sizing:border-box;width:300px;max-width:calc(100vw - 16px);padding:12px 14px;background:var(--panel,#171a23);color:var(--text,#e6e8ef);"
    + "border:1px solid var(--accent,#5b8cff);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.45);font-size:13px;line-height:1.4;"
    + "opacity:0;transform:translateY(6px);transition:opacity var(--mo-fast,180ms) ease,transform var(--mo-fast,180ms) var(--mo-ease-out,ease)}"
    + ".gs-hint.in{opacity:1;transform:none}"
    + ".gs-hint .gs-arrow{position:absolute;width:10px;height:10px;background:var(--panel,#171a23);border:0 solid var(--accent,#5b8cff);transform:rotate(45deg)}"
    + ".gs-hint .gs-arrow[data-side=\"bottom\"]{top:-6px;border-width:1px 0 0 1px}"
    + ".gs-hint .gs-arrow[data-side=\"top\"]{bottom:-6px;border-width:0 1px 1px 0}"
    + ".gs-hint .gs-arrow[data-side=\"right\"]{left:-6px;border-width:0 0 1px 1px}"
    + ".gs-hint .gs-arrow[data-side=\"left\"]{right:-6px;border-width:1px 1px 0 0}"
    + ".gs-hint .row{display:flex;gap:8px;margin-top:10px;justify-content:flex-end}"
    + ".gs-hint .foot{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;margin-top:10px;padding-top:8px;border-top:1px solid var(--line,#262b3a);font-size:12px}"
    + ".gs-hint .foot button{background:none;border:0;padding:2px 0;color:var(--muted,#8b92a5);font:inherit;cursor:pointer;text-decoration:underline}"
    + ".gs-hint .foot button:hover,.gs-hint .foot button:focus-visible{color:var(--text,#e6e8ef)}"
    + ".gs-hint .keys{flex-basis:100%;color:var(--muted,#8b92a5)}"
    + "html[data-motion=\"off\"] .gs-hint,html[data-motion=\"reduced\"] .gs-hint{transition:none;transform:none}"
    + "@media (prefers-reduced-motion:reduce){html:not([data-motion=\"normal\"]) .gs-hint{transition:none;transform:none}}";
  document.head.appendChild(css);

  const store = window.localStorage;
  let pop = null, okBtn = null, E = null;
  const note = (m) => { if (typeof toast === "function") toast(m); };
  const AFTER = " Per riattivarli: Impostazioni › Generale › Suggerimenti.";
  const mk = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt) e.textContent = txt; return e; };

  const ui = {
    open(h, text) {
      pop = mk("div", "gs-hint");
      pop.setAttribute("role", "status"); pop.setAttribute("aria-live", "polite");
      const row = mk("div", "row");
      okBtn = mk("button", "btn accent", "Ho capito"); okBtn.type = "button"; okBtn.setAttribute("aria-keyshortcuts", "Alt+H");
      okBtn.onclick = () => E.close();
      row.append(okBtn);
      const foot = mk("div", "foot");
      const day = mk("button", "", "Silenzia per 1 giorno"), off = mk("button", "", "Non mostrare più");
      day.type = off.type = "button";
      day.onclick = () => { E.setMode("day"); note("Suggerimenti silenziati per 1 giorno." + AFTER); };
      off.onclick = () => { E.setMode("off"); note("Suggerimenti disattivati." + AFTER); };
      foot.append(day, off, mk("span", "keys", "Esc chiude · Alt+H porta qui il focus"));
      pop.append(mk("div", "", text), row, foot);
      document.body.appendChild(pop);
      requestAnimationFrame(() => { if (pop) pop.classList.add("in"); });
    },
    measure: () => ({ w: pop.offsetWidth, h: pop.offsetHeight }),
    apply(pos) {
      pop.style.left = pos.left + "px"; pop.style.top = pos.top + "px";
      pop.querySelector(".gs-arrow")?.remove();
      if (pos.side === "center" || pos.arrow === null) return;
      const a = mk("span", "gs-arrow"); a.dataset.side = pos.side; a.setAttribute("aria-hidden", "true");
      a.style[pos.side === "top" || pos.side === "bottom" ? "left" : "top"] = (pos.arrow - 5) + "px";
      pop.appendChild(a);
    },
    close() {
      const el = pop; pop = null; okBtn = null;
      if (el) { el.classList.remove("in"); setTimeout(() => el.remove(), 200); }
    },
  };

  const BLOCK = "dialog[open],.pal-overlay,#pp,.onb,#sc-dlg,#bp-help,#splash:not([hidden]),#setup:not([hidden]),#lightbox:not([hidden]),#settings-page:not([hidden])";
  const visible = (el) => el.getClientRects().length > 0;
  E = engine({
    store, now: Date.now,
    query: (s) => { try { const el = document.querySelector(s); return el && visible(el) ? el : null; } catch (e) { return null; } },
    rect: (el) => el.getBoundingClientRect(),
    vp: () => ({ w: innerWidth, h: innerHeight }),
    inView: (r, vp) => window.GSAnchor.inView(r, vp),
    place: (r, size, vp) => window.GSAnchor.place(r, size, vp),
    blocked: () => [...document.querySelectorAll(BLOCK)].some(visible),
    ui,
  });

  let raf = 0;
  const relayout = () => { if (raf) return; raf = requestAnimationFrame(() => { raf = 0; E.relayout(); }); };
  addEventListener("resize", relayout);
  addEventListener("scroll", relayout, { capture: true, passive: true });
  document.addEventListener("keydown", (e) => {
    if (!E.current()) return;
    if (e.key === "Escape") { e.stopPropagation(); E.close(); }
    else if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === "h" || e.key === "H") && okBtn) { e.preventDefault(); okBtn.focus(); }
  }, true);
  addEventListener("pozzo:tour-start", () => E.pause());

  const hints = {
    register: E.register,
    show: E.show,
    settings: { mode: E.mode, setMode: E.setMode, resetSeen: E.resetSeen },
  };
  window.GS = window.GS || {};
  window.GS.hints = hints;

  // catalogo: ogni bersaglio esiste nel DOM reale (index.html, menubar.js, js/*.js); se in una grafica manca, si passa oltre
  const K = (id) => window.PozzoShortcuts?.keyLabel(id) || "";
  const withKey = (txt, id) => () => { const k = K(id); return k ? `${txt} (${k})` : txt; };
  const SET = ["#settings-btn", ".mb-top[data-m=\"Impostazioni\"]"];
  [
    { id: "search", target: "#search", priority: 9, text: withKey("Cerca per titolo o sviluppatore: premi il tasto per saltare qui da ovunque", "search") },
    { id: "palette", target: ["#view-title", "#menubar"], priority: 8, done: ".pal-overlay", text: withKey("Palette comandi: giochi, console, impostazioni e azioni in un solo campo", "palette") },
    { id: "bigpicture", target: "#bp-btn", priority: 8, text: withKey("Big Picture: la libreria a schermo intero, pensata per il controller", "bigPicture") },
    { id: "gamemenu", target: ".tile", priority: 7, text: "Clic destro su un gioco: preferiti, stato, collegamento sul desktop e altro." },
    { id: "random", target: "#random-btn", priority: 6, text: withKey("Non sai cosa giocare? Il dado sceglie un gioco a caso tra quelli mostrati", "random") },
    { id: "shortcuts", target: ["#menubar", "#experience-bar"], priority: 6, done: "#sc-dlg[open]", text: withKey("Tutte le scorciatoie da tastiera in un elenco, anche personalizzabili", "help") },
    { id: "wishlist", target: ".nav-item[data-view=\"wishlist\"]", priority: 5, text: withKey("Lista desideri: i giochi che vuoi, con avviso quando scendono di prezzo", "viewWishlist") },
    { id: "stats", target: ".nav-item[data-view=\"stats\"]", priority: 5, text: withKey("Statistiche: tempo di gioco, generi preferiti e andamento della libreria", "viewStats") },
    { id: "profile", target: ["#mb-profile", "#profile-btn"], priority: 5, text: withKey("Più persone in casa? Ognuno ha preferiti e tempo di gioco suoi: qui cambi utente", "profile") },
    { id: "settings", target: SET, priority: 5, done: "#settings-page:not([hidden])", text: withKey("Impostazioni: cartelle ROM, emulatori, store e tutte le opzioni", "settings") },
    { id: "appearance", target: SET, priority: 4, text: "In Impostazioni › Aspetto scegli animazioni, intensità del movimento e look dell'app." },
    { id: "themes", target: [".mb-top[data-m=\"Visualizza\"]", "#experience-nav"], priority: 4, text: withKey("Temi e grafiche cambiano l'aspetto: prova il tema successivo", "nextTheme") },
    { id: "experiences", target: ["#experience-nav", "#drawer-toggle"], priority: 4, text: withKey("La libreria ha più grafiche (Catalogo, Cinema, Console…): passa alla successiva", "nextExperience") },
    { id: "emucfg", target: "#d-emucfg", priority: 7, text: "Nella scheda del gioco trovi le impostazioni consigliate per l'emulatore, applicabili con un clic e annullabili." },
    { id: "mods", target: "#d-mod-sites", priority: 6, text: "Nella scheda del gioco: cerca le mod sui siti che le ospitano." },
  ].forEach(hints.register);

  setInterval(E.tick, TICK);
})();
