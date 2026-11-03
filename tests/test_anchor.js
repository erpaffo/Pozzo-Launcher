"use strict";
// Posizione dei fumetti: lato scelto, limiti della finestra, freccia, bersaglio fuori vista. Eseguito da test_js_harness.py.
const assert = require("assert");
const { place, inView } = require("../pozzo/app/static/anchor.js");

const rect = (l, t, w, h) => ({ left: l, top: t, width: w, height: h, right: l + w, bottom: t + h });
const vp = { w: 1000, h: 700 }, box = { w: 280, h: 100 };

// spazio sotto: va sotto, centrato sul bersaglio, freccia al centro del bersaglio
let p = place(rect(400, 100, 100, 40), box, vp);
assert.strictEqual(p.side, "bottom");
assert.strictEqual(p.top, 152);
assert.strictEqual(p.left, 450 - 140);
assert.strictEqual(p.arrow, 140);

// bersaglio in basso: va sopra
p = place(rect(400, 640, 100, 40), box, vp);
assert.strictEqual(p.side, "top");
assert.strictEqual(p.top, 640 - 12 - 100);

// bersaglio a destra del bordo: non esce dalla finestra e la freccia resta sul bersaglio
p = place(rect(950, 100, 40, 40), box, vp);
assert.ok(p.left + box.w <= vp.w - 8 && p.left >= 8);
assert.strictEqual(p.arrow, 970 - p.left);

// barra laterale stretta in alto-sinistra, poco spazio sotto e sopra: va a destra
p = place(rect(0, 0, 60, 700), box, vp, { prefer: ["right", "bottom"] });
assert.strictEqual(p.side, "right");
assert.strictEqual(p.left, 72);

// non entra da nessuna parte: centrato, senza freccia
p = place(rect(0, 0, 1000, 700), box, vp);
assert.strictEqual(p.side, "center");
assert.strictEqual(p.arrow, null);
assert.strictEqual(p.left, 360);

// finestra piccolissima: mai valori negativi
p = place(rect(10, 10, 20, 20), { w: 300, h: 200 }, { w: 200, h: 150 });
assert.ok(p.left >= 8 && p.top >= 8);

// visibilità del bersaglio
assert.strictEqual(inView(rect(10, 10, 100, 40), vp), true);
assert.strictEqual(inView(rect(10, 800, 100, 40), vp), false, "sotto la finestra");
assert.strictEqual(inView(rect(10, 680, 100, 40), vp), false, "visibile solo per metà altezza ma sotto il 60%");
assert.strictEqual(inView(rect(10, 10, 0, 0), vp), false, "elemento senza dimensioni");
assert.strictEqual(inView(rect(10, 650, 100, 100), vp, 0.4), true);

console.log("test_anchor: ok");
