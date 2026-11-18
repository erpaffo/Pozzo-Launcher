const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, x = s % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(x).padStart(2, "0")}`; };
const LABEL = () => ({ running: t("a.act.st.running"), done: t("a.act.st.done"), error: t("a.act.st.error"), cancelled: t("a.act.st.cancelled") });
let data = { jobs: [], now: 0 }, skew = 0;

function render() {
  const now = Date.now() / 1000 - skew;
  const run = data.jobs.filter((j) => j.status === "running").length;
  document.getElementById("sum").textContent = run ? t("a.act.runningCount", { n: run }) : "";
  document.getElementById("list").innerHTML = data.jobs.length ? data.jobs.map((j) => {
    const end = j.status === "running" ? now : (j.finished || now);
    const el = j.started ? end - j.started : null;
    const p = j.progress;
    // tempo rimanente stimato dal ritmo finora: solo dopo un minimo di avanzamento, prima e' troppo ballerino
    const eta = j.status === "running" && el && p > 0.02 && p < 1 ? el * (1 - p) / p : null;
    const width = j.status === "running" ? (p ?? 0) * 100 : 100;
    return `<div class="act ${esc(j.status)}">
      <div class="top"><span class="name">${esc(j.name)}</span><span class="badge">${esc(LABEL()[j.status] || j.status)}</span>
        ${j.stoppable ? `<button class="stop" data-id="${esc(j.id)}" title="${t("a.act.stopTitle")}">■ Stop</button>` : ""}
        ${j.status !== "running" ? `<button class="remove" data-remove="${esc(j.id)}" title="${t("a.act.removeTitle")}">✕</button>` : ""}
      </div>
      ${j.phase ? `<div class="phase muted" title="${esc(j.phase)}">${esc(j.phase)}</div>` : ""}
      ${j.last && j.last !== j.phase ? `<div class="last muted" title="${esc(j.last)}">${esc(j.last)}</div>` : ""}
      <div class="bar ${j.status === "running" && p == null ? "indet" : ""}"><i style="width:${width}%"></i></div>
      <div class="times muted"><span>${p != null && j.status === "running" ? Math.floor(p * 100) + "% · " : ""}${el != null ? "⏱ " + fmt(el) : ""}</span>
        <span>${eta != null ? t("a.act.eta", { time: fmt(eta) }) : ""}</span></div>
    </div>`;
  }).join("") : `<div class="empty muted">${t("a.act.empty")}</div>`;
}

async function poll() {
  try {
    data = await (await fetch("/api/activity")).json();
    skew = Date.now() / 1000 - data.now;
  } catch { /* server non raggiungibile: si riprova */ }
  render();
}

document.body.onclick = async (e) => {
  const clear = e.target.closest("[data-clear]");
  if (clear) {
    clear.disabled = true;
    try { data = await (await fetch("/api/activity/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: clear.dataset.clear === "done-error" ? "done-error" : "finished" }) })).json(); } catch {}
    render();
    return;
  }
  const remove = e.target.closest("[data-remove]");
  if (remove) {
    remove.disabled = true;
    try { data = await (await fetch(`/api/activity/${remove.dataset.remove}/remove`, { method: "POST" })).json(); } catch {}
    render();
    return;
  }
  const b = e.target.closest(".stop");
  if (!b) return;
  b.disabled = true;
  try { data = await (await fetch(`/api/activity/${b.dataset.id}/stop`, { method: "POST" })).json(); } catch { /* si vede al prossimo giro */ }
  render();
};

(async () => {  // stesso tema dell'app
  try {
    const ext = await (await fetch("/api/extensions")).json();
    const t = ext.themes.find((x) => x.id === ext.active_theme);
    if (t?.desktop) document.head.insertAdjacentHTML("beforeend", `<link rel="stylesheet" href="${esc(t.desktop)}">`);
    document.documentElement.dataset.theme = ext.active_theme || "default";
  } catch { /* tema predefinito */ }
})();
if (self !== top) document.querySelector("h1").hidden = true; // nel pannello dell'app il titolo c'e' gia'
poll();
setInterval(poll, 1500);
setInterval(render, 1000);
