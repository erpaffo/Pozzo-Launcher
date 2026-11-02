// Palette comandi: normalizzazione, ranking, limiti e debounce (nessun DOM). Esegui: node tests/test_palette.js
const assert = require("assert");
const P = require("../pozzo/app/static/palette.js");

assert.strictEqual(P.normalize("  Pokémon Ünova "), "pokemon unova");
assert.strictEqual(P.score("Pokémon Rosso", "pokemon"), 0);
assert.strictEqual(P.score("Super Pokémon", "POKEMON"), 1);
assert.strictEqual(P.score("Spokemon", "pokemon"), 2);
assert.strictEqual(P.score("Zelda", "mario"), -1);
assert.strictEqual(P.score("Super Mario Bros", "mario super"), 1); // tutte le parole, in qualsiasi ordine

const games = Array.from({ length: 20 }, (_, i) => ({ label: `Gioco ${i}`, hint: "NES" }));
games.push({ label: "Pokémon Blu", hint: "Game Boy" });
const src = {
  games,
  consoles: [{ label: "Game Boy" }, { label: "Nintendo 64" }],
  settings: [{ label: "Aspetto" }, { label: "Libreria" }],
  actions: [{ label: "Cerca", hint: "/" }, { label: "Big Picture (entra / esci)" }],
};
let g = P.search(src, "gioco");
assert.deepStrictEqual(g.map((x) => x.id), ["games"]);
assert.strictEqual(g[0].items.length, P.MAX_GAMES); // massimo 8
assert.strictEqual(g[0].items[0].label, "Gioco 0"); // ordine stabile a parità di punteggio
assert.deepStrictEqual(P.search(src, "pokemon")[0].items.map((x) => x.label), ["Pokémon Blu"]); // senza accenti
assert.deepStrictEqual(P.search(src, "game boy").map((x) => x.id), ["games", "consoles"]);
assert.deepStrictEqual(P.search(src, "ASPETTO").map((x) => x.id), ["settings"]);
assert.deepStrictEqual(P.search(src, "big").map((x) => x.id), ["actions"]);
assert.deepStrictEqual(P.search(src, "zzz"), []);
assert.deepStrictEqual(P.search(src, "").map((x) => x.id), ["consoles", "settings", "actions"]); // a vuoto niente giochi

// debounce: timer finti, durata minima 120 ms anche se se ne chiede meno
let now = 0, seq = 0, pending = new Map();
const timers = {
  set: (fn, ms) => { pending.set(++seq, { at: now + ms, fn }); return seq; },
  clear: (id) => pending.delete(id),
};
const tick = (ms) => { now += ms; for (const [id, t] of [...pending]) if (t.at <= now) { pending.delete(id); t.fn(); } };
const calls = [];
const d = P.debounce((v) => calls.push(v), 10, timers);
d("a"); tick(60); d("ab"); tick(100);
assert.deepStrictEqual(calls, []); // 100 ms dall'ultima chiamata: ancora in attesa
tick(30);
assert.deepStrictEqual(calls, ["ab"]); // una sola chiamata, con l'ultimo valore
d("x"); d.cancel(); tick(500);
assert.deepStrictEqual(calls, ["ab"]);
console.log("ok");