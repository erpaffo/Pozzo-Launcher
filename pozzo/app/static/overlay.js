// Overlay in gioco: schede (panoramica, prestazioni, emulatore, media e note). Navigabile con tastiera e controller.
const $ = (s) => document.querySelector(s);
const post = (u, b) => fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }).then((r) => r.json());
const fmt = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s % 60).padStart(2, "0"); };
let st = null, timer = null, statsTimer = null, tab = "overview", shown = false;
const bar = (id, pct) => { $(id).style.transform = `scaleX(${Math.max(0, Math.min(100, pct || 0)) / 100})`; };
// il server chiama ovHide() prima di nascondere la finestra: da chiusa non resta nessun timer ne' polling
window.ovHide = () => { shown = false; clearInterval(timer); clearInterval(statsTimer); timer = statsTimer = null; };

function tick() { if (shown) $("#ov-time").textContent = st && st.started ? fmt(Date.now() / 1000 - st.started) : "0:00"; }

// ---- schede
const tabBtns = () => [...document.querySelectorAll("[role=tab]")].filter((b) => !b.hidden);
function showTab(name, focus) {
  const b = tabBtns().find((x) => x.dataset.tab === name) || tabBtns()[0];
  tab = b.dataset.tab;
  tabBtns().forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  document.querySelectorAll("[data-panel]").forEach((p) => p.hidden = p.dataset.panel !== tab);
  if (focus) b.focus();
  pollStats();
}
const stepTab = (d) => { const l = tabBtns(), i = l.findIndex((x) => x.dataset.tab === tab); showTab(l[(i + d + l.length) % l.length].dataset.tab, true); };

// ---- prestazioni: si interroga il server solo con la scheda aperta e la finestra visibile, ogni 2 s
function setStat(id, text, pct) { $(id).textContent = text; bar(id + "-bar", pct); }
async function loadStats() {
  try {
    const s = await (await fetch("/api/overlay/stats")).json();
    setStat("#ov-cpu", s.cpu + "%", s.cpu); setStat("#ov-ram", s.ram + "%", s.ram);
    if (s.battery) setStat("#ov-bat", s.battery.percent + "%" + (s.battery.plugged ? " · " + t("o.overlay.plugged") : ""), s.battery.percent);
    else setStat("#ov-bat", t("o.overlay.noBattery"), 0);
  } catch (e) { /* server non raggiungibile: restano gli ultimi valori */ }
}
function pollStats() {
  clearInterval(statsTimer); statsTimer = null;
  if (tab !== "perf" || document.hidden || !shown) return;
  loadStats(); statsTimer = setInterval(loadStats, 2000);
}
document.addEventListener("visibilitychange", pollStats);

async function ovRefresh() {
  shown = true;
  try { st = await (await fetch("/api/overlay/state")).json(); } catch (e) { st = null; $("#ov-none").hidden = false; return; }  // server non raggiungibile: mostra "nessun gioco" invece di dati vecchi
  $("#ov-title").textContent = st.title || "";
  $("#ov-none").hidden = st.running;
  $("#ov-pause span").textContent = t(st.paused ? "o.overlay.resume" : "o.overlay.pause");
  const c = $("#ov-cover"); c.hidden = !st.gid; if (st.gid) c.src = `/img/${st.gid}/cover?w=300`;
  document.querySelector('[data-tab=emu]').hidden = !st.emu;  // la scheda emulatore c'e' solo con un emulatore supportato
  const ready = !!(st.emu && st.emu.ready);
  document.querySelectorAll("[data-emu]").forEach((b) => b.disabled = !ready);
  $("#ov-emu-msg").textContent = st.emu && !ready ? t("o.overlay.emuOff") : "";
  showTab(tab === "emu" && !st.emu ? "overview" : tab);
  clearInterval(timer); tick(); timer = setInterval(tick, 1000);
  $("#ov-ach").hidden = $("#ov-notes").hidden = true;
  if (!st.gid) return;
  fetch(`/api/game/${st.gid}/achievements`).then((r) => r.json()).then((a) => {  // il server tiene 1 ora di cache
    const d = a.data; if (!d || !d.total) return;
    $("#ov-ach").hidden = false; $("#ov-ach-txt").textContent = `${d.unlocked} / ${d.total}`;
    bar("#ov-ach-bar", 100 * d.unlocked / d.total);
  }).catch(() => {});
  fetch(`/plugin-api/diario/gioco?id=${st.gid}`).then((r) => r.ok ? r.json() : null).then((d) => {  // estensione assente: 404, si salta
    if (!d || !d.voci || !d.voci.length) return;
    $("#ov-notes-list").replaceChildren(...d.voci.slice(0, 3).map((v) => Object.assign(document.createElement("li"), { textContent: v.testo })));
    $("#ov-notes").hidden = false;
  }).catch(() => {});
  focusFirst();
}
window.ovRefresh = ovRefresh;

// frecce e croce scorrono i pulsanti della scheda aperta (e le schede); LB/RB e PagSu/PagGiu cambiano scheda
const btns = () => [...document.querySelectorAll(".ov-card button:not(:disabled)")].filter((b) => !b.hidden && !b.closest("[hidden]"));
function focusFirst() { const b = btns(); (b.find((x) => x.dataset.tab === tab) || b[0])?.focus(); }
function move(d) { const b = btns(); if (!b.length) return; const i = b.indexOf(document.activeElement); b[(i + d + b.length) % b.length].focus(); }
const close = () => post("/api/overlay/hide").catch(() => {});

// un'azione alla volta per pulsante; un errore di rete non lascia il pulsante bloccato ne' lancia eccezioni
async function act(btn, fn) {
  if (btn.disabled) return;
  btn.disabled = true;
  try { await fn(); } catch (e) { /* il server non risponde: si puo' riprovare */ } finally { btn.disabled = false; btn.focus(); }
}
$("#ov-back").onclick = $("#ov-close").onclick = close;
$("#ov-shot").onclick = (e) => act(e.currentTarget, () => post("/api/running/screenshot"));
$("#ov-pause").onclick = (e) => act(e.currentTarget, async () => { await post(st && st.paused ? "/api/running/resume" : "/api/running/pause"); await ovRefresh(); });
$("#ov-stop").onclick = async (e) => { await act(e.currentTarget, () => post("/api/running/stop")); close(); };
document.querySelectorAll("[data-media]").forEach((b) => b.onclick = () => act(b, () => post("/api/media/keys", { action: b.dataset.media })));
document.querySelectorAll("[data-emu]").forEach((b) => b.onclick = () => act(b, async () => {
  const r = await post("/api/overlay/emu", { action: b.dataset.emu });
  $("#ov-emu-msg").textContent = r.detail || "";  // errore del server gia' tradotto
}));
document.querySelectorAll("[role=tab]").forEach((b) => b.onclick = () => showTab(b.dataset.tab, true));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") close();
  else if (e.key === "PageDown") { e.preventDefault(); stepTab(1); }
  else if (e.key === "PageUp") { e.preventDefault(); stepTab(-1); }
  else if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
  else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
});

// controller: croce/levetta per spostarsi, A conferma, B chiude, LB/RB cambiano scheda (Select+R3 chiude anche da XInput lato server)
let prev = {};
setInterval(() => {
  if (document.hidden || !shown) return;  // overlay nascosto: niente polling del pad
  const p = (navigator.getGamepads ? [...navigator.getGamepads()] : []).find(Boolean); if (!p) return;
  const down = { l: p.buttons[14]?.pressed || p.axes[0] < -.6, r: p.buttons[15]?.pressed || p.axes[0] > .6,
    u: p.buttons[12]?.pressed || p.axes[1] < -.6, d: p.buttons[13]?.pressed || p.axes[1] > .6, a: p.buttons[0]?.pressed, b: p.buttons[1]?.pressed,
    lb: p.buttons[4]?.pressed, rb: p.buttons[5]?.pressed };
  if ((down.r || down.d) && !prev.r && !prev.d) move(1);
  if ((down.l || down.u) && !prev.l && !prev.u) move(-1);
  if (down.rb && !prev.rb) stepTab(1);
  if (down.lb && !prev.lb) stepTab(-1);
  if (down.a && !prev.a) document.activeElement?.click();
  if (down.b && !prev.b) close();
  prev = down;
}, 80);
window.addEventListener("load", () => setTimeout(ovRefresh, 300));
