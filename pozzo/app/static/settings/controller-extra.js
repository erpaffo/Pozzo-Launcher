async function cpInit() {
  const $ = (s) => document.querySelector(s), msg = $("#cp-msg");
  if (!$("#cp-type") || $("#cp-type").dataset.ready) return;
  $("#cp-type").dataset.ready = "1";
  for (const [id, key, def] of [["#ds-led", "dsLed", true], ["#ds-rumble", "dsRumble", false]]) { // pad Sony: salvate nel dispositivo (dualsense.js)
    $(id).checked = store.get(key, def);
    $(id).onchange = (e) => store.set(key, e.target.checked);
  }
  try {
    const d = await (await fetch("/api/controller-profiles")).json();
    $("#cp-type").innerHTML = Object.entries(d.types).map(([k, v]) => `<option value="${k}"${k === d.detected ? " selected" : ""}>${v}</option>`).join("");
    $("#cp-emu").innerHTML = d.emulators.filter((e) => e.exe).map((e) => `<option value="${esc(e.id)}">${esc(e.id)}${e.exists ? "" : t("k.ctrl.new")}</option>`).join("") || "<option value=''>" + t("k.ctrl.no_emu") + "</option>";
  } catch (e) { msg.textContent = t("k.ctrl.read_fail"); }
  $("#cp-apply").onclick = async () => {
    const r = await fetch("/api/controller-profiles/apply", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emulator: $("#cp-emu").value, type: $("#cp-type").value }) });
    const j = await r.json().catch(() => ({}));
    msg.textContent = r.ok ? t("k.ctrl.done", {file: j.file}) : (j.detail || t("k.ctrl.err"));
  };
}
// i pannelli delle impostazioni entrano via innerHTML: i loro <script> non girano, quindi si aspetta il campo
new MutationObserver(() => { if (document.querySelector("#cp-type")) cpInit(); }).observe(document.body, { childList: true, subtree: true });
