require("./_i18n_stub");
// Filtri salvati: gruppo nella palette Ctrl+K e widget della dashboard. Esegui: node tests/test_saved_filters.js
const assert = require("assert");
const P = require("../pozzo/app/static/palette.js");
const D = require("../pozzo/app/static/js/dashboard.js");

const filters = [{ label: "Platform RPG anni 90", hint: "Filtri salvati" }, { label: "Da finire" }];
const g = P.search({ filters }, "rpg");
assert.deepStrictEqual(g.map((x) => x.id), ["filters"]);
assert.strictEqual(g[0].items[0].label, "Platform RPG anni 90");
assert.deepStrictEqual(P.search({ filters }, "").map((x) => x.id), ["filters"]); // a vuoto compaiono

const w = D.builtInWidgets.find((x) => x.id === "games:saved_filters");
assert.ok(w, "widget registrato");
global.S = { savedF: [{ id: "f1", name: 'Anni "90" <b>' }] };
globalThis.S = global.S;
const html = w.render({});
assert.ok(html.includes('data-saved-filter="f1"'));
assert.ok(!html.includes("<b>"), "nome con escape");
global.S = globalThis.S = { savedF: [] };
assert.ok(w.render({}).includes("gs-widget-empty"));
console.log("ok");
