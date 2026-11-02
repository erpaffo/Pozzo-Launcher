// Tabella errore -> azione (C2): `node tests/test_action_errors.js`. Legge il blocco @errors di js/settings.js.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "..", "pozzo", "app", "static", "js", "settings.js"), "utf8");
const block = src.match(/\/\* @errors-begin[\s\S]*?@errors-end \*\//);
assert(block, "blocco @errors-begin/@errors-end non trovato");
const opened = [];
const ctx = { openSettings: (t) => opened.push(t) };
vm.createContext(ctx);
vm.runInContext(block[0] + "\nthis.ERROR_ACTIONS = ERROR_ACTIONS; this.errorCode = errorCode;", ctx);
const { ERROR_ACTIONS, errorCode } = ctx;

assert.strictEqual(errorCode({ code: "emulator_missing", message: "x" }), "emulator_missing");
assert.strictEqual(errorCode({ code: "sconosciuto", message: "Nessun emulatore configurato per GBA. Aggiungi" }), "emulator_missing");
assert.strictEqual(errorCode(new Error("File del gioco non trovato (disco scollegato?)")), "rom_folder_missing");
assert.strictEqual(errorCode(new Error("Nessun file avviabile nella cartella D:/x")), "rom_folder_missing");
assert.strictEqual(errorCode(new Error("altro")), "");
assert.strictEqual(errorCode(null), "");

ERROR_ACTIONS.emulator_missing.run();
ERROR_ACTIONS.rom_folder_missing.run();
assert.deepStrictEqual(opened, ["emu", "scan"]);
for (const [code, a] of Object.entries(ERROR_ACTIONS)) assert(a.text && a.label && typeof a.run === "function", code);
console.log("ok  tabella errori -> azione");
