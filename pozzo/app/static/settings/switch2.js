/* Impostazioni › Download › Switch 2: stato del supporto e strumento «Converti» (job in background, avanzamento a polling).
   Il pannello viene inserito da settings.js in modo asincrono: ci si aggancia quando compare. */
(function (global) {
  "use strict";
  const doc = global.document;
  if (!doc) return; // test in node: niente DOM
  const $ = (id) => doc.getElementById(id);
  const trad = (k, it, p) => (global.t ? global.t(k, p) : it.replace(/\{(\w+)\}/g, (m, n) => (p && n in p ? p[n] : m)));
  let jid = null;

  async function api(url, body) {
    const r = await fetch(url, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || r.statusText);
    return j;
  }

  function busy(on) {
    $("s2-go").disabled = on;
    $("s2-cancel").hidden = !on;
    $("s2-bar").hidden = !on;
  }

  async function stato() {
    try {
      const s = await api("/api/switch2/status");
      $("s2-status").textContent = s.supported ? trad("j.s2.ok", "Conversione disponibile.") : trad("j.s2.no", "Non disponibile: {why}", { why: s.reason });
      $("s2-go").disabled = !s.supported;
    } catch (e) { $("s2-status").textContent = e.message; }
  }

  async function segui() {
    while (jid) {
      let j;
      try { j = await api("/api/switch2/job/" + jid); } catch (e) { $("s2-msg").textContent = e.message; break; }
      $("s2-bar").value = j.pct;
      if (j.status !== "running") {
        $("s2-msg").textContent = j.status === "done" ? trad("j.s2.done", "Creato: {out}", { out: j.out })
          : j.status === "cancelled" ? trad("j.s2.cancelled", "Conversione annullata.") : j.error;
        break;
      }
      $("s2-msg").textContent = trad("j.s2.running", "Conversione in corso… {pct}%", { pct: j.pct });
      await new Promise((r) => setTimeout(r, 700));
    }
    jid = null;
    busy(false);
    stato();
  }

  async function parti() {
    const path = $("s2-src").value.trim();
    if (!path) return;
    busy(true);
    $("s2-bar").value = 0;
    $("s2-msg").textContent = "";
    try { jid = (await api("/api/switch2/convert", { path, format: $("s2-to").value })).id; } catch (e) { busy(false); $("s2-msg").textContent = e.message; return; }
    segui();
  }

  function aggancia() {
    const go = $("s2-go");
    if (!go || go.dataset.bound) return;
    go.dataset.bound = "1";
    go.addEventListener("click", parti);
    $("s2-cancel").addEventListener("click", () => { if (jid) api(`/api/switch2/job/${jid}/cancel`, {}).catch(() => {}); });
    for (const [id, kind] of [["s2-pick-file", "file"], ["s2-pick-dir", "folder"]]) {
      $(id).addEventListener("click", async () => { const p = await global.pickPath(kind); if (p) $("s2-src").value = p; });
    }
    stato();
  }

  new global.MutationObserver(aggancia).observe(doc.body, { childList: true, subtree: true });
  aggancia();
})(typeof window !== "undefined" ? window : globalThis);
