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

// larghezza delle colonne trascinate: mai sotto il minimo leggibile
assert.strictEqual(DLU.colW(200, 50), 250);
assert.strictEqual(DLU.colW(200, -120), 80);
assert.strictEqual(DLU.colW(60, -100), 56, "colonna mai più stretta del minimo");
assert.strictEqual(DLU.colW(200.4, 0), 200, "larghezze intere");
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

// tabella: host e ordinamento per colonna (stabile, ordine di coda a parità, null = ordine di coda)
assert.strictEqual(DLU.host({ type: "torrent", source: "magnet:?x" }), "torrent");
assert.strictEqual(DLU.host({ type: "http", source: "https://www.Example.com/a" }), "example.com");
const tq = [{ id: "a", name: "b", size: 5 }, { id: "b", name: "A", size: 9 }, { id: "c", name: "c", size: 5 }];
assert.deepStrictEqual(DLU.sortBy(tq, { key: "size", dir: "desc" }).map((t) => t.id), ["b", "a", "c"]);
assert.deepStrictEqual(DLU.sortBy(tq, { key: "name", dir: "asc" }).map((t) => t.id), ["b", "a", "c"]);
assert.strictEqual(DLU.sortBy(tq, null), tq);

// previsione dello spazio per disco: righe in parole, rosso e avviso se la coda non ci sta
const GB = 1024 ** 3;
assert.deepStrictEqual(DLU.spaceLines([{ drive: "C:", free_now: 120 * GB, after_queue: 80 * GB, after_extract: 35 * GB, ok: true }]),
  [{ text: "C: libero ora 120 GB · dopo la coda 80 GB · dopo l'estrazione 35 GB", bad: false }]);
assert.deepStrictEqual(DLU.spaceLines([{ drive: "D:", free_now: 9.5 * GB, after_queue: 1.5 * GB, after_extract: 512, ok: false, unknown: 2 }]),
  [{ text: "D: libero ora 9,5 GB · dopo la coda 1,5 GB · dopo l'estrazione 512 B (2 senza dimensione) · Spazio insufficiente: alcuni download restano in attesa", bad: true }],
  "ok=false: rosso con l'avviso; unknown>0: nota");
assert.strictEqual(DLU.spaceLines([{ drive: "E:", free_now: null, after_queue: undefined, after_extract: -1, unknown: 0 }])[0].text,
  "E: libero ora — · dopo la coda — · dopo l'estrazione —", "valori mancanti o negativi: trattino, nessuna nota");
assert.strictEqual(DLU.spaceLines([{ drive: "E:", free_now: 1, after_queue: 1, after_extract: 1 }])[0].bad, false, "ok assente: non è insufficiente");
assert.deepStrictEqual(DLU.spaceLines(undefined), []);
console.log("test_downloads_ui: spazio ok");

// gruppi (stessa partita): una testata alla posizione del primo membro, un solo membro = download singolo
const gl = [
  { id: "1", name: "Gioco v1", group: "g", group_title: "Gioco", kind: "base", status: "running", size: 1000, done: 250, speed: 100 },
  { id: "2", name: "Altro", status: "queued", size: 5 },
  { id: "3", name: "Gioco DLC", group: "g", group_title: "Gioco", kind: "dlc", status: "queued", size: 1000, done: 0 },
  { id: "4", name: "Gioco patch", group: "g", kind: "update", status: "paused", size: 0, done: 0 },
  { id: "5", name: "Solo", group: "h", status: "running", size: 10, done: 5, speed: 5 },
];
const grows = DLU.groupRows(gl);
assert.deepStrictEqual(grows.map((e) => (e.group ? "G:" + e.group.key : e.task.id)), ["G:g", "2", "5"], "testata dove sta il primo membro");
const gg = grows[0].group;
assert.strictEqual(gg.title, "Gioco");
assert.deepStrictEqual(gg.members.map((t) => t.id), ["1", "3", "4"], "membri nell'ordine di lista");
assert.deepStrictEqual([gg.size, gg.done, gg.progress, gg.unknown, gg.speed], [2000, 250, 0.125, 1, 100], "barra solo su chi ha la dimensione");
assert.strictEqual(gg.eta, 1750 / 100, "rimanente (750 + 1000) / velocità");
assert.strictEqual(gg.summary, "1 in corso, 1 in coda, 1 in pausa");
assert.deepStrictEqual(gg.kinds, ["base", "update", "dlc"]);
assert.strictEqual(grows[2].task.id, "5");
assert.strictEqual(DLU.groupAgg([{ status: "queued" }]).progress, 0, "nessuna dimensione: barra a zero");
assert.strictEqual(DLU.groupAgg([{ status: "queued", size: 10, done: 0 }]).eta, null, "ferma: niente tempo");
assert.strictEqual(DLU.groupAgg([{ status: "error", size: 10, done: 4 }]).summary, "1 con errore");
assert.strictEqual(DLU.groupAgg([{ status: "running", size: 10, done: 50, speed: 1 }]).done, 10, "fatto non oltre la dimensione");
assert.deepStrictEqual(DLU.groupRows([]), []);
assert.deepStrictEqual(DLU.groupRows([{ id: "x", group: "k", status: "running" }]).map((e) => e.task.id), ["x"], "un membro solo non è un gruppo");
console.log("test_downloads_ui: gruppi ok");

// pronto a giocare: testo dell'ora, passi (stepper) e ora della testata di gruppo
const now = new Date(2026, 10, 4, 10, 0).getTime();
const sec = (y, mo, d, h, mi) => new Date(y, mo, d, h, mi).getTime() / 1000;
assert.strictEqual(DLU.readyText({ ready_eta: sec(2026, 10, 4, 21, 40) }, now), "Pronto alle 21:40", "stesso giorno");
assert.strictEqual(DLU.readyText({ ready_eta: sec(2026, 10, 5, 8, 5) }, now), "Pronto domani alle 08:05", "giorno dopo: prefisso domani");
assert.strictEqual(DLU.readyText({ ready: true, ready_eta: sec(2026, 10, 4, 21, 40) }, now), "Pronto a giocare ✓", "pronto: niente ora");
assert.strictEqual(DLU.readyText({ ready: true }, now), "Pronto a giocare ✓");
assert.strictEqual(DLU.readyText({ ready_eta: null }, now), "", "ora sconosciuta: niente testo");
assert.strictEqual(DLU.readyText({ ready_eta: "boh" }, now), "", "ora illeggibile: niente testo");
assert.strictEqual(DLU.readyText(undefined, now), "");
assert.strictEqual(DLU.readyText({ ready_eta: sec(2026, 10, 6, 21, 40) }, now), "Pronto ven alle 21:40", "dopodomani: giorno della settimana, non domani");
assert.ok(DLU.stepperHtml({ stages: [{ id: "library", state: "active", pct: 0, note: "In attesa <dell'installazione>" }] })
  .includes("Libreria · In attesa &#60;dell'installazione&#62;"), "nota al posto della percentuale, con escape");

assert.strictEqual(DLU.stepperHtml({}), "", "senza passi: niente stepper");
assert.strictEqual(DLU.stepperHtml({ stages: [{ id: "download", state: "skip" }] }), "", "solo skip: niente stepper");
const stp = DLU.stepperHtml({ stages: [
  { id: "download", label: "x", state: "done", pct: 100 },
  { id: "extract", state: "active", pct: 42.4 },
  { id: "library", state: "skip" },
  { id: "data", state: "todo" },
] });
assert.match(stp, /^<ul class="dl-stepper" role="list"/, "lista accessibile");
assert.strictEqual((stp.match(/<li /g) || []).length, 3, "lo skip non compare");
assert.match(stp, /aria-label="Scarico: fatto"[^>]*>.*Scarico ✓/, "fatto: spunta");
assert.match(stp, /aria-label="Estrazione: in corso 42%"[^>]*>.*Estrazione 42%/, "attivo: percentuale");
assert.match(stp, /aria-label="Dati: da fare"[^>]*>.*Dati</, "da fare: solo il nome");
const err = DLU.stepperHtml({ stages: [{ id: "extract", state: "error", pct: 10 }, { id: "boh", state: "todo" }, { id: "library", state: "strano" }] });
assert.match(err, /aria-label="Estrazione: errore"[^>]*>.*Estrazione ✗/, "errore: croce");
assert.strictEqual((err.match(/<li /g) || []).length, 2, "fase sconosciuta: nascosta");
assert.match(err, /class="dl-step todo"/, "stato sconosciuto: da fare");
assert.strictEqual(DLU.stepperHtml({ stages: [{ id: "data", state: "active", pct: 250 }] }).includes("Dati 100%"), true, "percentuale nei limiti");

// gruppo: ora più tarda tra i membri; pronto solo se lo sono tutti
const gr = DLU.groupAgg([
  { status: "running", size: 10, done: 1, speed: 1, ready_eta: sec(2026, 10, 4, 20, 0) },
  { status: "queued", size: 10, done: 0, ready_eta: sec(2026, 10, 4, 22, 15) },
  { status: "queued", size: 10, done: 0 },
]);
assert.strictEqual(DLU.readyText(gr, now), "Pronto alle 22:15", "vince l'ora più tarda");
assert.strictEqual(gr.ready, false);
const grd = DLU.groupAgg([{ status: "completed", size: 1, done: 1, ready: true }, { status: "completed", size: 1, done: 1, ready: true }]);
assert.strictEqual(DLU.readyText(grd, now), "Pronto a giocare ✓");
assert.strictEqual(DLU.groupAgg([{ status: "queued", size: 1, done: 0 }]).ready_eta, null, "nessuna ora: null");
console.log("test_downloads_ui: pronto a giocare ok");

// velocità: sparkline (path SVG), campioni per task, storico per giorno e formato GB
assert.strictEqual(DLU.sparkPath([], 80, 18), "", "nessun campione: niente path");
assert.strictEqual(DLU.sparkPath(undefined, 80, 18), "");
const sp = DLU.sparkPath([0, 50, 100], 80, 18);
assert.strictEqual(sp, "M0.0,17.0 L40.0,9.0 L80.0,1.0", "scala 0..max, primo punto in basso a sinistra");
assert.strictEqual(DLU.sparkPath([0, 0, 0], 80, 18), "M0.0,17.0 L40.0,17.0 L80.0,17.0", "tutto zero: linea piatta sul fondo");
assert.strictEqual(DLU.sparkPath([5, 5, 5], 80, 18), "M0.0,1.0 L40.0,1.0 L80.0,1.0", "costante: nessun NaN");
assert.strictEqual(DLU.sparkPath([NaN, 10, "x", -4, null], 80, 18).includes("NaN"), false, "NaN e negativi non finiscono nel path");
assert.strictEqual(DLU.sparkPath([7], 80, 18), "M0.0,1.0 L80.0,1.0", "un solo campione: segmento piatto");
assert.ok(DLU.sparkPath([1, 2], 80, 18, true).endsWith(" L80,18 L0,18 Z"), "area chiusa sul fondo");
const sm2 = new Map();
for (let i = 1; i <= 45; i++) DLU.pushSample(sm2, "t", i, 40);
assert.strictEqual(sm2.get("t").length, 40, "al più 40 campioni");
assert.deepStrictEqual([sm2.get("t")[0], sm2.get("t")[39]], [6, 45], "i più vecchi escono");
assert.deepStrictEqual(DLU.pushSample(sm2, "u", NaN, 40), [0], "valore non valido: 0");
assert.strictEqual(DLU.fmtGB(0), "0 B");
assert.strictEqual(DLU.fmtGB(250 * 1024 ** 2), "250,0 MB", "sotto il GB: MB");
assert.strictEqual(DLU.fmtGB(1.5 * 1024 ** 3), "1,50 GB");
assert.strictEqual(DLU.fmtGB(120 * 1024 ** 3), "120,0 GB");
assert.strictEqual(DLU.fmtGB(null), "—");
assert.strictEqual(DLU.fmtGB(-5), "—");
const bl = DLU.barsLayout([{ day: "2026-10-01", bytes: 100 }, { day: "2026-10-02", bytes: 0 }, { day: "2026-10-03", bytes: NaN }], 60, 30);
assert.strictEqual(bl.max, 100);
assert.deepStrictEqual(bl.bars.map((b) => [b.x, b.y, b.height]), [[3, 0, 30], [23, 30, 0], [43, 30, 0]], "colonne proporzionali, mai NaN");
assert.deepStrictEqual(DLU.barsLayout([], 60, 30), { bars: [], max: 0 });
assert.ok(DLU.barsLayout([{ day: "x", bytes: 1 }], 60, 30).bars.every((b) => !Number.isNaN(b.y + b.height)));
console.log("test_downloads_ui: velocita ok");
