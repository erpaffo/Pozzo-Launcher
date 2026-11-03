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

// snooze 1 giorno e 7 giorni, poi si riattiva
H.setMode(st, "day", now);
assert.equal(H.mode(st, now), "day");
assert.equal(H.canShow(st, "a", now + 86400000 - 1), false);
assert.equal(H.canShow(st, "a", now + 86400000), true);
H.setMode(st, "week", now);
assert.equal(H.mode(st, now), "week");
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

// --- motore con ambiente finto ---
const anchor = require(path.join(__dirname, "..", "pozzo", "app", "static", "anchor.js"));
function env(init) {
  const e = { t: 1e12, els: {}, blocked: false, log: [], store: mem(init), open: null, pos: null };
  e.d = {
    store: e.store, now: () => e.t, rnd: () => 0,
    query: (s) => e.els[s] || null, rect: (el) => el, vp: () => ({ w: 1000, h: 800 }),
    inView: anchor.inView, place: (r, size, vp) => { e.placed = [r, size, vp]; return anchor.place(r, size, vp); },
    blocked: () => e.blocked,
    ui: { open: (h, t) => { e.open = h.id; e.text = t; }, measure: () => ({ w: 300, h: 100 }), apply: (p) => { e.pos = p; }, close: () => { e.open = null; } },
  };
  e.box = (l, t) => ({ left: l, top: t, right: l + 100, bottom: t + 40, width: 100, height: 40 });
  e.E = H.engine(e.d);
  return e;
}
const seenOf = (e) => Object.keys(H.load(e.store).seen).sort();

// visto al momento della comparsa; non prima di 10 s; poi mai ripetuto
let e = env();
e.els["#a"] = e.box(100, 100); e.els["#b"] = e.box(300, 100); e.els["#c"] = e.box(500, 100);
e.E.register({ id: "a", target: "#a", text: "A", priority: 9 });
e.E.register({ id: "b", target: "#b", text: () => "B", priority: 1 });
e.E.register({ id: "c", target: "#c", text: "C", priority: 1 });
e.t += 9000; e.E.tick(); assert.equal(e.open, null);
e.t += 1000; e.E.tick(); assert.equal(e.open, "a");
assert.deepEqual(seenOf(e), ["a"]);
// posizione calcolata da GSAnchor (sotto il bersaglio, con la misura del fumetto)
assert.deepEqual(e.placed[1], { w: 300, h: 100 });
assert.deepEqual(e.pos, anchor.place(e.els["#a"], { w: 300, h: 100 }, { w: 1000, h: 800 }));
e.E.close(); assert.deepEqual(seenOf(e), ["a"]);
// secondo: solo dopo 60 s, scelto tra i non visti (a escluso); poi massimo 2 per sessione
e.t += 59000; e.E.tick(); assert.equal(e.open, null);
e.t += 1000; e.E.tick(); assert.equal(e.open, "b");
e.E.close();
e.t += 999999; e.E.tick(); assert.equal(e.open, null);
assert.deepEqual(seenOf(e), ["a", "b"]);
// nuova sessione: restano solo i non visti; finiti tutti, niente più
e = env(e.store.getItem(H.KEY)); e.els["#c"] = e.box(500, 100);
e.E.register({ id: "a", target: "#a", text: "A" }); e.E.register({ id: "c", target: "#c", text: "C" });
e.t += 10000; e.E.tick(); assert.equal(e.open, "c"); e.E.close();
e.t += 60000; e.E.tick(); assert.equal(e.open, null);
e = env(e.store.getItem(H.KEY)); e.E.register({ id: "c", target: "#c", text: "C" }); e.els["#c"] = e.box(5, 5);
e.t += 10000; e.E.tick(); assert.equal(e.open, null);
// «Rivedi tutti»
e.E.resetSeen(); e.E.tick(); assert.equal(e.open, "c");

// bersaglio assente/fuori vista/when falso: saltato senza consumare
e = env();
e.els["#out"] = e.box(2000, 100); e.els["#ok"] = e.box(100, 100);
e.E.register({ id: "x", target: "#nope", text: "x", priority: 9 });
e.E.register({ id: "y", target: "#out", text: "y", priority: 8 });
e.E.register({ id: "w", target: "#ok", text: "w", priority: 7, when: () => false });
e.E.register({ id: "z", target: ["#nope", "#ok"], text: "z", priority: 1 });
e.t += 10000; e.E.tick(); assert.equal(e.open, "z");
assert.deepEqual(seenOf(e), ["z"]);
// il bersaglio sparisce mentre è aperto: si chiude senza consumare
delete e.els["#ok"]; e.E.relayout();
assert.equal(e.open, null); assert.deepEqual(seenOf(e), []);
// ...e non conta nel massimo per sessione
e.els["#ok"] = e.box(100, 100); e.E.tick(); assert.equal(e.open, "z");
// esce dalla vista in resize/scroll
e.els["#ok"] = e.box(5000, 0); e.E.relayout(); assert.equal(e.open, null); assert.deepEqual(seenOf(e), []);

// livello sopra la pagina: rimanda
e = env(); e.els["#a"] = e.box(1, 1); e.E.register({ id: "a", target: "#a", text: "A" });
e.blocked = true; e.t += 10000; e.E.tick(); assert.equal(e.open, null);
e.blocked = false; e.E.tick(); assert.equal(e.open, "a");

// già scoperto (done): segnato visto in silenzio
e = env(); e.els["#a"] = e.box(1, 1); e.els["#used"] = e.box(1, 1);
e.E.register({ id: "a", target: "#a", text: "A", done: "#used" }); e.t += 10000; e.E.tick();
assert.equal(e.open, null); assert.deepEqual(seenOf(e), ["a"]);

// snooze 1 giorno / 7 giorni / sempre, e riattivazione (il fumetto aperto si chiude restando visto)
for (const [m, ms] of [["day", 86400000], ["week", 7 * 86400000], ["off", 1e13]]) {
  e = env(); e.els["#a"] = e.box(1, 1); e.E.register({ id: "a", target: "#a", text: "A" });
  e.t += 10000; e.E.tick(); assert.equal(e.open, "a");
  e.E.setMode(m); assert.equal(e.open, null); assert.equal(e.E.mode(), m); assert.deepEqual(seenOf(e), ["a"]);
  e.E.resetSeen(); e.t += 120000; e.E.tick(); assert.equal(e.open, null);
  if (m !== "off") { e.t += ms; e.E.tick(); assert.equal(e.open, "a"); }
  e.E.setMode("on"); assert.equal(e.E.mode(), "on");
}

// tour: chiude senza consumare e sospende
e = env(); e.els["#a"] = e.box(1, 1); e.els["#b"] = e.box(1, 1);
e.E.register({ id: "a", target: "#a", text: "A" }); e.E.register({ id: "b", target: "#b", text: "B" });
e.t += 10000; e.E.tick(); assert.ok(e.open);
e.E.pause(); assert.equal(e.open, null); assert.deepEqual(seenOf(e), []);
e.t += 999999; e.E.tick(); assert.equal(e.open, null);

// show(id): subito, anche se già visto, ma non con un livello sopra
e = env(); e.els["#a"] = e.box(1, 1); e.E.register({ id: "a", target: "#a", text: "A" });
e.blocked = true; assert.equal(e.E.show("a"), false); e.blocked = false; assert.equal(e.E.show("a"), true);

console.log("test_hints: ok");
