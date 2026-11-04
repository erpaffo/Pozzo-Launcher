// Helper puri di extensions/notizie/segui.js e rassegna.js (conteggi, link sicuri, sezioni): `node tests/test_notizie_segui_ui.js`.
// I moduli sono ES: qui si tolgono gli export e si eseguono in un contesto vm, così si controlla anche che compilino.
"use strict";
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");

function load(file) {
  const src = fs.readFileSync(path.join(__dirname, "..", "extensions", "notizie", file), "utf8")
    .replace(/export default function/, "function __default")
    .replace(/^export /gm, "");
  const ctx = { URL };
  vm.createContext(ctx);
  vm.runInContext(src, ctx, { filename: file });
  return ctx;
}

const plain = (x) => JSON.parse(JSON.stringify(x)); // oggetti della realtà vm: confronto per struttura
const segui = load("segui.js");
const rass = load("rassegna.js");

// link: solo http/https
assert.strictEqual(segui.safeHref("https://example.com/a?b=1"), "https://example.com/a?b=1");
assert.strictEqual(segui.safeHref("http://example.com"), "http://example.com/");
assert.strictEqual(segui.safeHref("javascript:alert(1)"), "");
assert.strictEqual(segui.safeHref("data:text/html,x"), "");
assert.strictEqual(segui.safeHref("non un link"), "");
assert.strictEqual(segui.safeHref(undefined), "");
assert.strictEqual(rass.safeHref("ftp://x.org"), "");
console.log("ok  link solo http/https");

// notizie non lette
assert.strictEqual(segui.contaNonLetti([{ id: 1, unread: 2 }, { id: 2, unread: 0 }, { id: 3, unread: 5 }]), 7);
assert.strictEqual(segui.contaNonLetti([{ id: 1, unread: -4 }, { id: 2 }]), 0);
assert.strictEqual(segui.contaNonLetti(null), 0);
const m = segui.nonLettiPerGioco([{ id: 10, unread: 2 }, { id: 11, unread: 0 }, { id: 12, unread: "3" }]);
assert.deepStrictEqual(plain(Object.fromEntries(m)), { 10: 2, 12: 3 });
assert.strictEqual(m.has("11"), false);
assert.strictEqual(m.get("10"), 2);
console.log("ok  conteggio non letti");

// riepilogo della rassegna
const digest = {
  week_start: "2026-11-02", week_end: "2026-11-08",
  per_casa: { Nintendo: [{ title: "a" }, { title: "b" }], Sega: [], Xbox: [{ title: "c" }] },
  mine: [{ title: "m" }],
  counts: {},
};
assert.deepStrictEqual(plain(rass.riepilogo(digest)), { notizie: 3, mine: 1, case: 2 });
assert.deepStrictEqual(plain(rass.riepilogo({ per_casa: {}, mine: [] })), { notizie: 0, mine: 0, case: 0 });
assert.deepStrictEqual(plain(rass.riepilogo({})), { notizie: 0, mine: 0, case: 0 });
console.log("ok  riepilogo settimana");

// sezioni per casa: max 3 notizie, case vuote escluse, ordine invariato
const sez = rass.sezioniCase({
  A: [1, 2, 3, 4, 5], B: [], C: [6], D: undefined,
});
assert.deepStrictEqual(plain(sez), [["A", [1, 2, 3]], ["C", [6]]]);
assert.deepStrictEqual(plain(rass.sezioniCase({ A: [1, 2] }, 1)), [["A", [1]]]);
assert.deepStrictEqual(plain(rass.sezioniCase(undefined)), []);
console.log("ok  sezioni per casa");
