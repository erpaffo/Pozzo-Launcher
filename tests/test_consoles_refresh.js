const { inject } = require("./_i18n_stub");
// Barra laterale: tutte le console visibili (le vuote in «Altre console») e rilettura degli store senza riavvio.
// Esegui: node tests/test_consoles_refresh.js
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "pozzo", "app", "static", "js");
const els = new Map();
const el = (sel) => { if (!els.has(sel)) els.set(sel, { textContent: "", innerHTML: "", hidden: false }); return els.get(sel); };
const ls = new Map();
const listeners = {};
const ctx = inject({
  window: { addEventListener: (n, f) => { listeners[n] = f; } },
  localStorage: { getItem: (k) => ls.get(k) ?? null, setItem: (k, v) => ls.set(k, v) },
  $: el, esc: (s) => String(s ?? ""), platIcon: () => "", Intl, console,
  collator: new Intl.Collator("it"), favPlat: () => 0, favExt: () => 0, isApp: () => false,
  platName: (id) => id, renderStatusList() {}, renderSmartList() {}, renderCollList() {}, markActive() {}, updateHeader() {},
  smartGames: () => [], shopGames: () => [], renderLanguageFilter() {}, renderDiscTools() {}, addOnline() {}, loadOnline() {},
  decodeLibrary: () => ({}), RECO: {}, store: { get: (k, d) => d, set() {} }, GSI18n: { lang: "it", t: (k) => k },
  GS: { ui: { sidebarItems: [] }, emit() {} },
  S: { games: [], plats: new Map(), catalogs: {}, view: { type: "all" }, stores: [], shop: [], collCounts: null, oneVersion: true },
  api: async () => ({ catalogs: { snes: ["http://x"] } }),
});
ctx.t = (k) => k;
vm.createContext(ctx);
// solo renderSidebar (sidebar.js) e refreshCatalogs (state.js), estratte per nome
const grab = (file, re) => re.exec(fs.readFileSync(path.join(JS, file), "utf8").replace(/\r\n/g, "\n"))[0];
vm.runInContext(grab("sidebar.js", /function counts\(\)[\s\S]*?\n}\n/) + grab("sidebar.js", /function renderSidebar\(\)[\s\S]*?\n}\n/)
  + grab("state.js", /async function refreshCatalogs\(\)[\s\S]*?\n}\nwindow\.addEventListener\([^\n]*\n/), ctx);
const S = ctx.S;
for (const [id, name] of [["nes", "NES"], ["snes", "SNES"], ["ps2", "PS2"]]) S.plats.set(id, { id, name });
S.games = [{ platform: "nes", grp: { primary: 1, colls: [] }, id: 1, found: true }];

ctx.renderSidebar();
let html = el("#platform-list").innerHTML;
assert.match(html, /data-id="nes"/);
assert.doesNotMatch(html, /data-id="snes"|data-id="ps2"/, "console vuote nascoste nel gruppo chiuso");
assert.match(html, /data-other-plats/);
assert.match(html, /h\.nav\.otherConsoles/);

ls.set("gs.otherPlatsOpen", "1");
ctx.renderSidebar();
html = el("#platform-list").innerHTML;
assert.ok(html.indexOf("data-other-plats") < html.indexOf('data-id="snes"'), "le vuote stanno dopo l'intestazione del gruppo");
assert.match(html, /data-id="ps2"/);

// uno store aggiunto: la console passa nel gruppo principale
(async () => {
  await listeners["pz-catalogs-changed"]();
  assert.deepEqual(S.catalogs, { snes: ["http://x"] });
  html = el("#platform-list").innerHTML;
  assert.ok(html.indexOf('data-id="snes"') < html.indexOf("data-other-plats"), "snes ora nel gruppo principale");
  assert.ok(html.indexOf('data-id="ps2"') > html.indexOf("data-other-plats"));
  console.log("ok");
})();
