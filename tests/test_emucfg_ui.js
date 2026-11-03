// Harness Node: scheda gioco «Impostazioni emulatore» e selettore per console, con DOM e fetch finti.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const STATIC = path.join(__dirname, "..", "pozzo", "app", "static");
const SRC = fs.readFileSync(path.join(STATIC, "js", "detail-emucfg.js"), "utf8");
assert(!/innerHTML/.test(SRC), "detail-emucfg.js non deve usare innerHTML");

class Nodo {
  constructor(tag) { this.tag = tag; this.children = []; this.parent = null; this.attrs = {}; this.ev = {}; this.className = ""; this._t = ""; this.disabled = false; this.value = ""; this.id = ""; }
  set textContent(t) { this._t = String(t); this.children = []; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  append(...cs) { cs.forEach((c) => { c.parent = this; this.children.push(c); }); }
  appendChild(c) { this.append(c); return c; }
  replaceChildren() { this.children = []; this._t = ""; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); }
  addEventListener(n, f) { this.ev[n] = f; }
  async fire(n) { return this.ev[n] && this.ev[n](); }
  all() { return this.children.flatMap((c) => [c, ...c.all()]); }
  byClass(c) { return this.all().filter((n) => n.className.split(" ").includes(c)); }
  querySelector(s) { return this.all().find((n) => "#" + n.id === s) || null; }
}
const tick = () => new Promise((r) => setImmediate(r));
const risposta = (body, ok = true) => ({ ok, statusText: "err", json: async () => body });

function ambiente(routes) {
  const body = new Nodo("div");
  const doc = { createElement: (t) => new Nodo(t), querySelector: (s) => (s === "#detail-body" ? body : null) };
  const toasts = [], calls = [];
  const win = { S: { detail: null }, handlers: {}, confirm: () => true, addEventListener(n, f) { this.handlers[n] = f; } };
  const api = async (url, opts = {}) => {
    const m = opts.body !== undefined ? "POST" : opts.method || "GET";
    calls.push([m, url, opts.body]);
    const h = routes(m, url, opts.body);
    if (h instanceof Error) throw h;
    return h;
  };
  vm.runInNewContext(SRC, { window: win, document: doc, api, toast: (t, e) => toasts.push([t, !!e]), Set, Object, Promise, RegExp });
  return { body, win, toasts, calls, open: (d) => { win.S.detail = d; return win.handlers["pozzo:detail-open"]({ detail: d }); } };
}

const INFO = { supported: true, emulator: "duckstation", selection: "", console_selection: "",
  levels: [{ id: "quality", name: "Qualità" }, { id: "performance", name: "Prestazioni" }, { id: "faithful", name: "Fedele" }], note: "",
  preview: { preset: "quality", values: { GPU: { ResolutionScale: "3", "<img onerror=x>": "<b>" } }, sources: ["https://a.example/x", "javascript:alert(1)"], reason: "" } };

(async () => {
  // supportato: selettore + anteprima + fonti sicure; cambio -> POST giusto senza perdere gli altri campi
  let e = ambiente((m, u) => {
    if (u.endsWith("/emu-preset")) return INFO;
    if (m === "GET" && u.endsWith("/profile")) return { profile: { emulator: "duckstation", before: "a.bat" } };
    if (m === "POST" && u.endsWith("/profile")) return {};
    throw new Error("url " + u);
  });
  await e.open({ id: 7, title: "<img onerror=x>", files: ["a.iso"] }); await tick();
  const sec = e.body.querySelector("#d-emucfg");
  assert(sec, "sezione creata");
  const sel = sec.byClass("emucfg-select")[0];
  assert.deepStrictEqual(sel.children.map((o) => o.value), ["inherit", "leave", "quality", "performance", "faithful"]);
  assert.strictEqual(sel.value, "inherit");
  assert(sec.textContent.includes("GPU.ResolutionScale = 3") && sec.textContent.includes("GPU.<img onerror=x> = <b>"));
  const links = sec.byClass("emucfg-src");
  assert.strictEqual(links.length, 1, "solo fonti https");
  assert.strictEqual(links[0].rel, "noopener noreferrer"); assert.strictEqual(links[0].target, "_blank");
  sel.value = "performance"; await sel.fire("change");
  const post = e.calls.find((c) => c[0] === "POST");
  assert.strictEqual(JSON.stringify(post), JSON.stringify(["POST", "/api/game/7/profile", { emulator: "duckstation", before: "a.bat", preset: "performance" }]));
  assert.deepStrictEqual(e.toasts.at(-1), ["Preset salvato", false]);
  sel.value = "inherit"; await sel.fire("change");
  assert.strictEqual(e.calls.filter((c) => c[0] === "POST").at(-1)[2].preset, "");

  // errore di salvataggio -> toast d'errore
  e = ambiente((m, u) => (u.endsWith("/emu-preset") ? INFO : m === "GET" ? { profile: {} } : new Error("Preset non valido")));
  await e.open({ id: 1, files: ["a"] }); await tick();
  const s2 = e.body.querySelector("#d-emucfg").byClass("emucfg-select")[0];
  s2.value = "quality"; await s2.fire("change");
  assert.deepStrictEqual(e.toasts.at(-1), ["Preset non valido", true]);

  // Ripristina -> POST restore + conferma annullabile
  e = ambiente((m, u) => (u.endsWith("/emu-preset") ? INFO : { restored: true }));
  await e.open({ id: 3, files: ["a"] }); await tick();
  const rb = e.body.querySelector("#d-emucfg").byClass("emucfg-restore")[0];
  e.win.confirm = () => false; await rb.fire("click");
  assert(!e.calls.some((c) => c[1].endsWith("/restore")), "annullato: nessuna chiamata");
  e.win.confirm = () => true; await rb.fire("click");
  assert.deepStrictEqual(e.calls.at(-1), ["POST", "/api/game/3/emu-preset/restore", undefined]);
  assert.deepStrictEqual(e.toasts.at(-1), ["Impostazioni originali ripristinate", false]);

  // non supportato: solo la nota, nessun selettore
  e = ambiente(() => ({ supported: false, note: "emulatore non supportato", levels: [] }));
  await e.open({ id: 4, files: ["a"] }); await tick();
  const ns = e.body.querySelector("#d-emucfg");
  assert.strictEqual(ns.byClass("emucfg-select").length, 0);
  assert(ns.textContent.includes("emulatore non supportato"));

  // giochi store/senza ROM: nessuna sezione e nessuna chiamata
  e = ambiente(() => INFO);
  await e.open({ id: 5, store: "steam", files: [] }); await tick();
  assert(!e.body.querySelector("#d-emucfg") && e.calls.length === 0);

  // risposta tardiva ignorata se la scheda è cambiata
  let sblocca; const lenta = new Promise((r) => { sblocca = r; });
  e = ambiente(() => lenta);
  const p = e.open({ id: 8, files: ["a"] }); e.win.S.detail = { id: 9 };
  sblocca(INFO); await p; await tick();
  assert(!e.body.querySelector("#d-emucfg"), "risposta tardiva scartata");

  // Impostazioni › Emulatori: selettore per console, legge e scrive /api/emu-presets
  const { creaComponente } = require(path.join(STATIC, "settings", "emulatori-extra.js"));
  const body = new Nodo("body"); const tr = new Nodo("tr"); tr.querySelectorAll = undefined;
  body.querySelectorAll = () => [Object.assign(tr, { getAttribute: (k) => (k === "data-p" ? "ps1" : null), parentNode: { insertBefore: (n) => { body.rowExtra = n; } }, nextSibling: null, querySelector: () => null })];
  const chiamate = []; const toasts = [];
  globalThis.toast = (t, err) => toasts.push([t, !!err]);
  const fetchFinto = async (url, init) => {
    chiamate.push([init && init.method || "GET", url, init && init.body]);
    const r = (b) => ({ status: 200, ok: true, json: async () => b });
    if (url === "/api/emu-presets") return r({ ps1: "quality" });
    if (url === "/api/emu-presets/console") return r({});
    return { status: 404, ok: false, json: async () => ({}) };
  };
  const doc = { createElement: (t) => new Nodo(t) };
  creaComponente({ document: doc, root: body, fetch: fetchFinto, MutationObserver: null }).avvia();
  await tick(); await tick();
  const psel = body.rowExtra.byClass("xe-preset-sel")[0];
  assert.strictEqual(psel.value, "quality");
  psel.value = "faithful"; await psel.fire("change");
  assert.deepStrictEqual(chiamate.find((c) => c[1] === "/api/emu-presets/console").slice(0, 3), ["POST", "/api/emu-presets/console", JSON.stringify({ platform: "ps1", preset: "faithful" })]);
  assert(toasts.at(-1)[0].includes("salvate") && !toasts.at(-1)[1]);
  console.log("test_emucfg_ui: OK");
})().catch((err) => { console.error(err); process.exit(1); });
