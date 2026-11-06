"use strict";
const { inject } = require("./_i18n_stub");
// Card «Riprendi» in testa alla home Big Picture (stile Classico): `node tests/test_bp_resume.js`.
// Carica layouts/classic/layout.js in un contesto vm con globali finti (il DOM non serve: si controlla l'HTML prodotto).
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "..", "pozzo", "app", "static", "bigpicture", "layouts", "classic", "layout.js"), "utf8");

const flush = () => new Promise((r) => setTimeout(r, 0));
const yesterdayAt = (h, m) => { const d = new Date(); d.setDate(d.getDate() - 1); d.setHours(h, m, 0, 0); return d.getTime(); };

function makeCtx(resumeReply) {
  const ctx = {
    BPLayouts: {}, hueOf: () => 10, esc: (s) => String(s), STORE_SHORT: {}, SHORT: {}, platName: (p) => p.toUpperCase(),
    $: () => ({ style: {} }), document: { querySelectorAll: () => [], querySelector: () => null },
    card: (g, i) => `<div class="card" data-i="${i}">${g.title}</div>`, textCard: (l, s, i) => `<div class="card tile-text" data-i="${i}">${l}</div>`,
    window: {}, renderNav() {}, setBackground() {}, beep() {}, toast() {}, TABS: [], openTab() {}, toggleFav() {},
    console, main: { innerHTML: "" }, calls: { push: [], play: [], detail: [] },
    stackTop: null, api: null,
  };
  ctx.cur = () => ctx.stackTop;
  ctx.push = (s) => ctx.calls.push.push(s);
  ctx.gameScreen = (id) => ({ game: id });
  ctx.playGame = (d) => ctx.calls.play.push(d);
  ctx.detail = async (id) => { ctx.calls.detail.push(id); return ctx.detailReply; };
  ctx.api = async (p) => {
    if (p === "/api/home/resume") { if (resumeReply instanceof Error) throw resumeReply; return resumeReply; }
    throw new Error("api inattesa: " + p);
  };
  inject(ctx); vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

const shelves0 = () => [{ title: "Preferiti", items: [{ id: "g1", title: "Alfa", platform: "snes", cover: false, grp: {} }] }];
const sample = { id: "z1", key: "snes/z1", title: "Zelda", platform: "snes", cover: true, played_secs: 3600,
  hltb_main_secs: null, remaining_secs: 7200, last_played: 0, save: { time: yesterdayAt(22, 14), name: "s" } };

(async () => {
  // 1. con un gioco: Riprendi in testa, focus su di lui, card con tempo rimasto e salvataggio
  let ctx = makeCtx({ items: [sample] });
  let scr = ctx.BPLayouts.classic.shelves(shelves0(), "home");
  ctx.stackTop = scr;
  scr.render(ctx.main);
  await flush();
  assert.strictEqual(scr.shelves[0].title, "Riprendi");
  assert.strictEqual(scr.shelves[0].resume, true);
  assert.strictEqual(scr.shelves.length, 2);
  assert.strictEqual(scr.row, 0);
  assert.strictEqual(scr.cols.length, 2);
  assert.ok(ctx.main.innerHTML.includes("resume-card"), "card Riprendi renderizzata");
  assert.ok(ctx.main.innerHTML.includes("circa 2 h rimaste"));
  assert.ok(ctx.main.innerHTML.includes("salvataggio di ieri 22:14"), ctx.main.innerHTML);
  assert.ok(ctx.main.innerHTML.indexOf("Riprendi") < ctx.main.innerHTML.indexOf("Preferiti"));

  // 2. Invio/A sulla card: stesso percorso di «Gioca» (detail -> playGame)
  ctx.detailReply = { id: "z1", store: undefined, installed: false, emulator: "retroarch" };
  scr.ok();
  await flush();
  assert.deepStrictEqual(ctx.calls.detail, ["z1"]);
  assert.strictEqual(ctx.calls.play.length, 1);
  assert.strictEqual(ctx.calls.play[0], ctx.detailReply);

  // 2b. senza emulatore il gioco non parte: si apre la pagina, come il pulsante disabilitato
  ctx.detailReply = { id: "z1", emulator: null };
  scr.shelves[0].items[0].ok();
  await flush();
  assert.deepStrictEqual(ctx.calls.push, [{ game: "z1" }]);

  // 3. lista vuota: home invariata
  ctx = makeCtx({ items: [] });
  scr = ctx.BPLayouts.classic.shelves(shelves0(), "home");
  ctx.stackTop = scr;
  scr.render(ctx.main);
  await flush();
  assert.strictEqual(scr.shelves.length, 1);
  assert.ok(!ctx.main.innerHTML.includes("resume-card"));

  // 4. fetch fallito: home invariata, nessuna eccezione
  ctx = makeCtx(new Error("rete"));
  scr = ctx.BPLayouts.classic.shelves(shelves0(), "home");
  ctx.stackTop = scr;
  scr.render(ctx.main);
  await flush();
  assert.strictEqual(scr.shelves.length, 1);

  // 5. non home (es. Per te): nessuna richiesta
  ctx = makeCtx({ items: [sample] });
  scr = ctx.BPLayouts.classic.shelves(shelves0(), "foryou");
  ctx.stackTop = scr;
  scr.render(ctx.main);
  await flush();
  assert.strictEqual(scr.shelves.length, 1);

  // 6. focus già più in basso: si resta sulla stessa scheda (indice spostato di uno)
  ctx = makeCtx({ items: [sample] });
  const two = shelves0().concat([{ title: "Altra", items: [{ id: "g2", title: "Beta", platform: "snes", cover: false, grp: {} }, { id: "g3", title: "Gamma", platform: "snes", cover: false, grp: {} }] }]);
  scr = ctx.BPLayouts.classic.shelves(two, "home");
  ctx.stackTop = scr;
  scr.row = 1; scr.cols[1] = 1;
  scr.render(ctx.main);
  await flush();
  assert.strictEqual(scr.row, 2);
  assert.strictEqual(scr.cols[2], 1);
  assert.strictEqual(scr.shelves[2].title, "Altra");

  // 7. testo del salvataggio: oggi / ieri / ms o secondi / data non valida (senza riga)
  const saveLine = async (time) => {
    const c = makeCtx({ items: [{ ...sample, save: { time, name: "s" } }] });
    const s = c.BPLayouts.classic.shelves(shelves0(), "home");
    c.stackTop = s;
    s.render(c.main);
    await flush();
    return c.main.innerHTML;
  };
  const today = new Date(); today.setHours(9, 5, 0, 0);
  assert.ok((await saveLine(today.getTime())).includes("salvataggio di oggi 09:05"));
  assert.ok((await saveLine(Math.floor(yesterdayAt(22, 14) / 1000))).includes("salvataggio di ieri 22:14"));
  assert.ok(!(await saveLine("nonvalida")).includes("salvataggio di"));

  console.log("test_bp_resume: ok");
})().catch((e) => { console.error(e); process.exit(1); });
