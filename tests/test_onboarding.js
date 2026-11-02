const assert = require("node:assert/strict");
const path = require("node:path");

const O = require(path.join(__dirname, "..", "pozzo", "app", "static", "onboarding.js"));

const mem = (init) => {
  const m = new Map(init ? [["gs.onboarding", init]] : []);
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
};

// stato assente, corrotto o ostile: valori sicuri
assert.equal(O.load(mem()).step, 0);
assert.equal(O.load(mem("{rotto")).step, 0);
assert.equal(O.load(mem(JSON.stringify({ step: 99, skipped: [1, "x", 9], stores: [1] }))).step, O.STEPS.length - 1);
assert.deepEqual(O.load(mem(JSON.stringify({ step: 1, skipped: [1, "x", 9] }))).skipped, [1]);
assert.equal(O.load(mem(JSON.stringify({ stores: [1] }))).stores, null);

// ripresa: quello che si salva si ritrova
const s = mem();
O.save(s, { step: 2, roms: "D:\\ROM", stores: { steam: 1 }, theme: "x", experience: "", skipped: [0] });
const r = O.load(s);
assert.deepEqual([r.step, r.roms, r.stores, r.skipped], [2, "D:\\ROM", { steam: true }, [0]]);
O.save({ setItem() { throw new Error("pieno"); } }, r);  // storage pieno: nessuna eccezione

// console: niente doppioni, tetto, input non valido
assert.deepEqual(O.consoles([{ id: "a" }, { id: "a" }, { id: "b" }, null, {}], 2).map((p) => p.id), ["a", "b"]);
assert.deepEqual(O.consoles(undefined), []);

// BIOS
assert.equal(O.biosMissing({ items: [{ required: true, ok: false }] }), true);
assert.equal(O.biosMissing({ items: [{ required: false, ok: false }, { required: true, ok: true }] }), false);
assert.equal(O.biosMissing(null), false);
console.log("test_onboarding: ok");