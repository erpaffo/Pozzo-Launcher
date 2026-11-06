const { inject } = require("./_i18n_stub");
// Pannello «Perché non parte?» (diagnose): `node tests/test_diagnose_ui.js`.
// Estrae diagHtml, skelInline (detail.js) ed esc (core.js) ed esegue il bottone «Perché?» di launchErrorToast (actions.js) con un DOM finto minimo.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const read = (f) => fs.readFileSync(path.join(__dirname, "..", "pozzo", "app", "static", f), "utf8").replace(/\r\n/g, "\n");
const detailSrc = read("js/detail.js"), actionsSrc = read("js/actions.js"), coreSrc = read("core.js");

const escLine = coreSrc.match(/const esc = [^\n]*\n/);
assert(escLine, "esc non trovata in core.js");

const diagFns = ["function skelInline", "function diagHtml"].map((sig) => {
  const m = detailSrc.match(new RegExp(sig + "[\\s\\S]*?\\n\\}\\n"));
  assert(m, sig + " non trovata");
  return m[0];
});
const toastFn = actionsSrc.match(/function launchErrorToast[\s\S]*?\r?\n\}\r?\n/);
assert(toastFn, "launchErrorToast non trovata");

const ctx = { window: { GSSkeleton: undefined } };
inject(ctx); vm.createContext(ctx);
vm.runInContext(escLine[0] + diagFns.join("\n") + "\nthis.diagHtml = diagHtml; this.skelInline = skelInline;", ctx);

// diagnosi: causa più probabile in cima, testi escapati, ✓/✗ con causa e rimedio
const r = {
  ok: false, probabile: 1,
  checks: [
    { nome: "Emulatore", ok: true, causa: "", rimedio: "" },
    { nome: "BIOS <x>", ok: false, causa: "manca <b>bios</b>", rimedio: "copia & incolla" },
  ],
};
const html = ctx.diagHtml(r);
assert(html.indexOf("Causa più probabile") >= 0, "manca la causa più probabile");
assert(html.indexOf("dg-probable") < html.indexOf("dg-checks"), "la causa probabile deve stare in cima");
assert(html.includes("BIOS &lt;x&gt;") && !html.includes("BIOS <x>"), "nome non escapato");
assert(html.includes("manca &lt;b&gt;bios&lt;/b&gt;") && !html.includes("<b>bios</b>"), "causa non escapata");
assert(html.includes("copia &amp; incolla"), "rimedio non escapato");
assert(html.includes('dg-check ok') && html.includes('dg-check ko'), "ok/ko mancanti");
assert(!/dg-check ok[^]*?dg-causa/.test(html.split("</li>")[0]), "un check ok non deve mostrare causa");

// senza probabile valido (null, fuori indice, stringa): niente evidenza
for (const p of [null, 5, "1"]) {
  const h = ctx.diagHtml({ ok: false, probabile: p, checks: r.checks });
  assert(!h.includes("Causa più probabile"), "probabile " + p + " non dovrebbe evidenziare");
}
// tutto ok
assert(ctx.diagHtml({ ok: true, probabile: null, checks: [{ nome: "A", ok: true }] }).includes("Nessun problema trovato"));
// checks mancanti: nessun crash
assert.strictEqual(typeof ctx.diagHtml({}), "string");

// segnaposto: senza GSSkeleton il testo di fallback, con GSSkeleton la riga dg-skel-line
const el = { innerHTML: "vecchio" };
ctx.skelInline(el, 2, "<i>fallback</i>");
assert.strictEqual(el.innerHTML, "<i>fallback</i>", "fallback senza GSSkeleton");
const added = [];
ctx.window.GSSkeleton = { show: (c, n) => { c.innerHTML = ""; c.count = n; return { classList: { add: (x) => added.push(x) } }; } };
const el2 = { innerHTML: "" };
ctx.skelInline(el2, 3, "<i>fallback</i>");
assert.strictEqual(el2.count, 3, "conteggio righe");
assert.strictEqual(JSON.stringify(added), JSON.stringify(["dg-skel-line"]), "classe della riga");

// toast di avvio: «Perché?» solo se il pannello è caricato e il gioco è noto
class El {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = { cssText: "" }; this.textContent = ""; this.parentElement = null; }
  appendChild(c) { this.children.push(c); c.parentElement = this; return c; }
  append(...cs) { cs.forEach((c) => this.appendChild(c)); }
  replaceChildren(...cs) { this.children = []; this.append(...cs); }
  setAttribute() {}
}
const toastEl = new El("div"), overlay = new El("div");
toastEl.parentElement = overlay;
const opened = [];
const tctx = { window: {},
  document: { createElement: (t) => new El(t) },
  $: (sel) => (sel === "#toast" ? toastEl : null),
  overlayHost: () => overlay,
  toast: () => {},
  toastTimer: 0,
  clearTimeout: () => {},
  play: () => {},
  S: { byId: new Map([[7, { id: 7, key: "pc/x:1" }]]) },
  openDiagnose: (id) => opened.push(id),
};
inject(tctx); vm.createContext(tctx);
vm.runInContext(toastFn[0] + "\nthis.launchErrorToast = launchErrorToast;", tctx);
const all = (el, out = []) => { out.push(el); el.children.forEach((c) => all(c, out)); return out; };
const labels = () => all(toastEl).filter((e) => e.tagName === "button").map((b) => b.textContent);

tctx.launchErrorToast({ status: "error", key: "pc/x:1", message: "m", crash: { code: 1, duration: 1, log: "" } });
assert.strictEqual(JSON.stringify(labels()), JSON.stringify(["Perché?", "Chiudi"]), "bottone Perché? mancante");
all(toastEl).find((e) => e.tagName === "button").onclick();
assert.strictEqual(JSON.stringify(opened), JSON.stringify([7]), "Perché? deve aprire il pannello del gioco");
assert.strictEqual(toastEl.hidden, true);

// gioco non noto: niente «Perché?»
tctx.launchErrorToast({ status: "error", key: "pc/nope:1", message: "m", crash: { code: 1, duration: 1, log: "" } });
assert.strictEqual(JSON.stringify(labels()), JSON.stringify(["Chiudi"]));

console.log("ok  pannello perché non parte: diagnosi, segnaposto, toast");
