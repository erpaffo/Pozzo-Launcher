"use strict";
// Funzioni pure di extensions/media-locale/remote.js (ESM, importato via copia .mjs).
const assert = require("assert"), fs = require("fs"), os = require("os"), path = require("path"), { pathToFileURL } = require("url");
const tmp = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "mr-")), "remote.mjs");
fs.copyFileSync(path.join(__dirname, "../extensions/media-locale/remote.js"), tmp);
import(pathToFileURL(tmp).href).then((R) => {
  assert.deepStrictEqual([0, 1, 2, 3, 4, 9, 20].map(R.nextPollDelay), [0, 1000, 2000, 4000, 8000, 30000, 30000]);
  const a = { active: true, id: "x", paused: false, episode: 1, season: 1, pos: 5 };
  assert.strictEqual(R.shouldSendState(null, a, 0, 1), true);                         // primo stato
  assert.strictEqual(R.shouldSendState(a, { ...a, pos: 6 }, 1000, 1500), false);      // meno di 1 s
  assert.strictEqual(R.shouldSendState(a, { ...a, pos: 6 }, 1000, 2000), true);       // trascorso 1 s
  assert.strictEqual(R.shouldSendState(a, { ...a, paused: true }, 1000, 1100), true); // pausa: subito
  assert.strictEqual(R.shouldSendState(a, { ...a, episode: 2 }, 1000, 1100), true);   // episodio: subito
  assert.strictEqual(R.shouldSendState(a, { active: false }, 1000, 1100), true);      // chiusura
  assert.strictEqual(R.shouldSendState({ active: false }, { active: false }, 0, 9e9), false);
  console.log("test_media_remote.js: ok");
});
