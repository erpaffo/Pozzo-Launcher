// Scopri dello store estensioni: Novità, Consigliate, suggerimenti «Per te» (nessun DOM). Esegui: node tests/test_ext_discover_ui.js
const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

(async () => {
  const F = await import(pathToFileURL(path.join(__dirname, "..", "pozzo", "app", "plugins", "estensioni", "frontend.js")).href);
  const x = (id, state = "available", extra = {}) => ({ id, name: id, state, ...extra });
  const catalogo = [
    x("anniversari"), x("calendario-uscite"), x("diario", "installed"), x("pulizia", "update"),
    x("minerva", "available", { featured: true }), x("steamgriddb"), x("statistiche"),
  ];

  // Novità: solo le non installate, più recenti per prime (ultima voce dell'indice = più recente)
  const s = F.scopri(catalogo, {});
  assert.deepEqual(s.novita.map((e) => e.id), ["statistiche", "steamgriddb", "minerva", "calendario-uscite", "anniversari"]);
  assert.deepEqual(F.scopri([], {}).novita, []);

  // Consigliate: solo featured non installate; senza featured la sezione è vuota (nascosta dalla UI)
  assert.deepEqual(s.consigliate.map((e) => e.id), ["minerva"]);
  assert.deepEqual(F.scopri([x("a")], {}).consigliate, []);

  // suggerimenti: regole per id, ordine dell'input, motivazione, niente installate né id sconosciuti
  const sug = F.suggerimenti([x("pulizia"), x("steamgriddb"), x("diario", "installed"), x("sconosciuta"), x("statistiche", "update")], {});
  assert.deepEqual(sug.map((e) => e.id), ["pulizia", "steamgriddb"]); // diario installata, sconosciuta senza regola, update esclusa
  assert.match(sug[0].reason, /giochi/);
  assert.equal(sug[1].reason, "Copertine e artwork ad alta risoluzione per i tuoi giochi");

  // pulizia solo con più di 200 giochi; sconosciuto = vale comunque
  assert.equal(F.suggerimenti([x("pulizia")], { games: 200 }).length, 0);
  assert.equal(F.suggerimenti([x("pulizia")], { games: 201 })[0].reason, "Hai 201 giochi: trova duplicati e titoli dimenticati");
  assert.equal(F.suggerimenti([x("pulizia")], {}).length, 1);

  // minerva: con giochi console nomina la prima; senza console non compare; sconosciuto = generica
  assert.equal(F.suggerimenti([x("minerva")], { consoles: ["ps3", "switch"] })[0].reason, "Hai giochi PS3: importa gli archivi per quella console");
  assert.equal(F.suggerimenti([x("minerva")], { consoles: [] }).length, 0);
  assert.equal(F.suggerimenti([x("minerva")], { consoles: null }).length, 1);

  // calendario-uscite: con lista desideri vuota non compare; con elementi cita il numero
  assert.equal(F.suggerimenti([x("calendario-uscite")], { wishlist: 0 }).length, 0);
  // nuove estensioni: pc-adatto con console emulate, sconti con lista desideri, notizie e recensioni sempre
  assert.equal(F.suggerimenti([x("pc-adatto")], { consoles: ["snes"] })[0].reason, "Hai giochi SNES: scopri se il tuo PC li emula bene");
  assert.equal(F.suggerimenti([x("pc-adatto")], { consoles: [] }).length, 0);
  assert.equal(F.suggerimenti([x("sconti")], { wishlist: 0 }).length, 0);
  assert.equal(F.suggerimenti([x("sconti")], { wishlist: 3 }).length, 1);
  assert.equal(F.suggerimenti([x("notizie"), x("recensioni")], { games: 0, consoles: [], wishlist: 0 }).length, 2);
  assert.equal(F.suggerimenti([x("calendario-uscite")], { wishlist: 3 })[0].reason, "Hai 3 giochi in lista desideri: scopri quando escono");

  // ctx mancante o vuoto non rompe nulla
  assert.deepEqual(F.suggerimenti(null), []);
  assert.deepEqual(F.suggerimenti([x("steamgriddb")], undefined).length, 1);

  console.log("test_ext_discover_ui: ok");
})().catch((e) => { console.error(e); process.exit(1); });
