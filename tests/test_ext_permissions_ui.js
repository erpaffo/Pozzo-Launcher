// Permessi dello store estensioni: voci, sensibili, conferma prima di installare (nessun DOM). Esegui: node tests/test_ext_permissions_ui.js
const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

(async () => {
  const F = await import(pathToFileURL(path.join(__dirname, "..", "pozzo", "app", "plugins", "estensioni", "frontend.js")).href);

  // etichette italiane, fallback sull'id grezzo, sensibili segnati
  const voci = F.permessiVoci({
    permissions: ["rete:api.rawg.io", "scrittura:libreria", "file:C:/x", "avvio:programmi", "filemanager:y"],
    permissions_labels: [{ id: "rete:api.rawg.io", label: "Rete: api.rawg.io" }, { id: "bad" }, null],
  });
  assert.deepEqual(voci.map((v) => v.label), ["Rete: api.rawg.io", "scrittura:libreria", "file:C:/x", "avvio:programmi", "filemanager:y"]);
  assert.deepEqual(voci.map((v) => v.sensibile), [false, true, true, true, false]);
  assert.deepEqual(F.permessiVoci({}), []);
  // schema reale: libreria:scrittura e file:* sensibili, rete:* (qualsiasi sito) sensibile, letture no
  assert.deepEqual(F.permessiVoci({ permissions: ["libreria:scrittura", "libreria:lettura", "file:lettura", "rete:*", "impostazioni", "notifiche"] })
    .map((v) => v.sensibile), [true, false, true, true, false, false]);
  assert.deepEqual(F.permessiVoci({ permissions: ["libreria:lettura"], permissions_labels: "rotto" })[0].label, "libreria:lettura");

  // nessuna conferma se non ci sono permessi nuovi
  assert.equal(F.permessiConferma({ permissions: [] }), null);
  assert.equal(F.permessiConferma({ state: "available", permissions: ["libreria:lettura"] }).voci.length, 1);
  assert.deepEqual(F.permessiConferma({ permissions_unknown: true }), { nonDichiarati: true, voci: [] });

  // aggiornamento: solo i permessi nuovi, se si conoscono quelli installati; altrimenti tutti
  const up = { state: "update", permissions: ["rete:a", "scrittura:b"] };
  assert.deepEqual(F.permessiConferma({ ...up, installed_permissions: ["rete:a"] }).voci.map((v) => v.id), ["scrittura:b"]);
  assert.equal(F.permessiConferma({ ...up, installed_permissions: ["rete:a", "scrittura:b"] }), null);
  assert.deepEqual(F.permessiConferma(up).voci.map((v) => v.id), ["rete:a", "scrittura:b"]);

  console.log("test_ext_permissions_ui: ok");
})().catch((e) => { console.error(e); process.exit(1); });
