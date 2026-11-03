"use strict";
// Pagina «Download»: formati, stati, unione degli aggiornamenti SSE, riconnessione, filtri, selezione, priorità, modalità lenta, debrid. Eseguito da test_js_harness.py.
const assert = require("assert");
const DLU = require("../pozzo/app/static/js/downloads.js");

// byte e velocità
assert.strictEqual(DLU.bytes(0), "0 B");
assert.strictEqual(DLU.bytes(512), "512 B");
assert.strictEqual(DLU.bytes(1536), "1,50 KB");
assert.strictEqual(DLU.bytes(250 * 1024 ** 2), "250,0 MB");
assert.strictEqual(DLU.bytes(null), "—");
assert.strictEqual(DLU.speed(0), "—", "fermo: niente velocità");
assert.strictEqual(DLU.speed(2 * 1024 ** 2), "2,00 MB/s");

// tempo rimanente
assert.strictEqual(DLU.eta(null), "—");
assert.strictEqual(DLU.eta(Infinity), "—");
assert.strictEqual(DLU.eta(42), "42 s");
assert.strictEqual(DLU.eta(200), "3 min 20 s");
assert.strictEqual(DLU.eta(3900), "1 h 05 min");
assert.strictEqual(DLU.eta(90000), "1 g 1 h");

// stati
assert.strictEqual(DLU.status("running"), "In corso");
assert.strictEqual(DLU.status("paused"), "In pausa");
assert.strictEqual(DLU.status("completed"), "Completato");
assert.strictEqual(DLU.status("boh"), "boh", "stato sconosciuto: mostrato com'è");
assert.deepStrictEqual(DLU.FILE_PRIO.map(([v]) => v), [0, 1, 4, 7]);

// unione: aggiornamento per id, campi mantenuti, nuovi task aggiunti, ordine come il server
let tasks = DLU.merge([], [
  { id: "a", name: "A", status: "running", priority: 0, created: 1, speed: 100 },
  { id: "b", name: "B", status: "queued", priority: 0, created: 2 },
]);
assert.deepStrictEqual(tasks.map((t) => t.id), ["a", "b"]);
tasks = DLU.merge(tasks, [{ id: "b", priority: 2 }, { id: "c", status: "paused", priority: 0, created: 3 }, null]);
assert.deepStrictEqual(tasks.map((t) => t.id), ["b", "a", "c"], "priorità più alta in cima, poi per data");
assert.strictEqual(tasks[0].name, "B", "i campi non inviati restano");
const before = tasks;
DLU.merge(before, [{ id: "a", status: "paused" }]);
assert.strictEqual(before[1].status, "running", "lo stato precedente non viene modificato");

// riepilogo per il contatore della barra laterale
assert.deepStrictEqual(DLU.summary(tasks), { active: 2, speed: 100, up: 0 });
assert.deepStrictEqual(DLU.summary([]), { active: 0, speed: 0, up: 0 });
assert.strictEqual(DLU.summary([{ status: "completed", options: { upload_rate: 50 } }]).up, 50, "in condivisione conta l'upload");

// riconnessione dello stream: 2 s, 5 s, 10 s, poi sempre 30 s
assert.deepStrictEqual([0, 1, 2, 3, 4, 50].map(DLU.backoff), [2000, 5000, 10000, 30000, 30000, 30000]);
assert.strictEqual(DLU.backoff(-1), 2000);

// priorità -2..2
assert.strictEqual(DLU.prio(2), "Massima");
assert.strictEqual(DLU.prio(-1), "Bassa");
assert.strictEqual(DLU.prio(undefined), "Normale");
assert.strictEqual(DLU.prio(9), "Massima", "fuori scala: riportata nei limiti");
assert.strictEqual(DLU.clampPrio(-7), -2);
assert.deepStrictEqual(DLU.PRIO.map(([v]) => v), [2, 1, 0, -1, -2]);

// filtri e ricerca
const list = [
  { id: "1", name: "Ubuntu ISO", source: "https://x/ubuntu.iso", status: "running" },
  { id: "2", name: "Film", source: "magnet:?xt=urn:btih:abc", status: "paused" },
  { id: "3", name: null, source: "https://mega.nz/file/Zelda", status: "error" },
];
assert.deepStrictEqual(DLU.filter(list, "all", "").map((t) => t.id), ["1", "2", "3"]);
assert.deepStrictEqual(DLU.filter(list, "paused").map((t) => t.id), ["2"]);
assert.deepStrictEqual(DLU.filter(list, "all", "  UBUNTU ").map((t) => t.id), ["1"], "maiuscole e spazi ignorati");
assert.deepStrictEqual(DLU.filter(list, "all", "zelda").map((t) => t.id), ["3"], "cerca anche nel link");
assert.deepStrictEqual(DLU.filter(list, "running", "film"), []);
assert.ok(DLU.FILTERS.every(([k]) => k === "all" || DLU.status(k) !== k), "ogni filtro è uno stato noto");

// selezione: clic, Ctrl, Maiusc, tasto destro
const ids = ["a", "b", "c", "d"];
let st = DLU.select(new Set(), ids, null, "b", "one");
assert.deepStrictEqual([...st.sel], ["b"]);
st = DLU.select(st.sel, ids, st.anchor, "d", "toggle");
assert.deepStrictEqual([...st.sel].sort(), ["b", "d"]);
st = DLU.select(st.sel, ids, st.anchor, "d", "toggle");
assert.deepStrictEqual([...st.sel], ["b"], "Ctrl+clic toglie");
st = DLU.select(new Set(["a"]), ids, "a", "c", "range");
assert.deepStrictEqual([...st.sel], ["a", "b", "c"]);
assert.strictEqual(st.anchor, "a", "l'ancora resta per il Maiusc successivo");
assert.deepStrictEqual([...DLU.select(st.sel, ids, "c", "a", "range").sel], ["a", "b", "c"], "intervallo all'indietro");
assert.deepStrictEqual([...DLU.select(st.sel, ids, "zz", "b", "range").sel], ["b"], "ancora sparita: solo la riga");
assert.strictEqual(DLU.select(st.sel, ids, "a", "b", "ctx").sel, st.sel, "tasto destro su una selezionata: la selezione resta");
assert.deepStrictEqual([...DLU.select(st.sel, ids, "a", "d", "ctx").sel], ["d"], "tasto destro fuori: solo quella");

// limite del singolo download
assert.strictEqual(DLU.limit({ down: 500, up: 0 }), "↓ 500 KB/s");
assert.strictEqual(DLU.limit({ down: 500, up: 20 }), "↓ 500 KB/s ↑ 20 KB/s");
assert.strictEqual(DLU.limit(undefined), "");
assert.strictEqual(DLU.limit({ down: 0, up: 0 }), "");

// programmazione della modalità lenta
assert.strictEqual(DLU.schedule(null), "");
assert.strictEqual(DLU.schedule({ enabled: false, from: "22:00", to: "07:00" }), "");
assert.strictEqual(DLU.schedule({ enabled: true, from: "22:00", to: "07:00", days: [0, 1, 2, 3, 4, 5, 6] }), "ogni giorno, dalle 22:00 alle 07:00");
assert.strictEqual(DLU.schedule({ enabled: true, from: "09:00", to: "18:00", days: [4, 3, 2, 1, 0] }), "dal lunedì al venerdì, dalle 09:00 alle 18:00");
assert.strictEqual(DLU.schedule({ enabled: true, from: "1:00", to: "2:00", days: [6, 5] }), "sabato e domenica, dalle 1:00 alle 2:00");
assert.strictEqual(DLU.schedule({ enabled: true, from: "1:00", to: "2:00", days: [0, 2] }), "lun, mer, dalle 1:00 alle 2:00");
assert.strictEqual(DLU.schedule({ enabled: true, from: "1:00", to: "2:00", days: [] }), "nessun giorno, dalle 1:00 alle 2:00");
assert.ok(DLU.schedule({ enabled: true, from: "1:00", to: "2:00" }).startsWith("ogni giorno"), "giorni assenti: tutti");

// servizi debrid
assert.deepStrictEqual(DLU.DEBRID.map(([k]) => k), ["realdebrid", "alldebrid", "premiumize", "torbox", "debridlink"]);
assert.strictEqual(DLU.debridName("realdebrid"), "Real-Debrid");
assert.strictEqual(DLU.debridName("altro"), "altro");
assert.strictEqual(DLU.debridState({ ok: false, error: "Chiave non valida" }), "✗ Chiave non valida");
assert.strictEqual(DLU.debridState(null), "✗ Verifica non riuscita");
assert.strictEqual(DLU.debridState({ ok: true, user: "mario", premium: false }), "✓ Account mario · senza Premium");
assert.strictEqual(DLU.debridState({ ok: true, user: "mario", premium: true }), "✓ Account mario · Premium");
assert.match(DLU.debridState({ ok: true, user: "m", premium: true, expires: 1893456000 }), /Premium fino al .*2030/, "secondi Unix");
assert.match(DLU.debridState({ ok: true, user: "m", premium: true, expires: "2030-01-15T00:00:00Z" }), /fino al .*2030/, "data ISO");
assert.strictEqual(DLU.debridState({ ok: true, user: "m", premium: true, expires: "boh" }), "✓ Account m · Premium", "data illeggibile: omessa");

console.log("test_downloads_ui: ok");

// MultiUp: riconoscimento dei link, ordine e aspetto dei provider, scelta predefinita
assert.ok(DLU.isMultiup({ provider: "MultiUp", host: "ouo.io", url: "https://ouo.io/abc" }), "accorciatore con provider MultiUp");
assert.ok(DLU.isMultiup({ provider: "Mirror", host: "www.multiup.io", url: "https://www.multiup.io/download/x" }), "host multiup");
assert.ok(DLU.isMultiup("https://multiup.org/en/download/x/f"), "URL nudo");
assert.ok(!DLU.isMultiup({ provider: "1fichier", host: "1fichier.com", url: "https://1fichier.com/?a" }));
assert.ok(!DLU.isMultiup("https://notmultiup.example/x"), "solo il dominio vero");
assert.ok(DLU.isMirrorSource("https://ouo.io/abc") && DLU.isMirrorSource("https://multiup.io/x"));
assert.ok(!DLU.isMirrorSource("magnet:?xt=1") && !DLU.isMirrorSource("https://1fichier.com/?a"));
const mirrors = [
  { host: "datanodes.to", name: "datanodes", url: "u1", live: true },
  { host: "1fichier.com", name: "1fichier", url: "u2", live: true },
  { host: "megaup.net", name: "megaup", url: "u3", live: false },
  { host: "krakenfiles.com", name: "krakenfiles", url: "u4", live: true },
];
assert.deepStrictEqual(DLU.sortMirrors(mirrors).map((m) => m.url), ["u4", "u2", "u1", "u3"], "attivi per preferenza, offline in fondo");
assert.strictEqual(DLU.defaultMirror(mirrors).url, "u4");
assert.strictEqual(DLU.defaultMirror([mirrors[0]]).url, "u1", "solo DataNodes: meglio di niente");
assert.strictEqual(DLU.defaultMirror([mirrors[2]]), null, "tutti offline: nessuna scelta");
assert.deepStrictEqual(DLU.mirrorView(mirrors[2]), { label: "megaup", dead: true, browser: false, note: "offline", title: "megaup → megaup.net (offline)" });
assert.strictEqual(DLU.mirrorView(mirrors[0]).note, "richiede il browser");
assert.strictEqual(DLU.mirrorView({ host: "x.com" }).label, "x.com", "senza nome: l'host");
assert.strictEqual(DLU.muTitle(3), "MultiUp — 3 provider");

// registro del download: riga (ora locale, livello a parole e icona), unione incrementale
const at = new Date(2026, 0, 5, 9, 4, 7).getTime() / 1000;
const lv = DLU.logView({ t: at, level: "warn", msg: "riprovo tra 2 s" });
assert.deepStrictEqual([lv.time, lv.level, lv.label, lv.icon, lv.msg], ["09:04:07", "warn", "AVVISO", "⚠ ", "riprovo tra 2 s"]);
assert.strictEqual(lv.text, "09:04:07 AVVISO riprovo tra 2 s");
assert.strictEqual(DLU.logView({ t: at, level: "error", msg: "x" }).label, "ERRORE");
assert.strictEqual(DLU.logView({ t: at, level: "boh", msg: "x" }).level, "info", "livello sconosciuto: info");
assert.strictEqual(DLU.logView({ t: at, level: "info" }).msg, "", "senza testo: vuoto, non «undefined»");
let lg = DLU.logMerge(null, { lines: [{ msg: "a" }, { msg: "b" }], n: 2 });
assert.deepStrictEqual([lg.lines.length, lg.n, lg.fresh, lg.added.length], [2, 2, true, 2]);
lg = DLU.logMerge(lg, { lines: [{ msg: "c" }], n: 3 });
assert.deepStrictEqual([lg.lines.map((l) => l.msg).join(), lg.n, lg.fresh, lg.added.length], ["a,b,c", 3, false, 1]);
lg = DLU.logMerge(lg, { lines: [], n: 3 });
assert.deepStrictEqual([lg.lines.length, lg.fresh, lg.added.length], [3, false, 0], "nessuna riga nuova: resta com'è");
lg = DLU.logMerge(lg, { lines: [{ msg: "z" }], n: 1 });
assert.deepStrictEqual([lg.lines.length, lg.fresh], [1, true], "n scende: è un altro registro, si ricomincia");
lg = DLU.logMerge(null, { lines: Array.from({ length: 1200 }, (_, i) => ({ msg: String(i) })), n: 1200 });
assert.strictEqual(lg.lines.length, 1000);
assert.strictEqual(lg.lines[0].msg, "200", "la finestra tiene le ultime 1000");

// registro come cronologia: tempo relativo, tipo di riga, riepilogo
assert.strictEqual(DLU.logRel(100.4, 100), "+0,4 s");
assert.strictEqual(DLU.logRel(165, 100), "+1 min 05 s");
assert.strictEqual(DLU.logRel(90, 100), "+0,0 s", "mai negativo");
assert.strictEqual(DLU.logKind("  → 1fichier.com (3.2 s)"), "step");
assert.strictEqual(DLU.logKind("Completato: a.rar (1 GB)"), "key");
assert.strictEqual(DLU.logKind("Avanzamento 10%"), "");
const sm = DLU.logSummary([{ t: 10, level: "info" }, { t: 14.5, level: "warn" }, { t: 20, level: "error" }]);
assert.deepStrictEqual([sm.n, sm.warn, sm.error, sm.span], [3, 1, 1, "10,0 s"]);

// link da copiare con il tasto destro: solo http(s), mai i magnet
assert.deepStrictEqual(DLU.copyable(["https://a.b/x", "magnet:?xt=urn:btih:1", " http://c.d ", "", null, "https://a.b/x", "ftp://x"]), ["https://a.b/x", "http://c.d"]);
assert.deepStrictEqual(DLU.copyable(undefined), []);
