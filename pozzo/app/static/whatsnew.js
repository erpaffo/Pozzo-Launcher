"use strict";
/* Pozzo Launcher - novita' dopo un aggiornamento: una finestra con le funzioni aggiunte e, accanto a ciascuna,
 * «Mostra come» che avvia un tutorial con lo stesso aspetto del tour (GS.tour.start({steps})).
 * window.GS.whatsnew = {open(), check()}.
 * Elenco curato in NEWS (per versione, testi in i18n: b.news.<id>.title/.text, passi b.news.<id>.s<n>.title/.text).
 * Una versione senza voci curate ripiega sulle voci «### Aggiunto» del changelog (solo italiano, senza tutorial).
 * Stato in localStorage "gs.whatsnew" ({seen: "x.y.z"}): la finestra esce una volta per aggiornamento. Al primo avvio
 * in assoluto non esce (c'e' gia' il tour); chi aveva gia' Pozzo ma non questo stato vede le novita' dopo BASE. */
(() => {
  const KEY = "gs.whatsnew", BASE = "0.17.5";

  // --- logica pura (testata con node) ---
  const ver = (v) => String(v || "").split(/[.-]/).slice(0, 3).map((n) => parseInt(n, 10) || 0);
  const cmp = (a, b) => {
    const x = ver(a), y = ver(b);
    for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) - (y[i] || 0);
    return 0;
  };
  const loadSeen = (s) => {
    try { const o = JSON.parse(s.getItem(KEY)); return o && typeof o.seen === "string" ? o.seen : null; } catch { return null; }
  };
  const saveSeen = (s, v) => { try { s.setItem(KEY, JSON.stringify({ seen: v })); } catch { /* storage pieno o bloccato */ } };
  /** Da quale versione mostrare: l'ultima vista; senza stato, utente esistente (tour/suggerimenti usati) -> BASE, nuovo -> current. */
  const since = (s, current) => {
    const v = loadSeen(s);
    if (v) return v;
    let old = false;
    try { old = !!(s.getItem("gs.tour") || s.getItem("gs.hints")); } catch { /* storage bloccato: come nuovo */ }
    return old ? BASE : current;
  };
  /** Gruppi {version, items} delle versioni in (from, to], dalla piu' recente. */
  const pending = (news, from, to) => Object.keys(news)
    .filter((v) => cmp(v, from) > 0 && cmp(v, to) <= 0)
    .sort((a, b) => cmp(b, a))
    .map((version) => ({ version, items: news[version] }));
  const cut = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
  /** Voci «### Aggiunto» del changelog per le versioni in (from, to] escluse `skip`; «Non rilasciato» vale come `to`. */
  function fromChangelog(md, from, to, skip = []) {
    const out = [];
    let cur = null, added = false;
    for (const raw of String(md || "").split(/\r?\n/)) {
      const line = raw.trim();
      const h2 = /^##\s+(.+)$/.exec(line);
      if (h2) {
        const m = /^(\d+\.\d+\.\d+)/.exec(h2[1]);
        const v = m ? m[1] : /rilasciato/i.test(h2[1]) ? to : null;
        cur = v && cmp(v, from) > 0 && cmp(v, to) <= 0 && !skip.includes(v) ? { version: v, items: [] } : null;
        if (cur) { const prev = out.find((g) => g.version === v); if (prev) cur = prev; else out.push(cur); }
        added = false;
        continue;
      }
      if (/^###\s+/.test(line)) { added = /aggiunt/i.test(line); continue; }
      if (!cur || !added || !line.startsWith("- ")) continue;
      const body = line.slice(2).replace(/\*\*/g, "").replace(/`/g, "").trim();
      const i = body.search(/: |\. /);
      const title = cut(i > 0 && i < 90 ? body.slice(0, i) : body, 70);
      const text = cut(i > 0 && i < 90 ? body.slice(i + 2) : "", 170);
      cur.items.push({ id: `cl-${cur.version}-${cur.items.length}`, title, text });
    }
    return out.filter((g) => g.items.length).sort((a, b) => cmp(b.version, a.version));
  }

  const api = { KEY, BASE, cmp, loadSeen, saveSeen, since, pending, fromChangelog };
  if (typeof window === "undefined") { module.exports = api; return; }

  // --- tutorial: passi come il tour (sel = bersagli alternativi, wait = aspetta che compaia, prep = porta li') ---
  const go = (tab) => () => { if (typeof openSettings === "function") openSettings(tab); };
  const home = () => { const p = document.getElementById("settings-page"); if (p && !p.hidden && typeof closeSettings === "function") closeSettings(); };
  const step = (id, n, extra = {}) => ({
    id: `${id}-${n}`, get title() { return t(`b.news.${id}.s${n}.title`); }, text: () => t(`b.news.${id}.s${n}.text`), ...extra,
  });
  const DL_NAV = ['.nav-item[data-view="downloads"]', '#menubar button[data-view="downloads"]'];

  const NEWS = {
    "0.18.0": [
      { id: "whatsnew", icon: "✨" },
      { id: "themes", icon: "🎨", steps: [
        step("themes", 1, { sel: ["#theme-list"], wait: true, prep: go("aspetto") }),
        step("themes", 2, { sel: ['.mb-top[data-m="Visualizza"]', "#experience-nav"] }),
      ] },
      { id: "detailLayout", icon: "🗂️", steps: [
        step("detailLayout", 1, { sel: ["#detail-layout-list"], wait: true, prep: go("aspetto") }),
        step("detailLayout", 2, { sel: [".tile[data-id]", ".gs-dashboard__tile"], prep: home }),
      ] },
      { id: "clipboard", icon: "📋", steps: [
        step("clipboard", 1, { sel: ["#dls-clip"], wait: true, prep: go("download") }),
        step("clipboard", 2, { sel: DL_NAV, prep: home }),
      ] },
      { id: "savedFilters", icon: "🔖", steps: [
        step("savedFilters", 1, { sel: ["#sf-new"], prep: home }),
      ] },
      { id: "importers", icon: "📥", steps: [
        step("importers", 1, { sel: ["#imp-fmt"], wait: true, prep: go("libreria") }),
      ] },
      { id: "matchFix", icon: "🔎", steps: [
        step("matchFix", 1, { sel: [".tile[data-id]", ".gs-dashboard__tile"], prep: home }),
        step("matchFix", 2),
      ] },
      { id: "backup", icon: "💾", steps: [
        step("backup", 1, { sel: ["#backup-list"], wait: true, prep: go("dati") }),
        step("backup", 2, { sel: ["#bk-auto"], wait: true }),
      ] },
    ],
    "0.17.6": [
      { id: "switch2", icon: "🕹️", steps: [
        step("switch2", 1, { sel: ["#emu-inst"], wait: true, prep: go("emulatori") }),
        step("switch2", 2, { sel: ["#s2-go"], wait: true, prep: go("download") }),
      ] },
      { id: "downloads", icon: "⬇️", steps: [
        step("downloads", 1, { sel: DL_NAV, prep: home }),
        step("downloads", 2, { sel: ["#dls-cats"], wait: true, prep: go("download") }),
        step("downloads", 3, { sel: ["#dls-rss"], wait: true }),
      ] },
      { id: "multipart", icon: "🧩", steps: [
        step("multipart", 1, { sel: ["#dls-rules"], wait: true, prep: go("download") }),
      ] },
      { id: "webimages", icon: "🖼️", steps: [
        step("webimages", 1, { sel: [".tile[data-id]", ".gs-dashboard__tile"], prep: home }),
        step("webimages", 2),
      ] },
    ],
  };

  // --- interfaccia ---
  const CSS = `.gs-news{border:0;padding:0;background:transparent;color:var(--text,#e7e9ee);width:min(640px,calc(100vw - 32px));max-width:none;max-height:calc(100vh - 32px);overflow:visible}
.gs-news::backdrop{background:rgba(5,7,12,.62);backdrop-filter:blur(6px)}
.gs-news-card{display:flex;flex-direction:column;max-height:calc(100vh - 32px);background:var(--panel,#171a23);border:1px solid var(--line,#262b3a);border-radius:18px;overflow:hidden;
  box-shadow:0 28px 72px rgba(0,0,0,.55);opacity:0;transform:translateY(14px) scale(.98);
  transition:opacity var(--mo-base,240ms) ease,transform var(--mo-base,240ms) var(--mo-ease-out,ease)}
.gs-news-card.in{opacity:1;transform:none}
.gs-news-head{position:relative;padding:28px 28px 22px;border-bottom:1px solid var(--line,#262b3a);
  background:radial-gradient(120% 160% at 0% 0%,color-mix(in srgb,var(--accent,#5b8cff) 40%,transparent),transparent 58%),
    radial-gradient(110% 160% at 100% 0%,color-mix(in srgb,var(--accent-2,#8b72ff) 32%,transparent),transparent 55%)}
.gs-news-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  background:color-mix(in srgb,var(--accent,#5b8cff) 24%,transparent);border:1px solid color-mix(in srgb,var(--accent,#5b8cff) 45%,transparent)}
.gs-news-head h2{margin:14px 0 6px;font-size:26px;line-height:1.15;letter-spacing:-.01em}
.gs-news-head p{margin:0;color:var(--muted,#8b92a5);font-size:14px;line-height:1.5}
.gs-news-x{position:absolute;top:14px;right:14px;width:36px;height:36px;border-radius:50%;border:0;background:transparent;color:var(--muted,#8b92a5);font-size:20px;cursor:pointer}
.gs-news-x:hover{background:color-mix(in srgb,var(--text,#e7e9ee) 10%,transparent);color:var(--text,#e7e9ee)}
.gs-news-list{margin:0;padding:10px 14px 14px;overflow:auto;flex:1}
.gs-news-ver{margin:12px 8px 4px;color:var(--muted,#8b92a5);font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
.gs-news-item{display:grid;grid-template-columns:46px 1fr auto;gap:14px;align-items:center;padding:12px 10px;border-radius:14px;
  transition:background var(--mo-fast,180ms) ease}
.gs-news-item:hover{background:color-mix(in srgb,var(--text,#e7e9ee) 5%,transparent)}
.gs-news-ico{width:46px;height:46px;border-radius:14px;display:grid;place-items:center;font-size:22px;
  background:color-mix(in srgb,var(--accent,#5b8cff) 16%,transparent);border:1px solid color-mix(in srgb,var(--accent,#5b8cff) 34%,transparent)}
.gs-news-item h3{margin:0 0 3px;font-size:15px;line-height:1.3}
.gs-news-item p{margin:0;color:var(--muted,#8b92a5);font-size:13px;line-height:1.45}
.gs-news-how{white-space:nowrap;min-height:36px}
.gs-news-item.done .gs-news-how::before{content:"✓ "}
.gs-news-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 22px;border-top:1px solid var(--line,#262b3a)}
.gs-news-log{background:none;border:0;padding:6px 2px;color:var(--muted,#8b92a5);font:inherit;font-size:13px;text-decoration:underline;cursor:pointer}
.gs-news-log:hover{color:var(--text,#e7e9ee)}
.gs-news button:focus-visible{outline:3px solid var(--accent,#5b8cff);outline-offset:2px}
@media (max-width:560px){.gs-news-head{padding:24px 20px 18px}.gs-news-item{grid-template-columns:40px 1fr}.gs-news-ico{width:40px;height:40px}.gs-news-how{grid-column:2;justify-self:start}}
html[data-motion="off"] .gs-news-card,html[data-motion="reduced"] .gs-news-card{transition:none;transform:none}
@media (prefers-reduced-motion:reduce){html:not([data-motion="normal"]) .gs-news-card{transition:none;transform:none}}
@media (forced-colors:active){.gs-news-card{border-color:CanvasText}.gs-news-ico{border-color:CanvasText}}`;

  let store = null;
  try { store = window.localStorage; } catch { /* storage bloccato: la finestra esce a ogni avvio dopo un aggiornamento */ }
  const mem = { getItem: () => null, setItem() {} };
  const S = store || mem;
  let dlg = null, groups = [], current = "", reopen = false;
  const done = new Set(); // tutorial gia' visti in questa sessione (spunta accanto al pulsante)
  const BLOCK = ".pal-overlay,#pp,.onb,#sc-dlg,#bp-help,#splash:not([hidden]),#setup:not([hidden]),#lightbox:not([hidden]),.gs-tour,dialog[open]";
  const visible = (el) => el.getClientRects().length > 0;
  const blocked = () => [...document.querySelectorAll(BLOCK)].some(visible);
  const mk = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
  const label = (it, k) => it[k] ?? t(`b.news.${it.id}.${k}`);

  function css() {
    if (document.getElementById("gs-news-css")) return;
    const s = mk("style"); s.id = "gs-news-css"; s.textContent = CSS; document.head.appendChild(s);
  }

  function tutorial(it) {
    done.add(it.id);
    reopen = true;
    close();
    if (!window.GS?.tour?.start({ steps: it.steps })) { reopen = false; window.GS?.toast?.(t("b.news.noTutorial")); setTimeout(show, 50); } // l'evento close arriva dopo
  }

  function build() {
    css();
    const d = mk("dialog", "gs-news");
    d.setAttribute("aria-labelledby", "gs-news-title");
    const card = mk("div", "gs-news-card");
    const head = mk("div", "gs-news-head");
    const badge = mk("span", "gs-news-badge", `✨ ${t("b.news.badge", { v: current })}`);
    const h = mk("h2", "", t("b.news.title")); h.id = "gs-news-title";
    const x = mk("button", "gs-news-x", "×"); x.type = "button"; x.setAttribute("aria-label", t("b.news.close")); x.onclick = close;
    head.append(badge, h, mk("p", "", t("b.news.subtitle")), x);
    const list = mk("div", "gs-news-list");
    for (const g of groups) {
      if (groups.length > 1) list.append(mk("div", "gs-news-ver", t("b.news.version", { v: g.version })));
      for (const it of g.items) {
        const row = mk("div", "gs-news-item" + (done.has(it.id) ? " done" : ""));
        const txt = mk("div");
        txt.append(mk("h3", "", label(it, "title")));
        const desc = label(it, "text");
        if (desc) txt.append(mk("p", "", desc));
        row.append(mk("span", "gs-news-ico", it.icon || "•"), txt);
        if (it.steps?.length) {
          const b = mk("button", "btn gs-news-how", t("b.news.how")); b.type = "button";
          b.setAttribute("aria-label", `${t("b.news.how")}: ${label(it, "title")}`);
          b.onclick = () => tutorial(it);
          row.append(b);
        }
        list.append(row);
      }
    }
    const foot = mk("div", "gs-news-foot");
    const log = mk("button", "gs-news-log", t("b.news.changelog")); log.type = "button";
    log.onclick = () => { close(); if (typeof openSettings === "function") openSettings("sistema"); };
    const ok = mk("button", "btn primary", t("b.news.ok")); ok.type = "button"; ok.onclick = close;
    foot.append(log, ok);
    card.append(head, list, foot);
    d.append(card);
    d.addEventListener("close", () => { saveSeen(S, current); d.remove(); if (dlg === d) dlg = null; }); // anche Esc: vista
    d.addEventListener("click", (e) => { if (e.target === d) close(); }); // clic sul velo
    return d;
  }

  function show() {
    if (dlg || !groups.length) return;
    dlg = build();
    document.body.appendChild(dlg);
    dlg.showModal();
    requestAnimationFrame(() => dlg?.querySelector(".gs-news-card")?.classList.add("in"));
    dlg.querySelector(".gs-news-how, .btn.primary")?.focus();
  }

  function close() { if (dlg?.open) dlg.close(); }

  addEventListener("pozzo:tour-end", (e) => {
    if (!reopen || !e.detail?.custom) return;
    reopen = false;
    setTimeout(show, 250); // dopo il tutorial si torna all'elenco, per vedere le altre novita'
  });

  async function about() {
    const r = await fetch("/api/about");
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  }

  /** Dopo un aggiornamento: una volta, appena l'interfaccia e' libera (niente configurazione, tour o altre finestre). */
  async function check() {
    let a;
    try { a = await about(); } catch { return; }
    current = a.version || "";
    if (!current) return;
    const from = since(S, current);
    if (cmp(current, from) <= 0) { saveSeen(S, current); return; }
    const curated = pending(NEWS, from, current);
    groups = [...curated, ...fromChangelog(a.changelog, from, current, curated.map((g) => g.version))]
      .sort((x, y) => cmp(y.version, x.version));
    if (!groups.length) { saveSeen(S, current); return; }
    let tries = 0;
    const wait = () => {
      if (dlg) return;
      const desktop = (window.GS?.mode || "desktop") === "desktop";
      if (desktop && !blocked() && !document.hidden) { show(); return; }
      if (++tries < 120) setTimeout(wait, 2000); // al massimo ~4 minuti, poi alla prossima apertura
    };
    setTimeout(wait, 2500);
  }

  /** A richiesta (Impostazioni › Sistema): le novita' curate della versione installata, o le ultime presenti. */
  async function open() {
    if (dlg) return;
    if (!current) { try { current = (await about()).version || ""; } catch { return; } }
    const vs = Object.keys(NEWS).filter((v) => cmp(v, current) <= 0).sort((a, b) => cmp(b, a));
    groups = vs.length ? [{ version: vs[0], items: NEWS[vs[0]] }] : [];
    show();
  }

  document.addEventListener("click", (e) => { if (e.target.closest?.("#about-news-open")) open(); });
  window.GS = window.GS || {};
  window.GS.whatsnew = { open, check, NEWS };
  check();
})();
