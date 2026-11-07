"use strict";
// Extra del lettore (player.js): preferenze, Continua per profilo, auto-next, oggetto di controllo __pmCtl.
const assert = require("assert"), fs = require("fs"), os = require("os"), path = require("path"), { pathToFileURL } = require("url");
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "plx-"));
fs.copyFileSync(path.join(__dirname, "../extensions/media-locale/logica.js"), path.join(tmpDir, "logica.mjs"));
fs.writeFileSync(path.join(tmpDir, "player.mjs"), fs.readFileSync(path.join(__dirname, "../extensions/media-locale/player.js"), "utf8").replace("./logica.js", "./logica.mjs"));

const memStore = (init = {}) => { const m = { ...init }; return { m, getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: (k) => { delete m[k]; } }; };
const badStore = { getItem() { throw new Error("x"); }, setItem() { throw new Error("x"); } };

import(pathToFileURL(path.join(tmpDir, "player.mjs")).href).then(async (P) => {
  // preferenze
  assert.deepStrictEqual(P.loadPlayerPrefs(memStore()), { autonext: true, skipIntro: false, skipSecs: 85 });
  assert.deepStrictEqual(P.loadPlayerPrefs(badStore), { autonext: true, skipIntro: false, skipSecs: 85 });
  assert.deepStrictEqual(P.loadPlayerPrefs(null), { autonext: true, skipIntro: false, skipSecs: 85 });
  const st = memStore();
  P.savePlayerPrefs({ autonext: false, skipIntro: true, skipSecs: 9999 }, st);
  assert.deepStrictEqual(P.loadPlayerPrefs(st), { autonext: false, skipIntro: true, skipSecs: 600 });
  P.savePlayerPrefs({ skipSecs: 1 }, st);
  assert.strictEqual(P.loadPlayerPrefs(st).skipSecs, 5);
  assert.strictEqual(P.loadPlayerPrefs(st).autonext, false, "il patch tocca solo i campi dati");
  P.savePlayerPrefs({ autonext: true }, badStore); // non lancia
  assert.strictEqual(P.loadPlayerPrefs(memStore({ "gs.pm_skip_secs": "abc" })).skipSecs, 85);

  // logica pura
  assert.deepStrictEqual(P.nextCountdown(5), { secs: 4, done: false });
  assert.deepStrictEqual(P.nextCountdown(1), { secs: 0, done: true });
  assert.strictEqual(P.prefetchDue(29, 0), false);
  assert.strictEqual(P.prefetchDue(30, NaN), true);
  assert.strictEqual(P.prefetchDue(25, 100), true, "25% con durata nota");
  assert.strictEqual(P.prefetchDue(5, 1400), false);

  // Continua per profilo + migrazione
  globalThis.GS = { library: () => ({ profiles: { active: "anna" } }) };
  const item = { id: "e1", source: "media-locale", title: "T" };
  const s1 = memStore({ [P.CONTINUE_KEY]: JSON.stringify([{ id: "old", source: "media-locale", resume_pos: 5, duration: 100 }]) });
  assert.strictEqual(P.continueKey(), `${P.CONTINUE_KEY}:anna`);
  assert.deepStrictEqual(P.loadContinueCache(s1).map((x) => x.id), ["old"], "migrazione nel profilo attivo");
  assert.ok(!(P.CONTINUE_KEY in s1.m) && `${P.CONTINUE_KEY}:anna` in s1.m);
  P.saveContinueCache(item, 20, false, 100, s1);
  globalThis.GS = { library: () => ({ profiles: { active: "bob" } }) };
  assert.deepStrictEqual(P.loadContinueCache(s1), [], "un altro profilo non vede la lista di anna");
  P.saveContinueCache({ id: "b1", source: "media-locale" }, 10, false, 100, s1);
  assert.deepStrictEqual(P.loadContinueCache(s1).map((x) => x.id), ["b1"]);
  P.removeFromContinueCache("b1", s1);
  assert.deepStrictEqual(P.loadContinueCache(s1), []);
  globalThis.GS = { library: () => { throw new Error("x"); } };
  assert.strictEqual(P.continueKey(), `${P.CONTINUE_KEY}:default`);
  delete globalThis.GS;

  // lettore con DOM finto: __pmCtl, pm:state, auto-next
  {
    const mkEl = () => {
      const el = { children: [], style: {}, className: "", innerHTML: "", listeners: {}, hidden: false, dataset: {}, classList: { add() {}, remove() {}, contains: () => false },
        appendChild(c) { this.children.push(c); }, remove() { this.removed = true; }, setAttribute() {}, removeAttribute() {}, scrollIntoView() {},
        addEventListener(t, f) { (this.listeners[t] ||= []).push(f); },
        querySelectorAll() { return []; } };
      const cache = {};
      el.querySelector = (sel) => {
        if (sel === "video" || sel === "audio") return video;
        if (sel === ".pm-nextup") return null;
        return (cache[sel] ||= mkEl());
      };
      return el;
    };
    const fire = (el, t, ev = {}) => (el.listeners[t] || []).forEach((f) => f(ev));
    const video = Object.assign(mkEl(), { paused: true, currentTime: 0, duration: 100, volume: 1, muted: false, playbackRate: 1,
      play() { this.paused = false; return Promise.resolve(); }, pause() { this.paused = true; }, load() {} });
    const body = mkEl(), docL = {};
    global.document = { body, createElement: mkEl, querySelector: () => null,
      documentElement: {}, addEventListener(t, f) { docL[t] = f; }, removeEventListener(t) { delete docL[t]; } };
    const evs = [];
    global.window = { dispatchEvent: (e) => evs.push(e.detail), pywebview: null };
    global.CustomEvent = class { constructor(t, o) { this.type = t; this.detail = o.detail; } };
    const calls = [];
    const gs = { api: async (url, o) => { calls.push(url); return url.includes("play_target") ? { url: "http://x/v.mp4", external: false } : {}; }, toast() {} };
    const eps = [{ id: "a", season: 1, episode: 1, title: "Uno", source: "ricette-web" }, { id: "b", season: 1, episode: 2, title: "Due", source: "ricette-web" }];
    const r = await P.play(gs, eps[0], null, { episodes: eps });
    assert.ok(r && r.browserPlayable, "lettore aperto");
    const c = window.__pmCtl;
    assert.ok(c, "__pmCtl impostato");
    let s = c.getState();
    assert.strictEqual(s.active, true); assert.strictEqual(s.id, "a"); assert.strictEqual(s.hasNext, true); assert.strictEqual(s.hasPrev, false);
    assert.strictEqual(s.paused, true); assert.strictEqual(s.duration, 100); assert.strictEqual(s.skipSecs, 85);
    assert.strictEqual(c.command("volume", 0.5), true); assert.strictEqual(video.volume, 0.5);
    assert.strictEqual(c.command("mute"), true); assert.strictEqual(video.muted, true);
    assert.strictEqual(c.command("seek", 40), true); assert.strictEqual(video.currentTime, 40);
    assert.strictEqual(c.command("jump", -10), true); assert.strictEqual(video.currentTime, 30);
    assert.strictEqual(c.command("prev"), false, "nessun precedente");
    assert.strictEqual(c.command("boh"), false);
    // pre-caricamento: una volta sola
    fire(video, "timeupdate"); fire(video, "timeupdate");
    assert.strictEqual(calls.filter((u) => u.endsWith("/ricette-web/prefetch")).length, 1);
    // fine episodio: scheda con conto alla rovescia, Annulla ferma il timer
    const ticks = []; const realSI = global.setInterval, realCI = global.clearInterval;
    global.setInterval = (f) => { ticks.push(f); return ticks.length; };
    global.clearInterval = (id) => { ticks[id - 1] = null; };
    fire(video, "ended");
    const card = r.overlay.querySelector(".pm-player").children.find((x) => x.className === "pm-nextup");
    assert.ok(card && card.innerHTML.includes("Prossimo episodio tra") && card.innerHTML.includes("Due"));
    assert.strictEqual(ticks.filter(Boolean).length, 1);
    fire(card.querySelector("[data-nu-cancel]"), "click");
    assert.strictEqual(ticks.filter(Boolean).length, 0, "Annulla ferma il conto alla rovescia");
    // chiusura: niente __pmCtl e pm:state {active:false}
    fire(video, "ended");
    assert.strictEqual(ticks.filter(Boolean).length, 1);
    c.command("close");
    assert.strictEqual(ticks.filter(Boolean).length, 0, "chiusura: nessun timer pendente");
    assert.strictEqual(window.__pmCtl, undefined);
    assert.deepStrictEqual(evs[evs.length - 1], { active: false });
    global.setInterval = realSI; global.clearInterval = realCI;
    delete global.document; delete global.window; delete global.CustomEvent;
  }

  console.log("ok");
  process.exit(0); // il lettore finto lascia il suo timer di salvataggio (10 s) acceso: senza uscita esplicita node non termina
}).catch((e) => { console.error(e); process.exit(1); });
