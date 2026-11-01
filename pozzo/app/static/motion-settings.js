/* Impostazioni › Aspetto: scelta delle animazioni (complete / ridotte / nessuna) e segnaposto di
   caricamento per le griglie. Il valore passa da GSMotion.set (motion.js) e finisce in
   html[data-motion], che motion.css legge; senza una scelta esplicita vale prefers-reduced-motion.
   Il riquadro si aggiunge da solo quando l'app ha caricato le impostazioni: nessuna dipendenza da js/. */
(() => {
  "use strict";
  const KEY = "gs.motion";
  const VALUES = ["normal", "reduced", "off"];
  const LABELS = { normal: "Complete", reduced: "Ridotte", off: "Nessuna" };
  const root = document.documentElement;
  const system = typeof matchMedia === "function"
    ? matchMedia("(prefers-reduced-motion: reduce)")
    : { matches: false, addEventListener() {} };

  const stored = () => {
    try {
      const v = JSON.parse(localStorage.getItem(KEY) || "null");
      return VALUES.includes(v) ? v : null;
    } catch { return null; } // storage non disponibile o valore illeggibile
  };
  const current = () => stored() || (system.matches ? "reduced" : "normal");

  function set(v) {
    if (!VALUES.includes(v)) return;
    if (window.GSMotion && window.GSMotion.set) return window.GSMotion.set(v);
    try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* storage non disponibile */ }
    if (root.dataset) root.dataset.motion = v;
  }

  const inputs = [];
  const sync = () => { for (const i of inputs) i.checked = i.value === current(); };

  function panel() {
    const row = document.createElement("div");
    row.className = "srow";
    row.dataset.gsMotion = "1";
    row.innerHTML = `<div class="srow-txt"><div class="srow-title">Animazioni</div>
      <div class="srow-desc">Movimento di copertine, pannelli e finestre. Senza una scelta vale
      l'impostazione di sistema (Windows: «Effetti di animazione»).</div></div>
      <div class="row" role="radiogroup" aria-label="Animazioni">`
      + VALUES.map((v) => `<label class="chk"><input type="radio" name="gs-motion" value="${v}"> ${LABELS[v]}</label>`).join("")
      + `</div>`;
    inputs.push(...row.querySelectorAll("input"));
    row.addEventListener("change", (e) => { if (e.target.name === "gs-motion") set(e.target.value); });
    sync();
    return row;
  }

  function mount() {
    const body = document.getElementById("settings-body");
    if (!body) return; // Big Picture e telefono: nessun pannello impostazioni
    const pane = body.querySelector('[data-pane="aspetto"]');
    if (!pane || pane.querySelector("[data-gs-motion]")) return;
    const title = document.createElement("h3");
    title.textContent = "Animazioni";
    pane.append(title, panel());
  }

  function start() {
    mount();
    const body = document.getElementById("settings-body");
    // i riquadri delle impostazioni arrivano da fetch: si aspetta che la pagina Aspetto esista
    if (body && typeof MutationObserver === "function") {
      new MutationObserver(mount).observe(body, { childList: true, subtree: true });
    }
    if (system.addEventListener) system.addEventListener("change", sync); // segue il sistema finché non scegli
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();

  window.GSMotionSettings = { values: VALUES, current, set };

  /* Griglie: segnaposto leggeri al posto del vuoto durante il caricamento.
     GSSkeleton.show(document.querySelector("#grid-scroll"), 18) / GSSkeleton.hide(...) */
  window.GSSkeleton = {
    show(container, count = 18) {
      if (!container) return null;
      this.hide(container);
      const layer = document.createElement("div");
      layer.className = "gs-skel-layer";
      layer.dataset.gsSkel = "1";
      layer.setAttribute("aria-hidden", "true");
      const n = Math.max(1, Math.min(60, Math.trunc(count) || 18));
      for (let i = 0; i < n; i++) {
        const item = document.createElement("div");
        item.className = "gs-skel";
        layer.append(item);
      }
      container.append(layer);
      return layer;
    },
    hide(container) {
      if (!container) return;
      for (const el of container.querySelectorAll("[data-gs-skel]")) el.remove();
    },
  };
})();
