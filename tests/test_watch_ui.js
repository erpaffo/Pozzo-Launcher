"use strict";
// Avviso e riga di stato del rilevamento automatico dei giochi. Eseguito da test_js_harness.py.
const assert = require("assert");
const { watchToastText, watchStatusText } = require("../pozzo/app/static/js/watch.js");

assert.strictEqual(watchToastText({ platform: "SNES", count: 1, titles: ["Zelda"] }), "1 nuovo gioco in SNES: Zelda");
assert.strictEqual(watchToastText({ platform: "SNES", count: 3, titles: ["A", "B", "C"] }), "3 nuovi giochi in SNES: A, B, C");
assert.strictEqual(watchToastText({ platform: "SNES", count: 5, titles: ["A", "B", "C", "D", "E"] }), "5 nuovi giochi in SNES: A, B, C e altri 2");
assert.strictEqual(watchToastText({ platform: "SNES", count: 4, titles: [] }), "4 nuovi giochi in SNES");
assert.strictEqual(watchToastText({ count: 0 }), null);
assert.strictEqual(watchToastText(null), null);

assert.strictEqual(watchStatusText(null, 0), "");
assert.strictEqual(watchStatusText({ enabled: false }, 0), "Disattivato");
assert.strictEqual(watchStatusText({ enabled: true, pending: [], last_scan: 88 }, 100), "In ascolto · ultima verifica 12 s fa");
assert.strictEqual(watchStatusText({ enabled: true, pending: [], last_scan: null }, 100), "In ascolto");
assert.strictEqual(watchStatusText({ enabled: true, pending: ["snes", "gba"], last_scan: 1 }, 100), "Aspetto che finisca la copia di: snes, gba");
assert.strictEqual(watchStatusText({ enabled: true, pending: 2, last_scan: 1 }, 100), "Aspetto che finisca la copia di 2 file");
assert.strictEqual(watchStatusText({ enabled: true, pending: 0, last_scan: 88 }, 100), "In ascolto · ultima verifica 12 s fa");
assert.strictEqual(watchStatusText({ enabled: true, pending: [], last_scan: 40, errors: 2 }, 220), "In ascolto · ultima verifica 3 min fa · 2 errori");
console.log("test_watch_ui: ok");
