"use strict";
/* Rilevamento automatico dei giochi copiati nelle cartelle ROM: evento SSE «library_watch» e riga di stato nelle impostazioni. */

// Avviso per i giochi aggiunti da soli: {platform, count, titles} -> testo (al massimo 3 titoli, poi «e altri N»).
function watchToastText(ev) {
  const n = Number(ev?.count) || 0, titles = (ev?.titles || []).filter(Boolean);
  if (n < 1) return null;
  const shown = titles.slice(0, 3), more = n - shown.length;
  const list = shown.join(", ") + (shown.length && more > 0 ? ` e altri ${more}` : "");
  return `${n} ${n === 1 ? "nuovo gioco" : "nuovi giochi"}${ev.platform ? ` in ${ev.platform}` : ""}${list ? `: ${list}` : ""}`;
}

// Riga di stato dalla risposta di GET /api/library/watch.
function watchStatusText(w, nowSec) {
  if (!w) return "";
  if (!w.enabled) return "Disattivato";
  let s;
  const wait = Array.isArray(w.pending) ? w.pending : [], n = Array.isArray(w.pending) ? w.pending.length : Number(w.pending) || 0;
  if (wait.length) s = `Aspetto che finisca la copia di: ${wait.join(", ")}`;
  else if (n) s = `Aspetto che finisca la copia di ${n} file`;
  else {
    s = "In ascolto";
    if (w.last_scan) {
      const ago = Math.max(0, Math.round(nowSec - w.last_scan));
      s += ` · ultima verifica ${ago < 60 ? `${ago} s` : `${Math.round(ago / 60)} min`} fa`;
    }
  }
  return w.errors ? `${s} · ${w.errors} ${w.errors === 1 ? "errore" : "errori"}` : s;
}

if (typeof module !== "undefined") module.exports = { watchToastText, watchStatusText };

let watchTimer = 0;
function watchStatusStop() { clearTimeout(watchTimer); watchTimer = 0; }
async function watchStatusStart() {
  watchStatusStop();
  const line = $("#watch-state"), box = $("#watch-roms");
  if (!line || !box) return;
  if (!box.dataset.bound) { // il pannello si carica al primo ingresso nelle impostazioni: il controllo si aggancia qui, una volta
    box.dataset.bound = "1";
    autosaveControl(box, (enabled) => api("/api/app/watch-roms", { body: { enabled } }).then(watchStatusStart));
  }
  try {
    const w = await api("/api/library/watch");
    if (document.activeElement !== box) box.checked = !!w.enabled;
    line.textContent = watchStatusText(w, Date.now() / 1000);
    line.hidden = false;
  } catch { line.hidden = true; } // server senza rilevamento: niente riga, la pagina resta intera
  if (!$("#settings-page").hidden && SET.tab === "libreria") watchTimer = setTimeout(watchStatusStart, 5000);
}

if (typeof window !== "undefined") {
  if (window.EventSource) {
    const es = new EventSource("/api/v1/events"); // il browser si riconnette da solo
    es.addEventListener("library_watch", (e) => {
      let ev; try { ev = JSON.parse(e.data); } catch { return; }
      const t = watchToastText(ev);
      if (t) { toast(t); syncLibrary(); }
    });
    es.addEventListener("party_invite", (ev) => { let d = {}; try { d = JSON.parse(ev.data) || {}; } catch { return; } const code = typeof d.code === "string" ? d.code.trim() : ""; if (code && typeof window.openJoinWith === "function") window.openJoinWith(code); });
  }
}
