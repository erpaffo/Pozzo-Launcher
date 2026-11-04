// Segnaposto di caricamento nelle pagine di js/pages.js (wishlist, statistiche, top, schermate).
// Esegui: node tests/test_skeleton_pages.js
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const STATIC = path.join(__dirname, "..", "pozzo", "app", "static");
const motionSource = fs.readFileSync(path.join(STATIC, "motion-settings.js"), "utf8");
const pagesSource = fs.readFileSync(path.join(STATIC, "js", "pages.js"), "utf8");

// Elemento finto: figli, dataset, style; innerHTML con data-view crea un solo figlio (la pagina)
function makeEl(tag) {
  const el = {
    tagName: tag, className: "", dataset: {}, style: {}, attrs: {}, parent: null, children: [],
    setAttribute(k, v) { this.attrs[k] = v; },
    append(...nodes) { for (const n of nodes) { n.parent = this; this.children.push(n); } },
    remove() {
      const p = this.parent;
      if (p) p.children = p.children.filter((c) => c !== this);
    },
    addEventListener() {},
    querySelectorAll(sel) {
      const out = [];
      const walk = (n) => { for (const c of n.children) { if (sel === "[data-gs-skel]" && c.dataset.gsSkel) out.push(c); walk(c); } };
      walk(this);
      return out;
    },
    get firstElementChild() { return this.children[0] || null; },
    set innerHTML(html) {
      this.children = [];
      this.html = html;
      const m = /^<div class="page[^"]*"[^>]*data-view="(\w+)"/.exec(html);
      if (m) { const page = makeEl("div"); page.dataset.view = m[1]; this.append(page); }
    },
    get innerHTML() { return this.html || ""; },
  };
  return el;
}

function makeContext({ withSkeleton = true } = {}) {
  const context = {
    document: {
      readyState: "complete",
      documentElement: { dataset: {} },
      getElementById: () => null,
      createElement: makeEl,
      addEventListener() {},
    },
    localStorage: { getItem: () => null, setItem() {} },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {},
    setTimeout, clearTimeout, console,
    fetch: () => Promise.reject(new Error("offline")),
    // stub delle dipendenze di pages.js (definite altrove nell'app)
    $: () => ({}),
    esc: (s) => String(s ?? ""),
    remoteImg: (u) => u || "",
    toast() {}, vlist() {}, renderJobInto() {}, openDetail() {}, reload() {}, pollWishBadge() {},
    priceSpark: () => "", keyPrice: () => "", fmtTime: () => "", fmtDate: () => "",
    platName: () => "", STORE_SHORT: {}, STATUS: {},
    RECO: { canonGenres: () => [], GENRE_LABEL: {} },
    store: { get: (k, d) => d, set() {} },
    collator: { compare: () => 0 },
    S: { games: [], view: { type: "x", id: "all" } },
    // api: ogni chiamata resta in sospeso finche' il test non la risolve
    pending: null,
    api: () => new Promise((res, rej) => { context.pending = { res, rej }; }),
  };
  context.window = context;
  vm.createContext(context);
  if (withSkeleton) vm.runInContext(motionSource, context, { filename: "motion-settings.js" });
  vm.runInContext(pagesSource, context, { filename: "pages.js" });
  return context;
}

const flush = () => new Promise((r) => setImmediate(r));
const skelLayers = (pv) => pv.children.flatMap((c) => c.children).filter((c) => c.dataset.gsSkel);

const DATA = {
  wishlist: { settings: { has_key: false, has_gg: false, threshold: 30, country: "IT" }, items: [], log: [], checking: false, unseen: 0 },
  stats: { year: 2026, years: {}, months: Array(12).fill(0), top_year: [] },
  top: { job: { status: "idle", phase: "" }, items: [] },
  shots: { shots: [], settings: { hotkey: "" } },
};
const RENDER = { wishlist: "renderWishlist", stats: "renderStats", top: "renderTop", shots: "renderShots" };
const COUNT = { wishlist: 6, stats: 6, top: 10, shots: 12 };

const cases = [];
const test = (name, fn) => cases.push([name, fn]);

for (const key of Object.keys(RENDER)) {
  test(`${key}: segnaposto mentre aspetta i dati, con il numero giusto`, async () => {
    const ctx = makeContext();
    ctx.S.view.type = key;
    const pv = makeEl("div");
    vm.runInContext(`${RENDER[key]}(pv)`, Object.assign(ctx, { pv }));
    assert.equal(pv.firstElementChild.dataset.view, key);
    const [layer] = skelLayers(pv);
    assert.ok(layer, "layer di segnaposto presente");
    assert.equal(layer.children.length, COUNT[key]);
    ctx.pending.res(DATA[key]);
    await flush();
  });

  test(`${key}: il segnaposto sparisce quando la pagina viene disegnata`, async () => {
    const ctx = makeContext();
    ctx.S.view.type = key;
    const pv = makeEl("div");
    vm.runInContext(`${RENDER[key]}(pv)`, Object.assign(ctx, { pv }));
    ctx.pending.res(DATA[key]);
    await flush();
    assert.equal(skelLayers(pv).length, 0);
    assert.equal(pv.firstElementChild.dataset.view, key);
  });

  test(`${key}: il segnaposto sparisce anche se il fetch fallisce`, async () => {
    const ctx = makeContext();
    ctx.S.view.type = key;
    const pv = makeEl("div");
    vm.runInContext(`${RENDER[key]}(pv)`, Object.assign(ctx, { pv }));
    ctx.pending.rej(new Error("boom"));
    await flush();
    assert.equal(skelLayers(pv).length, 0);
    assert.match(pv.html, /boom/);
  });

  test(`${key}: refresh con la pagina gia' a schermo non rimette il segnaposto`, async () => {
    const ctx = makeContext();
    ctx.S.view.type = key;
    const pv = makeEl("div");
    vm.runInContext(`${RENDER[key]}(pv)`, Object.assign(ctx, { pv }));
    ctx.pending.res(DATA[key]);
    await flush();
    const before = pv.firstElementChild;
    vm.runInContext(`${RENDER[key]}(pv)`, Object.assign(ctx, { pv }));
    assert.equal(pv.firstElementChild, before, "stessa pagina, nessun ricaricamento");
    assert.equal(skelLayers(pv).length, 0);
    ctx.pending.res(DATA[key]);
    await flush();
  });
}

test("senza GSSkeleton la pagina non si rompe e resta com'era fino ai dati", async () => {
  const ctx = makeContext({ withSkeleton: false });
  const pv = makeEl("div");
  pv.innerHTML = `<div class="page" data-view="other"></div>`;
  const old = pv.firstElementChild;
  vm.runInContext("renderStats(pv)", Object.assign(ctx, { pv }));
  assert.equal(pv.firstElementChild, old, "nessun segnaposto: il contenuto precedente non viene toccato");
  ctx.pending.res(DATA.stats);
  await flush();
  assert.equal(pv.firstElementChild.dataset.view, "stats");
});

(async () => {
  let failed = 0;
  for (const [name, fn] of cases) {
    try { await fn(); console.log(`ok   ${name}`); }
    catch (e) { failed++; console.log(`FAIL ${name}\n     ${e.message}`); }
  }
  console.log(failed ? `${failed} test falliti` : `tutti i ${cases.length} test passano`);
  process.exitCode = failed ? 1 : 0;
})();
