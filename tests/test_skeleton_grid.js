// Segnaposto della griglia durante il caricamento: `node tests/test_skeleton_grid.js`.
// Esegue davvero grid.js e motion-settings.js (GSSkeleton) in un contesto vm con un DOM finto.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const STATIC = path.join(__dirname, "..", "pozzo", "app", "static");
const read = (f) => fs.readFileSync(path.join(STATIC, f), "utf8");

function makeEl(id) {
  const el = {
    id, className: "", textContent: "", innerHTML: "", hidden: false, children: [], dataset: {}, attrs: {},
    style: {}, parent: null, clientWidth: 1000, clientHeight: 800, scrollTop: 0, isConnected: true,
    setAttribute(k, v) { this.attrs[k] = v; },
    append(...nodes) { for (const n of nodes) { n.parent = this; this.children.push(n); } },
    appendChild(n) { this.append(n); return n; },
    remove() { const p = this.parent; if (p) p.children.splice(p.children.indexOf(this), 1); },
    addEventListener() {},
    getBoundingClientRect: () => ({ top: 0 }),
    get firstElementChild() { return this.children[0]; },
    get lastElementChild() { return this.children[this.children.length - 1]; },
    querySelectorAll(sel) { return all(this).filter((c) => sel === "[data-gs-skel]" && c.dataset.gsSkel); },
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
  };
  el.style = { setProperty(k, v) { el.style[k] = v; } };
  return el;
}
const all = (n) => n.children.flatMap((c) => [c, ...all(c)]);

// elementi per id, creati una volta sola: $("#empty") torna sempre lo stesso nodo
const els = new Map();
const $ = (sel) => { if (!els.has(sel)) els.set(sel, makeEl(sel)); return els.get(sel); };
const scroll = $("#grid-scroll");
scroll.clientHeight = 800;
$("#loadbar").hidden = true;

const ctx = {
  console, setTimeout, clearTimeout, requestAnimationFrame: () => 0,
  document: { readyState: "complete", documentElement: { dataset: {} }, getElementById: () => null,
    querySelector: (s) => $(s), createElement: (t) => makeEl(t), addEventListener() {} },
  localStorage: { getItem: () => null, setItem() {} },
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  fetch: () => Promise.resolve({ ok: true, json: async () => ({}) }),
  $, esc: (s) => String(s), sections: (items) => [{ label: null, items }],
  platName: () => "", fmtSize: () => "", S: null,
};
ctx.window = ctx;
vm.createContext(ctx);
// motion-settings.js definisce GSSkeleton; grid.js dipende da S (state.js) e dalle sue helper
vm.runInContext(read("motion-settings.js"), ctx);
ctx.S = {
  items: [], games: [], rows: [], total: 0, cols: 1, tw: 170, th: 260, gap: 18, pad: 22, zoom: 170, nodes: new Map(),
};
vm.runInContext(read("js/grid.js"), ctx);
// loading() sta in state.js (con molto altro): si esegue solo quella funzione
const loadingSrc = read("js/state.js").match(/function loading\(text\) \{[\s\S]*?\n\}/)[0];
vm.runInContext(loadingSrc, ctx);
const S = ctx.S;
const skel = () => all(scroll).filter((c) => c.dataset.gsSkel); // livelli
const tiles = () => all(scroll).filter((c) => c.className === "gs-skel"); // singoli segnaposto

// 1) senza GSSkeleton (prima che lo script carichi): nessun errore, vuoto come prima
{
  const saved = ctx.window.GSSkeleton;
  ctx.window.GSSkeleton = undefined;
  $("#loadbar").hidden = false;
  vm.runInContext("layout()", ctx);
  assert.strictEqual($("#empty").hidden, false, "senza GSSkeleton il comportamento resta quello di prima");
  assert.strictEqual(skel().length, 0);
  $("#loadbar").hidden = true;
  vm.runInContext("layout()", ctx);
  assert.strictEqual($("#empty").hidden, false, "senza caricamento il messaggio di libreria vuota torna");
  ctx.window.GSSkeleton = saved;
}

// 2) caricamento senza giochi: segnaposto da 12 a 24, messaggio nascosto, griglia invariata
{
  $("#loadbar").hidden = false;
  vm.runInContext("layout()", ctx);
  const n = tiles().length;
  assert(n >= 12 && n <= 24, "numero di segnaposto tra 12 e 24, ottenuto " + n);
  assert.strictEqual(scroll.children.filter((c) => c.dataset.gsSkel).length, 1, "un solo livello di segnaposto");
  assert.strictEqual(S.nodes.size, 0, "nessuna tessera reale disegnata");
  // nuova chiamata: nessun duplicato
  vm.runInContext("layout()", ctx);
  assert.strictEqual(tiles().length, n, "rifare il layout non duplica i segnaposto");
}

// 3) finito il caricamento con risultato vuoto: segnaposto via, messaggio di libreria vuota visibile
{
  $("#loadbar").hidden = true;
  vm.runInContext("loading(null)", ctx);
  assert.strictEqual(skel().length, 0, "segnaposto rimossi a caricamento finito");
  assert.strictEqual($("#empty").hidden, false, "con libreria vuota il messaggio torna");
  assert(/libreria è vuota/.test($("#empty").innerHTML), "messaggio di libreria vuota");
}

// 4) arrivano giochi mentre la loadbar e' ancora visibile: segnaposto via subito
{
  $("#loadbar").hidden = false;
  vm.runInContext("loading('Caricamento dei giochi degli store…')", ctx);
  assert(tiles().length >= 12, "segnaposto di nuovo visibili");
  S.items = [{ id: "a", title: "A" }];
  vm.runInContext("layout()", ctx);
  assert.strictEqual(tiles().length, 0, "con tessere reali i segnaposto spariscono");
  assert.strictEqual($("#empty").hidden, true);
  // la virtualizzazione non tocca i segnaposto: la mappa dei nodi resta quella delle tessere
  assert.strictEqual(S.nodes.size, 0);
}

// 5) senza loadbar e senza giochi non compaiono segnaposto
{
  S.items = [];
  $("#loadbar").hidden = true;
  vm.runInContext("layout()", ctx);
  assert.strictEqual(skel().length, 0);
}

console.log("ok  segnaposto della griglia durante il caricamento");
