
"use strict";
const $ = (s) => document.querySelector(s);

async function post(path, body) {
  const r = await fetch(path, { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch { /* niente */ } throw new Error(m); }
  return r.status === 204 ? null : r.json();
}

let toastT = 0;
function toast(msg, ok = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = ok ? "" : "err"; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 4000);
}

async function show() {
  let h = {};
  try { h = await (await fetch("/g/api/hello", { credentials: "same-origin" })).json(); } catch { /* senza rete */ }
  $("#join").hidden = !!h.paired;
  $("#inside").hidden = !h.paired;
  if (h.paired) {
    $("#video-addr").textContent = h.video || "___";
    $("#video-addr").hidden = !h.video;
    $("#video-ask").hidden = !!h.video;
    return;
  }
  const c = (location.hash.match(/code=(\d{6})/) || [])[1];
  if (c) $("#code").value = c;
}

$("#go").onclick = async () => {
  $("#join-err").textContent = "";
  try {
    await post("/g/api/join", { code: $("#code").value, name: $("#name").value });
    history.replaceState(null, "", "/g/");
    show();
  } catch (e) { $("#join-err").textContent = e.message; }
};

$("#pin-go").onclick = async () => {
  try { await post("/g/api/pin", { pin: $("#pin").value }); $("#pin").value = ""; toast("Moonlight abbinato: buon gioco", true); }
  catch (e) { toast(e.message); }
};

$("#out").onclick = async () => {
  try { await post("/m/api/logout"); } catch { /* gia' fuori */ }
  history.replaceState(null, "", "/g/");
  show();
};

show();
