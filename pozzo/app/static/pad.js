"use strict";
/* Controller, tastiera, suoni e lettura vocale condivisi da Big Picture e dalle esperienze desktop.
 * Pad.start({ input }) legge il pad e chiama input("left" | "a" | "lb" ...); i tasti da tastiera
 * si traducono con Pad.keyAction(e). Il resto (schermate, fuoco) e' di chi lo usa. */

const Pad = {
  kind: "xbox", sound: store.get("bpSound", true), talk: store.get("bpTalk", false),
  tones: { move: 520, ok: 880, back: 330, err: 180 }, // uno stile TV puo' sostituirli
};
const PAD_GLYPHS = {
  xbox: { a: "A", b: "B", x: "X", y: "Y", lb: "LB", rb: "RB", lt: "LT", rt: "RT", back: "View", start: "Menu" },
  ps: { a: "✕", b: "○", x: "□", y: "△", lb: "L1", rb: "R1", lt: "L2", rt: "R2", back: "Share", start: "Options" },
};
function glyph(k) {
  const t = PAD_GLYPHS[Pad.kind][k];
  return `<span class="btn-glyph ${k}${t.length > 1 ? " rect" : ""}">${esc(t)}</span>`;
}

/** Legge un messaggio con il lettore di schermo (regione aria-live, nessun effetto visivo). */
function announce(text) {
  if (!Pad.talk || !text) return;
  const live = $("#bp-live");
  if (!live) return;
  live.textContent = ""; // svuotare prima: alcuni lettori ignorano testi identici consecutivi
  setTimeout(() => { live.textContent = String(text).slice(0, 300); }, 60);
}

let actx = null;
function beep(kind) {
  if (kind === "move") window.Dualsense?.tick();
  if (!Pad.sound) return;
  try {
    actx = actx || new AudioContext();
    const o = actx.createOscillator(), g = actx.createGain();
    o.frequency.value = Pad.tones[kind] || 500;
    o.type = "sine"; g.gain.value = 0.035;
    o.connect(g); g.connect(actx.destination);
    o.start(); g.gain.exponentialRampToValueAtTime(0.0001, actx.currentTime + 0.07); o.stop(actx.currentTime + 0.08);
  } catch { /* audio non disponibile */ }
}

/** Annuncia con il lettore di schermo ciò che si sposta il fuoco (card, pulsanti, schede). */
let lastSpoken = "", lastSpokenAt = 0;
Pad.resetSpoken = () => { lastSpoken = ""; };
Pad.watchFocus = ({ focus, roots, section = ".shelf" }) => {
  const obs = new MutationObserver(() => {
    const el = document.querySelector(focus);
    if (!el) return;
    const txt = (el.querySelector(".lbl")?.textContent || el.getAttribute("aria-label") || el.textContent || "")
      .replace(/\s+/g, " ").trim();
    if (!txt || txt === lastSpoken) return;
    const now = Date.now();
    if (now - lastSpokenAt < 250) return;
    lastSpoken = txt;
    lastSpokenAt = now;
    const sec = el.closest(section)?.querySelector("h2")?.textContent?.trim() || "";
    announce(sec ? `${txt} — ${sec}` : txt);
  });
  for (const root of roots) {
    const node = $(root);
    if (node) obs.observe(node, { subtree: true, attributes: true, attributeFilter: ["class"] });
  }
};

/** Tasto di tastiera -> azione del pad ("" se non e' un tasto di navigazione). */
Pad.keyAction = (e) => {
  if (e.key === "Backspace") return "b";
  if (e.key === "Tab") return e.shiftKey ? "lb" : "rb";
  if (e.key === "f" || e.key === "F") return "x";
  return { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down", Enter: "a", Escape: "b",
    PageUp: "lt", PageDown: "rt", "/": "y", q: "lb", Q: "lb", e: "rb", E: "rb", s: "start", S: "start", " ": "a" }[e.key] || "";
};

/** Gamepad (mappa standard, tutti i pad collegati insieme, zona morta radiale, ripetizione tenendo premuto).
 *  Il polling gira solo con un pad collegato (gamepadconnected lo riaccende) e rallenta dopo 5 s di inattivita'.
 *  Azioni extra: "select" (tocco breve su Select/View), "l3", "r3", stick destro = lt/rt (pagina).
 *  Select/Guide + A/B/X/Y/LB/RB chiamano onChord(playPause|exitBigPicture|muteMic|deafen|prev|next);
 *  Select tenuto 1 s da solo = onChord("exitBigPicture"). Select+Start tenuti chiamano combo.run (se combo.when()). */
Pad.start = ({ input, onKind, combo, onChord }) => {
  const SC = window.PozzoShortcuts;
  const chordKeys = Object.keys(SC.PAD_CHORDS);
  const st = { held: {}, next: {}, comboSince: 0, selSince: 0, chorded: false, long: false, last: 0, on: false };
  const list = () => (navigator.getGamepads ? [...navigator.getGamepads()].filter((p) => p && p.connected) : []);
  const poll = (ts) => {
    const pads = list();
    if (!pads.length) { st.on = false; st.held = {}; st.selSince = 0; return; }
    const kind = SC.isPlayStation(pads[0].id) ? "ps" : "xbox";
    if (kind !== Pad.kind) { Pad.kind = kind; onKind?.(kind); }
    const s = SC.padStateAll(pads);
    const mod = s.select || s.guide;
    if (s.select && !st.selSince) { st.selSince = ts; st.chorded = false; st.long = false; for (const k of chordKeys) st.held["c" + k] = s[k]; }
    const dirs = { left: s.left, right: s.right, up: s.up, down: s.down, a: s.a, b: s.b, x: s.x, y: s.y, lb: s.lb, rb: s.rb,
      lt: s.lt || s.scrollUp, rt: s.rt || s.scrollDown, start: s.start, l3: s.l3, r3: s.r3 };
    let active = false;
    for (const [k, on] of Object.entries(dirs)) {
      if (on) active = true;
      if (mod && (k === "start" || chordKeys.includes(k))) { // con Select tenuto questi tasti sono scorciatoie, non comandi
        const c = "c" + k;
        if (k !== "start" && s[k] && !st.held[c]) { st.chorded = true; onChord?.(SC.PAD_CHORDS[k]); }
        st.held[c] = s[k]; st.held[k] = s[k];
        if (k === "start" && s.start) st.chorded = true;
        continue;
      }
      const rep = ["left", "right", "up", "down", "lt", "rt"].includes(k);
      if (on && !st.held[k]) { st.held[k] = true; st.next[k] = ts + 380; input(k); }
      else if (on && rep && ts >= st.next[k]) { st.next[k] = ts + 85; input(k); }
      else if (!on) st.held[k] = false;
    }
    if (s.select) {
      if (!st.chorded && !st.long && ts - st.selSince > 1000) { st.long = true; onChord?.("exitBigPicture"); }
    } else if (st.selSince) {
      if (!st.chorded && !st.long) input("select");
      st.selSince = 0;
    }
    // Select/View + Start/Menu tenuti premuti
    if (combo && s.select && s.start && combo.when()) {
      if (!st.comboSince) st.comboSince = ts;
      if (ts - st.comboSince > 1800) { st.comboSince = Infinity; combo.run(); }
    } else st.comboSince = 0;
    if (active || mod) st.last = ts;
    if (ts - st.last > 5000) setTimeout(() => poll(performance.now()), 90);
    else requestAnimationFrame(poll);
  };
  const wake = () => { if (st.on) return; st.on = true; st.last = performance.now(); requestAnimationFrame(poll); };
  window.addEventListener("gamepadconnected", wake);
  if (list().length) wake();
};
