/* Splash all'avvio del gioco + «riposo» della UI mentre il gioco e' in primo piano.
   Eventi SSE: game_splash (mostra), game_foreground / splash_end / game_stopped (chiude), game_background (riprende). */
(() => {
  "use strict";
  if (typeof window === "undefined" || !window.EventSource) return;
  const root = document.documentElement;
  let el = null, paused = [];

  function hide() {
    if (!el) return;
    const e = el; el = null;
    e.classList.add("bs-out");
    setTimeout(() => e.remove(), 500);
  }

  function show(d) {
    hide();
    el = document.createElement("div");
    el.id = "game-splash";
    el.setAttribute("role", "status");
    el.setAttribute("aria-label", d.title || "");
    const logo = new Image();
    logo.className = "gs-logo"; logo.alt = d.title || "";
    const title = document.createElement("h1");
    title.className = "gs-title"; title.textContent = d.title || "";
    logo.onerror = () => logo.replaceWith(title);
    logo.src = `/img/${d.gid}/logo`;
    const spin = document.createElement("div");
    spin.className = "gs-spin";
    el.append(logo, spin);
    document.body.appendChild(el);
    const bg = el; // sfondo: hero, poi fanart; senza immagini resta lo scuro
    const tryBg = (kinds) => {
      if (!kinds.length) return;
      const im = new Image();
      im.onload = () => { bg.style.backgroundImage = `url(${im.src})`; };
      im.onerror = () => tryBg(kinds.slice(1));
      im.src = `/img/${d.gid}/${kinds[0]}`;
    };
    tryBg(["hero", "fanart", "screenshot"]);
  }

  function rest(on) {
    root.classList.toggle("pz-rest", on);
    if (on) {
      paused = [...document.querySelectorAll("video,audio")].filter((m) => !m.paused);
      paused.forEach((m) => m.pause());
    } else {
      paused.forEach((m) => m.play().catch(() => {}));
      paused = [];
    }
    window.dispatchEvent(new CustomEvent("pz-rest", { detail: { on } })); // chi ha timer propri (attract...) si ferma qui
  }

  const es = window.gsEventSource || new EventSource("/api/v1/events");
  window.gsEventSource = es;
  const on = (name, fn) => es.addEventListener(name, (e) => { let d = {}; try { d = JSON.parse(e.data) || {}; } catch {} fn(d); });
  on("game_splash", show);
  on("game_foreground", () => { hide(); rest(true); });
  on("game_background", () => rest(false));
  on("splash_end", hide);
  on("game_stopped", () => { hide(); rest(false); });
})();
