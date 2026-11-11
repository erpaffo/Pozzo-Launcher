"use strict";
// Vista «Strumenti»: formati, azioni di adozione, richieste, scelta dei giochi. Eseguito da test_js_harness.py.
const assert = require("assert");
const TLU = require("../pozzo/app/static/js/tools.js");

assert.strictEqual(TLU.bytes(null), "");
assert.strictEqual(TLU.bytes(512), "512 B");
assert.strictEqual(TLU.bytes(1536), "1,50 KB");
assert.strictEqual(TLU.bytes(3 * 1024 ** 3), "3,00 GB");

// adozione: solo i lavori che producono file e sono finiti; predefinita = originale nel Cestino
const done = { tool: "chd", status: "done", out: "/r/a.chd" };
assert.deepStrictEqual(TLU.actions(done).map((a) => [a.id, a.move_old]), [["trash", true], ["keep", false], ["skip", undefined]]);
assert.strictEqual(TLU.actions(done)[0].primary, true);
for (const j of [{ ...done, tool: "verify" }, { ...done, tool: "m3u" }, { ...done, tool: "dump" }, { ...done, status: "running" },
  { ...done, out: null }, { ...done, adopted: "trash" }]) assert.deepStrictEqual(TLU.actions(j), [], JSON.stringify(j));

// dimensioni: solo se note
assert.deepStrictEqual(TLU.sizes(done), { before: null, after: null });
assert.deepStrictEqual(TLU.sizes({ size_src: 100, size_out: 40 }), { before: 100, after: 40 });

// cosa manca prima dell'avvio
const T = (id, needs_game = true) => ({ id, needs_game });
const game = { platform: "psx", files: ["/r/a.cue"] };
assert.strictEqual(TLU.missing(T("chd"), null, {}), "game");
assert.strictEqual(TLU.missing(T("chd"), game, {}), "");
assert.strictEqual(TLU.missing(T("patch"), game, {}), "patch");
assert.strictEqual(TLU.missing(T("patch"), game, { patch: "/p.ips" }), "");
assert.strictEqual(TLU.missing(T("dump", false), null, {}), "drive");
assert.strictEqual(TLU.missing(T("dump", false), null, { drive: "D:" }), "dst");
assert.strictEqual(TLU.missing(T("dump", false), null, { drive: "D:", dst: "/o" }), "");

// richieste
assert.deepStrictEqual(TLU.request(T("chd"), game, {}), { tool: "chd", platform: "psx", path: "/r/a.cue" });
assert.deepStrictEqual(TLU.request(T("nup"), game, { format: "nsp" }).options, { format: "nsp" });
assert.deepStrictEqual(TLU.request(T("nup"), game, { format: "boh" }).options, { format: "nup" });
assert.deepStrictEqual(TLU.request(T("patch"), game, { patch: "/p.bps" }).options, { patch: "/p.bps" });
assert.deepStrictEqual(TLU.request(T("dump", false), null, { drive: "D:", dst: "/o" }),
  { tool: "dump", platform: "", dst: "/o", options: { drive: "D:" } });

// giochi scegliibili: niente store, ricerca senza accenti, limite
const fold = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const games = [{ id: 1, title: "Pokémon Rosso" }, { id: 2, title: "Steam Game", store: "steam" }, { id: 3, title: "Altro" }];
assert.deepStrictEqual(TLU.pickGames(games, "pokemon", fold).map((g) => g.id), [1]);
assert.deepStrictEqual(TLU.pickGames(games, "", fold).map((g) => g.id), [1, 3]);
assert.strictEqual(TLU.pickGames(games, "", fold, 1).length, 1);
console.log("test_tools_ui ok");
