// Harness Node: DOM e fetch finti, nessuna rete. Prova gusto, ordine di gioco, consigli e classifica ROM (404 incluso).
const assert = require("assert");
const path = require("path");
const dir = path.join(__dirname, "..", "pozzo", "app", "static");
const PozzoTaste = require(path.join(dir, "taste.js"));
const PozzoFranchise = require(path.join(dir, "franchise.js"));
const PozzoRecommend = require(path.join(dir, "recommend.js"));

class Nodo {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.ev = {}; this.style = {}; this.className = ""; this._t = ""; this._h = ""; this.hidden = false; this.cls = new Set(); this.classList = { add: (c) => this.cls.add(c) }; }
  set textContent(t) { this._t = String(t); this.children = []; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  set innerHTML(h) { this._h = h; this.children = []; }
  get innerHTML() { return this._h; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  appendChild(c) { this.children.push(c); return c; }
  addEventListener(n, f) { this.ev[n] = f; }
  all() { return this.children.flatMap((c) => [c, ...c.all()]); }
  porTag(t) { return this.all().filter((n) => n.tag === t); }
}
const doc = { createElement: (t) => new Nodo(t) };
const risposta = (status, body) => async () => ({ ok: status === 200, status, json: async () => body });
const urls = [];
const rotte = (mappa) => async (u) => { urls.push(u); const k = Object.keys(mappa).find((p) => u.startsWith(p)); return (k ? mappa[k] : risposta(404, {}))(u); };

(async () => {
  // gusto
  let h = new Nodo("section");
  let f = rotte({ "/api/taste": risposta(200, { genres: [["RPG", 10], ["Platform", 5]], decades: [["1990", 8]], reliable: false }) });
  assert.strictEqual(await PozzoTaste.mount(h, { fetch: f, doc }), true);
  assert.strictEqual(h.hidden, false);
  const righe = h.porTag("li");
  assert.strictEqual(righe.length, 3);
  assert.strictEqual(righe[0].getAttribute("aria-label"), "RPG: 100%");
  assert.strictEqual(righe[1].porTag("span").pop().style.transform, "scaleX(0.500)");
  assert.ok(h.textContent.includes("1990s") && h.textContent.includes("indicativo"));
  assert.ok(h.porTag("ul").every((u) => u.getAttribute("role") === "list"));
  for (const f404 of [risposta(404, {}), risposta(200, { genres: [], decades: [] }), async () => { throw new Error("rete"); }]) {
    h = new Nodo("section");
    assert.strictEqual(await PozzoTaste.mount(h, { fetch: rotte({ "/api/taste": f404 }), doc }), false);
    assert.strictEqual(h.hidden, true);
  }

  // ordine di gioco
  const fr = { series: "Zelda", order: [1, 2, 3], owned: [1, 2], missing: ["Zelda 4"], titles: { 1: "Zelda 1", 2: "Zelda 2", 3: "Zelda 3" } };
  h = new Nodo("div");
  let aperto = null;
  assert.strictEqual(await PozzoFranchise.mount(h, 2, { fetch: rotte({ "/api/franchise/2": risposta(200, fr) }), doc, onOpen: (id) => { aperto = id; } }), true);
  const voci = h.porTag("li").filter((n) => n.className.includes("fr-item"));
  assert.strictEqual(voci.length, 3);
  assert.strictEqual(voci[1].getAttribute("aria-current"), "true");
  const bott = h.porTag("button");
  assert.strictEqual(bott.length, 1); // solo il capitolo posseduto e non corrente
  bott[0].ev.click();
  assert.strictEqual(aperto, 1);
  assert.ok(h.textContent.includes("Non posseduto") && h.textContent.includes("Zelda 4"));
  for (const risp of [risposta(404, {}), risposta(200, { series: null, order: [2], owned: [2], missing: [] })]) {
    h = new Nodo("div");
    assert.strictEqual(await PozzoFranchise.mount(h, 2, { fetch: rotte({ "/api/franchise/": risp }), doc }), false);
    assert.strictEqual(h.hidden, true);
  }

  // consigli
  h = new Nodo("div");
  aperto = null;
  f = rotte({ "/api/recommend": risposta(200, { items: [{ id: 7, title: "Chrono Trigger", score: 3, reasons: [{ kind: "genere", text: "Genere RPG" }] }] }) });
  assert.strictEqual(await PozzoRecommend.mount(h, { fetch: f, doc, onOpen: (id) => { aperto = id; } }), true);
  assert.ok(h.textContent.includes("Genere RPG"));
  h.porTag("button")[0].ev.click();
  assert.strictEqual(aperto, 7);
  h = new Nodo("div");
  assert.strictEqual(await PozzoRecommend.mount(h, { fetch: rotte({}), doc }), false);
  assert.strictEqual(h.hidden, true);

  // classifica ROM: poche voci senza vlist, <script> escapato, click delegato
  h = new Nodo("div");
  const lista = (n) => Array.from({ length: n }, (_, i) => ({ id: i + 1, title: i ? `Gioco ${i}` : "<b>Zero</b>", score: 90 - i / 10, source: "x" }));
  urls.length = 0;
  let chiamate = 0;
  const vlist = () => { chiamate++; };
  f = rotte({ "/api/top/roms": risposta(200, { console: "snes", items: lista(5) }) });
  aperto = null;
  assert.strictEqual(await PozzoRecommend.mountRanking(h, { fetch: f, doc, console: "snes", onOpen: (id) => { aperto = id; }, box: new Nodo("div"), vlist }), true);
  assert.ok(urls[0].startsWith("/api/top/roms?console=snes"));
  const l = h.children[1];
  assert.ok(l.innerHTML.includes("&lt;b&gt;Zero") && !l.innerHTML.includes("<b>"));
  assert.strictEqual(chiamate, 0);
  l.ev.click({ target: { closest: () => ({ getAttribute: () => "3" }) } });
  assert.strictEqual(aperto, 3);
  // lista lunga: passa da vlist (non si ricrea un virtualizzatore)
  h = new Nodo("div");
  f = rotte({ "/api/top/roms": risposta(200, { items: lista(500) }) });
  const box = new Nodo("div");
  let resa = null;
  await PozzoRecommend.mountRanking(h, { fetch: f, doc, box, vlist: (b, host, items, cell) => { chiamate++; resa = cell(items[1]); assert.strictEqual(items.length, 500); } });
  assert.strictEqual(chiamate, 1);
  assert.ok(resa.includes("rank-pos") && resa.includes("Gioco 1"));
  // 404: nascosta
  h = new Nodo("div");
  assert.strictEqual(await PozzoRecommend.mountRanking(h, { fetch: rotte({}), doc }), false);
  assert.strictEqual(h.hidden, true);
  console.log("OK test_reco_ui");
})().catch((e) => { console.error(e); process.exit(1); });