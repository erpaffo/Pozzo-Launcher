// Harness Node senza dipendenze: DOM finto minimale + fetch finto per esercitare render, click e polling.
const assert = require("assert");
const path = require("path");
const { creaComponente, statoBios } = require(path.join(__dirname, "..", "pozzo", "app", "static", "settings", "emulatori-extra.js"));

class Nodo {
  constructor(tag) { this.tag = tag; this.children = []; this.parentNode = null; this.attrs = {}; this.ev = {}; this.style = {}; this.className = ""; this._t = ""; this.hidden = false; this.disabled = false; }
  get nextSibling() { const i = this.parentNode ? this.parentNode.children.indexOf(this) : -1; return i >= 0 ? this.parentNode.children[i + 1] || null : null; }
  set textContent(t) { this._t = String(t); this.children = []; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  insertBefore(c, rif) { c.parentNode = this; const i = rif ? this.children.indexOf(rif) : -1; if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); return c; }
  addEventListener(n, f) { this.ev[n] = f; }
  click() { if (!this.disabled && this.ev.click) return this.ev.click(); }
  all() { return this.children.flatMap((c) => [c, ...c.all()]); }
  querySelectorAll(sel) {
    if (sel === "tr[data-p]") return this.all().filter((n) => n.tag === "tr" && "data-p" in n.attrs);
    throw new Error("selettore non supportato " + sel);
  }
  querySelector(sel) { return this.all().find((n) => n.tag === sel) || null; }
  byClass(c) { return this.all().filter((n) => n.className.split(" ").includes(c)); }
}
const doc = { createElement: (t) => new Nodo(t) };
class Obs { constructor(f) { this.f = f; Obs.ultimo = this; } observe() {} }
const risposta = (status, body) => ({ status, ok: status >= 200 && status < 300, json: async () => { if (body === undefined) throw new Error("no json"); return body; } });
const tick = () => new Promise((r) => setImmediate(r));
async function attendi(cond) { for (let i = 0; i < 200 && !cond(); i++) await tick(); assert(cond(), "condizione non raggiunta"); }

function tabella(...consoles) {
  const body = new Nodo("body"); const table = new Nodo("table"); body.appendChild(table);
  consoles.forEach((c) => { const tr = new Nodo("tr"); tr.setAttribute("data-p", c); const td = new Nodo("td"); td.textContent = c.toUpperCase() + "consigliati: x"; tr.appendChild(td); table.appendChild(tr); });
  return { body, table };
}

(async () => {
  // classificazione BIOS: verde / rosso / giallo neutro
  assert.strictEqual(statoBios({ found: true, ok: true, sha1: "a" }), "ok");
  assert.strictEqual(statoBios({ found: false, ok: false, sha1: null }), "missing");
  assert.strictEqual(statoBios({ found: true, ok: false, sha1: "a" }), "unknown");
  assert.strictEqual(statoBios({ found: true, ok: false, sha1: "a", mismatch: true }), "mismatch");

  // render, consiglio, BIOS, install con polling a 500 ms
  const { body, table } = tabella("ps1", "gba");
  const chiamate = []; const attese = []; let polls = 0; let sbloccaPost;
  const fetchFinto = async (url, init) => {
    chiamate.push((init && init.method || "GET") + " " + url);
    if (url.startsWith("/api/emulators/recommend?console=ps1")) return risposta(200, { emulator: "duckstation", reason: "Il più compatibile", installed: false, supported: true });
    if (url.startsWith("/api/emulators/bios?console=ps1")) return risposta(200, { items: [
      { file: "a.bin", required: true, found: true, ok: true, sha1: "x", help_url: "https://h/a" },
      { file: "b.bin", required: true, found: false, ok: false, sha1: null, help_url: "https://h/a" },
      { file: "c.bin", required: false, found: true, ok: false, sha1: "y", help_url: "https://h/a" }] });
    if (url.startsWith("/api/emulators/recommend?console=gba")) return risposta(200, { emulator: "boh", reason: "Nessun installer", installed: false, supported: false });
    if (url.startsWith("/api/emulators/bios?console=gba")) return risposta(404);
    if (init && init.method === "POST") { assert.deepStrictEqual(JSON.parse(init.body), { console: "ps1" }); await new Promise((r) => { sbloccaPost = r; }); return risposta(200, { ok: true, message: "Installato duckstation" }); }
    if (url.startsWith("/api/emulators/install-recommended?console=ps1")) { polls++; return risposta(200, { ready: false, progress: 0.5, steps: [{ id: "i", label: "Scarico", state: "running" }] }); }
    throw new Error("url inatteso " + url);
  };
  const comp = creaComponente({ document: doc, root: body, fetch: fetchFinto, MutationObserver: Obs, sleep: async (ms) => { attese.push(ms); await tick(); } });
  comp.avvia();
  const righe = table.children.filter((n) => n.attrs["data-xe"]);
  assert.strictEqual(righe.length, 2, "un pannello per console");
  await attendi(() => table.byClass("xe-install").length === 1 && table.byClass("xe-list").length === 1);

  const ps1 = righe[0];
  assert.strictEqual(ps1.byClass("xe-item").length, 3);
  const [verde, rosso, giallo] = ps1.byClass("xe-item");
  assert(verde.className.includes("xe-ok") && rosso.className.includes("xe-bad") && giallo.className.includes("xe-warn"));
  assert(ps1.textContent.includes("Il più compatibile"));
  const link = ps1.byClass("xe-help")[0];
  assert.strictEqual(link.getAttribute("href"), "https://h/a");
  assert(link.getAttribute("rel").includes("noopener"));
  assert(ps1.all().find((n) => n.getAttribute("role") === "status"), "regione live");

  // console non supportata: motivo, niente pulsante; BIOS 404 gestito
  const gba = righe[1];
  assert(gba.textContent.includes("Nessun installer") && gba.textContent.includes("non sa installare"));
  assert.strictEqual(gba.byClass("xe-install").length, 0);
  assert(gba.textContent.includes("non disponibile"));

  // click: POST + sondaggio, poi stato finale
  const btn = ps1.byClass("xe-install")[0];
  assert(btn.getAttribute("aria-label").includes("duckstation"));
  btn.click(); btn.click();
  await attendi(() => polls >= 2);
  assert.strictEqual(btn.disabled, true);
  assert.strictEqual(chiamate.filter((c) => c.startsWith("POST")).length, 1, "niente doppio POST");
  assert(attese.every((m) => m === 500));
  assert.strictEqual(ps1.byClass("xe-fill")[0].style.transform, "scaleX(0.5)");
  assert(ps1.byClass("xe-state")[0].textContent.includes("Scarico"));
  sbloccaPost();
  await attendi(() => ps1.byClass("xe-state")[0].textContent.startsWith("✓"));
  assert(btn.hidden);

  // la tabella viene ridisegnata: i pannelli si ricreano una sola volta
  table.children.length = 0;
  const tr = new Nodo("tr"); tr.setAttribute("data-p", "ps1"); tr.appendChild(new Nodo("td")); table.appendChild(tr);
  Obs.ultimo.f(); Obs.ultimo.f();
  assert.strictEqual(table.children.filter((n) => n.attrs["data-xe"]).length, 1);

  // errore di rete e di installazione
  const b2 = tabella("ps2");
  let rete = false;
  const f2 = async (url, init) => {
    if (url.startsWith("/api/emulators/recommend")) return risposta(200, { emulator: "pcsx2", reason: "r", installed: false, supported: true });
    if (url.startsWith("/api/emulators/bios")) throw new TypeError("offline");
    if (init && init.method === "POST") return risposta(502, { detail: "Connessione non disponibile" });
    return risposta(200, { ready: false, progress: 0, steps: [] });
  };
  creaComponente({ document: doc, root: b2.body, fetch: f2, MutationObserver: Obs, sleep: tick }).avvia();
  const p2 = b2.table.children.find((n) => n.attrs["data-xe"]);
  await attendi(() => p2.byClass("xe-install").length === 1);
  assert(p2.textContent.includes("Rete non raggiungibile"));
  p2.byClass("xe-install")[0].click();
  await attendi(() => p2.byClass("xe-state")[0].textContent.startsWith("✗"));
  assert(p2.textContent.includes("Connessione non disponibile"));
  assert.strictEqual(p2.byClass("xe-install")[0].disabled, false, "si può riprovare");
  console.log("OK test_emulators_ui");
})().catch((e) => { console.error(e); process.exit(1); });