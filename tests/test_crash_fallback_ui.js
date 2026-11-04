// Toast di errore di avvio con crash e fallback (C2): `node tests/test_crash_fallback_ui.js`.
// Estrae launchErrorToast da js/actions.js e la esegue con un DOM finto minimo.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "..", "pozzo", "app", "static", "js", "actions.js"), "utf8");
const fn = src.match(/function launchErrorToast[\s\S]*?\n\}\n/);
assert(fn, "launchErrorToast non trovata");

class El {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = { cssText: "" }; this.textContent = ""; this.parentElement = null; this.attrs = {}; }
  appendChild(c) { this.children.push(c); c.parentElement = this; return c; }
  append(...cs) { cs.forEach((c) => this.appendChild(c)); }
  replaceChildren(...cs) { this.children = []; this.append(...cs); }
  setAttribute(k, v) { this.attrs[k] = v; }
}
const toastEl = new El("div");
const overlay = new El("div");
toastEl.parentElement = overlay;
const played = [];
const ctx = {
  document: { createElement: (t) => new El(t) },
  $: (sel) => (sel === "#toast" ? toastEl : null),
  overlayHost: () => overlay,
  toast: (m) => { ctx.plain = m; },
  toastTimer: 0,
  clearTimeout: () => {},
  play: (id, body) => played.push([id, body]),
  S: { byId: new Map([[7, { id: 7, key: "pc/x:1" }]]) },
};
vm.createContext(ctx);
vm.runInContext(fn[0] + "\nthis.launchErrorToast = launchErrorToast;", ctx);

const all = (el, out = []) => { out.push(el); el.children.forEach((c) => all(c, out)); return out; };
const labels = () => all(toastEl).filter((e) => e.tagName === "button").map((b) => b.textContent);

// crash con log HTML e fallback
ctx.launchErrorToast({ status: "error", key: "pc/x:1", message: "ignorato",
  crash: { code: 1, duration: 2.34, log: "<script>x</script>\nerrore" },
  fallback: { label: "RetroArch core X", kind: "core", id: "core:x" } });
assert.strictEqual(toastEl.children[0].children[0].textContent, "L'emulatore si è chiuso subito (codice 1, dopo 2.3 s)");
const det = all(toastEl).find((e) => e.tagName === "details");
assert(det && det.children[0].textContent === "Ultimo log" && det.children[1].tagName === "pre", "details/summary/pre");
assert.strictEqual(det.children[1].textContent, "<script>x</script>\nerrore", "log non escapato come testo");
assert.strictEqual(JSON.stringify(labels()), JSON.stringify(["Prova con RetroArch core X", "Chiudi"]));
all(toastEl).find((e) => e.tagName === "button").onclick();
assert.strictEqual(JSON.stringify(played), JSON.stringify([[7, { fallback: "core:x" }]]));
assert.strictEqual(toastEl.hidden, true);

// senza crash ne' fallback: toast normale
ctx.launchErrorToast({ status: "error", key: "pc/x:1", message: "Boom" });
assert.strictEqual(ctx.plain, "Boom");

// crash senza fallback: niente bottone di riprova, nessun log = nessun details
ctx.launchErrorToast({ status: "error", key: "pc/nope:1", message: "m", crash: { code: 3, duration: 0.4, log: "" }, fallback: { label: "Z", id: "z" } });
assert.strictEqual(JSON.stringify(labels()), JSON.stringify(["Chiudi"]));
assert(!all(toastEl).some((e) => e.tagName === "details"));
assert.strictEqual(toastEl.children[0].children[0].textContent, "L'emulatore si è chiuso subito (codice 3, dopo 0.4 s)");
console.log("ok  toast crash con log e fallback");
