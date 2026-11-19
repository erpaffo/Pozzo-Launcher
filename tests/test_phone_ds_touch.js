"use strict";
// Schermo DS sul telefono: dal tocco al punto 0..1 con rotazione (pulsante ⟳) e proporzioni originali (bande nere).
// m.js tocca il DOM al caricamento, quindi si legge solo la funzione. Eseguito con node.
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "../pozzo/app/static/m/m.js"), "utf8");
const m = src.match(/^function dsPoint\([^)]*\) \{[\s\S]*?^\}$/m);
assert.ok(m, "dsPoint non trovata in m.js");
const dsPoint = new Function(`${m[0]}; return dsPoint;`)();
const near = (p, x, y, msg) => assert.ok(Math.abs(p.x - x) < 1e-9 && Math.abs(p.y - y) < 1e-9, `${msg}: ${JSON.stringify(p)}`);

// riquadro 400x300 non ruotato: centro, angolo in alto a sinistra, fuori dal riquadro (limitato)
near(dsPoint(0, 0, 400, 300, 0), 0.5, 0.5, "centro");
near(dsPoint(-200, -150, 400, 300, 0), 0, 0, "angolo in alto a sinistra");
near(dsPoint(500, 0, 400, 300, 0), 1, 0.5, "fuori a destra: limitato a 1");

// ruotato di 90° in senso orario: l'angolo in alto a sinistra del riquadro finisce in alto a destra sullo schermo
// (sullo schermo il riquadro occupa 300 di larghezza e 400 di altezza)
near(dsPoint(150, -200, 400, 300, 90), 0, 0, "90°: alto a sinistra del gioco");
near(dsPoint(-150, 200, 400, 300, 90), 1, 1, "90°: basso a destra del gioco");
near(dsPoint(-150, -200, 400, 300, 90), 0, 1, "90°: basso a sinistra del gioco in alto a sinistra sullo schermo");
near(dsPoint(200, 150, 400, 300, 180), 0, 0, "180°: capovolto");
near(dsPoint(-150, 200, 400, 300, 270), 0, 0, "270°: alto a sinistra del gioco in basso a sinistra");

// proporzioni originali: immagine 256x192 (4:3) in un riquadro 800x300 -> 400x300 al centro, bande nere ai lati
near(dsPoint(-200, -150, 800, 300, 0, 256, 192, true), 0, 0, "contain: angolo dell'immagine");
near(dsPoint(-390, 0, 800, 300, 0, 256, 192, true), 0, 0.5, "contain: tocco sulla banda nera limitato al bordo");
near(dsPoint(-200, -150, 800, 300, 0, 256, 192, false), 0.25, 0, "riempi: si misura sul riquadro intero");
near(dsPoint(-200, -150, 800, 300, 0, 0, 0, true), 0.25, 0, "immagine non ancora arrivata: riquadro intero");

console.log("test_phone_ds_touch: ok");
