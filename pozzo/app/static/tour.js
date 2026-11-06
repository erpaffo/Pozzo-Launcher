"use strict";
/* Pozzo Launcher - tour guidato di primo avvio: passi con velo scuro, evidenza attorno al bersaglio e una scheda
 * ancorata (GSAnchor.place). window.GS.tour = {start(opts), stop(), isActive(), state(), settings}.
 * Stato in localStorage "gs.tour" ({done, off}); parte da solo UNA volta, dopo "pozzo:onboarding-done"; start({manual:true})
 * ignora done/off. Eventi su window: "pozzo:tour-start" e "pozzo:tour-end". I passi il cui bersaglio manca o non e'
 * visibile (altre esperienze, finestra stretta) vengono saltati e "Passo n di N" conta solo quelli mostrati.
 * create(env) e' esportata per i test con node (DOM finto). */
(() => {
  const KEY = "gs.tour", PAD = 6;

  const CSS = `.gs-tour{position:fixed;inset:0;z-index:9500}
.gs-tour-veil{position:absolute;inset:0}
.gs-tour-veil.dim{background:rgba(0,0,0,.62)}
.gs-tour-ring{position:absolute;border-radius:10px;pointer-events:none;box-shadow:0 0 0 9999px rgba(0,0,0,.62),0 0 0 3px var(--accent,#5b8cff)}
.gs-tour-ring[hidden]{display:none}
.gs-tour-card{position:absolute;box-sizing:border-box;width:min(360px,calc(100vw - 16px));max-height:calc(100vh - 16px);overflow:auto;padding:18px 20px;
  background:var(--panel,#171a23);color:var(--text,#e6e8ef);border:1px solid var(--accent,#5b8cff);border-radius:12px;
  box-shadow:0 12px 32px rgba(0,0,0,.5);font-size:15px;line-height:1.5;opacity:0;transform:translateY(8px);
  transition:opacity var(--mo-fast,180ms) ease,transform var(--mo-fast,180ms) var(--mo-ease-out,ease)}
.gs-tour-card[data-in]{opacity:1;transform:none}
.gs-tour-card::before{content:"";display:none;position:absolute;width:12px;height:12px;background:var(--panel,#171a23);
  border:0 solid var(--accent,#5b8cff);transform:rotate(45deg)}
.gs-tour-card[data-side=bottom]::before{display:block;top:-7px;left:calc(var(--arrow,40px) - 6px);border-width:1px 0 0 1px}
.gs-tour-card[data-side=top]::before{display:block;bottom:-7px;left:calc(var(--arrow,40px) - 6px);border-width:0 1px 1px 0}
.gs-tour-card[data-side=right]::before{display:block;left:-7px;top:calc(var(--arrow,40px) - 6px);border-width:0 0 1px 1px}
.gs-tour-card[data-side=left]::before{display:block;right:-7px;top:calc(var(--arrow,40px) - 6px);border-width:1px 1px 0 0}
.gs-tour-card h2{margin:0 0 6px;font-size:18px}
.gs-tour-card p{margin:0 0 12px}
.gs-tour-meta{display:flex;align-items:center;gap:10px;margin-bottom:12px;color:var(--muted,#8b92a5);font-size:13px}
.gs-tour-dots{display:flex;gap:5px}
.gs-tour-dots i{width:8px;height:8px;border-radius:50%;background:var(--line,#262b3a)}
.gs-tour-dots i.on{background:var(--accent,#5b8cff)}
.gs-tour-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.gs-tour-row.end{justify-content:space-between;margin-top:6px}
.gs-tour-card .btn{min-height:40px;font-size:15px}
.gs-tour-off{background:none;border:0;color:var(--text,#e6e8ef);text-decoration:underline;font:inherit;padding:8px 4px;min-height:40px;cursor:pointer}
.gs-tour-live{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.gs-tour button:focus-visible{outline:3px solid var(--accent,#5b8cff);outline-offset:2px}
html[data-motion="off"] .gs-tour-card,html[data-motion="reduced"] .gs-tour-card{transition:none;transform:none}
@media (prefers-reduced-motion:reduce){html:not([data-motion="normal"]) .gs-tour-card{transition:none;transform:none}}
@media (forced-colors:active){.gs-tour-ring{box-shadow:none;outline:3px solid Highlight;outline-offset:2px}.gs-tour-card{border-color:CanvasText}
  .gs-tour-dots i{background:GrayText}.gs-tour-dots i.on{background:Highlight}}`;

  // sel = selettori alternativi (il primo visibile vince; nessun sel = scheda centrata); k = tasti letti da shortcuts.js
  const STEPS = [
    { id: "welcome", get title() { return t("b.tour.welcome.title"); },
      text: () => t("b.tour.welcome.text") },
    { id: "views", sel: ["#nav", "#experience-nav"], get title() { return t("b.tour.views.title"); },
      text: () => t("b.tour.views.text") },
    { id: "search", sel: ["#search"], get title() { return t("b.tour.search.title"); },
      text: (k) => t("b.tour.search.text", {cerca: k.search, palette: k.palette}) },
    { id: "sort", sel: ["#sort"], get title() { return t("b.tour.sort.title"); },
      text: () => t("b.tour.sort.text") },
    { id: "game", sel: [".tile[data-id]", ".gs-dashboard__tile"], get title() { return t("b.tour.game.title"); },
      text: () => t("b.tour.game.text") },
    { id: "top", sel: ["#bp-btn"], get title() { return t("b.tour.top.title"); },
      text: () => t("b.tour.top.text") },
    { id: "settings", sel: ["#settings-btn"], get title() { return t("b.common.settings"); },
      text: () => t("b.tour.settings.text") },
    { id: "themes", sel: ["#settings-btn"], get title() { return t("b.tour.themes.title"); },
      text: () => t("b.tour.themes.text") },
    { id: "profile", sel: ["#mb-profile", "#profile-btn"], get title() { return t("b.tour.profile.title"); },
      text: () => t("b.tour.profile.text") },
    { id: "keys", sel: ['.mb-top[data-m="Impostazioni"]'], get title() { return t("b.tour.keys.title"); },
      text: (k) => t("b.tour.keys.text", {aiuto: k.help}) },
    { id: "end", get title() { return t("b.tour.end.title"); },
      text: () => t("b.tour.end.text") },
  ];

  const loadState = (s) => {
    let o = null;
    try { o = JSON.parse(s.getItem(KEY)); } catch { /* assente, corrotto o storage non disponibile */ }
    o = o && typeof o === "object" ? o : {};
    return { done: o.done === true, off: o.off === true };
  };

  /** Passi realmente mostrabili: senza sel sempre; con sel solo se un candidato esiste ed e' visibile nella finestra. */
  function resolve(steps, find, vp, A) {
    const out = [];
    for (const step of steps) {
      if (!step.sel) { out.push({ step, el: null }); continue; }
      for (const sel of step.sel) {
        let el = null;
        try { el = find(sel); } catch { /* selettore non valido: prossimo */ }
        if (el && A.inView(el.getBoundingClientRect(), vp)) { out.push({ step, el }); break; }
      }
    }
    return out;
  }

  function create(env) {
    const { win, doc, store, A } = env;
    let mem = null, ui = null, cur = null, shownId = null, opener = null, raf = 0, timer = 0, armed = false;

    const read = () => mem || loadState(store);
    const write = (st) => { mem = st; try { store.setItem(KEY, JSON.stringify(st)); } catch { /* si perde solo la memoria */ } };
    const vp = () => ({ w: win.innerWidth, h: win.innerHeight });
    const list = () => resolve(STEPS, (s) => doc.querySelector(s), vp(), A);
    const safe = (f) => (...a) => { try { return f(...a); } catch (e) { try { console.warn("tour", e); } catch { /* niente console */ } } };

    function keys() {
      const PS = win.PozzoShortcuts, lab = (id) => {
        try { return PS.keysOf(PS.REGISTRY.find((x) => x.id === id)).map((c) => PS.formatCombo(c)); } catch { return []; }
      };
      return { search: lab("search")[0] || "/", palette: lab("palette")[0] || "Ctrl+K",
        help: lab("help").sort((a, b) => a.length - b.length)[0] || "?" };
    }

    function build() {
      if (!doc.getElementById("gs-tour-css")) {
        const css = doc.createElement("style"); css.id = "gs-tour-css"; css.textContent = CSS; doc.head.appendChild(css);
      }
      const el = (tag, cls, txt) => {
        const e = doc.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e;
      };
      const btn = (cls, txt, fn) => {
        const b = el("button", cls, txt); b.setAttribute("type", "button"); b.addEventListener("click", safe(fn)); return b;
      };
      const u = { root: el("div", "gs-tour"), veil: el("div", "gs-tour-veil"), ring: el("div", "gs-tour-ring"), card: el("div", "gs-tour-card"),
        title: el("h2"), text: el("p"), count: el("span"), dots: el("span", "gs-tour-dots"), live: el("div", "gs-tour-live") };
      u.title.id = "gs-tour-title"; u.text.id = "gs-tour-text";
      u.ring.hidden = true;
      u.live.setAttribute("aria-live", "polite");
      u.card.setAttribute("role", "dialog"); u.card.setAttribute("aria-modal", "true");
      u.card.setAttribute("aria-labelledby", "gs-tour-title"); u.card.setAttribute("aria-describedby", "gs-tour-text");
      u.dots.setAttribute("aria-hidden", "true");
      u.back = btn("btn", t("b.common.back"), () => go(-1));
      u.next = btn("btn accent", t("b.common.next"), () => go(1));
      u.skip = btn("btn", t("b.tour.skip"), () => end("done"));
      u.off = btn("gs-tour-off", t("b.tour.off"), () => end("off"));
      const meta = el("div", "gs-tour-meta"); meta.append(u.count, u.dots);
      const r1 = el("div", "gs-tour-row"); r1.append(u.back, u.next, u.skip);
      const r2 = el("div", "gs-tour-row end"); r2.append(u.off);
      u.card.append(u.title, u.text, meta, r1, r2);
      u.root.append(u.veil, u.ring, u.card, u.live);
      const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
      for (const t of ["click", "mousedown", "contextmenu", "wheel", "touchmove", "dblclick"]) u.veil.addEventListener(t, stop, { passive: false });
      return u;
    }

    function render() {
      if (!ui) return;
      const shown = list();
      if (!shown.length) return end(null);
      let i = shown.findIndex((s) => s.step.id === cur);
      if (i < 0) { // il bersaglio e' sparito: il prossimo passo mostrabile, altrimenti l'ultimo prima
        const pos = STEPS.findIndex((s) => s.id === cur);
        i = shown.findIndex((s) => STEPS.indexOf(s.step) > pos);
        if (i < 0) i = shown.length - 1;
        cur = shown[i].step.id;
      }
      const { step, el } = shown[i], n = shown.length;
      if (shownId !== cur) {
        shownId = cur;
        ui.title.textContent = step.title;
        ui.text.textContent = step.text(keys());
        ui.count.textContent = t("b.common.stepOf", {n: i + 1, tot: n});
        ui.dots.textContent = "";
        shown.forEach((_, k) => { const d = doc.createElement("i"); if (k === i) d.className = "on"; ui.dots.appendChild(d); });
        ui.back.disabled = i === 0;
        ui.next.textContent = i === n - 1 ? t("b.common.end") : t("b.common.next");
        ui.live.textContent = `${t("b.common.stepOf", {n: i + 1, tot: n})}. ${step.title}. ${ui.text.textContent}`;
        ui.next.focus();
      } else {
        ui.count.textContent = t("b.common.stepOf", {n: i + 1, tot: n});
        ui.back.disabled = i === 0;
        ui.next.textContent = i === n - 1 ? t("b.common.end") : t("b.common.next");
      }
      const v = vp(), sz = { w: ui.card.offsetWidth || 360, h: ui.card.offsetHeight || 240 };
      let p;
      if (el) {
        const r = el.getBoundingClientRect();
        const t = { left: r.left - PAD, top: r.top - PAD, right: r.right + PAD, bottom: r.bottom + PAD, width: r.width + 2 * PAD, height: r.height + 2 * PAD };
        ui.ring.hidden = false;
        Object.assign(ui.ring.style, { left: `${t.left}px`, top: `${t.top}px`, width: `${t.width}px`, height: `${t.height}px` });
        p = A.place(t, sz, v, { gap: 16 });
      } else {
        ui.ring.hidden = true;
        p = { left: Math.max(8, Math.round((v.w - sz.w) / 2)), top: Math.max(8, Math.round((v.h - sz.h) / 2)), side: "center", arrow: null };
      }
      ui.veil.className = el ? "gs-tour-veil" : "gs-tour-veil dim";
      ui.card.style.left = `${p.left}px`; ui.card.style.top = `${p.top}px`;
      ui.card.setAttribute("data-side", p.side);
      ui.card.style.setProperty("--arrow", `${p.arrow ?? 0}px`);
    }

    function go(d) {
      if (!ui) return;
      const shown = list(), i = shown.findIndex((s) => s.step.id === cur);
      if (i < 0) return render();
      const j = i + d;
      if (j < 0) return;
      if (j >= shown.length) return end("done");
      cur = shown[j].step.id;
      render();
    }

    const schedule = () => { if (!raf) raf = win.requestAnimationFrame(() => { raf = 0; safe(render)(); }); };

    function onKey(e) {
      if (!ui) return;
      const k = e.key, a = doc.activeElement, btns = [ui.back, ui.next, ui.skip, ui.off].filter((b) => !b.disabled);
      const eat = () => { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation?.(); };
      if (k === "Escape") { eat(); end("done"); }
      else if (k === "Tab") {
        if (!btns.includes(a)) { eat(); btns[0].focus(); }
        else if (e.shiftKey && a === btns[0]) { eat(); btns[btns.length - 1].focus(); }
        else if (!e.shiftKey && a === btns[btns.length - 1]) { eat(); btns[0].focus(); }
      } else if (k === "ArrowRight") { eat(); go(1); }
      else if (k === "ArrowLeft") { eat(); go(-1); }
      else if (k === "Enter" && !btns.includes(a)) { eat(); go(1); }
      else if ((k === "Enter" || k === " ") && btns.includes(a)) e.stopPropagation(); // il pulsante a fuoco fa il suo clic
      else if (!(e.ctrlKey || e.metaKey)) { e.stopPropagation(); e.stopImmediatePropagation?.(); } // le scorciatoie dell'app restano ferme
    }

    function end(kind) {
      if (!ui) return;
      if (kind) { const st = { ...read() }; if (kind === "off") st.off = true; else st.done = true; write(st); }
      doc.removeEventListener("keydown", onKey, true);
      win.removeEventListener("resize", schedule);
      win.removeEventListener("scroll", schedule, true);
      win.clearInterval(timer); if (raf && win.cancelAnimationFrame) win.cancelAnimationFrame(raf);
      raf = 0; timer = 0;
      ui.root.remove(); ui = null; cur = shownId = null;
      if (opener && opener.isConnected !== false && opener.focus) opener.focus();
      opener = null;
      win.dispatchEvent(new CustomEvent("pozzo:tour-end", { detail: { kind: kind || "stop" } }));
      if (kind === "off") env.toast?.(t("b.tour.toast.off"));
    }

    function start(opts = {}) {
      if (ui) return false;
      try {
        if (!opts.manual) {
          const st = read();
          if (st.done || st.off || doc.querySelector(".onb")) return false;
        }
        if (env.desktop && !env.desktop()) return false;
        const shown = list();
        if (!shown.length) return false;
        opener = doc.activeElement;
        ui = build();
        cur = shown[0].step.id; shownId = null;
        doc.body.appendChild(ui.root);
        doc.addEventListener("keydown", onKey, true);
        win.addEventListener("resize", schedule);
        win.addEventListener("scroll", schedule, true);
        timer = win.setInterval(schedule, 500);
        win.dispatchEvent(new CustomEvent("pozzo:tour-start"));
        render();
        win.requestAnimationFrame(() => { if (ui) ui.card.setAttribute("data-in", "1"); });
        return true;
      } catch (e) {
        try { console.warn("tour", e); } catch { /* niente console */ }
        if (ui) end(null);
        return false;
      }
    }

    // avvio automatico: una sola volta, 600 ms dopo la fine della procedura di primo avvio
    function arm() {
      if (armed) return; armed = true;
      const h = () => { win.removeEventListener("pozzo:onboarding-done", h); env.setTimeout(() => start(), 600); };
      win.addEventListener("pozzo:onboarding-done", h);
    }

    return {
      start, stop: () => end(null), isActive: () => !!ui, state: () => ({ ...read() }), arm,
      settings: {
        auto: () => !read().off,
        setAuto: (on) => write(on ? { done: false, off: false } : { ...read(), off: true }),
      },
    };
  }

  const api = { KEY, STEPS, loadState, resolve, create };
  if (typeof window === "undefined") { module.exports = api; return; }

  let store = null;
  try { store = window.localStorage; } catch { /* storage bloccato */ }
  const tour = create({ win: window, doc: document, store, A: window.GSAnchor, setTimeout: (f, ms) => window.setTimeout(f, ms),
    desktop: () => (window.GS?.mode || "desktop") === "desktop", toast: (m) => window.GS?.toast?.(m) });
  window.GS = window.GS || {};
  window.GS.tour = tour;
  tour.arm();
})();
