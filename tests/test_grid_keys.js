"use strict";
// Navigazione con le frecce nella griglia desktop: `node tests/test_grid_keys.js`.
// Esegue davvero grid.js in un contesto vm con un DOM finto: si controllano la tabella di nextIndex, il fuoco
// dopo lo scorrimento, il tabindex a scelta unica (roving) e le scorciatoie che devono restare al browser.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "..", "pozzo", "app", "static", "js", "grid.js"), "utf8");

function makeCtx(rows) {
  const handlers = {};
  const scroller = { scrollTop: 0, clientHeight: 220, clientWidth: 1000 };
  const layer = { addEventListener: (t, f) => { handlers[t] = f; }, appendChild() {} };
  const els = { "#grid-scroll": scroller, "#grid-layer": layer, "#grid-sizer": { style: {} }, "#popover": { hidden: true } };
  const ctx = {
    console, esc: (s) => String(s), setTimeout: () => 0, clearTimeout() {}, requestAnimationFrame: () => 0,
    $: (sel) => els[sel] || { style: {}, hidden: true },
    document: {
      querySelector: () => null,
      createElement: () => ({ style: {}, dataset: {}, innerHTML: "", className: "" }),
    },
    focused: null, focusedEl: null, removed: [],
  };
  ctx.S = { rows, nodes: new Map(), cols: 3, th: 100, gap: 10, pad: 0, items: [], detail: null, total: 0 };
  ctx.box = scroller;
  ctx.window = ctx; // videosnap.js pubblica GSVideo su window
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "pozzo", "app", "static", "videosnap.js"), "utf8"), ctx); // grid.js usa GSVideo
  vm.runInContext(src, ctx);
  // la tessera vera (copertina, badge) non serve: la sostituisce un elemento minimo con fuoco registrato
  ctx.tileEl = (g) => ({
    dataset: { id: String(g.id) }, style: {}, tabIndex: -1,
    focus() { ctx.focused = this.dataset.id; ctx.focusedEl = this; },
    closest(sel) { return sel === ".tile[data-id]" ? this : null; },
    querySelector: () => null,
    remove() { ctx.removed.push(this.dataset.id); },
  });
  ctx.keydown = handlers.keydown;
  ctx.focusin = handlers.focusin;
  return ctx;
}

/** Righe come le costruisce layout(): colonne `cols`, altezza 100, intervallo 10, da 16 px in giu'. */
function buildRows(ids, cols, sectionStarts = []) {
  const rows = [];
  let y = 16, col = 0;
  ids.forEach((id, i) => {
    if (i === 0 || sectionStarts.includes(i)) {
      if (i > 0) { rows.push({ type: "h", y, h: 44, label: "S", count: 1 }); y += 56; } // intestazione di sezione
      col = 0; // una sezione inizia sempre una riga nuova
    }
    if (col === 0) { rows.push({ type: "t", y, h: 100, items: [] }); y += 110; }
    rows[rows.length - 1].items.push({ id, title: "t" + id });
    col = (col + 1) % cols;
  });
  return rows;
}

const press = (ctx, key, o = {}) => {
  const ev = { key, ctrlKey: !!o.ctrl, shiftKey: !!o.shift, altKey: !!o.alt, metaKey: false, defaultPrevented: false,
    target: o.target || ctx.focusedEl, preventDefault() { this.defaultPrevented = true; } };
  ctx.keydown(ev);
  return ev;
};

// 1. tabella pura, griglia piatta: 10 elementi, 3 per riga (righe 0-2, 3-5, 6-8, 9)
{
  const ctx = makeCtx([]);
  const n = (k, i, ctrl = false, rpp = 2) => ctx.nextIndex(k, i, 3, 10, rpp, ctrl);
  assert.strictEqual(n("ArrowRight", 0), 1);
  assert.strictEqual(n("ArrowRight", 9), 9);
  assert.strictEqual(n("ArrowLeft", 0), 0);
  assert.strictEqual(n("ArrowLeft", 5), 4);
  assert.strictEqual(n("ArrowDown", 1), 4);
  assert.strictEqual(n("ArrowDown", 7), 9, "riga corta: si ferma all'ultimo elemento");
  assert.strictEqual(n("ArrowUp", 4), 1);
  assert.strictEqual(n("ArrowUp", 1), 1, "prima riga: resta dov'e'");
  assert.strictEqual(n("PageDown", 0), 6, "una schermata = 2 righe");
  assert.strictEqual(n("PageDown", 6), 9, "oltre la fine: ultimo");
  assert.strictEqual(n("PageUp", 9), 3);
  assert.strictEqual(n("Home", 5), 3, "Home: inizio della riga");
  assert.strictEqual(n("End", 3), 5, "End: fine della riga");
  assert.strictEqual(n("Home", 5, true), 0, "Ctrl+Home: inizio di tutto");
  assert.strictEqual(n("End", 3, true), 9, "Ctrl+End: fine di tutto");
  assert.strictEqual(n("a", 3), null, "tasto non di navigazione");
  assert.strictEqual(ctx.nextIndex("ArrowDown", 0, 3, 0, 2, false), null, "lista vuota");
  assert.strictEqual(ctx.nextIndex("ArrowDown", 0, 1, 3, 2, false), 1, "una colonna");
}

// 2. tabella con sezioni: righe di lunghezza diversa (righe 0:[0,1] 1:[2,3,4] 2:[5,6,7] 3:[8,9])
{
  const ctx = makeCtx([]);
  const starts = [0, 2, 5, 8];
  const n = (k, i, ctrl = false) => ctx.nextIndex(k, i, 3, 10, 2, ctrl, starts);
  assert.strictEqual(n("ArrowDown", 1), 3, "colonna 1 della riga successiva, non l'indice + 3");
  assert.strictEqual(n("ArrowDown", 4), 7);
  assert.strictEqual(n("ArrowDown", 3), 6);
  assert.strictEqual(n("ArrowUp", 9), 6);
  assert.strictEqual(n("ArrowDown", 8), 8, "ultima riga");
  assert.strictEqual(n("Home", 6), 5);
  assert.strictEqual(n("End", 3), 4);
}

// 3. vm con la griglia vera: 30 tessere (id 100..129), 3 per riga, finestra di 220 px (2 righe)
const ids = Array.from({ length: 30 }, (_, i) => 100 + i);
{
  const ctx = makeCtx(buildRows(ids, 3));
  ctx.render();
  // fuoco iniziale sulla prima tessera, come farebbe il Tab
  const first = ctx.S.nodes.get(100); first.focus();
  ctx.focusin({ target: first });
  assert.strictEqual(ctx.S.nodes.get(100).tabIndex, 0);

  const roving = () => [...ctx.S.nodes.values()].filter((el) => el.dataset.id !== undefined);
  const expectRoving = (id) => {
    const tab = roving().filter((el) => el.tabIndex === 0);
    assert.deepStrictEqual(tab.map((el) => el.dataset.id), [String(id)], "una sola tessera tabulabile");
  };
  expectRoving(100);

  // giu' di due righe: la riga 2 (y=236) esce dalla finestra, lo scorrimento la porta in vista
  let ev = press(ctx, "ArrowDown"); press(ctx, "ArrowDown");
  assert.strictEqual(ctx.focused, "106");
  assert.ok(ev.defaultPrevented);
  assert.strictEqual(ctx.box.scrollTop, 336 - 220, "allineata al bordo inferiore");
  expectRoving(106);

  // Ctrl+End: ultima tessera, molto lontana; la finestra viene disegnata da capo
  press(ctx, "End", { ctrl: true });
  assert.strictEqual(ctx.focused, "129");
  assert.strictEqual(ctx.box.scrollTop, 1106 - 220);
  expectRoving(129);

  // Ctrl+Home: torna in cima
  press(ctx, "Home", { ctrl: true });
  assert.strictEqual(ctx.focused, "100");
  assert.strictEqual(ctx.box.scrollTop, 16);
  expectRoving(100);

  // PageDown: due righe in giu'
  press(ctx, "PageDown");
  assert.strictEqual(ctx.focused, "106");
  expectRoving(106);

  // il fuoco resta sull'indice anche se si ridisegna
  ctx.render();
  assert.strictEqual(ctx.focusedEl.dataset.id, "106");
  expectRoving(106);

  // con la rotella la tessera corrente esce dalla finestra: resta corrente e la prima visibile e' tabulabile
  ctx.box.scrollTop = 1000; ctx.render();
  assert.ok(!ctx.S.nodes.has(106), "la tessera corrente non e' disegnata");
  assert.strictEqual(roving().filter((el) => el.tabIndex === 0).length, 1);

  // scorciatoie che non devono essere toccate: Ctrl+freccia, Alt, Shift, controllo fuori dalla griglia
  ctx.box.scrollTop = 0; ctx.render();
  press(ctx, "Home", { ctrl: true });
  const before = ctx.focused;
  for (const o of [{ key: "ArrowRight", alt: true }, { key: "ArrowRight", shift: true }, { key: "ArrowRight", ctrl: true }]) {
    const ev2 = press(ctx, o.key, o);
    assert.ok(!ev2.defaultPrevented, `ignorato: ${JSON.stringify(o)}`);
  }
  assert.strictEqual(ctx.focused, before);
  // dentro un campo della scheda: la freccia resta al campo
  const inner = { dataset: {}, closest: () => ctx.focusedEl };
  assert.ok(!press(ctx, "ArrowRight", { target: inner }).defaultPrevented);
  // dettaglio aperto: la griglia non si muove
  ctx.S.detail = { id: 1 };
  assert.ok(!press(ctx, "ArrowRight").defaultPrevented);
  ctx.S.detail = null;

  // filtro: la lista si accorcia e la tessera corrente viene riportata nei limiti
  press(ctx, "End", { ctrl: true });
  ctx.S.rows = buildRows(ids.slice(0, 4), 3);
  ctx.box.scrollTop = 0; // il browser riporta lo scorrimento nei limiti quando lo spazio si accorcia
  ctx.render();
  assert.strictEqual(roving().filter((el) => el.tabIndex === 0).length, 1);
  press(ctx, "ArrowRight");
  assert.strictEqual(ctx.focused, "103", "clampata all'ultima della lista filtrata");
}

// 4. sezioni: l'intestazione occupa una riga, le frecce su/giu' la saltano
{
  const sectioned = buildRows(ids.slice(0, 8), 3, [3]); // sezione 1: 3 tessere; sezione 2: 5 tessere
  const ctx = makeCtx(sectioned);
  ctx.render();
  ctx.S.nodes.get(100).focus(); ctx.focusin({ target: ctx.S.nodes.get(100) });
  // sezione 1: [100 101 102]; sezione 2: [103 104 105] [106 107]
  press(ctx, "ArrowDown");
  assert.strictEqual(ctx.focused, "103", "la riga sotto e' la prima della sezione 2");
  press(ctx, "ArrowRight"); press(ctx, "ArrowRight"); // 105
  press(ctx, "ArrowDown");
  assert.strictEqual(ctx.focused, "107", "riga corta: colonna 2 non c'e', va all'ultima");
  press(ctx, "ArrowUp");
  assert.strictEqual(ctx.focused, "104", "su dalla riga 2 (colonna 1) alla riga 1");
}

console.log("ok  nextIndex (griglia piatta e con sezioni)");
console.log("ok  focus, scorrimento e tabindex a scelta unica nella griglia");
