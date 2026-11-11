"use strict";
/* Pozzo Launcher - «Completa i mancanti dal web»: anteprima delle immagini trovate sul web per i tipi che mancano; si salva solo cio' che l'utente conferma. Script classico (usa MD, MDK, mediaChanged di actions.js). */

const MF = { items: [], ctl: null, busy: false };
const mfBox = () => $("#md-fill-box");

function mfStop() { MF.ctl?.abort(); MF.ctl = null; MF.busy = false; }

function mfRender(note) {
  const box = mfBox(), n = MF.items.filter((i) => i.candidate_url && i.on).length;
  box.hidden = false;
  box.innerHTML = `<p class="small" role="status">${note ? esc(note) : ""}</p>
    <div class="mf-grid">${MF.items.map((it, i) => `<div class="mf-card${it.candidate_url && !it.on ? " off" : ""}">
      <div class="mf-img">${it.thumb ? `<img src="${esc(it.thumb)}" alt="${esc(it.label)}">` : `<span class="muted small">${it.pending ? "…" : "—"}</span>`}</div>
      ${it.candidate_url ? `<label><input type="checkbox" data-mf="${i}" ${it.on ? "checked" : ""}> ${esc(it.label)}</label>
        <span class="muted small">${it.w}×${it.h} · ${Math.round(it.size / 1024)} KB · ${esc(it.domain)}</span>
        <button class="btn small" type="button" data-mf-change="${i}">${t("h.media.fillChange")}</button>`
      : `<strong>${esc(it.label)}</strong><span class="muted small">${it.pending ? t("h.media.fillSearching") : "⚠ " + esc(it.error || "")}</span>`}
    </div>`).join("")}</div>
    <div class="mf-bar"><button class="btn primary" type="button" id="mf-apply" ${n && !MF.busy ? "" : "disabled"}>${t("h.media.fillApply", {n})}</button>
      <button class="btn" type="button" id="mf-cancel">${t("h.media.fillCancel")}</button></div>`;
}

async function mfSearch(kinds, skip = []) {
  const g = MD, ctl = MF.ctl;
  const r = await api(`/api/game/${g.id}/media/fill/preview`, { body: { kinds, skip }, signal: ctl.signal });
  return MD === g && MF.ctl === ctl ? r.items : [];
}

async function mfStart() {
  if (!MD || MF.busy) return;
  mfStop();
  MF.ctl = new AbortController();
  MF.busy = true;
  const g = MD, ctl = MF.ctl, missing = (MDK?.kinds || []).filter((k) => !k.url && k.kind !== "icon").map((k) => ({ kind: k.kind, label: k.label, pending: true }));
  if (!missing.length) { MF.busy = false; MF.items = []; mfRender(t("h.media.fillNone")); return; }
  MF.items = missing;
  mfRender(t("h.media.fillSearching"));
  // un tipo alla volta: le anteprime compaiono man mano e «Annulla» ferma subito
  for (const m of missing) {
    try {
      const [it] = await mfSearch([m.kind]);
      if (MF.ctl !== ctl) return;  // annullato o altro gioco
      if (it) Object.assign(m, it, { pending: false, on: !!it.candidate_url });
    } catch (e) {
      if (MF.ctl !== ctl) return;
      Object.assign(m, { pending: false, error: e.message });
    }
    mfRender(t("h.media.fillSearching"));
  }
  MF.busy = false;
  mfRender(t("h.media.fillReview"));
}

async function mfChange(i) {
  const it = MF.items[i];
  if (!it || MF.busy || !MF.ctl) return;
  MF.busy = true;
  it.pending = true;
  const old = it.candidate_url, ctl = MF.ctl;
  mfRender(t("h.media.fillSearching"));
  try {
    const [n] = await mfSearch([it.kind], [old]);
    if (n && n.candidate_url) Object.assign(it, n, { pending: false, on: true });
    else Object.assign(it, { pending: false, error: n?.error });
  } catch (e) {
    if (MF.ctl !== ctl) return;
    it.pending = false;
    toast(e.message, true);
  }
  it.pending = false;
  MF.busy = false;
  mfRender(t("h.media.fillReview"));
}

async function mfApply() {
  const g = MD, sel = MF.items.filter((i) => i.candidate_url && i.on).map((i) => ({ kind: i.kind, candidate_url: i.candidate_url }));
  if (!g || !sel.length || MF.busy) return;
  MF.busy = true;
  mfRender(t("h.media.fillSaving"));
  let r;
  try { r = await api(`/api/game/${g.id}/media/fill/apply`, { body: { items: sel } }); }
  catch (e) { MF.busy = false; mfRender("⚠ " + e.message); return; }
  MF.busy = false;
  const bad = r.results.filter((x) => !x.ok);
  mfBox().hidden = true;
  MF.items = [];
  await mediaChanged(r, t("h.media.fillDone", {n: r.results.length - bad.length}));
  if (bad.length) toast(bad.map((x) => `${x.kind}: ${x.error}`).join(" · "), true);
}

(() => {
  $("#md-fill").onclick = mfStart;
  mfBox().addEventListener("click", (e) => {
    const c = e.target.closest("[data-mf-change]");
    if (c) return mfChange(+c.dataset.mfChange);
    if (e.target.closest("#mf-apply")) return mfApply();
    if (e.target.closest("#mf-cancel")) { mfStop(); MF.items = []; mfBox().hidden = true; }
  });
  mfBox().addEventListener("change", (e) => {
    const k = e.target.dataset?.mf;
    if (k == null) return;
    MF.items[+k].on = e.target.checked;
    mfRender(t("h.media.fillReview"));
    mfBox().querySelector(`[data-mf="${k}"]`)?.focus();
  });
  // chiudere il dialogo o cambiare gioco annulla la ricerca
  $("#media-dlg").addEventListener("close", () => { mfStop(); MF.items = []; mfBox().hidden = true; });
})();
