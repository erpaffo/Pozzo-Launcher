"use strict";
// Link incollati dal telefono: estrazione dal testo. m.js tocca il DOM al caricamento, quindi si legge solo la funzione. Eseguito con node.
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "../pozzo/app/static/m/m.js"), "utf8");
const m = src.match(/^function extractLinks\([^)]*\) \{[\s\S]*?^\}$/m);
assert.ok(m, "extractLinks non trovata in m.js");
const extractLinks = new Function(`${m[0]}; return extractLinks;`)();

assert.deepStrictEqual(
  extractLinks("ciao https://a.it/x, poi magnet:?xt=urn:btih:ABC&dn=x\nhttp://b.it/y."),
  ["https://a.it/x", "magnet:?xt=urn:btih:ABC&dn=x", "http://b.it/y"], "link misti, punteggiatura finale tolta");
assert.deepStrictEqual(extractLinks("https://a.it https://a.it (https://c.it/z)"), ["https://a.it", "https://c.it/z"], "doppioni tolti");
assert.deepStrictEqual(extractLinks("niente qui, ftp://x.it"), [], "nessun link valido");
assert.deepStrictEqual(extractLinks(undefined), [], "testo assente");

console.log("test_phone_paste_ui: ok");
