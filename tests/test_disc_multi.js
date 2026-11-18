const strict = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const core = fs.readFileSync(path.join(__dirname, "..", "pozzo", "app", "static", "core.js"), "utf8");
const src = core.slice(core.indexOf("const THIS_YEAR"), core.indexOf("/** Generi piu'"));
const ctx = { t: (k) => k, collator: new Intl.Collator(),
  fold: (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase() };
vm.runInNewContext(`${src}\nthis.discNorm=discNorm;this.discActive=discActive;this.discover=discover;`, ctx);
const J = (x) => JSON.stringify(x), eq = (a, b) => strict.equal(J(a), J(b));
const { discNorm, discActive, discover } = ctx;

eq(discNorm({ preset: "", genre: "", decade: "" }), { preset: [], genre: [], decade: [], genreMode: "any" });
eq(discNorm({ preset: "top", genre: "rpg", decade: 1990 }), { preset: ["top"], genre: ["rpg"], decade: ["1990"], genreMode: "any" });
eq(discNorm({ preset: ["", "top", "top"], genre: null, decade: [1990, "1990", 2000], genreMode: "all" }),
  { preset: ["top"], genre: [], decade: ["1990", "2000"], genreMode: "all" });
eq(discNorm(null), discNorm({})); eq(discNorm({ genreMode: "x" }).genreMode, "any");
strict.ok(!discActive({}) && !discActive({ preset: "" }) && discActive({ genre: ["a"] }) && discActive({ decade: 1990 }));

const mk = (id, year, genres, o = {}) => ({ id, year, genres, sort: id, critics: null, rating: null, votes: 0, ...o });
const G = [mk("a", 1995, "RPG, Azione", { critics: 0.95, rating: 0.9, votes: 100 }), mk("b", 2005, "Azione"),
  mk("c", 2015, "RPG", { critics: 0.8, votes: 3 }), mk("d", 1992, "Azione, RPG", { critics: 0.76 })];
const ids = (r) => r.items.map((g) => g.id).join("");
strict.equal(ids(discover(G, { decade: ["1990", "2010"] })), "acd");
strict.equal(ids(discover(G, { genre: ["rpg", "azione"] })), "abcd"); // any
strict.equal(ids(discover(G, { genre: ["rpg", "azione"], genreMode: "all" })), "ad");
strict.equal(ids(discover(G, { genre: ["rpg"], decade: ["1990"] })), "ad"); // AND tra categorie
// preset multipli: AND degli ok, cmp del primo che ce l'ha
let r = discover(G, { preset: ["critics", "loved"] });
strict.equal(ids(r), "a"); strict.equal(r.preset.id, "critics"); strict.equal(typeof r.cmp, "function");
r = discover(G, { preset: ["unrated", "critics"] }); strict.equal(r.items.length, 0);
// formato vecchio e preset singolo (Big Picture)
r = discover(G, { preset: "critics" });
strict.equal(ids(r), "acd"); strict.equal(r.preset.id, "critics"); strict.equal(typeof r.cmp, "function");
strict.equal(r.items.sort(r.cmp)[0].id, "a");
strict.equal(ids(discover(G, { preset: "", genre: "azione", decade: "1990" })), "ad");
r = discover(G); strict.equal(ids(r), "abcd"); strict.equal(r.cmp, null); strict.equal(r.preset.id, "");
console.log("ok test_disc_multi");
