"use strict";
// Video snap: ritardo del passaggio del mouse e permesso di movimento: `node tests/test_videosnap.js`.
const assert = require("assert"), path = require("path");
const V = require(path.join(__dirname, "..", "pozzo", "app", "static", "videosnap.js"));

let now = 0, jobs = [], log = [];
const setT = (f, ms) => { jobs.push({ f, at: now + ms }); return jobs.length; };
const clearT = (id) => { if (jobs[id - 1]) jobs[id - 1].f = null; };
const tick = (ms) => { now += ms; jobs.filter((j) => j.f && j.at <= now).forEach((j) => { const f = j.f; j.f = null; f(); }); };
const h = V.createHover({ delay: V.HOVER_MS, setT, clearT, play: (k) => log.push("p" + k), stop: (k) => log.push("s" + k) });

h.enter(1); tick(599); assert.deepStrictEqual(log, []);   // prima di 600 ms niente
tick(1); assert.deepStrictEqual(log, ["p1"]);             // a 600 ms parte
h.enter(2); h.leave(1); tick(300); assert.deepStrictEqual(log, ["p1", "s1"]); // cambiare tessera ferma la prima
h.leave(2); tick(1000); assert.deepStrictEqual(log, ["p1", "s1"]);            // uscire prima del ritardo: mai partito
h.enter(3); tick(600); h.leave(3); assert.deepStrictEqual(log.slice(-2), ["p3", "s3"]);

assert.strictEqual(V.motionOk("normal", true), true);
assert.strictEqual(V.motionOk("reduced", false), false);
assert.strictEqual(V.motionOk("off", false), false);
assert.strictEqual(V.motionOk(undefined, true), false);
assert.strictEqual(V.motionOk(undefined, false), true);
console.log("ok  videosnap");
