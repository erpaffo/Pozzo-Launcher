"use strict";
// Griglia Big Picture: le card si ricostruiscono solo se cambia la finestra visibile, altrimenti si sposta .focus: `node tests/test_bp_grid.js`.
// Estrae gridScreen da bigpicture.js e lo esegue in un contesto vm con un DOM finto minimo.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "..", "pozzo", "app", "static", "bigpicture.js"), "utf8");
const a = src.indexOf("function gridScreen("), b = src.indexOf("/* ---- Aspetto", a);
assert(a > 0 && b > a, "gridScreen non trovata");

let builds = 0;
const mkNode = (i) => { const cl = new Set(); return { dataset: { i: String(i) }, classList: { add: (c) => cl.add(c), remove: (c) => cl.delete(c), has: (c) => cl.has(c) } }; };
const inner = {
  style: {}, nodes: [],
  set innerHTML(h) { builds++; this.nodes = [...h.matchAll(/data-i="(\d+)"/g)].map((m) => mkNode(m[1])); },
  get firstElementChild() { return this.nodes[0] || null; },
  querySelector(sel) {
    if (sel === ".card.focus") return this.nodes.find((n) => n.classList.has("focus")) || null;
    const m = sel.match(/data-i="(\d+)"/); return this.nodes.find((n) => n.dataset.i === m[1]) || null;
  },
};
const grid = { clientWidth: 1200, clientHeight: 700 };
const ctx = {
  $: (s) => (s === "#grid-inner" ? inner : s === "#grid" ? grid : { innerHTML: "" }),
  document: { documentElement: {} }, getComputedStyle: () => ({ fontSize: "16px" }),
  renderNav() {}, setBackground() {}, esc: String, t: (k) => k, GSI18n: { lang: "it" }, glyph: () => "", scoreText: () => "",
  card: (it, k, pos) => `<div class="card" data-i="${k}" ${pos}></div>`, textCard: (l, s, k) => `<div class="card" data-i="${k}"></div>`,
  toggleFav() {}, push() {}, gameScreen() {}, openTab() {}, TABS: [{}, {}], console,
};
vm.createContext(ctx);
vm.runInContext(src.slice(a, b) + "\nthis.gridScreen = gridScreen;", ctx);

const items = Array.from({ length: 400 }, (_, i) => ({ id: "g" + i, title: "G" + i }));
const scr = ctx.gridScreen("T", items);
scr.render({ innerHTML: "" });
assert(scr.cols > 1);
assert.strictEqual(builds, 1, "render: una sola costruzione");

// stesso intervallo di righe: nessuna ricostruzione, il focus passa al nodo successivo
const first = inner.nodes[0];
scr.move(1, 0);
assert.strictEqual(builds, 1, "focus sul vicino: niente rebuild");
assert.strictEqual(inner.nodes[0], first, "i nodi sono gli stessi");
assert(!inner.nodes[0].classList.has("focus") && inner.querySelector('.card[data-i="1"]').classList.has("focus"));
assert.strictEqual(inner.nodes.filter((n) => n.classList.has("focus")).length, 1);

// scorrendo fino a cambiare la finestra: ricostruisce e il focus e' sulla card giusta
for (let r = 0; r < 12; r++) scr.move(0, 1);
assert(builds > 1, "finestra cambiata: rebuild");
assert(inner.querySelector(`.card[data-i="${scr.i}"]`).classList.has("focus"));

// focus sulla barra delle schede: nessuna card focalizzata
while (scr.navFocus === null) scr.move(0, -1);
assert(inner.nodes.every((n) => !n.classList.has("focus")));
// ritorno alla griglia: il focus torna sulla card corrente
scr.move(0, 1);
assert(inner.querySelector(`.card[data-i="${scr.i}"]`).classList.has("focus"));
console.log("test_bp_grid ok");
