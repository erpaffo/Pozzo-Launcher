"use strict";
// Helper puri di extensions/notizie/logica.js (ESM, importato via copia .mjs).
const assert = require("assert"), fs = require("fs"), os = require("os"), path = require("path"), { pathToFileURL } = require("url");
const tmp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "nz-")), "logica.mjs");
fs.copyFileSync(path.join(__dirname, "../extensions/notizie/logica.js"), tmp);
import(pathToFileURL(tmp).href).then((L) => {
  assert.strictEqual(L.fold("Pokémon: Rosso!"), "pokemon rosso");
  const now = Date.parse("2026-01-10T12:00:00Z");
  assert.strictEqual(L.relDate("2026-01-10T11:59:50Z", now), "adesso");
  assert.strictEqual(L.relDate("2026-01-10T11:59:00Z", now), "1 minuto fa");
  assert.strictEqual(L.relDate("2026-01-10T09:00:00Z", now), "3 ore fa");
  assert.strictEqual(L.relDate("2026-01-08T12:00:00Z", now), "2 giorni fa");
  assert.strictEqual(L.relDate("boh", now), "");
  assert.strictEqual(L.safeUrl("javascript:alert(1)"), "");
  assert.strictEqual(L.safeUrl("https://a.it/x"), "https://a.it/x");
  assert.ok(L.validUrl("http://a.it") && !L.validUrl("ftp://a.it") && !L.validUrl("x"));
  const lib = { games: [{ title: "Zelda: Tears of the Kingdom" }, { title: "Up" }], plats: new Map([["s", { name: "Nintendo Switch" }]]) };
  const m = L.matcher(L.buildSets(lib));
  assert.ok(m({ title: "Zelda Tears of the Kingdom, nuova patch", summary: "" }));
  assert.ok(m({ title: "x", summary: "Esce su Nintendo Switch" }));
  assert.ok(!m({ title: "Up and running", summary: "" }));   // titolo < 4 caratteri ignorato
  assert.ok(!m({ title: "Altro", summary: "niente" }));
  const it = [{ kind: "annuncio" }, { kind: "patch" }, { kind: "uscita" }];
  assert.strictEqual(L.upcoming(it).length, 2);
  console.log("ok");
}).catch((e) => { console.error(e); process.exit(1); });
