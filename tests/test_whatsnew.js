// Novita' dopo un aggiornamento (whatsnew.js): versioni, stato visto, gruppi da mostrare e ripiego sul changelog.
require("./_i18n_stub");
const assert = require("node:assert/strict");
const path = require("node:path");
const W = require(path.join(__dirname, "..", "pozzo", "app", "static", "whatsnew.js"));

const store = (o = {}) => ({ m: { ...o }, getItem(k) { return k in this.m ? this.m[k] : null; }, setItem(k, v) { this.m[k] = String(v); } });

// confronto di versioni: numerico, non alfabetico
assert.ok(W.cmp("0.18.0", "0.17.6") > 0);
assert.ok(W.cmp("0.17.10", "0.17.9") > 0);
assert.equal(W.cmp("0.18.0", "0.18.0"), 0);
assert.ok(W.cmp("1.0.0-dev", "0.99.99") > 0);

// da quale versione partire
assert.equal(W.since(store(), "0.18.0"), "0.18.0", "primo avvio in assoluto: nessuna finestra");
assert.equal(W.since(store({ "gs.tour": "{}" }), "0.18.0"), W.BASE, "utente esistente senza stato: novita' dopo BASE");
const s = store(); W.saveSeen(s, "0.17.6");
assert.equal(W.since(s, "0.18.0"), "0.17.6");
assert.equal(W.loadSeen(store({ [W.KEY]: "{rotto" })), null, "stato corrotto: ignorato");
assert.equal(W.loadSeen(store({ [W.KEY]: '{"seen":3}' })), null, "versione non testuale: ignorata");

// gruppi curati in (from, to], dal piu' recente
const NEWS = { "0.17.6": [{ id: "a" }], "0.18.0": [{ id: "b" }], "0.19.0": [{ id: "c" }] };
assert.deepEqual(W.pending(NEWS, "0.17.5", "0.18.0").map((g) => g.version), ["0.18.0", "0.17.6"]);
assert.deepEqual(W.pending(NEWS, "0.18.0", "0.18.0"), [], "gia' vista: niente");
assert.deepEqual(W.pending(NEWS, "0.17.6", "0.18.0").map((g) => g.version), ["0.18.0"]);

// ripiego sul changelog: solo «Aggiunto», solo versioni nell'intervallo e non curate; «Non rilasciato» = versione attuale
const MD = `# Changelog

## Non rilasciato

### Aggiunto

- **Novità**: una finestra dopo ogni aggiornamento.

### Corretto

- Un errore che non deve comparire.

## 0.17.6 (2026-11-11)

### Aggiunto

- Nintendo Switch 2: nuova console con l'emulatore Eglantine.

## 0.17.0 (2026-11-07)

### Aggiunto

- Troppo vecchia: fuori intervallo.
`;
const cl = W.fromChangelog(MD, "0.17.5", "0.18.0");
assert.deepEqual(cl.map((g) => g.version), ["0.18.0", "0.17.6"]);
assert.equal(cl[0].items.length, 1, "le voci «Corretto» non sono novita'");
assert.equal(cl[0].items[0].title, "Novità");
assert.equal(cl[0].items[0].text, "una finestra dopo ogni aggiornamento.");
assert.equal(cl[1].items[0].title, "Nintendo Switch 2");
assert.deepEqual(W.fromChangelog(MD, "0.17.5", "0.18.0", ["0.17.6"]).map((g) => g.version), ["0.18.0"], "versioni curate escluse");
assert.deepEqual(W.fromChangelog("", "0.17.5", "0.18.0"), []);
const long = W.fromChangelog(`## 0.18.0\n### Aggiunto\n- ${"x".repeat(300)}\n`, "0.17.0", "0.18.0")[0].items[0];
assert.ok(long.title.length <= 70 && long.title.endsWith("…"), "titolo troncato");

console.log("test_whatsnew: ok");
