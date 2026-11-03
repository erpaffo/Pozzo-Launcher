const assert = require("node:assert/strict");
const path = require("node:path");

const S = path.join(__dirname, "..", "pozzo", "app", "static");
const T = require(path.join(S, "tour.js"));
const A = require(path.join(S, "anchor.js"));

// --- DOM finto minimo ---
class El {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.style = { setProperty(k, v) { this[k] = v; } }; this.ls = {}; this.className = ""; this.disabled = false; this.parent = null; this._t = ""; this.hidden = false; }
  set textContent(v) { this._t = String(v); this.children = []; }
  get textContent() { return this._t; }
  append(...c) { c.forEach((x) => this.appendChild(x)); }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((x) => x !== this); this.parent = null; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(t, f) { (this.ls[t] = this.ls[t] || []).push(f); }
  click() { (this.ls.click || []).forEach((f) => f({ preventDefault() {}, stopPropagation() {} })); }
  focus() { this.doc.activeElement = this; }
  getBoundingClientRect() { return this.rect || { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
  find(cls) { return this.children.reduce((r, c) => r || (c.className.split(" ").includes(cls) ? c : c.find(cls)), null); }
  get isConnected() { return true; }
}
const box = (l, t, w, h) => ({ left: l, top: t, right: l + w, bottom: t + h, width: w, height: h });

function world({ stored, noStorage = false, sels = {}, w = 1200, h = 800 } = {}) {
  const doc = { activeElement: null, body: new El("body"), head: new El("head"), ls: {}, targets: {} };
  const mk = (tag) => { const e = new El(tag); e.doc = doc; return e; };
  doc.createElement = mk;
  doc.getElementById = () => null;
  doc.querySelector = (s) => doc.targets[s] || null;
  doc.addEventListener = (t, f) => { (doc.ls[t] = doc.ls[t] || []).push(f); };
  doc.removeEventListener = (t, f) => { doc.ls[t] = (doc.ls[t] || []).filter((x) => x !== f); };
  for (const [s, r] of Object.entries(sels)) { const e = mk("div"); e.rect = r; doc.targets[s] = e; }
  const ev = [], wl = {}, timers = [];
  const win = {
    innerWidth: w, innerHeight: h, PozzoShortcuts: undefined,
    addEventListener: (t, f) => { (wl[t] = wl[t] || []).push(f); },
    removeEventListener: (t, f) => { wl[t] = (wl[t] || []).filter((x) => x !== f); },
    dispatchEvent: (e) => { ev.push(e.type); (wl[e.type] || []).slice().forEach((f) => f(e)); return true; },
    requestAnimationFrame: (f) => { f(); return 0; }, cancelAnimationFrame() {},
    setInterval: () => 7, clearInterval() {},
  };
  const mem = new Map(stored ? [["gs.tour", JSON.stringify(stored)]] : []);
  const store = noStorage ? { getItem() { throw new Error("no"); }, setItem() { throw new Error("no"); } }
    : { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, v) };
  const toasts = [];
  const tour = T.create({ win, doc, store, A, setTimeout: (f, ms) => timers.push([f, ms]), toast: (m) => toasts.push(m) });
  const root = () => doc.body.children[0];
  const key = (k, o = {}) => { const e = { key: k, ...o, preventDefault() { this.pd = true; }, stopPropagation() {}, stopImmediatePropagation() {} }; (doc.ls.keydown || []).forEach((f) => f(e)); return e; };
  return { doc, win, tour, ev, wl, timers, store, mem, toasts, root, key,
    card: () => root().find("gs-tour-card"), btn: (c) => root().find("gs-tour-card").find(c) };
}

const ALL = {
  "#nav": box(0, 60, 220, 600), "#search": box(300, 20, 300, 30), "#sort": box(620, 20, 140, 30), ".tile[data-id]": box(300, 200, 170, 250),
  "#bp-btn": box(900, 10, 120, 30), "#settings-btn": box(1030, 10, 120, 30), "#mb-profile": box(1000, 0, 100, 24), '.mb-top[data-m="Impostazioni"]': box(200, 0, 90, 24),
};
function textOf(card, cls) { return card.find(cls).children.map((c) => c.textContent).join(""); }
const where = (w) => textOf(w.card(), "gs-tour-meta"); // "Passo n di N"
const nextBtn = (w) => w.card().children.find((c) => c.className === "gs-tour-row").children[1];

// 1) filtraggio: bersagli mancanti o fuori vista saltati, N calcolato sui passi mostrati
{
  const full = T.resolve(T.STEPS, (s) => (ALL[s] ? { getBoundingClientRect: () => ALL[s] } : null), { w: 1200, h: 800 }, A);
  assert.equal(full.length, T.STEPS.length);
  const part = T.resolve(T.STEPS, (s) => (s === "#sort" || s === "#search" ? { getBoundingClientRect: () => ALL[s] } : s === "#bp-btn" ? { getBoundingClientRect: () => box(5000, 0, 10, 10) } : null), { w: 1200, h: 800 }, A);
  assert.deepEqual(part.map((p) => p.step.id), ["welcome", "search", "sort", "end"]);
  // un selettore alternativo prende il posto del primo
  const alt = T.resolve(T.STEPS, (s) => (s === ".gs-dashboard__tile" ? { getBoundingClientRect: () => box(10, 10, 50, 50) } : null), { w: 800, h: 600 }, A);
  assert.ok(alt.some((p) => p.step.id === "game"));
  assert.equal(T.resolve(T.STEPS, () => { throw new Error("x"); }, { w: 1, h: 1 }, A).length, 2);
}

// 2) avvio, conteggio, avanti/indietro/fine
{
  const w = world({ sels: { "#search": ALL["#search"], "#sort": ALL["#sort"] } });
  assert.equal(w.tour.start(), true);
  assert.equal(w.tour.isActive(), true);
  assert.equal(w.doc.activeElement, nextBtn(w));
  assert.equal(where(w), "Passo 1 di 4");           // welcome, search, sort, end
  assert.equal(w.card().attrs.role, "dialog");
  assert.equal(w.card().attrs["aria-modal"], "true");
  assert.ok(w.root().find("gs-tour-live").textContent.startsWith("Passo 1 di 4"));
  assert.equal(w.btn("btn").disabled, true);        // Indietro al primo passo
  nextBtn(w).click(); assert.equal(where(w), "Passo 2 di 4");
  assert.equal(w.card().attrs["data-side"], "bottom");
  assert.equal(w.root().find("gs-tour-ring").hidden, false);
  w.key("ArrowLeft"); assert.equal(where(w), "Passo 1 di 4");
  w.key("ArrowRight"); w.doc.activeElement = null; w.key("Enter"); w.key("ArrowRight");
  assert.equal(where(w), "Passo 4 di 4");
  assert.equal(nextBtn(w).textContent, "Fine");
  assert.equal(w.root().find("gs-tour-ring").hidden, true);
  assert.equal(w.card().attrs["data-side"], "center");
  nextBtn(w).click();
  assert.equal(w.tour.isActive(), false);
  assert.equal(w.doc.body.children.length, 0);
  assert.deepEqual(w.tour.state(), { done: true, off: false });
  assert.deepEqual(w.ev, ["pozzo:tour-start", "pozzo:tour-end"]);
}

// 3) salta (pulsante ed Esc) = done; "Non mostrare più" = off + toast
{
  const w = world({ sels: ALL });
  w.tour.start(); w.card().children.find((c) => c.className === "gs-tour-row").children[2].click();
  assert.deepEqual(w.tour.state(), { done: true, off: false });
  const e = world({ sels: ALL });
  e.tour.start(); const ev = e.key("Escape");
  assert.equal(ev.pd, true); assert.equal(e.tour.isActive(), false); assert.equal(e.tour.state().done, true);
  const o = world({ sels: ALL });
  o.tour.start(); o.card().children.find((c) => c.className === "gs-tour-row end").children[0].click();
  assert.equal(o.tour.state().off, true); assert.equal(o.tour.isActive(), false);
  assert.match(o.toasts[0], /Rivedi il tour/);
  assert.equal(o.tour.start(), false);              // spento: nessun avvio automatico
  assert.equal(o.tour.start({ manual: true }), true); // ma il manuale lo ignora
  o.tour.stop();
  assert.equal(o.tour.state().off, true);
}

// 4) avvio automatico: solo dopo l'evento, una volta, mai se done/off
{
  const w = world({ sels: ALL });
  w.tour.arm();
  assert.equal(w.tour.isActive(), false);
  w.win.dispatchEvent({ type: "pozzo:onboarding-done" });
  assert.equal(w.timers.length, 1); assert.equal(w.timers[0][1], 600);
  assert.equal(w.tour.isActive(), false);           // non prima del ritardo
  w.timers[0][0](); assert.equal(w.tour.isActive(), true);
  w.tour.stop();
  w.win.dispatchEvent({ type: "pozzo:onboarding-done" });
  assert.equal(w.timers.length, 1);                 // una sola volta
  for (const stored of [{ done: true }, { off: true }]) {
    const x = world({ sels: ALL, stored }); x.tour.arm();
    x.win.dispatchEvent({ type: "pozzo:onboarding-done" }); x.timers[0][0]();
    assert.equal(x.tour.isActive(), false);
  }
  const m = world({ sels: ALL, stored: { done: true, off: true } });
  assert.equal(m.tour.start({ manual: true }), true);
  const d = world({ sels: ALL }); d.tour.settings.setAuto(false);
  assert.equal(d.tour.settings.auto(), false); d.tour.settings.setAuto(true);
  assert.deepEqual(d.tour.state(), { done: false, off: false });
}

// 5) tastiera: Tab nella trappola, Invio sul pulsante a fuoco, altri tasti bloccati
{
  const w = world({ sels: ALL });
  w.tour.start();
  const rows = w.card().children.filter((c) => c.className.startsWith("gs-tour-row"));
  const [back, next, skip] = rows[0].children, off = rows[1].children[0];
  assert.equal(w.doc.activeElement, next);
  w.doc.activeElement = off; assert.equal(w.key("Tab").pd, true); assert.equal(w.doc.activeElement, next); // Indietro e' disattivato: il primo e' Avanti
  w.doc.activeElement = next; assert.equal(w.key("Tab", { shiftKey: true }).pd, true); assert.equal(w.doc.activeElement, off);
  w.doc.activeElement = skip; assert.notEqual(w.key("Tab").pd, true);   // in mezzo: Tab normale
  w.doc.activeElement = { focus() {} }; w.key("Tab"); assert.equal(w.doc.activeElement, next);  // fuori dalla scheda: rientra
  w.doc.activeElement = skip; w.key("Enter"); assert.equal(where(w), "Passo 1 di 11"); // Invio su un pulsante lascia il clic al pulsante
  assert.equal(w.key("/").pd !== true, true);       // non scrive, ma non e' nemmeno "mangiato" dal tour
}

// 6) bersaglio che sparisce o finestra che cambia: ricalcolo senza errori
{
  const w = world({ sels: ALL });
  w.tour.start();
  for (let i = 0; i < 2; i++) w.key("ArrowRight");  // sulla ricerca
  assert.equal(w.card().find("gs-tour-meta").children[0].textContent, "Passo 3 di 11");
  assert.equal(textOf(w.card(), "gs-tour-meta").startsWith("Passo 3"), true);
  w.doc.targets["#search"].rect = box(-500, 0, 10, 10);   // fuori vista
  w.wl.resize.forEach((f) => f());
  assert.equal(w.tour.isActive(), true);
  assert.equal(w.card().find("gs-tour-meta").children[0].textContent, "Passo 3 di 10");   // ora e' "Ordina e filtra"
  assert.match(w.root().find("gs-tour-live").textContent, /Passo 3 di 11|Ordina/);
  w.win.innerWidth = 300; w.win.innerHeight = 400; w.wl.scroll.forEach((f) => f());
  assert.equal(w.tour.isActive(), true);
  w.doc.targets = {}; w.wl.resize.forEach((f) => f());  // restano solo benvenuto e fine
  assert.equal(w.tour.isActive(), true);
  assert.equal(w.card().find("gs-tour-meta").children[0].textContent.endsWith("di 2"), true);
}

// 7) senza localStorage: funziona e ricorda in memoria
{
  const w = world({ sels: ALL, noStorage: true });
  assert.equal(w.tour.start(), true);
  w.key("Escape");
  assert.equal(w.tour.state().done, true);
  assert.equal(w.tour.start(), false);
  const n = T.loadState(null); assert.deepEqual(n, { done: false, off: false });
  assert.deepEqual(T.loadState({ getItem: () => "{rotto" }), { done: false, off: false });
}

// 8) niente DOM desktop: nessun avvio
{
  const w = world({ sels: ALL });
  const t = T.create({ win: w.win, doc: w.doc, store: w.store, A, setTimeout() {}, desktop: () => false });
  assert.equal(t.start({ manual: true }), false);
}
console.log("test_tour: ok");
