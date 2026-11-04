"use strict";
// coverTransition (js/detail.js): un solo elemento con view-transition-name, pulito a fine transizione; fallback senza API/motion.
const assert = require("assert");
const { coverTransition } = require("../pozzo/app/static/js/detail.js");

const el = (tile) => ({ style: {}, isConnected: true, closest: () => tile, classList: { add() {}, remove() {} } });
function setup({ api = true, motion = "normal", throwing = false } = {}) {
  const tile = { classList: { add() {}, remove() {} } };
  const a = el(tile), b = el(tile);
  const cls = new Set();
  const log = [];
  let fin;
  const finished = new Promise((r) => { fin = r; });
  global.document = {
    documentElement: { dataset: { motion }, classList: { add: (c) => cls.add(c), remove: (c) => cls.delete(c) } },
    ...(api ? { startViewTransition(cb) {
      if (throwing) throw new Error("x");
      const done = Promise.resolve().then(cb);
      return { updateCallbackDone: done, finished: done.then(() => finished) };
    } } : {}),
  };
  const names = () => [a, b].filter((e) => e.style.viewTransitionName === "cover").length;
  return { a, b, cls, log, names, fin };
}

(async () => {
  let t = setup();
  const p = coverTransition(t.a, () => t.log.push("upd"), () => t.b);
  assert.strictEqual(t.a.style.viewTransitionName, "cover", "nome sulla tessera prima");
  await p;
  assert.deepStrictEqual(t.log, ["upd"]);
  assert.strictEqual(t.names(), 1);
  assert.strictEqual(t.b.style.viewTransitionName, "cover", "dopo l'update il nome passa alla scheda");
  assert.strictEqual(t.a.style.viewTransitionName, "");
  assert.ok(t.cls.has("vt-cover"));
  t.fin(); await new Promise((r) => setTimeout(r, 5));
  assert.strictEqual(t.names(), 0, "nomi tolti a fine transizione");
  assert.ok(!t.cls.has("vt-cover"));

  for (const o of [{ api: false }, { motion: "reduced" }, { motion: "off" }, { throwing: true }]) {
    t = setup(o);
    await coverTransition(t.a, () => t.log.push("upd"), () => t.b);
    assert.deepStrictEqual(t.log, ["upd"], "fallback: update eseguito una volta " + JSON.stringify(o));
    assert.strictEqual(t.names(), 0);
  }
  t = setup();
  await coverTransition(null, () => t.log.push("upd"), () => t.b);
  assert.deepStrictEqual(t.log, ["upd"], "tessera assente: nessuna transizione");
  console.log("ok");
})();
