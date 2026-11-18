/* Immagini rotte senza onerror= inline (la CSP blocca i gestori inline): un solo ascoltatore in cattura,
   perché l'evento "error" delle <img> non risale. Attributi sull'<img>:
     data-fb="url"          prima riprova con questo indirizzo (una volta sola)
     data-onerr="remove"    toglie l'immagine
     data-onerr="hide"      la nasconde lasciando lo spazio (visibility)
     data-onerr="parent"    toglie l'elemento che la contiene
     data-onerr="text"      la sostituisce con data-onerr-text, dentro data-onerr-tag (span se manca) con data-onerr-class e data-onerr-style
*/
(() => {
  if (window.__gsImgFallback) return;
  window.__gsImgFallback = true;
  document.addEventListener("error", (e) => {
    const img = e.target;
    if (!(img instanceof HTMLImageElement)) return;
    const d = img.dataset;
    if (d.fb) { const fb = d.fb; d.fb = ""; img.src = fb; return; }
    switch (d.onerr) {
      case "remove": img.remove(); break;
      case "hide": img.style.visibility = "hidden"; break;
      case "parent": img.parentNode && img.parentNode.remove(); break;
      case "text": {
        const el = document.createElement(d.onerrTag || "span");
        if (d.onerrClass) el.className = d.onerrClass;
        if (d.onerrStyle) el.style.cssText = d.onerrStyle;
        el.textContent = d.onerrText || "";
        img.replaceWith(el);
        break;
      }
    }
  }, true);
})();
