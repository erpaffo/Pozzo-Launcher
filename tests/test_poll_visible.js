// pollWhileVisible (core.js): niente giri a finestra nascosta, un giro subito al ritorno in vista.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const core = fs.readFileSync(path.join(__dirname, "..", "pozzo", "app", "static", "core.js"), "utf8");
const block = core.slice(core.indexOf("/* poll:start"), core.indexOf("/* poll:end */"));
assert.ok(block.includes("function pollWhileVisible"));
const run = vm.runInNewContext(block + "; pollWhileVisible", {});

const timers = new Map(); let nid = 0, listener = null;
const doc = { hidden: false, addEventListener: (_, f) => { listener = f; } };
const env = { document: doc, setInterval: (f) => { timers.set(++nid, f); return nid; }, clearInterval: (i) => timers.delete(i) };
const tick = () => [...timers.values()].forEach((f) => f());
let n = 0;
run(() => n++, 1000, env);
assert.equal(timers.size, 1); assert.equal(n, 0, "nessun giro all'avvio");
tick(); assert.equal(n, 1);
doc.hidden = true; listener();
assert.equal(timers.size, 0, "nascosta: timer fermo"); tick(); assert.equal(n, 1);
listener(); assert.equal(timers.size, 0);
doc.hidden = false; listener();
assert.equal(timers.size, 1); assert.equal(n, 2, "ritorno in vista: un giro subito");
listener(); assert.equal(timers.size, 1); assert.equal(n, 2, "visibilitychange ripetuto: nessun timer doppio");
// avviata a pagina gia' nascosta: parte solo quando si vede, con un giro di recupero? no: mai stata attiva
doc.hidden = true; timers.clear(); n = 0; listener = null;
run(() => n++, 1000, env); assert.equal(timers.size, 0);
doc.hidden = false; listener(); assert.equal(timers.size, 1); assert.equal(n, 1);
console.log("test_poll_visible: ok");
