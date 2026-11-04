"use strict";
// Pulizia libreria, «File identici su disco»: funzioni pure di extensions/pulizia/logica.js. Eseguito con node.
const assert = require("assert");
const path = require("path");
const { pathToFileURL } = require("url");

(async () => {
  const L = await import(pathToFileURL(path.join(__dirname, "..", "extensions", "pulizia", "logica.js")).href);

  assert.strictEqual(L.fmtBytes(0), "0 B");
  assert.strictEqual(L.fmtBytes(512), "512 B");
  assert.strictEqual(L.fmtBytes(1536), "1,5 KB");
  assert.strictEqual(L.fmtBytes(3 * 1024 ** 3), "3,0 GB");
  assert.strictEqual(L.fmtBytes(null), "—");

  assert.strictEqual(L.baseName("C:\\Giochi\\a\\Doom.exe"), "Doom.exe");
  assert.strictEqual(L.baseName("/x/y.iso"), "y.iso");

  const f = (p, extra = {}) => ({ path: p, game: null, region: null, same_volume_as_first: true, is_hardlink: false, ...extra });
  const g = {
    hash: "abc", size: 100, keep: 0,
    files: [f("D:/a/Doom.iso"), f("D:/b/Doom.iso"), f("E:/c/Doom.iso", { same_volume_as_first: false })],
  };
  assert.strictEqual(L.freeable(g), 200, "tenendo la prima: due copie liberano");
  assert.strictEqual(L.freeable(g, 1), 200);
  assert.strictEqual(L.freeable({ ...g, files: [g.files[0], { ...g.files[1], is_hardlink: true }, g.files[2]] }), 100, "hardlink gia' fatto: niente spazio");
  assert.strictEqual(L.freeableTotal([g, g]), 400);

  assert.strictEqual(L.linkable(g, 0), false, "una copia su un altro disco");
  assert.strictEqual(L.linkable({ ...g, files: g.files.slice(0, 2) }, 1), true);
  // con «dev» si confronta con la copia scelta, non con la prima
  const gd = { ...g, files: [f("D:/a", { dev: 1 }), f("E:/b", { dev: 2, same_volume_as_first: false }), f("E:/c", { dev: 2, same_volume_as_first: false })] };
  assert.strictEqual(L.linkable(gd, 0), false);
  assert.strictEqual(L.linkable({ ...gd, files: gd.files.slice(1) }, 0), true, "due copie sullo stesso disco, diverso dalla prima");

  const conf = L.confirmText("delete", g, 0);
  assert.ok(conf.startsWith("Eliminare definitivamente 2 copie:") && conf.includes("E:/c/Doom.iso") && conf.includes("Si tiene:\n  D:/a/Doom.iso"));
  assert.ok(L.confirmText("hardlink", g, 0).startsWith("Sostituire con collegamenti (hardlink) 2 copie:"));

  const after = L.afterApply(g, "delete", [{ path: "D:/b/Doom.iso", ok: true }, { path: "E:/c/Doom.iso", ok: false }]);
  assert.deepStrictEqual(after.files.map((x) => x.path), ["D:/a/Doom.iso", "E:/c/Doom.iso"]);
  assert.strictEqual(after.keep, 0);
  const linked = L.afterApply(g, "hardlink", [{ path: "D:/b/Doom.iso", ok: true }]);
  assert.strictEqual(linked.files[1].is_hardlink, true);
  assert.strictEqual(L.afterApply(g.files.length && { ...g, files: g.files.slice(0, 2) }, "delete", [{ path: "D:/b/Doom.iso", ok: true }]), null, "resta una sola copia: gruppo chiuso");

  console.log("test_pulizia_dupfiles_ui: ok");
})().catch((e) => { console.error(e); process.exit(1); });
