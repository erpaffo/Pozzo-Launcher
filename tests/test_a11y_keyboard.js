// Navigazione da tastiera: ordine di tabulazione, focus visibile e movimento ridotto. Nessun DOM: si legge l'HTML
// come testo, come fa test_a11y_shell.py. Esegui: node tests/test_a11y_keyboard.js
const strict = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const S = path.join(__dirname, "..", "pozzo", "app", "static");
const read = (f) => fs.readFileSync(path.join(S, f), "utf8");

// Togliamo commenti, script e stili: restano solo i tag che il browser mette nell'ordine di tabulazione.
function tags(html) {
  const clean = html.replace(/<!--[\s\S]*?-->/g, "").replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, "");
  const out = [];
  for (const m of clean.matchAll(/<([a-zA-Z][\w-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/g)) {
    const attrs = {};
    for (const a of m[2].matchAll(/([^\s"'>\/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g)) {
      attrs[a[1].toLowerCase()] = a[2] ?? a[3] ?? a[4] ?? "";
    }
    out.push({ tag: m[1].toLowerCase(), attrs });
  }
  return out;
}

// Stessa logica del browser: elemento con tabindex >= 0 o nativamente interattivo, non nascosto.
const NATIVE = new Set(["button", "input", "select", "textarea", "summary"]);
function tabbable(el) {
  if ("hidden" in el.attrs) return false;
  if (el.attrs.tabindex !== undefined) return Number(el.attrs.tabindex) >= 0;
  if (el.tag === "a") return "href" in el.attrs;
  if (el.tag === "input" && el.attrs.type === "hidden") return false;
  return NATIVE.has(el.tag);
}

// Selettori semplici (tag, [attr], [attr="val"]) della regola :where(...):focus-visible in app.css.
function focusSelectors(css) {
  const m = css.match(/:where\(([^)]*\[tabindex\])\):focus-visible/);
  strict.ok(m, "regola :where(...):focus-visible presente in app.css");
  return m[1].split(",").map((s) => s.trim());
}
function matches(sel, el) {
  const attr = sel.match(/^\[([\w-]+)(?:="([^"]*)")?\]$/);
  if (attr) return attr[1] in el.attrs && (attr[2] === undefined || el.attrs[attr[1]] === attr[2]);
  return sel === el.tag;
}

const pages = ["index.html", "bigpicture.html", "settings/aspetto.html"];
const css = read("app.css");
const focusSel = focusSelectors(css);

// --- nessun tabindex positivo: l'ordine di tabulazione resta quello del documento
for (const f of [...pages, "settings/dati.html", "settings/libreria.html", "settings/generale.html"]) {
  const bad = tags(read(f)).filter((el) => el.attrs.tabindex !== undefined && Number(el.attrs.tabindex) > 0);
  strict.deepEqual(bad.map((el) => el.tag), [], `${f}: tabindex positivo`);
}

// --- ogni elemento raggiungibile con Tab ha il focus visibile (regola :where in app.css)
for (const f of pages) {
  const els = tags(read(f)).filter(tabbable);
  strict.ok(els.length > 0, f + ": elementi raggiungibili con Tab");
  for (const el of els) {
    strict.ok(focusSel.some((s) => matches(s, el)), `${f}: senza focus-visible: <${el.tag}> ${JSON.stringify(el.attrs).slice(0, 120)}`);
  }
}

// --- barra laterale: voci nell'ordine atteso, tutte raggiungibili e attivabili con Invio/Spazio
{
  const nav = tags(read("index.html")).filter((el) => el.attrs.class && el.attrs.class.split(/\s+/).includes("nav-item") && tabbable(el));
  const order = nav.map((el) => el.attrs["data-view"]);
  strict.deepEqual(order, ["foryou", "all", "favorites", "shop", "multi", "free", "ports", "wishlist", "shots", "top", "achievements", "stats", "recent", "tools", "downloads", "missing", "dups", "hidden"], "ordine Tab della barra laterale");
  strict.equal(new Set(order).size, order.length, "data-view duplicati nella barra");
  for (const el of nav) strict.equal(el.attrs.role, "button", "voce non annunciata come pulsante: " + el.attrs["data-view"]);
  const ev = read("js/events.js");
  strict.ok(/\$\("#nav"\)\.addEventListener\("keydown"[\s\S]{0,200}e\.key !== "Enter" && e\.key !== " "/.test(ev), "Invio/Spazio attivano le voci della barra");
}

// --- link di salto: porta il focus nel <main>, che ha tabindex="-1" per riceverlo
{
  const idx = tags(read("index.html"));
  const skip = idx.find((el) => el.tag === "a" && el.attrs.class === "skip-link");
  strict.ok(skip && skip.attrs.href === "#main", "link di salto verso #main");
  const main = idx.find((el) => el.tag === "main");
  strict.equal(main.attrs.id, "main");
  strict.equal(main.attrs.tabindex, "-1");
  strict.equal(idx.indexOf(skip) < idx.indexOf(main), true, "il link di salto viene prima del contenuto");
}

// --- CSS: focus visibile non tolto altrove, token del anello, movimento ridotto globale
{
  strict.match(css, /--focus-ring: var\(--accent\);/, "token --focus-ring");
  // :focus senza :focus-visible con outline: none. Ammesso solo il menu contestuale, che usa il fondo come indicatore.
  const bare = [...css.matchAll(/([^{}]*?):focus\s*(?:,|\{)[^{}]*\{[^}]*outline:\s*(?:none|0)\b/g)].map((m) => m[1].trim().split("\n").pop());
  strict.deepEqual(bare.filter((s) => !/#ctxmenu/.test(s)), [], "outline: none su :focus senza :focus-visible");
  strict.match(css, /@media \(forced-colors: active\)/, "contrasto elevato: focus con colori di sistema");
  // regola globale: animazioni e transizioni quasi nulle con prefers-reduced-motion
  strict.match(css, /@media \(prefers-reduced-motion: reduce\) \{\s*\*, \*::before, \*::after \{\s*animation-duration: \.01ms !important;/, "movimento ridotto globale");
}

console.log("test_a11y_keyboard: ok");
