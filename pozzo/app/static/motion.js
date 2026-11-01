/* Ingresso scaglionato delle copertine + pausa a scheda nascosta + preferenza gs.motion.
   Nessuna dipendenza; non tocca il DOM dell'app oltre a una classe temporanea. */
(() => {
  "use strict";
  const root = document.documentElement;
  const MAX = 24, MIN_BATCH = 6;
  const SEL = ".tile .cover, .cnx-card, .gs-dashboard__tile, .vetrina-game, .gs-console-game, .card .cv";

  const read = () => { try { return JSON.parse(localStorage.getItem("gs.motion")); } catch { return null; } };
  const apply = (v) => { if (v === "off" || v === "reduced" || v === "normal") root.dataset.motion = v; else delete root.dataset.motion; };
  apply(read());
  window.GSMotion = { set(v) { try { localStorage.setItem("gs.motion", JSON.stringify(v)); } catch { /* storage non disponibile */ } apply(v); } };

  const sync = () => root.classList.toggle("mo-paused", document.hidden);
  document.addEventListener("visibilitychange", sync); sync();

  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const enabled = () => root.dataset.motion !== "off" && root.dataset.motion !== "reduced" && (root.dataset.motion === "normal" || !reduced.matches);

  let lastScroll = 0, pending = [], queued = false;
  document.addEventListener("scroll", () => { lastScroll = performance.now(); }, { capture: true, passive: true });

  function flush() {
    queued = false;
    const nodes = pending; pending = [];
    if (!enabled() || document.hidden || performance.now() - lastScroll < 250) return;
    const found = new Set();
    for (const n of nodes) {
      if (!n.isConnected) continue;
      if (n.matches(SEL)) found.add(n);
      else if (n.firstElementChild) for (const el of n.querySelectorAll(SEL)) { found.add(el); if (found.size > 120) break; }
    }
    if (found.size < MIN_BATCH) return;
    const vh = innerHeight, vw = innerWidth, picked = [];
    for (const el of found) {
      const r = el.getBoundingClientRect();
      if (r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw) picked.push([r, el]);
    }
    if (picked.length < MIN_BATCH) return;
    picked.sort((a, b) => (a[0].top - b[0].top) || (a[0].left - b[0].left));
    picked.slice(0, MAX).forEach(([, el], i) => {
      el.style.setProperty("--mo-i-idx", i);
      el.classList.add("mo-in");
      el.addEventListener("animationend", () => { el.classList.remove("mo-in"); el.style.removeProperty("--mo-i-idx"); }, { once: true });
    });
  }

  new MutationObserver((muts) => {
    for (const m of muts) for (const n of m.addedNodes) if (n.nodeType === 1 && !n.classList.contains("mo-in")) pending.push(n);
    if (pending.length && !queued) { queued = true; requestAnimationFrame(flush); }
  }).observe(document.body || root, { childList: true, subtree: true });
})();
