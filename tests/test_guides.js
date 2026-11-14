// Libreria dei tutorial e novita' (whatsnew.js) e tour di primo avvio (tour.js): testi in tutte le lingue, bersagli esistenti, finestra.
const S = require("./_i18n_stub");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const STATIC = path.join(__dirname, "..", "pozzo", "app", "static");
const LOCALES = path.join(__dirname, "..", "pozzo", "data", "locales");
const W = require(path.join(STATIC, "whatsnew.js"));
const T = require(path.join(STATIC, "tour.js"));
const cats = Object.fromEntries(["it", "en", "de", "es", "fr", "pt-BR"].map((l) => [l, JSON.parse(fs.readFileSync(path.join(LOCALES, `${l}.json`), "utf8"))]));

// chiavi i18n usate: si registrano le chiamate a t() mentre si leggono titoli e testi dei passi
const used = new Set();
const real = globalThis.t;
globalThis.t = (k, p) => { used.add(k); return real(k, p); };
const KEYS = { search: "/", palette: "Ctrl+K", help: "?", nextTheme: "Ctrl+Shift+T" };
const readStep = (st) => { void st.title; st.text(KEYS); };

const items = [];
for (const [v, list] of Object.entries(W.NEWS)) for (const it of list) items.push({ it, where: `NEWS ${v}` });
for (const sec of W.SECTIONS) {
  assert.ok(sec.items.length > 0, `sezione vuota: ${sec.id}`);
  used.add(`b.guide.sec.${sec.id}`);
  for (const it of sec.items) { assert.ok(it, `voce mancante in ${sec.id}`); items.push({ it, where: `sezione ${sec.id}` }); }
}
assert.ok(new Set(W.SECTIONS.flatMap((s) => s.items.map((i) => i.id))).size >= 20, "almeno 20 tutorial nella libreria");

for (const { it, where } of items) {
  const pre = it.p || "b.news";
  used.add(`${pre}.${it.id}.title`); used.add(`${pre}.${it.id}.text`);
  if (it.id === "whatsnew") continue;
  if (it.steps) {
    assert.ok(it.steps.length >= 1 && it.steps.length <= 4, `${where}/${it.id}: da 1 a 4 passi`);
    assert.ok(it.steps.filter((s) => !s.sel).length <= 1, `${where}/${it.id}: al massimo un passo centrato`);
    assert.equal(new Set(it.steps.map((s) => s.id)).size, it.steps.length, `${it.id}: id dei passi unici`);
    it.steps.forEach(readStep);
  }
}
T.STEPS.forEach(readStep);
for (const k of ["b.guide.title", "b.guide.subtitle", "b.guide.news", "b.guide.settingsBtn", "b.guide.menu", "b.guide.palette"]) used.add(k);
globalThis.t = real;

// ogni chiave esiste in tutte le lingue e ha gli stessi segnaposto
for (const k of used) {
  assert.ok(k in cats.it, `chiave assente in it: ${k}`);
  const ph = (s) => (s.match(/\{\w+\}/g) || []).sort().join();
  for (const [l, c] of Object.entries(cats)) {
    assert.ok(typeof c[k] === "string" && c[k].trim(), `chiave assente in ${l}: ${k}`);
    assert.equal(ph(c[k]), ph(cats.it[k]), `segnaposto diversi in ${l}: ${k}`);
  }
}

// ogni selettore compare nei sorgenti statici (HTML delle pagine, JS dell'interfaccia): id, classi e valori degli attributi
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? (["m", "g", "l", "extensions-preview"].includes(e.name) ? [] : walk(path.join(d, e.name))) : [path.join(d, e.name)]));
const SRC = walk(STATIC).filter((f) => /\.(html|js)$/.test(f) && !/(tour|whatsnew)\.js$/.test(f)).map((f) => fs.readFileSync(f, "utf8")).join("\n");
function checkSel(sel, label) {
  for (const [, id] of sel.matchAll(/#([\w-]+)/g)) assert.ok(SRC.includes(id), `${label}: id «${id}» assente dai sorgenti (${sel})`);
  for (const [, cl] of sel.replace(/"[^"]*"/g, "").matchAll(/\.([\w-]+)/g)) assert.ok(SRC.includes(cl), `${label}: classe «${cl}» assente (${sel})`);
  for (const [, v] of sel.matchAll(/="([^"]+)"/g)) assert.ok(SRC.includes(v), `${label}: valore «${v}» assente (${sel})`);
}
let nsel = 0;
for (const { it, where } of items) for (const st of it.steps || []) for (const s of st.sel || []) { checkSel(s, `${where}/${it.id}/${st.id}`); nsel++; }
for (const st of T.STEPS) for (const s of st.sel || []) { checkSel(s, `tour/${st.id}`); nsel++; }
assert.ok(nsel > 40, "pochi selettori controllati: " + nsel);

// finestra: libreria con sezioni, senza badge di versione e senza toccare lo stato «visto»
class E {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.ls = {}; this.className = ""; this._t = ""; this.open = false; this.parentElement = null; }
  set textContent(v) { this._t = String(v); this.children = []; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  append(...c) { c.forEach((x) => this.appendChild(x)); }
  appendChild(c) { c.parentElement = this; this.children.push(c); return c; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(k, f) { (this.ls[k] = this.ls[k] || []).push(f); }
  remove() {}
  querySelector() { return null; }
  showModal() { this.open = true; }
  close() { if (this.open) { this.open = false; (this.ls.close || []).forEach((f) => f()); } }
  all(cls) { return [...this.children.flatMap((c) => c.all(cls)), ...(this.className.split(" ").includes(cls) ? [this] : [])]; }
}
const writes = [];
const doc = {
  createElement: (tag) => new E(tag), getElementById: () => null, head: new E("head"), body: new E("body"), hidden: false,
  addEventListener() {}, querySelectorAll: () => [],
};
const win = { GS: {}, localStorage: { getItem: () => null, setItem: (k, v) => writes.push([k, v]) }, addEventListener() {} };
const ctx = vm.createContext({ window: win, document: doc, t: real, addEventListener() {}, setTimeout: () => 0, requestAnimationFrame: () => 0,
  fetch: () => Promise.reject(new Error("offline")), console });
vm.runInContext(fs.readFileSync(path.join(STATIC, "whatsnew.js"), "utf8"), ctx);
win.GS.whatsnew.guides();
const dlg = doc.body.children[0];
assert.ok(dlg && dlg.open, "la libreria si apre");
assert.equal(dlg.all("gs-news-head")[0].children.find((c) => c.tag === "h2").textContent, "Tutorial");
assert.equal(dlg.all("gs-news-badge").length, 0, "nessun badge di versione");
assert.deepEqual(dlg.all("gs-news-ver").map((e) => e.textContent), W.SECTIONS.map((s) => cats.it[`b.guide.sec.${s.id}`]));
assert.equal(dlg.all("gs-news-how").length, W.SECTIONS.reduce((n, s) => n + s.items.filter((i) => i.steps?.length).length, 0));
dlg.close();
assert.deepEqual(writes, [], "chiudere la libreria non salva la versione vista");

console.log("test_guides: ok (" + items.length + " voci, " + nsel + " selettori)");
