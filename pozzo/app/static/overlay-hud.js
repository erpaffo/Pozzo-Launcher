// HUD leggero: nessuna richiesta se la finestra e' nascosta; una sola richiesta (tempo + metriche) ogni 2 s
const $ = (s) => document.querySelector(s);
let started = null;
const fmt = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s % 60).padStart(2, "0"); };
async function poll() {
  if (document.hidden) return;
  try {
    const s = await (await fetch("/api/overlay/stats")).json();
    started = s.started;
    $("#h-st").textContent = `${t("o.overlay.cpu")} ${s.cpu}% · ${t("o.overlay.ram")} ${s.ram}%`;
  } catch (e) { /* server non raggiungibile: restano gli ultimi valori */ }
}
setInterval(() => { if (!document.hidden) $("#h-time").textContent = started ? fmt(Date.now() / 1000 - started) : "0:00"; }, 1000);
setInterval(poll, 2000);
window.addEventListener("load", () => setTimeout(poll, 300));
