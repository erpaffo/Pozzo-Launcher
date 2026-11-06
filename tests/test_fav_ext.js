"use strict";
// Test per le estensioni preferite (ordinamento e persistenza in favExts).
const assert = require("assert");

// Mock store
const storage = new Map();
const store = {
  get(key, def) {
    return storage.has(key) ? storage.get(key) : def;
  },
  set(key, val) {
    storage.set(key, val);
  },
};

// Implementazione pura sotto test
const favExt = (id) => (store.get("favExts", []).includes(id) ? 1 : 0);
function toggleFavExt(id) {
  const cur = store.get("favExts", []);
  store.set("favExts", cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
}

// 1. Stato iniziale
assert.strictEqual(favExt("media"), 0);
assert.strictEqual(favExt("notizie"), 0);

// 2. Aggiunta preferiti
toggleFavExt("media");
assert.strictEqual(favExt("media"), 1);
assert.strictEqual(favExt("notizie"), 0);
assert.deepStrictEqual(store.get("favExts"), ["media"]);

// 3. Rimozione preferiti
toggleFavExt("media");
assert.strictEqual(favExt("media"), 0);
assert.deepStrictEqual(store.get("favExts"), []);

// 4. Ordinamento estensioni sidebar
const collator = new Intl.Collator("it");
const items = [
  { id: "statistiche", label: "Statistiche" },
  { id: "media", label: "Media" },
  { id: "notizie", label: "Notizie" },
  { id: "anniversari", label: "Anniversari" },
];

toggleFavExt("media");
toggleFavExt("statistiche");

// Ordina: prima preferiti (b - a), poi alfabetico
const sorted = [...items].sort((a, b) => (favExt(b.id) - favExt(a.id)) || collator.compare(a.label || a.id, b.label || b.id));
assert.deepStrictEqual(sorted.map(x => x.id), ["media", "statistiche", "anniversari", "notizie"]);

// 5. Ordinamento plugin settings
const plugins = [
  { id: "ricette-web", name: "Ricette Web" },
  { id: "media-locale", name: "Media Locale" },
  { id: "pulizia", name: "Pulizia" },
];

toggleFavExt("pulizia");
const sortedPlugins = [...plugins].sort((a, b) => (favExt(b.id) - favExt(a.id)) || (a.name || a.id).localeCompare(b.name || b.id));
assert.strictEqual(sortedPlugins[0].id, "pulizia");

// 6. Store estensioni sempre in cima alla sidebar e non considerato estensione ordinabile
const allSidebar = [
  { id: "statistiche", label: "Statistiche" },
  { id: "estensioni", label: "Store estensioni" },
  { id: "media", label: "Media" },
  { id: "notizie", label: "Notizie" },
];
const storeExt = allSidebar.find((x) => x.id === "estensioni");
const otherExts = allSidebar.filter((x) => x.id !== "estensioni")
  .sort((a, b) => (favExt(b.id) - favExt(a.id)) || collator.compare(a.label || a.id, b.label || b.id));
const finalSidebarIds = [storeExt?.id, ...otherExts.map(x => x.id)].filter(Boolean);
assert.deepStrictEqual(finalSidebarIds, ["estensioni", "media", "statistiche", "notizie"]);

console.log("test_fav_ext: ok");
