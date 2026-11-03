"use strict";
// Evento «game_downloaded» letto da /api/status: avviso una sola volta e apertura del gioco posseduto al posto della voce online. Eseguito da test_js_harness.py.
const assert = require("assert");
const { downloadedPlan, dlRows, dlPick, dlRank, dlSortRows, dlMagnetOf } = require("../pozzo/app/static/js/detail.js");
global.DLU = { isMultiup: (x) => /multiup/.test(x.host || "") };

const ev = { seq: 3, game_id: 77, from_id: 12, title: "Zelda" };
assert.strictEqual(downloadedPlan(null, 0, 12), null, "nessun evento");
assert.strictEqual(downloadedPlan(ev, 3, 12), null, "già annunciato");
const p = downloadedPlan(ev, 2, 12);
assert.strictEqual(p.toast, "«Zelda» scaricato ed estratto: pronto da giocare");
assert.strictEqual(p.open, 77, "scheda aperta sulla voce online: passa al gioco posseduto");
assert.strictEqual(p.seq, 3);
assert.strictEqual(downloadedPlan(ev, 0, 5).open, null, "scheda su un altro gioco: solo l'avviso");
assert.strictEqual(downloadedPlan(ev, 0, null).open, null, "scheda chiusa: solo l'avviso");

// pannello link di un repack PC: magnet, pagina e parti convivono nella stessa riga, i ruoli restano distinti
const rows = dlRows([
  { kind: "game", label: "1337x", provider: "1337x", url: "https://1337x.to/x", host: "1337x.to", role: "page" },
  { kind: "game", label: "1337x", provider: "magnet", url: "magnet:?xt=urn:btih:aa", host: "", role: "magnet" },
  { kind: "game", label: "DataNodes", provider: "datanodes.to", url: "https://datanodes.to/a/1.rar", host: "datanodes.to", role: "direct", part: 1 },
  { kind: "game", label: "DataNodes", provider: "datanodes.to", url: "https://datanodes.to/b/2.rar", host: "datanodes.to", role: "direct", part: 2 },
  { kind: "game", label: "vecchio", provider: "1fichier", url: "https://1fichier.com/x", host: "1fichier.com" },
]);
assert.strictEqual(rows.length, 3, "una riga per etichetta");
assert.strictEqual(rows[2].items[0].role, "download", "senza role resta un download normale");
assert.deepStrictEqual(rows[1].items.map((x) => x.part), [1, 2], "le parti restano nella riga del loro provider");
assert.deepStrictEqual(dlPick({ rows }), ["https://datanodes.to/a/1.rar", "https://datanodes.to/b/2.rar"],
  "«Scarica» prende le parti della fonte migliore, non la pagina né il torrent");
// FuckingFast prima di tutto, poi DataNodes: è quello che fa il pulsante principale
const ff = dlRows([
  { kind: "game", label: "DataNodes", host: "datanodes.to", role: "direct", url: "https://datanodes.to/c" },
  { kind: "game", label: "FuckingFast", host: "fuckingfast.co", role: "direct", url: "https://fuckingfast.co/a#1.rar" },
  { kind: "game", label: "FuckingFast", host: "fuckingfast.co", role: "direct", url: "https://fuckingfast.co/b#2.rar" },
  { kind: "game", label: "Gioco", role: "magnet", url: "magnet:?xt=urn:btih:aa" },
]);
assert.deepStrictEqual(dlPick({ rows: ff }),
  ["https://fuckingfast.co/a#1.rar", "https://fuckingfast.co/b#2.rar"], "FuckingFast per primo");
assert.strictEqual(dlMagnetOf(ff), "magnet:?xt=urn:btih:aa", "il magnet resta per il suo pulsante");
const onlyMag = dlRows([{ kind: "game", label: "Gioco", role: "magnet", url: "magnet:?xt=urn:btih:bb" }]);
assert.deepStrictEqual(dlPick({ rows: onlyMag }), ["magnet:?xt=urn:btih:bb"], "senza file diretti si usa il torrent");
// l'aggiornamento è una riga a parte: «Scarica» prende il gioco, il pulsante «gioco + aggiornamento» tutto
const upd = dlRows([
  { kind: "game", label: "DataNodes", host: "datanodes.to", role: "direct", url: "https://datanodes.to/gioco" },
  { kind: "update", label: "DataNodes", host: "datanodes.to", role: "direct", url: "https://datanodes.to/update" },
]);
assert.deepStrictEqual(dlPick({ rows: upd }, "game"), ["https://datanodes.to/gioco"], "solo il gioco");
assert.deepStrictEqual(dlPick({ rows: upd }), ["https://datanodes.to/gioco", "https://datanodes.to/update"],
  "gioco + aggiornamento");

// ordine delle fonti: torrent per primo, poi FuckingFast, DataNodes, FileKeeper, gli altri
const ranked = [
  { kind: "game", label: "DataNodes", host: "datanodes.to", role: "direct", url: "d" },
  { kind: "game", label: "Altro", host: "esempio.test", role: "paste", url: "p" },
  { kind: "game", label: "FuckingFast", host: "fuckingfast.co", role: "direct", url: "f" },
  { kind: "game", label: "Gioco", host: "", role: "magnet", url: "magnet:?xt=urn:btih:aa" },
  { kind: "game", label: "FileKeeper", host: "filekeeper.net", role: "direct", url: "k" },
];
assert.deepStrictEqual(ranked.map(dlRank), [2, 9, 1, 0, 3], "torrent, poi FuckingFast, DataNodes, FileKeeper, il resto");
assert.strictEqual(dlRank({ role: "paste", provider: "FileKeeper", host: "paste.esempio.test" }), 3,
  "un paste si ordina dal nome del servizio, non dall'host del paste");
const sorted = dlSortRows(dlRows(ranked), []);
assert.deepStrictEqual(sorted.map((r) => r.label), ["Gioco", "FuckingFast", "DataNodes", "FileKeeper", "Altro"],
  "le righe vanno dalla fonte più affidabile alla meno");

// tasto destro su un link: i link di download si copiano, il magnet no; le parti si copiano tutte assieme
global.DLU = { ...global.DLU, copyable: (u) => u.filter((x) => /^https?:\/\//i.test(x)) };
const { linkUrlsOf, DL_PARTS } = require("../pozzo/app/static/js/detail.js");
DL_PARTS.push(["https://a/1.rar", "https://a/2.rar"]);
assert.deepStrictEqual(linkUrlsOf({ dataset: { dl: "https://1fichier.com/x" } }), ["https://1fichier.com/x"]);
assert.deepStrictEqual(linkUrlsOf({ dataset: { dl: "magnet:?xt=urn:btih:aa" } }), [], "il magnet non ha il menu");
assert.deepStrictEqual(linkUrlsOf({ dataset: { dparts: "0" } }), ["https://a/1.rar", "https://a/2.rar"]);
assert.deepStrictEqual(linkUrlsOf({ dataset: { open: "https://nxbrew.net/g" } }), ["https://nxbrew.net/g"]);
console.log("test_detail_downloaded.js: ok");
