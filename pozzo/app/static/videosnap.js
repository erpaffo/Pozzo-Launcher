"use strict";
/* Video snap: clip di gameplay mute sopra le immagini (griglia, scheda, Big Picture, salvaschermo). Una sola global (GSVideo).
 * Parte pura (ritardo del passaggio del mouse, permesso di movimento) testata da tests/test_videosnap.js. */
(() => {
  const HOVER_MS = 600;
  /** Il video parte dopo `delay` ms sullo stesso elemento; uscire (o cambiare elemento) lo ferma. Uno alla volta. */
  const createHover = ({ delay = HOVER_MS, setT, clearT, play, stop }) => {
    let timer = 0, cur = null;
    const end = () => { clearT(timer); timer = 0; if (cur !== null) { stop(cur); cur = null; } };
    return {
      enter(key) { if (key === cur) return; end(); timer = setT(() => { timer = 0; cur = key; play(key); }, delay); },
      leave(key) { if (key === cur || timer) end(); },
      stopAll: end,
    };
  };
  /** Animazioni a "normal"; senza scelta esplicita vale prefers-reduced-motion. */
  const motionOk = (dataMotion, systemReduced) => dataMotion === "normal" || (!dataMotion && !systemReduced);

  let on = null;
  const enabled = () => (on ||= fetch("/api/app/video-snap").then((r) => r.json()).then((j) => !!j.enabled).catch(() => false));
  const allowed = () => typeof document !== "undefined"
    && motionOk(document.documentElement.dataset.motion, !!matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  const tokens = new WeakMap(); // contenitore -> ultima richiesta (annulla quelle vecchie)

  /** Toglie i video del contenitore e annulla un attach in attesa. */
  const stop = (box) => { tokens.set(box, {}); box.querySelectorAll(":scope > video.vsnap").forEach((v) => { v.pause(); v.removeAttribute("src"); v.load(); v.remove(); }); };

  /** Mette il video del gioco nel contenitore (dopo `after`, se dato). Se manca il file o e' spento non si vede nulla. */
  async function attach(box, id, { after = null, delay = 0 } = {}) {
    stop(box);
    const tok = tokens.get(box);
    if (!allowed() || !(await enabled())) return;
    if (delay) await new Promise((r) => setTimeout(r, delay));
    if (tokens.get(box) !== tok || !box.isConnected) return;
    const v = document.createElement("video");
    v.className = "vsnap"; v.muted = true; v.loop = true; v.playsInline = true; v.preload = "auto"; v.setAttribute("aria-hidden", "true");
    v.addEventListener("playing", () => v.classList.add("on"));
    v.addEventListener("error", () => v.remove()); // nessun video per questo gioco (404)
    v.src = `/img/${id}/video`;
    if (after?.isConnected) after.after(v); else box.append(v);
    v.play().catch(() => v.remove());
  }
  const api = { HOVER_MS, createHover, motionOk, attach, stop, reset: () => { on = null; } };
  if (typeof window !== "undefined") window.GSVideo = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
