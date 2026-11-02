const assert = require("node:assert/strict");
const path = require("node:path");
const H = require(path.join(__dirname, "..", "pozzo", "app", "static", "hints.js"));

const mem = (init) => {
  const m = new Map(init ? [[H.KEY, init]] : []);
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
};
const now = 1e12;

// stato assente, corrotto o ostile: valori sicuri
assert.deepEqual(H.load(mem()), { seen: {}, snoozeUntil: 0, off: false });
assert.deepEqual(H.load(mem("{rotto")), { seen: {}, snoozeUntil: 0, off: false });
assert.deepEqual(H.load(mem(JSON.stringify({ seen: { a: true, b: 1 }, snoozeUntil: "x", off: "si" }))), { seen: { a: true }, snoozeUntil: 0, off: false });

// seen: dopo «Ho capito» non si rivede; il reset lo riporta
const st = H.load(mem());
assert.equal(H.canShow(st, "a", now), true);
st.seen.a = true;
assert.equal(H.canShow(st, "a", now), false);
assert.equal(H.canShow(H.resetSeen(st), "a", now), true);

// snooze 7 giorni, poi si riattiva
H.setMode(st, "snooze", now);
assert.equal(H.mode(st, now), "snooze");
assert.equal(H.canShow(st, "a", now + 6 * 86400000), false);
assert.equal(H.canShow(st, "a", now + 7 * 86400000), true);

// off per sempre; tornare su «on» azzera tutto
H.setMode(st, "off", now);
assert.equal(H.canShow(st, "a", now + 999 * 86400000), false);
H.setMode(st, "on", now);
assert.deepEqual([H.mode(st, now), H.canShow(st, "a", now)], ["on", true]);

// salvataggio e storage pieno
const s = mem();
H.save(s, { seen: { z: true }, snoozeUntil: 5, off: true });
assert.deepEqual(H.load(s), { seen: { z: true }, snoozeUntil: 5, off: true });
H.save({ setItem() { throw new Error("pieno"); } }, st);
console.log("test_hints: ok");
