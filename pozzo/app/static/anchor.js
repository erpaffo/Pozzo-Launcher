"use strict";
/* Pozzo Launcher - posizione di un fumetto (suggerimento, tour) rispetto a un elemento.
 * Funzioni pure, provate con node: GSAnchor.place(rettangolo del bersaglio, {w,h} del fumetto, {w,h} della finestra).
 * Rettangoli come da getBoundingClientRect(): {left, top, right, bottom, width, height}. Il fumetto sceglie il lato
 * con spazio (preferenza: sotto, sopra, destra, sinistra); se non entra da nessuna parte, o il bersaglio è quasi grande
 * come la finestra, si centra senza freccia. Non esce mai dalla finestra. */
(() => {
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  /** il bersaglio è visibile nella finestra almeno per `min` (0..1) della sua area? */
  function inView(t, vp, min = 0.6) {
    const w = Math.min(t.right, vp.w) - Math.max(t.left, 0), h = Math.min(t.bottom, vp.h) - Math.max(t.top, 0);
    if (w <= 0 || h <= 0 || !t.width || !t.height) return false;
    return (w * h) / (t.width * t.height) >= min;
  }

  function place(t, size, vp, opt = {}) {
    const gap = opt.gap ?? 12, m = opt.margin ?? 8, order = opt.prefer || ["bottom", "top", "right", "left"];
    const room = {
      bottom: vp.h - t.bottom - gap - m, top: t.top - gap - m,
      right: vp.w - t.right - gap - m, left: t.left - gap - m,
    };
    const need = { bottom: size.h, top: size.h, right: size.w, left: size.w };
    const huge = t.width > vp.w * 0.8 && t.height > vp.h * 0.8;
    const side = huge ? "center" : order.find((s) => room[s] >= need[s]) || "center";
    let left, top, arrow = null;
    if (side === "bottom" || side === "top") {
      left = t.left + t.width / 2 - size.w / 2;
      top = side === "bottom" ? t.bottom + gap : t.top - gap - size.h;
    } else if (side === "right" || side === "left") {
      top = t.top + t.height / 2 - size.h / 2;
      left = side === "right" ? t.right + gap : t.left - gap - size.w;
    } else {
      left = (vp.w - size.w) / 2; top = (vp.h - size.h) / 2;
    }
    left = clamp(left, m, Math.max(m, vp.w - size.w - m));
    top = clamp(top, m, Math.max(m, vp.h - size.h - m));
    if (side === "bottom" || side === "top") arrow = clamp(t.left + t.width / 2 - left, 16, Math.max(16, size.w - 16));
    else if (side === "right" || side === "left") arrow = clamp(t.top + t.height / 2 - top, 16, Math.max(16, size.h - 16));
    return { left: Math.round(left), top: Math.round(top), side, arrow: arrow === null ? null : Math.round(arrow) };
  }

  const api = { place, inView };
  if (typeof window === "undefined") { module.exports = api; return; }
  window.GSAnchor = api;
})();
