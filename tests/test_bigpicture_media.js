"use strict";
// Big Picture · Media: logica pura (righe, serie/stagioni, pad -> comando, assenza estensione): `node tests/test_bigpicture_media.js`.
const assert = require("assert"), path = require("path");
global.window = {};
const M = require(path.join(__dirname, "..", "pozzo", "app", "static", "bigpicture-media.js"));

const ep = (series, season, episode, extra = {}) => ({ id: `${series}${season}${episode}`, kind: "episodio", title: `Ep ${episode}`, series, season, episode, source: "media-locale", poster: "", ...extra });
const list = [
  { id: 1, kind: "film", title: "Zeta", source: "media-locale", resume_pos: 120, duration: 600 },
  { id: 2, kind: "film", title: "Alfa", source: "media-locale", seen: true, resume_pos: 50 },
  { id: 3, kind: "brano", title: "Canzone" },
  ep("Lost", 2, 1), ep("Lost", 1, 2, { resume_pos: 300, duration: 600, poster: "/p.jpg" }), ep("Lost", 1, 1, { seen: true }),
  ep("Naruto", 1, 1, { genre: "Animazione" }),
  { id: 9, kind: "serie", title: "Catalogo", series: "Catalogo", source: "ricette-web" },
];

// solo video, niente doppioni, sorgente assente (null/errore) ignorata
assert.strictEqual(M.mergeSources([{ items: list }, null, { items: [list[0]] }]).length, list.length - 1);

// serie: stagioni e episodi ordinati, conteggio solo se reale
const s = M.groupSeries(M.mergeSources([list]));
const lost = s.find((x) => x.title === "Lost");
assert.deepStrictEqual(lost.seasons.map((x) => [x.season, x.episodes.map((e) => e.episode)]), [[1, [1, 2]], [2, [1]]]);
assert.strictEqual(lost.count, 3);
assert.strictEqual(lost.poster, "/p.jpg");
assert.strictEqual(M.groupSeries([ep("X", 1, 1, { source: "ricette-web" })])[0].count, null);

// Continua a guardare: iniziati e non visti
assert.deepStrictEqual(M.continueItems(list).map((i) => i.id), [1, "Lost12"]);

// righe: vuote omesse, anime separati, conteggi non inventati
const rows = M.buildRows(M.mergeSources([list]), [{ title: "Dune", item_id: "7", source: "media-locale" }]);
assert.deepStrictEqual(rows.map((r) => r.id), ["continue", "film", "serie", "anime", "watchlist"]);
assert.deepStrictEqual(rows.find((r) => r.id === "film").cards.map((c) => c.label), ["Alfa", "Zeta"]);
assert.deepStrictEqual(rows.find((r) => r.id === "serie").cards.map((c) => c.label), ["Lost", "Catalogo"]);
assert.strictEqual(rows.find((r) => r.id === "serie").cards[0].sub, "3 episodi");
assert.strictEqual(rows.find((r) => r.id === "serie").cards[1].sub, "Serie");
assert.strictEqual(rows.find((r) => r.id === "anime").cards[0].label, "Naruto");
assert.strictEqual(rows[0].cards[0].pct, 20);
assert.deepStrictEqual(M.buildRows([], []), []);

// watchlist -> file noto
assert.strictEqual(M.matchWatch({ title: "zeta" }, list).id, 1);
assert.strictEqual(M.matchWatch({ title: "Nulla", item_id: "99" }, list), null);

// mappatura pad -> comando
const P = M.padCommand;
assert.deepStrictEqual(P("a"), { name: "toggle" });
assert.deepStrictEqual(P("b"), { name: "close" });
assert.deepStrictEqual(P("left"), { name: "jump", arg: -10 });
assert.deepStrictEqual(P("right", {}, true), { name: "jump", arg: 30 });
assert.deepStrictEqual(P("up", { volume: 0.5 }), { name: "volume", arg: 0.55 });
assert.deepStrictEqual(P("up", { volume: 1 }), { name: "volume", arg: 1 });
assert.deepStrictEqual(P("down", { volume: 0.02 }), { name: "volume", arg: 0 });
assert.strictEqual(P("lb", { hasPrev: false }), null);
assert.deepStrictEqual(P("rb", { hasNext: true }), { name: "next" });
assert.deepStrictEqual([P("y").name, P("x").name, P("start").name], ["episodes", "skip", "fullscreen"]);
assert.strictEqual(P("lt"), null);

// handlePad: senza lettore non prende nulla; con lettore prende tutto e invia il comando (±30 se tenuto)
assert.strictEqual(M.handlePad("down", 1000), false);
const sent = [];
global.window.__pmCtl = { getState: () => ({ active: true, volume: 0.5 }), command: (n, a) => sent.push([n, a]) };
assert.strictEqual(M.handlePad("a", 1000), true);
assert.strictEqual(M.handlePad("left", 2000), true);
assert.strictEqual(M.handlePad("left", 2380), true); // ripetizione = tenuto
assert.strictEqual(M.handlePad("left", 5000), true); // pressione nuova
assert.deepStrictEqual(sent, [["toggle", undefined], ["jump", -10], ["jump", -30], ["jump", -10]]);
global.window.__pmCtl.getState = () => ({ active: false });
assert.strictEqual(M.handlePad("down", 9000), false);

// estensione assente / disattiva / in errore: nessuna voce
const ext = (p) => ({ plugins: [p] });
assert.strictEqual(M.isAvailable(ext({ id: "media-locale", enabled: true })), true);
assert.strictEqual(M.isAvailable(ext({ id: "media-locale", enabled: false })), false);
assert.strictEqual(M.isAvailable(ext({ id: "media-locale", enabled: true, error: "x" })), false);
assert.strictEqual(M.isAvailable({ plugins: [] }), false);
assert.strictEqual(M.isAvailable(null), false);
M.available(async () => { throw new Error("giu"); }).then((v) => { assert.strictEqual(v, false); console.log("test_bigpicture_media ok"); });
