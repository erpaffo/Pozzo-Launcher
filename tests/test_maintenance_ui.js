// Formattazione del rapporto di manutenzione (N3): `node tests/test_maintenance_ui.js`.
// Estrae il blocco puro da js/settings.js (esc e fmtSize da core.js) e lo esegue in un contesto isolato.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const root = path.join(__dirname, "..", "pozzo", "app", "static");
const settings = fs.readFileSync(path.join(root, "js", "settings.js"), "utf8");
const core = fs.readFileSync(path.join(root, "core.js"), "utf8");
const block = settings.match(/\/\* pure:maintenance:start[\s\S]*?\*\/([\s\S]*?)\/\* pure:maintenance:end \*\//);
assert(block, "blocco pure:maintenance non trovato");
const esc = core.match(/const esc = [^\r\n]*\r?\n/);
const fmtSize = core.match(/function fmtSize[\s\S]*?\n\}\r?\n/);
assert(esc && fmtSize, "esc o fmtSize non trovati in core.js");

const ctx = {};
vm.createContext(ctx);
vm.runInContext(esc[0] + fmtSize[0] + block[1]
  + "\nthis.h = { maintList, maintDiffLines, maintRenderReport };", ctx);
const { maintList, maintDiffLines, maintRenderReport } = ctx.h;
const count = (s, re) => (s.match(re) || []).length;

// testo escapato: niente tag iniettati
const evil = maintList([{ game: "<img src=x onerror=alert(1)>", path: "C:\\a&b" }]);
assert(!evil.includes("<img"), "nome non escapato");
assert(evil.includes("&lt;img") && evil.includes("a&amp;b"), "escape incompleto");

// elenco troncato a 20 + "e altre N"
const many = Array.from({ length: 25 }, (_, i) => `ROM ${i}`);
const long = maintList(many);
assert.strictEqual(count(long, /<li/g), 21, "20 voci + una riga «e altre»");
assert(long.includes("e altre 5"), "conteggio resto errato");
assert(maintList([]).includes("Nessuno."), "elenco vuoto");

// diff: rosso = peggio, verde = meglio
const lines = maintDiffLines({
  rom_nuove_mancanti: [{ game: "A" }, { game: "B" }], rom_ripristinate: ["C"], bios_nuovi_invalidi: [],
  covers_delta: -3, freeable_delta: 2048, peggiora: true,
});
// JSON: gli array creati nel contesto vm hanno un altro prototipo, deepStrictEqual li rifiuterebbe
assert.deepStrictEqual(JSON.parse(JSON.stringify(lines.map((l) => l.cls))),
  ["maint-bad", "maint-good", "maint-good", "maint-bad"], "classi diff errate");
assert.strictEqual(lines[0].text, "2 ROM nuove mancanti: A, B");
assert.strictEqual(lines[2].text, "Copertine mancanti: -3");
assert.strictEqual(lines[3].text, "Spazio liberabile: +2,00 KB");
assert.strictEqual(maintDiffLines(null).length, 0, "senza diff nessuna riga");

// rapporto completo: passi, diff vuoto, spazio non calcolato
const html = maintRenderReport({
  steps: [{ nome: "Scansione <b>", ok: true }, { nome: "Copertine", ok: false, note: "timeout" }],
  rom_missing: [], bios_invalid: ["scph1001.bin"], covers_missing: 4, freeable_bytes: null,
}, { rom_nuove_mancanti: [], rom_ripristinate: [], bios_nuovi_invalidi: [], covers_delta: 0, freeable_delta: null });
assert(html.includes("maint-good") && html.includes("maint-bad"), "passi ✓/✗ mancanti");
assert(html.includes("✓") && html.includes("✗"), "glifi ✓/✗ mancanti");
assert(!html.includes("<b>") && html.includes("Scansione &lt;b&gt;"), "nome del passo non escapato");
assert(html.includes("non calcolato"), "spazio null");
assert(html.includes("Nessuna differenza."), "diff senza variazioni");
assert(html.includes("scph1001.bin"), "BIOS non validi");

console.log("test_maintenance_ui: ok");
