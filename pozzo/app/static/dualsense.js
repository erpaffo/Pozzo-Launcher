"use strict";
/* Pad Sony: batteria (icona + %), barra luminosa dalla copertina e tick di vibrazione. Condiviso da app e Big Picture.
 * Impostazioni nel dispositivo (store gs.dsLed, gs.dsRumble). Il server scrive sul pad solo fuori partita (vedi routes/pad.py). */
const Dualsense = (() => {
  const NEUTRAL = "#5b8cff"; // accento di Pozzo
  const sony = () => navigator.getGamepads ? [...navigator.getGamepads()].filter((p) => p && p.connected && window.PozzoShortcuts?.isPlayStation(p.id)) : [];
  const post = (color, force) => fetch("/api/pad/led", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ color, force: !!force }) }).catch(() => {});

  async function battery() {
    const el = document.getElementById("ds-bat");
    if (!el) return;
    let b = null;
    if (sony().length) { try { b = await (await fetch("/api/pad/battery")).json(); } catch { /* server non raggiungibile */ } }
    if (!b?.present || b.percent == null) { el.hidden = true; return; }
    el.hidden = false;
    el.textContent = `${b.charging ? "⚡" : "🔋"} ${b.percent}%`;
    el.title = t("a.pad.battery", { n: b.percent });
    el.classList.toggle("low", b.percent <= 20 && !b.charging);
  }

  let timer = 0, last = "";
  /** Colora la barra dalla copertina del gioco (id null = colore neutro). force: anche in partita (avvio/fine). */
  function led(id, force) {
    clearTimeout(timer);
    if (!store.get("dsLed", true) || !sony().length) return;
    timer = setTimeout(async () => {
      let c = NEUTRAL;
      if (id) { try { c = (await (await fetch(`/api/game/${id}/cover-accent`)).json()).accent || NEUTRAL; } catch { /* resta neutro */ } }
      if (c === last && !force) return;
      last = c;
      post(c, force);
    }, force ? 0 : 400);
  }

  function tick() {
    if (!store.get("dsRumble", false)) return;
    sony()[0]?.vibrationActuator?.playEffect("dual-rumble", { duration: 18, strongMagnitude: 0, weakMagnitude: 0.3 })?.catch?.(() => {});
  }

  window.addEventListener("gamepadconnected", () => { last = ""; battery(); });
  window.addEventListener("gamepaddisconnected", battery);
  setInterval(() => { if (sony().length) battery(); }, 30000); // solo con un pad Sony collegato
  if (sony().length) battery();
  return { led, tick, battery };
})();
