require("./_i18n_stub");
"use strict";
// Card «Riprendi» della home: testi di tempo e salvataggio, HTML della card. Eseguito con node.
const assert = require("assert");
// stub dei globali del browser usati dal modulo (esc/hue/platName sono definiti altrove in js/)
global.esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
global.hue = () => 200;
global.platName = (p) => `P:${p}`;
const { resumeLeftText, resumeSaveText, resumeHtml } = require("../pozzo/app/static/js/home.js");

// tempo rimasto
assert.strictEqual(resumeLeftText(null), "", "sconosciuto: nessuna riga");
assert.strictEqual(resumeLeftText(undefined), "", "undefined: nessuna riga");
assert.strictEqual(resumeLeftText(0), "", "zero: nessuna riga");
assert.strictEqual(resumeLeftText(6 * 3600), "circa 6 h rimaste");
assert.strictEqual(resumeLeftText(6 * 3600 + 1200), "circa 6 h rimaste", "arrotondato all'ora");
assert.strictEqual(resumeLeftText(3600), "circa 1 h rimasta");
assert.strictEqual(resumeLeftText(45 * 60), "circa 45 min rimasti");
assert.strictEqual(resumeLeftText(10), "circa 1 min rimasti", "mai zero minuti");
assert.strictEqual(resumeLeftText(3570), "circa 1 h rimasta", "59.5 min arrotondati all'ora");

// salvataggio: giorno relativo + HH:MM (ora locale)
const now = new Date(2026, 10, 4, 12, 0).getTime() / 1000;
const at = (y, mo, d, h, mi) => new Date(y, mo, d, h, mi).getTime() / 1000;
assert.strictEqual(resumeSaveText(null, now), "", "nessun salvataggio");
assert.strictEqual(resumeSaveText({ time: at(2026, 10, 4, 9, 5), name: "x" }, now), "salvataggio di oggi 09:05");
assert.strictEqual(resumeSaveText({ time: at(2026, 10, 3, 22, 14), name: "x" }, now), "salvataggio di ieri 22:14");
assert.strictEqual(resumeSaveText({ time: at(2026, 10, 1, 7, 0), name: "x" }, now), "salvataggio di 3 giorni fa 07:00");
// il confine e' il giorno di calendario, non le 24 ore
assert.strictEqual(resumeSaveText({ time: at(2026, 10, 3, 23, 59), name: "x" }, at(2026, 10, 4, 0, 1)), "salvataggio di ieri 23:59");

// HTML: primo elemento grande, gli altri righe piccole con ▶
const items = [
  { id: 7, key: "k7", title: "Zelda <3", platform: "switch", cover: true, played_secs: 100, hltb_main_secs: null,
    remaining_secs: 6 * 3600, last_played: now, save: { time: at(2026, 10, 3, 22, 14), name: "s" } },
  { id: 8, key: "k8", title: "Doom", platform: "pc", cover: null, played_secs: 50, hltb_main_secs: null,
    remaining_secs: null, last_played: now, save: null },
  { id: 9, key: "k9", title: "Celeste", platform: "pc", cover: null, played_secs: 50, hltb_main_secs: null,
    remaining_secs: null, last_played: now, save: null },
];
const html = resumeHtml(items);
assert.ok(html.includes('class="resume-hero"'), "card grande");
assert.ok(html.includes("Zelda &lt;3"), "titolo escapato");
assert.ok(html.includes("circa 6 h rimaste") && html.includes("salvataggio di ieri 22:14"), "righe del primo gioco");
assert.ok(html.includes('data-resume-play="7"'), "▶ della card grande");
assert.ok(html.includes('data-resume-play="8"') && html.includes('data-resume-play="9"'), "▶ delle righe piccole");
assert.ok(html.includes('data-shelf-game="8"') && html.includes('data-shelf-game="9"'), "righe piccole aprono la scheda");
assert.ok(!html.includes('data-shelf-game="7"'), "il primo gioco non e' ripetuto nelle righe");
assert.strictEqual((html.match(/data-resume-play=/g) || []).length, 3);
// senza tempo rimasto e senza salvataggio: niente righe vuote, e una sola card
const solo = resumeHtml([items[1]]);
assert.ok(!solo.includes("rimast") && !solo.includes("salvataggio"), "nessuna riga opzionale");
assert.ok(!solo.includes("resume-row"), "nessuna riga piccola con un solo gioco");

console.log("test_home_resume_ui.js: ok");
