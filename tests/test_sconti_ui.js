"use strict";
// Sconti e bundle: funzioni pure di extensions/sconti/logica.js e vista di extensions/sconti/frontend.js
// (con gs e DOM finti). Eseguito con node.
const assert = require("assert");
const path = require("path");
const { pathToFileURL } = require("url");

const file = (f) => pathToFileURL(path.join(__dirname, "..", "extensions", "sconti", f)).href;

(async () => {
  const L = await import(file("logica.js"));

  // prezzi e sconti
  assert.strictEqual(L.fmtPrice(12.5), "12,50 €");
  assert.strictEqual(L.fmtPrice(0), "Gratis");
  assert.strictEqual(L.fmtPrice(null), "—");
  assert.strictEqual(L.fmtPrice("abc"), "—");
  assert.strictEqual(L.fmtPercent(37.4), "-37%");
  assert.strictEqual(L.fmtPercent(150), "-100%");
  assert.strictEqual(L.fmtPercent(0), null);
  assert.strictEqual(L.fmtPercent(null), null);

  // scadenze: secondi, millisecondi, ISO, «AAAA-MM-GG HH:MM» (fonte gratis)
  const now = Date.UTC(2026, 10, 4, 12, 0, 0);
  assert.strictEqual(L.countdown(now / 1000 + 3 * 86400 + 60, now), "scade tra 3 giorni");
  assert.strictEqual(L.countdown(now + 86400000 + 5, now), "scade tra 1 giorno");
  assert.strictEqual(L.countdown(now + 5 * 3600000, now), "scade tra 5 h");
  assert.strictEqual(L.countdown(new Date(now + 20 * 60000).toISOString(), now), "scade tra 20 min");
  assert.strictEqual(L.countdown(now - 1, now), "scaduto");
  assert.strictEqual(L.countdown(null, now), null);
  assert.strictEqual(L.countdown("non una data", now), null);
  const sameDay = new Date(now + 5 * 3600000);
  const hm = `${sameDay.getFullYear()}-${String(sameDay.getMonth() + 1).padStart(2, "0")}-${String(sameDay.getDate()).padStart(2, "0")} ${String(sameDay.getHours()).padStart(2, "0")}:${String(sameDay.getMinutes()).padStart(2, "0")}`;
  assert.strictEqual(L.countdown(hm, now + 5 * 3600000 - 60000), "scade tra 1 min");
  assert.ok(L.fmtDate("2026-11-10").includes("2026"));
  assert.ok(L.fmtDate("2026-11-10 23:59").includes("2026"));
  assert.strictEqual(L.fmtDate(undefined), null);

  // solo http(s) si apre
  assert.strictEqual(L.isHttpUrl("https://store.example/x"), true);
  assert.strictEqual(L.isHttpUrl("http://a.b"), true);
  assert.strictEqual(L.isHttpUrl("javascript:alert(1)"), false);
  assert.strictEqual(L.isHttpUrl("file:///C:/x"), false);
  assert.strictEqual(L.isHttpUrl(""), false);
  assert.strictEqual(L.isHttpUrl(undefined), false);

  // ordinamento
  const deals = [{ title: "B", cut_percent: 10, price: 5 }, { title: "A", cut_percent: null, price: 1 }, { title: "C", cut_percent: 50, price: 9 }];
  assert.deepStrictEqual(L.sortDeals(deals).map((d) => d.title), ["C", "B", "A"]);
  assert.deepStrictEqual(L.sortDeals(deals, "price").map((d) => d.title), ["A", "B", "C"]);
  assert.strictEqual(deals[0].title, "B", "l'originale non viene modificato");
  const bundles = [
    { title: "scaduto", expiry: now - 1000, mine: false },
    { title: "lontano", expiry: now + 9 * 86400000, mine: false },
    { title: "senza", expiry: null, mine: false },
    { title: "vicino", expiry: now + 86400000, mine: false },
    { title: "mio", expiry: now + 5 * 86400000, mine: true },
  ];
  assert.deepStrictEqual(L.sortBundles(bundles, now).map((b) => b.title), ["mio", "vicino", "lontano", "senza", "scaduto"]);

  // fasce e giochi (forma reale: {price, currency, addon, games}; anche {name, price} e stringhe)
  assert.strictEqual(L.tierText({ name: "Base", price: 3 }), "Base · 3,00 €");
  assert.strictEqual(L.tierText({ price: 2, currency: "EUR", addon: false, games: ["Doom"] }), "2,00 €");
  assert.strictEqual(L.tierText({ price: 4, currency: "EUR", addon: true, games: [] }), "Add-on · 4,00 €");
  assert.strictEqual(L.tierText("Gold"), "Gold");
  assert.strictEqual(L.gameNames([{ title: "Doom" }, "Quake", null]), "Doom, Quake");
  assert.strictEqual(L.gameNames(undefined), "");

  // vista, con gs e DOM finti: il pannello e i pulsanti delle schede sono oggetti con listener
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const flush = () => new Promise((r) => setTimeout(r, 0));
  const makeEl = () => {
    const panel = { innerHTML: "", querySelectorAll: () => [] };
    const tabs = ["deals", "bundles", "free"].map((id) => ({
      dataset: { tab: id }, tabIndex: 0, setAttribute() {},
      addEventListener(ev, fn) { this.fn = fn; }, click() { this.fn(); },
    }));
    return {
      innerHTML: "", panel, tabs,
      querySelector: (s) => (s === ".sc-panel" ? panel : null),
      querySelectorAll: (s) => (s === "[data-tab]" ? tabs : []),
    };
  };
  let view = null, sidebar = null, apiImpl = null;
  const gs = {
    esc,
    addSidebarItem: (x) => { sidebar = x; },
    registerView: (id, v) => { view = v; },
    toast() {},
    api: (p, o) => apiImpl(p, o),
  };
  const mod = (await import(file("frontend.js"))).default;
  mod(gs);
  assert.strictEqual(sidebar.label, "Sconti");
  assert.strictEqual(sidebar.view, "sconti");
  assert.strictEqual(view.title, "Sconti e bundle");

  // risposte nella forma reale del backend (extensions/sconti/backend.py)
  const dealsBody = {
    deals: [
      { title: "<img src=x onerror=alert(1)>", store: "Steam", price: 4.5, regular: 9, cut_percent: 50, url: "https://s.example/a", historical_low: true },
      { title: "Senza link", store: "", price: 0, regular: null, cut_percent: 0, url: "javascript:alert(1)", historical_low: false },
    ],
    error: "",
  };
  let bundlesBody = null;
  const freeBody = {
    games: [{ title: "Gioco", kind: "Free to keep", source: "gamerpower", console: "pc", drm: "steam", url: "https://e.example/g",
      end: "2026-11-10 23:59:00", worth: "$19.99" }],
    error: "",
  };
  const calls = [];
  apiImpl = async (p) => {
    calls.push(p);
    if (p.endsWith("/deals")) return dealsBody;
    if (p.endsWith("/bundles")) return bundlesBody;
    if (p.endsWith("/free")) return freeBody;
    throw new Error("percorso inatteso " + p);
  };

  // lista desideri (prima scheda)
  let el = makeEl();
  view.render(el);
  await flush();
  let html = el.panel.innerHTML;
  assert.ok(html.includes("&lt;img src=x"), "titolo escapato");
  assert.ok(!html.includes("<img src=x"), "nessun HTML grezzo dal titolo");
  assert.ok(html.includes("-50%"), "badge sconto");
  assert.ok(html.includes("Minimo storico"), "chip minimo storico");
  assert.ok(html.includes("<s class=\"muted\">9,00 €</s>"), "prezzo pieno barrato");
  assert.ok(html.includes("data-url=\"https://s.example/a\""), "link https con Apri");
  assert.ok(!html.includes("javascript:alert"), "nessun pulsante per link non http");
  assert.ok(!html.includes("Dati non aggiornati"), "nessuna nota senza errore");
  assert.deepStrictEqual(calls, ["/plugin-api/sconti/deals"]);

  // errore del backend con elementi in cache: nota gentile, elementi ancora visibili
  dealsBody.error = "HTTPError: 503";
  el = makeEl();
  view.render(el);
  await flush();
  html = el.panel.innerHTML;
  assert.ok(html.includes("Dati non aggiornati: HTTPError: 503"), "nota errore");
  assert.ok(html.includes("Minimo storico"), "elementi in cache ancora mostrati");
  dealsBody.error = "";

  // risposta come array nudo: accettata
  const bare = dealsBody.deals;
  dealsBody.deals = undefined;
  apiImpl = async () => bare;
  el = makeEl();
  view.render(el);
  await flush();
  assert.ok(el.panel.innerHTML.includes("Minimo storico"), "array nudo accettato");
  apiImpl = async (p) => {
    calls.push(p);
    if (p.endsWith("/deals")) return dealsBody;
    if (p.endsWith("/bundles")) return bundlesBody;
    if (p.endsWith("/free")) return freeBody;
    throw new Error("percorso inatteso " + p);
  };
  dealsBody.deals = bare;

  // bundle con chiave: per te evidenziato, fasce e giochi, nessun messaggio di chiave
  bundlesBody = {
    bundles: [{ title: "Pacchetto", store: "IsThereAnyDeal", url: "http://b.example", expiry: null, mine: true,
      games: ["Doom"], tiers: [{ price: 2, currency: "EUR", addon: false, games: ["Doom"] }] }],
    error: "",
  };
  el = makeEl();
  view.render(el);
  await flush();
  el.tabs[1].click();
  await flush();
  html = el.panel.innerHTML;
  assert.ok(!html.includes("Serve la chiave IsThereAnyDeal"), "nessun messaggio chiave con chiave presente");
  assert.ok(html.includes("sc-mine"), "bundle per te evidenziato");
  assert.ok(html.includes("<li>2,00 €</li>"), "fasce");
  assert.ok(html.includes("Doom"), "giochi del bundle");

  // bundle senza chiave ITAD: messaggio chiave (forma reale: bundles vuoto, need_key true)
  bundlesBody = { bundles: [], need_key: true, error: "" };
  el = makeEl();
  view.render(el);
  await flush();
  el.tabs[1].click();
  await flush();
  html = el.panel.innerHTML;
  assert.ok(html.includes("Serve la chiave IsThereAnyDeal nelle impostazioni"), "messaggio chiave");

  // gratis ora: scadenza con conto alla rovescia, DRM, valore
  el = makeEl();
  view.render(el);
  await flush();
  el.tabs[2].click();
  await flush();
  html = el.panel.innerHTML;
  assert.ok(html.includes("fino al"), "scadenza gratuita");
  assert.ok(html.includes("scade tra") || html.includes("scaduto"), "conto alla rovescia dalla scadenza");
  assert.ok(html.includes("sc-chip\">Steam</span>"), "DRM come chip");
  assert.ok(html.includes("Valore $19.99"), "valore");

  // errore di rete: messaggio in italiano, nessun crash
  apiImpl = async () => { throw new Error("Pozzo Launcher non risponde"); };
  el = makeEl();
  view.render(el);
  await flush();
  assert.ok(el.panel.innerHTML.includes("Impossibile caricare gli sconti"));

  console.log("test_sconti_ui: ok");
})().catch((e) => { console.error(e); process.exit(1); });
