const strict = require("node:assert/strict");
const assert = Object.assign((...a) => strict(...a), strict, { // gli oggetti nati nel vm hanno un altro prototipo: si confrontano come JSON
  deepEqual: (a, b, m) => strict.equal(JSON.stringify(a), JSON.stringify(b), m),
});
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const S = path.join(__dirname, "..", "pozzo", "app", "static");
const read = (f) => fs.readFileSync(path.join(S, f), "utf8");
const core = read("core.js");
const block = core.slice(core.indexOf("/* ui-prefs:start"), core.indexOf("/* ui-prefs:end */"));
assert.ok(block.includes("const GSUi"), "blocco ui-prefs presente in core.js");

function world(initial = {}) {
  const ls = new Map(Object.entries(initial));
  const head = { children: [], appendChild(c) { c.parent = this; this.children.push(c); } };
  const mk = (tag) => ({ tag, id: "", textContent: "", remove() { head.children = head.children.filter((x) => x !== this); } });
  const root = { dataset: {}, style: { vars: {}, setProperty(k, v) { this.vars[k] = v; } } };
  const document = { documentElement: root, head, createElement: mk, getElementById: (id) => head.children.find((c) => c.id === id) || null };
  const store = { // come store di core.js
    get(k, d) { try { const v = ls.get("gs." + k); return v === undefined ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { ls.set("gs." + k, JSON.stringify(v)); },
  };
  const ctx = { document, store, window: {} };
  vm.runInNewContext(`${block}\nthis.GSUi = GSUi;`, ctx);
  return { U: ctx.GSUi, document, root, ls, store, head };
}
const GOOD = { bg: "#0f1115", "bg-2": "#151821", "bg-3": "#1c2030", panel: "#171a23", line: "#262b3a", text: "#e7e9ee",
  muted: "#8b92a5", accent: "#5b8cff", "accent-2": "#8b72ff", fav: "#ffcf4a" };

// --- zoom e densita': 90..125 a passi di 5, valori ignoti tornano ai predefiniti
{
  const { U, root } = world();
  assert.deepEqual([...U.ZOOMS], [90, 95, 100, 105, 110, 115, 120, 125]);
  assert.deepEqual({ ...U.prefs(null) }, { zoom: 100, density: "comfortable", idle: 3, coverAccent: true });
  assert.equal(U.prefs({ zoom: 87 }).zoom, 100);
  assert.equal(U.prefs({ zoom: 130 }).zoom, 100);
  assert.equal(U.prefs({ density: "tiny" }).density, "comfortable");
  assert.equal(U.prefs({}).coverAccent, true, "colore copertina: attivo di predefinito");
  assert.equal(U.prefs({ coverAccent: false }).coverAccent, false);
  assert.equal(U.prefs({ coverAccent: "no" }).coverAccent, true, "valore non booleano: predefinito");
  assert.equal(U.prefs({ idle: 0 }).idle, 0);          // 0 = disattivato, non "predefinito"
  assert.equal(U.prefs({ idle: 7 }).idle, 3);
  assert.equal(U.prefs({ idle: 3 }).idle, 3);
  assert.equal(root.dataset.uiZoom, undefined, "100% all'avvio: nessun attributo, layout invariato");
  assert.equal(root.style.vars["--ui-zoom"], "1");
  assert.equal(root.dataset.uiDensity, "comfortable");
}

// --- l'avvio applica le preferenze salvate prima del resto della pagina
{
  const { root, document } = world({ "gs.ui": JSON.stringify({ zoom: 125, density: "compact", idle: 10 }) });
  assert.equal(root.dataset.uiZoom, "125");
  assert.equal(root.style.vars["--ui-zoom"], "1.25");
  assert.equal(root.dataset.uiDensity, "compact");
  assert.equal(document.getElementById("gs-user-theme"), null);
}
{
  const { root } = world({ "gs.ui": "{rotto" }); // JSON illeggibile: predefiniti
  assert.equal(root.dataset.uiZoom, undefined);
  assert.equal(root.dataset.uiDensity, "comfortable");
}
{
  const { U, store } = world();
  store.set("ui", { zoom: 110 });
  assert.equal(U.saved().zoom, 110);
  const w = world(); w.U.applyPrefs(w.document, { zoom: 90 });
  assert.equal(w.root.dataset.uiZoom, "90");
  w.U.applyPrefs(w.document, { zoom: 100 });
  assert.equal(w.root.dataset.uiZoom, undefined, "tornare a 100% toglie l'attributo");
}

// --- colori e contrasto WCAG
{
  const { U } = world();
  assert.equal(U.toHex("#abc"), "#aabbcc");
  assert.equal(U.toHex("RGB(15, 17, 21)"), "#0f1115");
  assert.equal(U.toHex("rgb(300,0,0)"), null);
  assert.equal(U.toHex("url(x)"), null);
  assert.equal(U.toHex("red"), null);
  for (const hex of ["#5b8cff", "#000000", "#ffffff", "#0f1115", "#ff0000"]) {
    const [h, s, l] = U.hexToHsl(hex);
    const back = U.hslToHex(h, s, l);
    const d = [1, 3, 5].map((i) => Math.abs(parseInt(hex.slice(i, i + 2), 16) - parseInt(back.slice(i, i + 2), 16)));
    assert.ok(Math.max(...d) <= 3, `${hex} -> ${back}`);
  }
  assert.equal(U.hslToHex(0, 100, 50), "#ff0000");
  assert.equal(U.contrastRatio("#000000", "#ffffff").toFixed(2), "21.00");
  assert.equal(U.contrastRatio("#ffffff", "#000000").toFixed(2), "21.00");
  assert.equal(U.contrastRatio("#777777", "#777777"), 1);
  assert.equal(U.contrastRatio("#767676", "#ffffff").toFixed(2), "4.54"); // valore noto: appena sopra AA
  const rep = U.contrastReport(GOOD);
  assert.ok(rep.every((c) => c.ok), JSON.stringify(rep));
  const bad = U.contrastReport({ ...GOOD, text: "#202020" });
  assert.equal(bad.find((c) => c.fg === "text" && c.bg === "bg").ok, false);
}

// --- import/export rigoroso e versionato
{
  const { U } = world();
  const json = U.serializeTheme("Notte", GOOD);
  const t = U.parseTheme(json);
  assert.equal(t.name, "Notte");
  assert.deepEqual(t.tokens, GOOD);
  assert.equal(U.parseTheme(JSON.stringify({ format: "pozzo-theme", version: 1, name: " X ", tokens: { ...GOOD, bg: "#0F1115" } })).tokens.bg, "#0f1115");
  const mk = (patch, tokens = GOOD) => JSON.stringify({ format: "pozzo-theme", version: 1, name: "T", tokens, ...patch });
  const rejects = (text, re) => assert.throws(() => U.parseTheme(text), re);
  rejects("non json", /JSON/);
  rejects("[]", /Tema non valido/);
  rejects(mk({ version: 2 }), /versione/);
  rejects(mk({ format: "altro" }), /versione/);
  rejects(mk({ css: "body{}" }), /campi sconosciuti/);
  rejects(mk({ name: "" }), /Nome/);
  rejects(mk({ name: "<b>" }), /Nome/);
  rejects(mk({ name: "x".repeat(41) }), /Nome/);
  rejects(mk({}, { ...GOOD, "evil": "#000000" }), /sconosciuti/);
  rejects(mk({}, { ...GOOD, bg: "url(http://x/y.png)" }), /Colore non valido: bg/);
  rejects(mk({}, { ...GOOD, bg: "red" }), /Colore non valido: bg/);
  rejects(mk({}, { ...GOOD, bg: "#fff" }), /Colore non valido: bg/);
  rejects(mk({}, { ...GOOD, bg: "#000000;} body{display:none" }), /Colore non valido: bg/);
  const { fav, ...partial } = GOOD;
  rejects(mk({}, partial), /Colore non valido: fav/);
  rejects(mk({}, "x"), /Colori mancanti/);
  rejects("x".repeat(5000), /troppo grande/);
  assert.equal(U.themeCss(GOOD), "html:root{" + Object.entries(GOOD).map(([k, v]) => `--${k}:${v}`).join(";") + "}");
}

// --- tema utente salvato: sopravvive al riavvio, un valore manomesso viene ignorato
{
  const w = world();
  const theme = { enabled: true, name: "Mio", tokens: GOOD };
  w.store.set("userTheme", theme);
  assert.deepEqual(JSON.parse(JSON.stringify(w.U.savedTheme())), theme);
  const style = w.U.applyTheme(w.document);
  assert.ok(style && style.textContent.startsWith("html:root{--bg:#0f1115"));
  assert.equal(w.head.children.length, 1);
  w.U.applyTheme(w.document);                       // riapplicato dopo il tema scelto: mai duplicato
  assert.equal(w.head.children.length, 1);
  w.store.set("userTheme", { ...theme, enabled: false });
  assert.equal(w.U.applyTheme(w.document), null);
  assert.equal(w.head.children.length, 0);
  w.store.set("userTheme", { enabled: true, name: "Mio", tokens: { ...GOOD, bg: "url(x)" } });
  assert.equal(w.U.savedTheme(), null);
  // riavvio: stesso localStorage, nuovo contesto
  const again = world({ "gs.userTheme": JSON.stringify(theme) });
  assert.equal(again.head.children.length, 1);
}

// --- salvaschermo: scelta delle foto, movimento, inattivita' con orologio finto
{
  const { U } = world();
  const games = Array.from({ length: 200 }, (_, i) => ({ id: i, title: "G" + i, cover: i % 4 === 0 ? 0 : 1 }));
  const picked = U.pickSlides(games, () => 0.5);
  assert.equal(picked.length, 60);
  assert.ok(picked.every((g) => g.cover));
  assert.equal(new Set(picked.map((g) => g.id)).size, 60);
  assert.equal(U.pickSlides(games, Math.random, 500).length, 60, "limite assoluto 60");
  assert.equal(U.pickSlides([{ id: 1 }], Math.random).length, 0);
  assert.equal(U.attractMotion("off", false), "none");
  assert.equal(U.attractMotion("reduced", false), "fade");
  assert.equal(U.attractMotion("normal", true), "full", "la scelta manuale batte il sistema");
  assert.equal(U.attractMotion(undefined, true), "fade");
  assert.equal(U.attractMotion(undefined, false), "full");

  let now = 0, id = 0, timers = new Map();
  const clock = {
    setT: (f, ms) => { timers.set(++id, [now + ms, f]); return id; },
    clearT: (t) => timers.delete(t),
    tick(ms) { now += ms; for (const [k, [at, f]] of [...timers]) if (at <= now) { timers.delete(k); f(); } },
  };
  const log = []; let minutes = 5, can = true;
  const idle = U.createIdle({ minutes: () => minutes, canRun: () => can, start: () => log.push("start"), stop: () => log.push("stop"), ...clock });
  idle.arm();
  clock.tick(4 * 60000 + 59000); assert.deepEqual(log, []);
  clock.tick(1000); assert.deepEqual(log, ["start"]); assert.equal(idle.isActive(), true);
  assert.equal(idle.activity(), true, "il primo input chiude e va consumato");
  assert.deepEqual(log, ["start", "stop"]);
  assert.equal(idle.activity(), false, "poi gli input passano normalmente");
  clock.tick(5 * 60000 - 1); assert.equal(log.length, 2);   // l'attivita' ha riavviato il conto
  clock.tick(1); assert.equal(log.length, 3);
  idle.activity();
  can = false;                                               // gioco in corso: non parte, ci riprova piu' tardi
  clock.tick(5 * 60000); assert.equal(idle.isActive(), false); assert.equal(log.length, 4);
  can = true; clock.tick(5 * 60000); assert.equal(idle.isActive(), true);
  assert.equal(idle.close(), true); assert.equal(idle.close(), false);
  minutes = 0; idle.activity(); assert.equal(timers.size, 0, "0 = disattivato: nessun timer");
}

// --- cablaggio nei file: variabili root, input intercettato, nessun endpoint nuovo
{
  const app = read("app.css"), bp = read("bigpicture.css"), js = read("bigpicture.js"), html = read("bigpicture.html"), aspetto = read("settings/aspetto.html");
  assert.match(app, /--ui-zoom: 1;/);
  assert.match(bp, /:root \{ --ui-zoom: 1;/);
  assert.match(app, /html\[data-ui-zoom\]:not\(\[data-mode="bigpicture"\]\) body \{ zoom: var\(--ui-zoom\)/);
  assert.match(bp, /font-size: calc\(clamp\(15px, 1\.15vw, 24px\) \* var\(--ui-zoom, 1\)\)/);
  assert.match(bp, /html\[data-bptext="large"\] body \{ font-size: calc\(clamp\(18px, 1\.4vw, 28px\) \* var\(--ui-zoom, 1\)\); \}/);
  assert.match(bp, /html\[data-bptext="xlarge"\] body \{ font-size: calc\(clamp\(21px, 1\.7vw, 33px\) \* var\(--ui-zoom, 1\)\); \}/);
  assert.match(js, /idle\.activity\(\)\) attractClosedAt/);
  assert.match(js, /capture: true, passive: false/);
  assert.match(js, /idle\.close\(\);\r?\n\s*const o = \$\("#bp-running"\)/);
  assert.ok(html.includes('id="bp-attract"'));
  assert.match(aspetto, /<input id="ui-zoom" type="range" min="90" max="125" step="5"/);
  assert.match(app, /--space-scale: 1;/); assert.match(bp, /--space-scale: 1;/);
  assert.match(app, /data-ui-density="compact"\] \{ --space-scale: \.7; \}/);
  assert.match(app, /--nav-pad: calc\(6px \* var\(--space-scale\)\)/);
  for (const f of ["index.html", "bigpicture.html"]) {
    const h = read(f), head = h.slice(0, h.indexOf("</head>"));
    assert.ok(head.indexOf("ui-boot") > 0 && head.indexOf("ui-boot") < head.indexOf("<link rel=\"stylesheet\""), f + ": bootstrap nell'head prima dei CSS");
    // stesso risultato di GSUi.applyPrefs per zoom, densita' e valori non validi
    for (const [ui, zoom, dens] of [[{ zoom: 125, density: "compact" }, "125", "compact"], [{ zoom: 100 }, undefined, undefined], [{ zoom: 87 }, undefined, undefined],
      [{ zoom: "110" }, undefined, undefined], [{ zoom: 90, density: "x" }, "90", undefined]]) {
      const root = { dataset: {}, style: { setProperty() {} } };
      const code = head.match(/<script>([\s\S]*?)<\/script>/)[1];
      vm.runInNewContext(code, { document: { documentElement: root }, localStorage: { getItem: () => JSON.stringify(ui) }, JSON });
      assert.equal(root.dataset.uiZoom === undefined ? undefined : String(root.dataset.uiZoom), zoom, JSON.stringify(ui));
      assert.equal(root.dataset.uiDensity, dens);
    }
    const bad = { dataset: {}, style: { setProperty() {} } };
    vm.runInNewContext(head.match(/<script>([\s\S]*?)<\/script>/)[1], { document: { documentElement: bad }, localStorage: { getItem() { throw new Error("no storage"); } }, JSON });
    assert.deepEqual(bad.dataset, {});
  }
  for (const id of ["ui-zoom", "ui-density", "ui-idle", "te-save", "te-export", "te-import"]) assert.ok(aspetto.includes(`id="${id}"`), id);
  assert.ok(!/fetch\(|api\(["'`]\/api\/(ui|attract)/.test(js), "nessun endpoint inventato");
}

// --- colore del gioco (Task 4): solo #rrggbb, mai --accent del tema
{
  const { safeAccent } = require(path.join(S, "js", "detail.js"));
  assert.equal(safeAccent("#A1b2C3"), "#a1b2c3");
  for (const bad of [null, undefined, "", "#fff", "red", "#12345g", "#1234567", "url(x)", "#aabbcc;}", 5, {}]) assert.equal(safeAccent(bad), null, String(bad));
  const det = read("js/detail.js"), bp = read("bigpicture.js"), bpcss = read("bigpicture.css"), app = read("app.css");
  assert.ok(!/setProperty\("--accent"/.test(det + bp), "il tema non si sovrascrive");
  assert.match(det, /paintGameAccent\(null\);\r?\n\s*S\.detail = null/, "chiusa la scheda si toglie");
  assert.match(det, /my === S\.openSeq && coverAccentOn\(\)\) paintGameAccent/, "risposta tardiva ignorata");
  assert.match(bp, /const safeAccent = \(v\) => \(typeof v === "string" && \/\^#\[0-9a-f\]\{6\}\$\/i/);
  // salvaschermo: media -> /shots (in cache) -> copertina
  assert.match(bp, /m\.fanart \|\| await shotOf\(g\.id\)/);
  assert.match(bp, /api\(`\/api\/game\/\$\{id\}\/shots`\)/);
  assert.match(bp, /if \(!shotCache\.has\(id\)\)/);
  assert.match(bp, /if \(!id \|\| !bpCoverAccentOn\(\)\) \{ bg\.style\.removeProperty\("--game-accent"\)/);
  assert.match(bpcss, /var\(--game-accent, transparent\)/);
  assert.match(det, /if \(!coverAccentOn\(\)\) return paintGameAccent\(null\)/, "opzione spenta: nessun colore");
  assert.match(det, /addEventListener\("gs-ui-change"/); assert.match(bp, /addEventListener\("gs-ui-change"/);
  assert.ok(read("settings/aspetto.html").includes('id="ui-cover-accent" type="checkbox" checked'));
  assert.match(app, /#detail\[data-game-accent\]/);
  assert.ok(det.includes("/api/game/${id}/cover-accent") && bp.includes("/api/game/${id}/cover-accent"), "endpoint cover-accent");
  assert.ok(!/\/accent`/.test(det + bp), "vecchio endpoint rimosso");
}

console.log("test_ui_prefs: ok");
