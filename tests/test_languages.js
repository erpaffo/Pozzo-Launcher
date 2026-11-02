const assert = require("node:assert/strict");
const Languages = require("../pozzo/app/static/languages.js");

assert.deepEqual(Languages.codes("Metroid Prime (en, it, es, fr)"), ["en", "it", "es", "fr"]);
assert.deepEqual(Languages.codes("Gioco [EN + IT]"), ["en", "it"]);
assert.deepEqual(Languages.codes("Gioco (pt_BR)"), ["pt-BR"]);
assert.deepEqual(Languages.codes("Gioco (ita) (USA)"), ["it"]);
assert.deepEqual(Languages.codes("Gioco (USA, Europe)"), ["en"]);
assert.deepEqual(Languages.codes("Gioco senza tag"), ["en"]);
assert.deepEqual(Languages.labels("Gioco (en, it)"), ["Inglese", "Italiano"]);
console.log("ok");
