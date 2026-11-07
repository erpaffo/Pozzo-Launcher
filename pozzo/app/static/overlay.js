// Overlay in gioco: tempo, azioni rapide, appunti del diario, obiettivi, musica. Navigabile con tastiera e controller.
const $ = (s) => document.querySelector(s);
const post = (u, b) => fetch(u, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b || {}) }).then((r) => r.json());
const fmt = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s % 60).padStart(2, "0"); };
let st = null, timer = null;

function tick() { $("#ov-time").textContent = st && st.started ? fmt(Date.now() / 1000 - st.started) : "0:00"; }

async function ovRefresh() {
  try { st = await (await fetch("/api/overlay/state")).json(); } catch (e) { return; }
  $("#ov-title").textContent = st.title || "";
  $("#ov-none").hidden = st.running;
  $("#ov-pause").textContent = t(st.paused ? "o.overlay.resume" : "o.overlay.pause");
  const c = $("#ov-cover"); c.hidden = !st.gid; if (st.gid) c.src = `/img/${st.gid}/cover?w=300`;
  clearInterval(timer); tick(); timer = setInterval(tick, 1000);
  $("#ov-ach").hidden = $("#ov-notes").hidden = true;
  if (!st.gid) return;
  fetch(`/api/game/${st.gid}/achievements`).then((r) => r.json()).then((a) => {  // il server tiene 1 ora di cache
    const d = a.data; if (!d || !d.total) return;
    $("#ov-ach").hidden = false; $("#ov-ach-txt").textContent = `${d.unlocked} / ${d.total}`;
    $("#ov-ach-bar").style.width = Math.round(100 * d.unlocked / d.total) + "%";
  }).catch(() => {});
  fetch(`/plugin-api/diario/gioco?id=${st.gid}`).then((r) => r.ok ? r.json() : null).then((d) => {  // estensione assente: 404, si salta
    if (!d || !d.voci || !d.voci.length) return;
    $("#ov-notes-list").replaceChildren(...d.voci.slice(0, 3).map((v) => Object.assign(document.createElement("li"), { textContent: v.testo })));
    $("#ov-notes").hidden = false;
  }).catch(() => {});
  focusFirst();
}
window.ovRefresh = ovRefresh;

const btns = () => [...document.querySelectorAll(".ov-card button")];
function focusFirst() { const b = btns(); b[0] && b[0].focus(); }
function move(d) { const b = btns(), i = b.indexOf(document.activeElement); b[(i + d + b.length) % b.length].focus(); }
const close = () => post("/api/overlay/hide");

$("#ov-back").onclick = $("#ov-close").onclick = close;
$("#ov-shot").onclick = () => post("/api/running/screenshot");
$("#ov-pause").onclick = async () => { await post(st.paused ? "/api/running/resume" : "/api/running/pause"); ovRefresh(); };
$("#ov-stop").onclick = async () => { await post("/api/running/stop"); close(); };
document.querySelectorAll("[data-media]").forEach((b) => b.onclick = () => post("/api/media/keys", { action: b.dataset.media }));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") close();
  else if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(1); }
  else if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(-1); }
});

// controller: croce/levetta per spostarsi, A conferma, B chiude (Select+R3 chiude anche da XInput lato server)
let prev = {};
setInterval(() => {
  const p = (navigator.getGamepads ? [...navigator.getGamepads()] : []).find(Boolean); if (!p) return;
  const down = { l: p.buttons[14]?.pressed || p.axes[0] < -.6, r: p.buttons[15]?.pressed || p.axes[0] > .6,
    u: p.buttons[12]?.pressed || p.axes[1] < -.6, d: p.buttons[13]?.pressed || p.axes[1] > .6, a: p.buttons[0]?.pressed, b: p.buttons[1]?.pressed };
  if ((down.r || down.d) && !prev.r && !prev.d) move(1);
  if ((down.l || down.u) && !prev.l && !prev.u) move(-1);
  if (down.a && !prev.a) document.activeElement?.click();
  if (down.b && !prev.b) close();
  prev = down;
}, 80);
window.addEventListener("load", () => setTimeout(ovRefresh, 300));
