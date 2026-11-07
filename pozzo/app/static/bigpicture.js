"use strict";
/* Pozzo Launcher - Big Picture: interfaccia a schermo intero per controller (e tastiera).
 *
 * Controller: Gamepad API standard (Xbox, PlayStation, Switch Pro...). Croce/stick per muoversi,
 * A conferma, B indietro, Y cerca, X preferito, LB/RB salti veloci, Select+Start tenuti premuti
 * chiudono il gioco in esecuzione. Tastiera: frecce, Invio, Esc/Backspace, F (preferito), / (cerca).
 * Ogni schermata e' un oggetto con render/move/ok/back: la navigazione e' per indici, non per
 * coordinate, quindi resta fluida anche con migliaia di giochi (le griglie sono virtualizzate).
 */

const BP = { lib: null, stack: [], details: new Map(), running: null, layout: "classic",
  palette: store.get("bpPalette", "default"), text: store.get("bpText", "normal") };
const main = $("#bp-main");

/* ------------------------------------------------------------------ utilita' */
function hueOf(s) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360; return h; }
function platName(id) { return BP.lib.plats.get(id)?.name || id; }
function fmtTime(sec) { if (!sec) return ""; const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60); return h ? `${h} h ${m} min` : `${m} min`; }

function toast(msg, err = false) {
  const t = $("#bp-toast");
  t.textContent = msg; t.className = err ? "err" : ""; t.hidden = false;
  announce(msg);
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), err ? 6000 : 3000);
}
GS.toast = toast;

/* ------------------------------------------------------------------ accessibilità */

/** Applica palette, dimensione dei testi e lettura vocale, ricordando le scelte sul PC. */
function applyLook() {
  const html = document.documentElement;
  html.dataset.palette = BP.palette || "default";
  html.dataset.bptext = BP.text || "normal";
}


const PALETTES = [
  { id: "default", get label() { return t("c.palette.default"); } },
  { id: "deuteranopia", get label() { return t("c.palette.deuteranopia"); } },
  { id: "protanopia", get label() { return t("c.palette.protanopia"); } },
  { id: "tritanopia", get label() { return t("c.palette.tritanopia"); } },
  { id: "contrast", get label() { return t("c.palette.contrast"); } },
];
const TEXTS = [
  { id: "normal", get label() { return t("c.textsize.normal"); } },
  { id: "large", get label() { return t("c.textsize.large"); } },
  { id: "xlarge", get label() { return t("c.textsize.xlarge"); } },
];


/** Big Picture serve solo a giocare: restano ROM presenti e giochi PC installati (niente store, cataloghi o «da installare»). */
const playable = (g) => (!g.store || g.installed) && g.store !== "online";

/** Toglie dalla libreria tutto ciò che non si può avviare; se il gioco principale di un gruppo cade, ne sceglie uno avviabile. */
function keepPlayable(lib) {
  lib.games = lib.games.filter(playable);
  const first = new Map();
  for (const g of lib.games) if (!first.has(g.gi) || g.id === g.grp.primary) first.set(g.gi, g.id);
  for (const [gi, id] of first) lib.groups[gi].primary = id;
  lib.byId = new Map(lib.games.map((g) => [g.id, g]));
  return lib;
}
const loadLibrary = async () => keepPlayable(decodeLibrary(await api("/api/library?part=owned")));

function visibleGames() {
  return BP.lib.games.filter((g) => g.id === g.grp.primary && !g.grp.hidden && playable(g));
}


/* ------------------------------------------------------------------ sfondo e dettagli */
async function detail(id) {
  if (!BP.details.has(id)) BP.details.set(id, api(`/api/game/${id}`).catch(() => null));
  return BP.details.get(id);
}

/** "#rrggbb" oppure null: qualsiasi altro valore non diventa mai CSS. */
const safeAccent = (v) => (typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v) ? v.toLowerCase() : null);
const accents = new Map(); // id -> promessa del colore (null se assente)
const bpCoverAccentOn = () => GSUi.prefs(GSUi.saved()).coverAccent; // Aspetto > Colore della copertina, predefinito attivo
async function setGlow(id) {
  const bg = $("#bp-bg");
  if (!id || !bpCoverAccentOn()) { bg.style.removeProperty("--game-accent"); return; }
  if (!accents.has(id)) accents.set(id, api(`/api/game/${id}/cover-accent`).then((r) => safeAccent(r?.accent)).catch(() => null));
  const c = await accents.get(id);
  if (glowId !== id) return; // nel frattempo il fuoco e' passato altrove
  if (c && bpCoverAccentOn()) bg.style.setProperty("--game-accent", c); else bg.style.removeProperty("--game-accent");
}
window.addEventListener("gs-ui-change", () => setGlow(glowId));
window.addEventListener("storage", (e) => { if (e.key === "gs.ui") setGlow(glowId); }); // cambiata da un'altra finestra

let bgTimer = 0, bgFront = 0, glowId = null;
function setBackground(id) {
  window.Dualsense?.led(id);
  clearTimeout(bgTimer);
  glowId = id || null;
  setGlow(glowId);
  bgTimer = setTimeout(async () => {
    const d = id ? await detail(id) : null;
    const m = d?.media || {};
    const src = m.hero || m.screenshot || m.fanart || m.header || m.title || m.cover;
    const layers = document.querySelectorAll("#bp-bg .bg-img");
    const next = layers[1 - bgFront];
    if (!src) { layers.forEach((l) => l.classList.remove("on")); return; }
    next.style.backgroundImage = `url("${src}?w=1280")`;
    next.classList.add("on");
    layers[bgFront].classList.remove("on");
    bgFront = 1 - bgFront;
  }, 220);
}

/* ------------------------------------------------------------------ stili TV */
/** Pezzo dello stile attivo; quello che manca viene dallo stile Classico. */
const layoutPart = (name) => BPLayouts[BP.layout]?.[name] || BPLayouts.classic[name];
const homeScreen = (...a) => layoutPart("home")(...a);
const shelvesScreen = (...a) => layoutPart("shelves")(...a);
const gameScreen = (...a) => layoutPart("game")(...a);
const card = (...a) => layoutPart("card")(...a);
const textCard = (...a) => layoutPart("textCard")(...a);
const renderNav = (...a) => layoutPart("nav")(...a);

/* ------------------------------------------------------------------ schermate */
function push(screen) { BP.stack.push(screen); show(); }
function pop() { if (BP.stack.length > 1) { BP.stack.pop(); beep("back"); show(); } }
function cur() { return BP.stack[BP.stack.length - 1]; }
function show() { const s = cur(); main.innerHTML = ""; s.render(main); renderNav(); renderHints(); announce(s.title || ""); Pad.resetSpoken(); }

const TABS = [
  { id: "home", get label() { return t("c.tab.home"); }, open: () => { BP.stack = [homeScreen()]; show(); } },
  { id: "foryou", get label() { return t("c.tab.foryou"); }, open: () => push(forYouScreen()) },
  { id: "all", get label() { return t("c.tab.all"); }, open: () => push(discoverScreen(t("c.tab.all"), sortTitle(visibleGames()), "all")) },
  { id: "plat", get label() { return t("c.tab.plat"); }, open: () => push(platformsScreen()) },
  { id: "coll", get label() { return t("c.tab.coll"); }, open: () => push(collectionsScreen()) },
  { id: "fav", get label() { return t("c.tab.fav"); }, open: () => push(gridScreen(t("c.tab.fav"), sortTitle(visibleGames().filter((g) => g.grp.favorite)), "fav")) },
  { id: "search", get label() { return t("c.action.search"); }, open: () => push(searchScreen()) },
  { id: "look", get label() { return t("c.tab.look"); }, open: () => push(lookScreen()) },
  { id: "media", get label() { return t("c.tab.media"); }, get aria() { return t("c.tab.media.aria"); }, icon: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18V5l11-2v13"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/></svg>', open: () => window.PozzoMedia?.toggle() },
  { id: "user", get label() { return t("c.tab.user"); }, get aria() { return t("c.tab.user.aria"); }, open: () => { beep("ok"); GSProfilePicker.open({ toast }); } },
  { id: "exit", get label() { return t("c.tab.exit"); }, open: () => exitBigPicture() },
];
const MEDIA_TAB = TABS.findIndex((t) => t.id === "media");
// alla chiusura del pannello il focus torna sulla voce «Musica» della barra
window.addEventListener("pozzo-media-close", () => { const s = cur(); if (s && "navFocus" in s) { s.navFocus = MEDIA_TAB; renderNav(); } });

/** Apre una scheda del menu' in alto (le schede non si accumulano: Home + scheda). */
function openTab(i) {
  const t = TABS[i];
  if (!t) return;
  if (t.id === "exit" || t.id === "media" || t.id === "user") { t.open(); return; }
  BP.stack = [homeScreen()];
  if (t.id === "home") show(); else t.open();
}

/** L1/R1 (LB/RB), Q/E, Tab: scheda precedente/successiva ("Esci" non si apre scorrendo). */
function stepTab(d) {
  const ids = TABS.map((_, i) => i).filter((i) => !["exit", "media", "user"].includes(TABS[i].id));
  let k = ids.findIndex((i) => TABS[i].id === cur().tab);
  if (k < 0) k = 0;
  k = (k + d + ids.length) % ids.length;
  beep("move");
  openTab(ids[k]);
  const el = document.querySelectorAll(".bp-tab")[ids[k]];
  if (el) { el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); }
}


const sortTitle = (list) => list.slice().sort((a, b) => collator.compare(a.sort, b.sort));


/* ---- griglia virtualizzata (console, collezione, PC, libreria) */
/** Griglia con i filtri Scopri: LT/RT cambiano il filtro, l'intestazione mostra quello attivo. */
function discoverScreen(title, base, tab, preset = store.get("bpDisc", ""), i = 0) {
  const d = discover(base, { preset });
  const items = d.cmp ? d.items.slice().sort(d.cmp) : d.items;
  const head = `<div class="shop-chips"><span class="chip"><b>${glyph("lt")}</b><b>${glyph("rt")}</b> ${esc(d.preset.label)}</span>`
    + (d.preset.hint ? `<span class="chip muted">${esc(d.preset.hint)}</span>` : "") + `</div>`;
  const scr = gridScreen(title, items, tab, { head, score: d.preset.score });
  scr.i = Math.min(i, Math.max(0, items.length - 1));
  const go = (dir) => {
    const k = (PRESETS.findIndex((p) => p.id === preset) + dir + PRESETS.length) % PRESETS.length;
    store.set("bpDisc", PRESETS[k].id);
    BP.stack[BP.stack.length - 1] = discoverScreen(title, base, tab, PRESETS[k].id);
    show(); beep("move");
  };
  scr.lt = () => go(-1);
  scr.rt = () => go(1);
  scr.hints = [["a", t("c.action.open")], ["b", t("c.action.back")], ["x", t("c.action.fav")], ["lt", t("c.hint.filter")], ["rt", t("c.hint.filter")]];
  return scr;
}

function gridScreen(title, items, tab = "all", opts = {}) {
  const scr = {
    tab, title, items, i: 0, navFocus: null, cols: 6, cw: 0, ch: 0,
    render(el) {
      el.innerHTML = `<div class="bp-grid-view"><div class="bp-grid-head"><h1>${esc(title)}</h1><span>${items.length.toLocaleString(GSI18n.lang)} ${opts.unit || t("c.unit.games")}</span>`
        + (opts.head || "") + `</div><div class="bp-grid" id="grid"><div class="bp-grid-inner" id="grid-inner"></div></div></div>`;
      if (!items.length) { $("#grid-inner").innerHTML = `<p style="padding:0 3rem" class="muted">${t("c.grid.empty")}</p>`; return; }
      const W = $("#grid").clientWidth - 6 * 16;
      const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
      const cardW = (opts.text ? 15 : 11) * rem, gap = 1.3 * rem;
      this.cols = Math.max(1, Math.floor((W + gap) / (cardW + gap)));
      this.cw = cardW + gap;
      this.ch = (opts.text ? cardW * 9 / 16 : cardW * 4 / 3) + (opts.text ? 1.4 : 3.2) * rem;
      this.update();
    },
    update() {
      renderNav();
      const inner = $("#grid-inner"), grid = $("#grid");
      if (!inner || !items.length) return;
      const row = Math.floor(this.i / this.cols), H = grid.clientHeight;
      const rowsVisible = Math.ceil(H / this.ch) + 2;
      const scrollRow = Math.max(0, row - Math.floor(rowsVisible / 2) + 1);
      const from = Math.max(0, (scrollRow - 1) * this.cols), to = Math.min(items.length, (scrollRow + rowsVisible + 1) * this.cols);
      inner.style.transform = `translateY(${-scrollRow * this.ch}px)`;
      const pad = 3 * parseFloat(getComputedStyle(document.documentElement).fontSize);
      let html = "";
      for (let k = from; k < to; k++) {
        const r = Math.floor(k / this.cols), c = k % this.cols, it = items[k];
        const pos = `style="left:${pad + c * this.cw}px;top:${r * this.ch + 16}px"`;
        html += opts.text ? textCard(it.label, it.sub, k, it.key, it.img, it).replace(`data-i="${k}"`, `data-i="${k}" ${pos}`)
          : card(it, k, pos, opts.score ? scoreText(it, opts.score) : "");
      }
      inner.innerHTML = html;
      if (this.navFocus === null) inner.querySelector(`.card[data-i="${this.i}"]`)?.classList.add("focus");
      const cur = items[this.i];
      if (cur && !opts.text) setBackground(cur.id);
    },
    move(dx, dy) {
      if (this.navFocus !== null) {
        if (dy > 0) { this.navFocus = null; this.update(); return true; }
        const n = this.navFocus + dx;
        if (n < 0 || n >= TABS.length) return false;
        this.navFocus = n; renderNav(); return true;
      }
      let n = this.i + dx + dy * this.cols;
      if (dy < 0 && n < 0) { this.navFocus = 0; this.update(); return true; }
      if (dx && Math.floor(n / this.cols) !== Math.floor(this.i / this.cols)) return false;
      if (n < 0) return false;
      if (n >= items.length) { if (dy > 0 && Math.floor(this.i / this.cols) < Math.floor((items.length - 1) / this.cols)) n = items.length - 1; else return false; }
      this.i = n; this.update(); return true;
    },
    jump(d) { this.i = Math.max(0, Math.min(items.length - 1, this.i + d * this.cols * 3)); this.update(); },
    ok() {
      if (this.navFocus !== null) { openTab(this.navFocus); return; }
      const it = items[this.i];
      if (!it) return;
      if (opts.text) it.ok(); else push(gameScreen(it.id));
    },
    fav() { const it = items[this.i]; if (it && !opts.text) toggleFav(it); },
    hints: opts.text ? [["a", t("c.action.open")], ["b", t("c.action.back")]] : [["a", t("c.action.open")], ["b", t("c.action.back")], ["x", t("c.action.fav")], ["lt", t("c.hint.page")]],
  };
  return scr;
}

/* ---- Aspetto (accessibilità): palette per il daltonismo, dimensione dei testi, suoni, lettura vocale */
function lookScreen() {
  const items = [];
  const same = (a, b) => a === b;
  for (const p of PALETTES) {
    items.push({
      label: `${same(BP.palette, p.id) ? "●" : "○"} ${p.label}`, sub: same(BP.palette, p.id) ? t("c.look.inuse") : "",
      key: "pal:" + p.id,
      ok: () => {
        BP.palette = p.id; store.set("bpPalette", p.id); applyLook(); beep("ok");
        toast(t("c.toast.palette", { name: p.label })); push(lookScreen());
      },
    });
  }
  for (const t of TEXTS) {
    items.push({
      label: `${same(BP.text, t.id) ? "●" : "○"} ${window.t("c.look.textsize", { size: t.label.toLowerCase() })}`,
      sub: same(BP.text, t.id) ? window.t("c.look.inuse") : "", key: "txt:" + t.id,
      ok: () => {
        BP.text = t.id; store.set("bpText", t.id); applyLook(); beep("ok");
        toast(window.t("c.toast.textsize", { size: t.label })); push(lookScreen());
      },
    });
  }
  items.push({
    label: `${Pad.sound ? "●" : "○"} ${t("c.look.sounds")}`, sub: Pad.sound ? t("c.look.sounds.on") : t("c.look.sounds.off"), key: "snd",
    ok: () => { Pad.sound = !Pad.sound; store.set("bpSound", Pad.sound); beep("ok"); push(lookScreen()); },
  });
  items.push({
    label: `${Pad.talk ? "●" : "○"} ${t("c.look.talk")}`, sub: Pad.talk ? t("c.look.talk.on") : t("c.look.talk.off"), key: "talk",
    ok: () => {
      Pad.talk = !Pad.talk; store.set("bpTalk", Pad.talk);
      toast(Pad.talk ? t("c.toast.talk.on") : t("c.toast.talk.off"));
      announce(Pad.talk ? t("c.toast.talk.on") : t("c.toast.talk.off"));
      push(lookScreen());
    },
  });
  const scr = gridScreen(t("c.tab.look"), items, "look", { text: true, unit: t("c.unit.options") });
  scr.hints = [["a", t("c.action.choose")], ["b", t("c.action.back")], ["lt", t("c.hint.tab")]];
  return scr;
}


/* ---- "Per te": righe di consigli + questionario */
function forYouScreen() {
  RECO.setPlatName(platName);
  const rows = RECO.rows(BP.lib.games, RECO.tastes());
  const shelves = [{ title: t("c.quiz.title"), text: true, items: [
    { label: "🎲 " + t("c.quiz.title"), sub: t("c.quiz.sub"), key: "quiz", ok: () => push(quizScreen(0, {})) }] }]
    .concat(rows.map((r) => ({ title: r.title, sub: r.why, items: r.items })));
  // sezione collezioni: saghe da continuare, collezioni affini, le meglio valutate
  const games = visibleGames();
  for (const r of RECO.collectionRows(BP.lib.games, BP.lib.colls, RECO.tastes())) {
    shelves.push({ title: r.title, text: true, items: r.items.map((x) => ({ label: x.coll.name, sub: x.why, key: x.coll.slug, ...collArt(x.coll.slug),
      ok: () => push(gridScreen(x.coll.name, games.filter((g) => g.grp.colls.includes(x.coll.idx)).sort((a, b) => (a.year || 9999) - (b.year || 9999)), "coll")) })) });
  }
  const scr = shelvesScreen(shelves, "foryou");
  scr.row = Math.min(1, shelves.length - 1);
  return scr;
}

function quizScreen(step, a) {
  const Q = RECO.QUESTIONS;
  if (step >= Q.length) {
    RECO.saveTastes(a);
    const res = RECO.suggest(BP.lib.games, a, 18);
    const scr = gridScreen(t("c.reco.now"), res.map((x) => x.g), "foryou", { head: `<span>${t("c.reco.basedon")}</span>` });
    return scr;
  }
  const q = Q[step];
  const sel = new Set(q.multi ? a[q.id] || [] : []);
  const items = q.options.map((o) => ({ label: (sel.has(o.id) ? "✓ " : "") + o.label, key: o.id,
    ok: () => {
      if (q.multi) {
        sel.has(o.id) ? sel.delete(o.id) : sel.add(o.id);
        const i = cur().i;
        BP.stack[BP.stack.length - 1] = quizScreen(step, { ...a, [q.id]: [...sel] });
        cur().i = i; show();
      } else { BP.stack[BP.stack.length - 1] = quizScreen(step + 1, { ...a, [q.id]: o.id }); show(); }
    } }));
  if (q.multi) items.push({ label: t("c.quiz.next"), sub: sel.size ? t("c.quiz.chosen", { n: sel.size }) : t("c.quiz.skip"), key: "next",
    ok: () => { BP.stack[BP.stack.length - 1] = quizScreen(step + 1, a); show(); } });
  return gridScreen(`${step + 1}/${Q.length} · ${q.title}`, items, "foryou", { text: true });
}

function platformsScreen() {
  const games = visibleGames();
  const n = new Map();
  for (const g of games) n.set(g.platform, (n.get(g.platform) || 0) + 1);
  const plats = [...BP.lib.plats.values()].filter((p) => p.id !== "windows" && n.get(p.id)).sort((a, b) => collator.compare(a.name, b.name));
  return gridScreen(t("c.tab.plat"), plats.map((p) => ({ label: p.name, sub: t("c.count.games", { n: n.get(p.id) }), key: p.id,
    img: `/icons/platform/${encodeURIComponent(p.id)}`,
    ok: () => push(discoverScreen(p.name, sortTitle(games.filter((g) => g.platform === p.id)), "plat")) })), "plat", { text: true, unit: t("c.unit.consoles") });
}

const collArt = (slug) => ({ art: `/coll-img/${encodeURIComponent(slug)}/cover?w=640`, icon: `/coll-img/${encodeURIComponent(slug)}/icon?w=256` });

function collectionsScreen() {
  const games = visibleGames();
  const counts = new Map();
  for (const g of games) for (const i of g.grp.colls) counts.set(i, (counts.get(i) || 0) + 1);
  const colls = BP.lib.colls.filter((c) => !c.hidden && counts.get(c.idx)).sort((a, b) => (counts.get(b.idx) || 0) - (counts.get(a.idx) || 0));
  const smart = (BP.lib.smart || []).map((s) => ({ s, items: smartGames(BP.lib.games, s.rules) })).filter((x) => x.items.length);
  return gridScreen(t("c.tab.coll"), smart.map(({ s, items }) => ({ label: `${s.icon || "⚡"} ${s.name}`, sub: t("c.count.smart", { n: items.length }), key: s.id,
    ok: () => push(gridScreen(s.name, sortTitle(items), "coll")) })).concat(colls.map((c) => ({ label: c.name, sub: t("c.count.games", { n: counts.get(c.idx) }), key: c.slug, ...collArt(c.slug),
    ok: () => push(gridScreen(c.name, games.filter((g) => g.grp.colls.includes(c.idx)).sort((a, b) => (a.year || 9999) - (b.year || 9999)), "coll")) }))),
  "coll", { text: true, unit: t("c.unit.collections") });
}

/* ---- schermate del gioco: visualizzatore a tutto schermo, sinistra/destra per scorrere */
function shotsScreen(d) {
  const scr = {
    tab: null, i: 0, list: [], navFocus: null,
    async render(el) {
      el.innerHTML = `<div class="bp-shots"><p class="muted">${t("c.shots.loading")}</p></div>`;
      try { this.list = (await api(`/api/game/${d.id}/shots`)).shots; } catch (e) { toast(e.message, true); return; }
      this.update();
    },
    update() {
      renderNav();
      const s = this.list[this.i];
      const el = document.querySelector(".bp-shots");
      if (!el) return;
      el.innerHTML = s ? `<img src="${s.url}" alt=""><div class="bp-shots-bar"><b>${esc(d.title)}</b>
        <span>${new Date(s.taken * 1000).toLocaleString(GSI18n.lang, { dateStyle: "medium", timeStyle: "short" })} · ${esc(s.source)}</span>
        <span>${this.i + 1} / ${this.list.length}</span></div>` : `<p class="muted">${t("c.shots.none")}</p>`;
    },
    move(dx) {
      const n = this.i + dx;
      if (!dx || n < 0 || n >= this.list.length) return false;
      this.i = n; this.update(); return true;
    },
    ok() {},
    hints: [["b", t("c.action.back")]],
  };
  return scr;
}

function versionsScreen(d) {
  return gridScreen(t("c.versions.title", { title: d.title }), d.versions.filter((v) => !v.store || v.installed).map((v) => ({
    label: v.file, sub: v.primary ? t("c.versions.main") : "", key: v.file,
    ok: async () => {
      const vd = await detail(v.id);
      if (vd) playGame(vd);
    },
  })), null, { text: true });
}

/* ---- ricerca con tastiera a schermo */
function searchScreen() {
  const KEYS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".split("").concat(["␣", "⌫", "Cancella"]);
  const scr = {
    tab: "search", q: "", k: 0, results: [], navFocus: null, inResults: false, r: 0,
    render(el) {
      el.innerHTML = `<div class="bp-search"><div class="kbd">${KEYS.map((k, i) => `<div class="k${k.length > 1 ? " wide" : ""}" data-k="${i}">${k === "Cancella" ? t("c.search.clear") : k}</div>`).join("")}</div>
        <div><div class="search-box" id="sq"></div><div class="search-res" id="sr"></div></div></div>`;
      this.search();
    },
    search() {
      const toks = fold(this.q).split(/\s+/).filter(Boolean);
      this.results = toks.length ? visibleGames().filter((g) => toks.every((t) => g.q.includes(t))).slice(0, 24) : [];
      $("#sq").textContent = this.q || t("c.search.placeholder");
      $("#sr").innerHTML = this.results.map((g, i) => card(g, i)).join("");
      this.r = Math.min(this.r, Math.max(0, this.results.length - 1));
      this.update();
    },
    update() {
      renderNav();
      document.querySelectorAll(".kbd .k").forEach((e) => e.classList.toggle("focus", +e.dataset.k === this.k && !this.inResults && this.navFocus === null));
      document.querySelectorAll("#sr .card").forEach((e) => e.classList.toggle("focus", +e.dataset.i === this.r && this.inResults));
      if (this.inResults && this.results[this.r]) setBackground(this.results[this.r].id);
    },
    move(dx, dy) {
      if (this.navFocus !== null) {
        if (dy > 0) { this.navFocus = null; this.update(); return true; }
        const n = this.navFocus + dx;
        if (n < 0 || n >= TABS.length) return false;
        this.navFocus = n; renderNav(); return true;
      }
      if (this.inResults) {
        const per = Math.max(1, Math.floor($("#sr").clientWidth / ($("#sr .card")?.offsetWidth + 16 || 160)));
        let n = this.r + dx + dy * per;
        if (dx < 0 && this.r % per === 0) { this.inResults = false; this.update(); return true; }
        if (n < 0 || n >= this.results.length) return false;
        this.r = n; this.update(); return true;
      }
      const cols = 7;
      if (dy < 0 && this.k < cols) { this.navFocus = 0; this.update(); return true; }
      if (dx > 0 && (this.k % cols === cols - 1 || this.k === KEYS.length - 1) && this.results.length) { this.inResults = true; this.update(); return true; }
      const n = this.k + dx + dy * cols;
      if (n < 0 || n >= KEYS.length) return false;
      this.k = n; this.update(); return true;
    },
    ok() {
      if (this.navFocus !== null) { openTab(this.navFocus); return; }
      if (this.inResults) { const g = this.results[this.r]; if (g) push(gameScreen(g.id)); return; }
      const key = KEYS[this.k];
      if (key === "⌫") this.q = this.q.slice(0, -1);
      else if (key === "Cancella") this.q = "";
      else this.q += key === "␣" ? " " : key.toLowerCase();
      this.search();
    },
    typed(ch) { if (ch === "Backspace") this.q = this.q.slice(0, -1); else this.q += ch.toLowerCase(); this.search(); },
    hints: [["a", t("c.action.type")], ["b", t("c.action.back")]],
  };
  return scr;
}

/* ------------------------------------------------------------------ azioni */
async function toggleFav(g) {
  const v = !g.grp.favorite;
  try { await api(`/api/game/${g.id}/flag`, { body: { field: "favorite", value: v } }); } catch (e) { return toast(e.message, true); }
  g.grp.favorite = v ? 1 : 0;
  BP.details.delete(g.id);
  beep("ok");
  toast(v ? t("c.fav.added", { title: g.title }) : t("c.fav.removed", { title: g.title }));
  const s = cur();
  if (s.d) { s.d = null; show(); }
}

async function installGame(d) {
  try { await api(`/api/game/${d.id}/install`, { body: {} }); } catch (e) { return toast(e.message, true); }
  toast(t("c.install.opening", { store: d.store_name, title: d.title }));
}

async function playGame(d, body = {}) {
  let r;
  try { r = await api(`/api/game/${d.id}/play`, { body }); } catch (e) { beep("err"); return toast(e.message, true); }
  if (r.ask) { // port senza modalità salvata: si sceglie qui, «ricorda» la salva nel port
    const modes = { windowed: t("c.mode.windowed"), borderless: t("c.mode.borderless"), fullscreen: t("c.mode.fullscreen") };
    const items = [false, true].flatMap((remember) => Object.entries(modes).map(([k, l]) => ({
      label: l, sub: remember ? t("c.mode.remember") : t("c.mode.once"), key: k + remember,
      ok: () => { pop(); playGame(d, { window: k, remember }); } })));
    return push(gridScreen(t("c.mode.title"), items, cur().tab, { text: true, unit: t("c.unit.options") }));
  }
  beep("ok");
  window.Dualsense?.led(d.id, true);
  BP.running = { id: d.id, title: d.title };
  showRunning(t("c.run.starting"));
  pollRunning();
}

function showRunning(msg) {
  idle.close();
  const o = $("#bp-running");
  o.hidden = false;
  o.innerHTML = `<div class="logo big" style="color:var(--accent);font-size:3rem">◆</div><h2>${esc(BP.running?.title || "")}</h2>`
    + `<p class="muted">${esc(msg)}</p><p class="muted">Per chiudere il gioco: ${t("c.run.hold", { back: glyph("back"), start: glyph("start") })}</p>`;
}

async function pollRunning() {
  let r;
  try { r = await api("/api/running"); } catch { r = {}; }
  if (["starting", "extracting", "running"].includes(r.status)) {
    showRunning(r.status === "extracting" ? (r.message || t("c.run.extracting")) : r.status === "starting" ? t("c.run.starting")
      : `${t("c.run.running", { emulator: r.emulator })}${r.shots ? ` (${r.shots})` : ""}`);
    if (BP.running && (r.shots || 0) > (BP.running.shots || 0)) toast(t("c.run.shot"));
    if (BP.running) BP.running.shots = r.shots || 0;
    setTimeout(pollRunning, 1500);
    return;
  }
  $("#bp-running").hidden = true;
  if (BP.running) {
    if (r.status === "error") toast(r.message, true);
    else if (r.status === "finished" && r.played > 30) toast(`${t("c.run.session", { time: fmtTime(r.played) })}${r.shots ? ` · 📷 ${r.shots}` : ""}`);
    BP.running = null;
    window.Dualsense?.led(cur().d?.id ?? null, true);
    try { window.pywebview?.api?.focus_window?.(); } catch { /* browser */ }
    await reloadLibrary();
  }
}

async function reloadLibrary() {
  const lib = await loadLibrary();
  BP.lib = lib;
  BP.details.clear();
  const s = cur();
  if (s.tab === "home") { BP.stack = [homeScreen()]; show(); }
}

async function exitBigPicture() {
  try { await window.pywebview?.api?.set_fullscreen?.(false); } catch { /* browser */ }
  location.href = "/";
}

/* ------------------------------------------------------------------ input: controller e tastiera */
function renderHints() {
  const s = cur();
  const h = s.hints || [["a", t("c.action.select")], ["b", t("c.action.back")]];
  $("#bp-hints").className = Pad.kind === "ps" ? "ps" : "";
  $("#bp-hints").style.display = store.get("bpHints", true) ? "" : "none";
  const all = h.some(([k]) => k === "y") ? h : h.concat([["y", t("c.action.search")]]);
  $("#bp-hints").innerHTML = `<span class="hint" data-k="rb">${glyph("lb")}${glyph("rb")} ${t("c.hint.menu")}</span>`
    + all.map(([k, l]) => `<span class="hint" data-k="${k}">${glyph(k)} ${esc(l)}</span>`).join("");
}

/* ---- legenda nascondibile e pannello delle scorciatoie (controller e tastiera) */
function toggleHints() {
  const on = !store.get("bpHints", true);
  store.set("bpHints", on);
  renderHints();
  toast(on ? t("c.hints.on") : t("c.hints.off"));
}
const helpOpen = () => !!$("#bp-help");
function closeHelp() { $("#bp-help")?.remove(); }
function openHelp() {
  if (helpOpen()) return closeHelp();
  const SC = window.PozzoShortcuts;
  const pad = SC.PAD_HELP.map(([ks, l]) => `<tr><td>${ks.map((k) => (PAD_GLYPHS[Pad.kind][k] ? glyph(k) : `<span class="btn-glyph rect">${k.toUpperCase()}</span>`)).join(" + ")}</td><td>${esc(l)}</td></tr>`).join("");
  const kb = SC.REGISTRY.filter((en) => en.scope !== "desktop" && SC.keysOf(en).length)
    .map((en) => `<tr><td>${SC.keysOf(en).map((k) => `<kbd>${esc(SC.formatCombo(k))}</kbd>`).join(" ")}</td><td>${esc(en.label)}</td></tr>`).join("");
  const el = document.createElement("div");
  el.id = "bp-help";
  el.innerHTML = `<div class="bp-help-in"><h2>${t("c.help.title")}</h2><div class="cols"><table>${pad}</table>
    <table>${kb}<tr><td><kbd>${t("c.key.arrows")}</kbd> <kbd>${t("c.key.enter")}</kbd> <kbd>Esc</kbd></td><td>${t("c.help.move")}</td></tr>
    <tr><td><kbd>F</kbd> <kbd>/</kbd> <kbd>Q</kbd> <kbd>E</kbd></td><td>${t("c.help.favsearch")}</td></tr></table></div>
    <p class="muted">${t("c.help.legend", { x: glyph("x"), b: glyph("b"), state: store.get("bpHints", true) ? t("c.help.visible") : t("c.help.hidden") })}</p></div>`;
  $("#bp").appendChild(el);
}
function mediaChord(name) {
  if (name === "exitBigPicture") { if (!BP.running) exitBigPicture(); return; }
  beep("ok");
  if (!window.PozzoShortcuts.runMedia(name)) toast(t("c.media.unavailable"));
}

function input(action) {
  if (idle.activity()) attractClosedAt = performance.now();
  if (performance.now() - attractClosedAt < 350) return; // il tasto che chiude il salvaschermo non arriva alla schermata
  if (window.GSProfilePicker?.isOpen()) { window.GSProfilePicker.pad(action); return; } // «Chi gioca?» cattura tutto
  if (window.PozzoMedia?.handlePad?.(action)) return;
  if (window.BPMedia?.handlePad(action)) return; // lettore Media aperto: il pad comanda il video, non la schermata
  const s = cur();
  if (helpOpen()) { // il pannello comandi cattura tutto: X cambia la legenda, il resto lo chiude
    if (action === "up" || action === "down") $("#bp-help .bp-help-in")?.scrollBy({ top: (action === "up" ? -1 : 1) * 120, behavior: "smooth" });
    else if (action === "x") { toggleHints(); closeHelp(); openHelp(); } else if (["a", "b", "select", "start", "y"].includes(action)) closeHelp();
    return;
  }
  if (!$("#bp-running").hidden) return; // durante il gioco l'interfaccia ignora i comandi
  switch (action) {
    case "select": beep("ok"); openHelp(); break;
    case "l3": if (BP.stack.length > 1 || s.tab !== "home") { beep("back"); openTab(0); } break;
    case "r3": toggleHints(); break;
    case "left": if (s.move(-1, 0)) beep("move"); break;
    case "right": if (s.move(1, 0)) beep("move"); break;
    case "up": if (s.move(0, -1)) beep("move"); break;
    case "down": if (s.move(0, 1)) beep("move"); break;
    case "a": beep("ok"); s.ok(); break;
    case "b": if (s.navFocus !== null && s.navFocus !== undefined) { s.navFocus = null; s.update(); beep("back"); } else pop(); break;
    case "x": s.fav?.(); break;
    case "y": if (s.alt) s.alt(); else { push(searchScreen()); beep("ok"); } break;
    case "lt": if (s.lt) s.lt(); else s.jump?.(-1); break;
    case "rt": if (s.rt) s.rt(); else s.jump?.(1); break;
    case "start": s.start?.(); break;
    case "lb": if (s.lb) s.lb(); else stepTab(-1); break;
    case "rb": if (s.rb) s.rb(); else stepTab(1); break;
    default: break;
  }
}

document.addEventListener("keydown", (e) => {
  // lettore Media aperto: la tastiera la gestisce il lettore (spazio, frecce, F, Esc); tradurla anche in azioni del pad le raddoppierebbe
  if (window.BPMedia?.active()) return;
  if (PozzoShortcuts.dispatch(e, "bp")) return;
  const s = cur();
  if (!helpOpen() && s.typed && (e.key.length === 1 && /[\p{L}\p{N} ]/u.test(e.key) || e.key === "Backspace")) { e.preventDefault(); s.typed(e.key); return; }
  const a = Pad.keyAction(e);
  if (a) { e.preventDefault(); input(a); }
});
/* ---- mouse: clic su schede, giochi, pulsanti, tasti e suggerimenti; rotella per scorrere */
$("#bp-top").addEventListener("click", (e) => {
  const t = e.target.closest(".bp-tab");
  if (t) { beep("ok"); openTab(+t.dataset.tab); }
});
$("#bp-hints").addEventListener("click", (e) => {
  const h = e.target.closest(".hint");
  if (h) input(h.dataset.k);
});
main.addEventListener("click", (e) => {
  if (!$("#bp-running").hidden) return;
  const s = cur();
  const btn = e.target.closest(".bp-btn[data-i]");
  if (btn && s.buttons) { s.navFocus = null; s.i = +btn.dataset.i; s.update(); beep("ok"); s.ok(); return; }
  const key = e.target.closest(".kbd .k");
  if (key && "k" in s) { s.navFocus = null; s.inResults = false; s.k = +key.dataset.k; beep("ok"); s.ok(); return; }
  const c = e.target.closest(".card[data-i]");
  if (!c) return;
  s.navFocus = null;
  if (c.closest("#sr")) { s.inResults = true; s.r = +c.dataset.i; }
  else if (c.closest(".shelf")) { s.row = +c.closest(".shelf").dataset.r; s.cols[s.row] = +c.dataset.i; }
  else s.i = +c.dataset.i;
  s.update?.();
  beep("ok");
  s.ok();
});
/** Dissolvenza ai bordi della barra solo dove c'è altro da scorrere. */
function updateNavFade() {
  const n = $("#bp-nav");
  n.classList.toggle("more-l", n.scrollLeft > 4);
  n.classList.toggle("more-r", n.scrollLeft + n.clientWidth < n.scrollWidth - 4);
}
$("#bp-nav").addEventListener("scroll", updateNavFade, { passive: true });
window.addEventListener("resize", updateNavFade);
$("#bp-nav").addEventListener("wheel", (e) => {
  const n = $("#bp-nav");
  if (n.scrollWidth <= n.clientWidth) return;
  e.preventDefault();
  n.scrollLeft += e.deltaX || e.deltaY;
}, { passive: false });
let wheelAt = 0;
main.addEventListener("wheel", (e) => {
  e.preventDefault();
  const now = performance.now();
  if (now - wheelAt < 90 || !$("#bp-running").hidden) return;
  wheelAt = now;
  const s = cur();
  const horiz = Math.abs(e.deltaX) > Math.abs(e.deltaY) || e.shiftKey;
  const d = Math.sign(horiz ? e.deltaX || e.deltaY : e.deltaY);
  if (!d) return;
  if (s.navFocus !== null && s.navFocus !== undefined) { s.navFocus = null; s.update?.(); }
  if (s.move?.(horiz ? d : 0, horiz ? 0 : d)) beep("move");
}, { passive: false });
// tasto "indietro" del mouse e clic destro = Indietro
document.addEventListener("mouseup", (e) => { if (e.button === 3) { e.preventDefault(); input("b"); } });
document.addEventListener("contextmenu", (e) => { e.preventDefault(); input("b"); });

document.addEventListener("mousemove", () => { $("#bp").classList.add("mouse"); clearTimeout(document.mt); document.mt = setTimeout(() => $("#bp").classList.remove("mouse"), 2500); });

window.addEventListener("gamepadconnected", (e) => toast(t("c.pad.connected", { name: e.gamepad.id.split("(")[0].trim() })));
PozzoShortcuts.bind("bp", { help: openHelp, legend: toggleHints, profile: () => { if (BP.running) return false; GSProfilePicker.open({ toast }); }, bigPicture: () => { if (BP.running) return false; exitBigPicture(); } });

/* ------------------------------------------------------------------ salvaschermo (attract mode)
 * Dopo N minuti senza input (Impostazioni > Aspetto, 0 = mai) mostra a rotazione schermate o copertine, al massimo 60 giochi.
 * Non parte con un gioco in esecuzione, il pannello comandi, ?Chi gioca?? o il pannello musica aperti; la musica non viene mai
 * messa in pausa ne' ripresa da qui. Il primo input lo chiude e non viene inoltrato. Logica pura e testata: GSUi (core.js). */
const attractEl = $("#bp-attract");
let attractTimer = 0, attractIdx = 0, attractSlides = [], attractFront = 0, attractClosedAt = -1000;
const ATTRACT_MS = 9000;
const shotCache = new Map(); // id -> promessa dell'URL della prima schermata (null se non ce ne sono)
const shotOf = (id) => {
  if (!shotCache.has(id)) shotCache.set(id, api(`/api/game/${id}/shots`).then((r) => { const u = r?.shots?.[0]?.url; return typeof u === "string" && /^\/[^"'()\\\s]*$/.test(u) ? u : null; }).catch(() => null));
  return shotCache.get(id);
};
async function attractNext() {
  clearTimeout(attractTimer);
  const g = attractSlides[attractIdx++ % attractSlides.length];
  const d = g && await detail(g.id);
  if (!g || !idle.isActive()) return;
  const m = d?.media || {};
  const shot = m.screenshot || m.hero || m.fanart || await shotOf(g.id); // poi la copertina
  if (!idle.isActive()) return;
  const layers = attractEl.querySelectorAll(".at-slide");
  const next = layers[1 - attractFront];
  next.classList.toggle("poster", !shot);
  next.style.backgroundImage = `url("${shot ? shot + (shot.includes("?") ? "&" : "?") + "w=1280" : `/img/${g.id}/cover?w=640`}")`;
  next.classList.add("on");
  layers[attractFront].classList.remove("on");
  attractFront = 1 - attractFront;
  attractEl.querySelector(".at-info b").textContent = g.title;
  attractEl.querySelector(".at-info span").textContent = platName(g.platform);
  attractTimer = setTimeout(attractNext, ATTRACT_MS);
}
const idle = GSUi.createIdle({
  minutes: () => GSUi.prefs(GSUi.saved()).idle,
  canRun: () => !!BP.lib && !BP.running && !document.hidden && !helpOpen() && !window.GSProfilePicker?.isOpen?.()
    && $("#bp-media-widget")?.hidden !== false && !window.BPMedia?.active() && GSUi.pickSlides(visibleGames()).length > 0,
  start() {
    attractSlides = GSUi.pickSlides(visibleGames());
    attractIdx = 0;
    attractEl.dataset.fx = GSUi.attractMotion(document.documentElement.dataset.motion, !!matchMedia?.("(prefers-reduced-motion: reduce)").matches);
    attractEl.hidden = false;
    attractNext();
  },
  stop() {
    clearTimeout(attractTimer);
    attractEl.hidden = true;
    attractEl.querySelectorAll(".at-slide").forEach((l) => { l.classList.remove("on"); l.style.backgroundImage = ""; });
  },
  setT: (f, ms) => setTimeout(f, ms),
  clearT: (t) => clearTimeout(t),
});
function attractWake(e) {
  if (!idle.activity()) return;
  attractClosedAt = performance.now();
  e.preventDefault?.(); e.stopImmediatePropagation?.();
}
for (const t of ["keydown", "mousedown", "mouseup", "click", "wheel", "touchstart", "pointerdown", "contextmenu"]) {
  window.addEventListener(t, attractWake, { capture: true, passive: false });
}
let attractX = -1, attractY = 0;
window.addEventListener("mousemove", (e) => {
  const far = attractX < 0 || Math.hypot(e.clientX - attractX, e.clientY - attractY) > 6; // il tremolio del mouse non conta
  attractX = e.clientX; attractY = e.clientY;
  if (far && attractX >= 0) attractWake(e);
}, { capture: true });
setInterval(() => { // pulsanti o stick non mappati dai comandi di Big Picture contano comunque come attivita'
  const pads = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : [];
  if (pads.some((p) => p.buttons.some((b) => b.pressed) || p.axes.some((a) => Math.abs(a) > 0.6))) attractWake({});
}, 400);

/* ------------------------------------------------------------------ monitor fps */
function initFpsMonitor() {
  if (typeof requestAnimationFrame === "undefined") return;
  const frames = [];
  let last = null, lowSince = null, highSince = null, rafId = 0;
  function tick(now) {
    if (last !== null) {
      const delta = now - last;
      if (delta > 0) {
        frames.push(1000 / delta);
        if (frames.length > 60) frames.shift();
        const avg = frames.reduce((a, b) => a + b, 0) / frames.length;
        if (avg < 30) {
          highSince = null;
          if (lowSince === null) lowSince = now;
          else if (now - lowSince >= 2000) {
            if (typeof document !== "undefined" && document.body) {
              if (!document.body.dataset) document.body.dataset = {};
              if (document.body.dataset.motion !== "reduced") {
                document.body.dataset.motion = "reduced";
                toast(t("c.perf.on"));
              }
            }
          }
        } else if (avg > 45) {
          lowSince = null;
          if (highSince === null) highSince = now;
          else if (now - highSince >= 2000) {
            if (typeof document !== "undefined" && document.body?.dataset) {
              if (document.body.dataset.motion === "reduced") {
                delete document.body.dataset.motion;
              }
            }
          }
        } else {
          lowSince = null;
          highSince = null;
        }
      }
    }
    last = now;
    rafId = requestAnimationFrame(tick);
  }
  rafId = requestAnimationFrame(tick);
  return {
    stop: () => (typeof cancelAnimationFrame === "function" ? cancelAnimationFrame(rafId) : null),
    getFps: () => (frames.length ? frames.reduce((a, b) => a + b, 0) / frames.length : 0),
  };
}
BP.initFpsMonitor = initFpsMonitor;

/* ------------------------------------------------------------------ avvio */
function clock() { $("#bp-clock").textContent = new Date().toLocaleTimeString(GSI18n.lang, { hour: "2-digit", minute: "2-digit" }); }

(async function start() {
  clock(); setInterval(clock, 15000);
  applyLook(); // palette e dimensione dei testi scelte la volta prima
  initFpsMonitor();
  Pad.watchFocus({ focus: "#bp-main .card.focus, #bp-main .bp-btn.focus, #bp-top .bp-tab.focus", roots: ["#bp-main", "#bp-top"] }); // lettura vocale di ciò che si seleziona (se attiva)
  try {
    BP.lib = await loadLibrary();
  } catch (e) {
    $("#bp-loading").innerHTML = `<p>${t("c.load.error", { msg: esc(e.message) })}</p>`;
    return;
  }
  GS.library = () => BP.lib;
  GS.openGame = (id) => push(gameScreen(id));
  await loadExtensions();
  if (await BPMedia.available(api)) { // voce «Media» (video): solo con l'estensione Media locale attiva
    TABS.splice(MEDIA_TAB + 1, 0, { id: "videos", label: "Media", open: () => push(BPMedia.screen({ api, toast, esc, push, cur, main: () => main, renderNav, openTab, beep,
      tabIndex: () => TABS.findIndex((x) => x.id === "videos"), tabsCount: () => TABS.length })) });
  }
  $("#bp-loading").hidden = true;
  BP.stack = [homeScreen()];
  show();
  Pad.start({ input, onKind: renderHints, onChord: mediaChord, combo: { when: () => !!BP.running,
    run: () => api("/api/running/stop", { body: {} }).then(() => toast(t("c.run.closing"))) } });
  idle.arm();
  // se un gioco e' gia' in esecuzione (es. avviato prima di entrare)
  const r = await api("/api/running").catch(() => ({}));
  if (["starting", "extracting", "running"].includes(r.status)) { BP.running = { title: r.title }; pollRunning(); }
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = Object.assign(BP, { BP, initFpsMonitor });
}
