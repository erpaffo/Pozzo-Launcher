"use strict";
/* Badge di verifica ROM; l'endpoint locale fornisce lo stato già calcolato dal report DAT. */
window.addEventListener("pozzo:detail-open", async (event) => {
  const game = event.detail;
  const box = document.querySelector("#detail-body .files");
  if (!box) return;
  box.querySelector(".rom-verify")?.remove();
  try {
    const result = await api(`/api/game/${game.id}/verify`);
    if (window.S?.detail?.id !== game.id) return;
    const labels = {
      verificata: "ROM verificata",
      sconosciuta: "ROM sconosciuta",
      "nessun DAT": "Nessun DAT disponibile",
    };
    const label = labels[result.status];
    if (!label) return;
    const badge = document.createElement("span");
    badge.className = `tag rom-verify rom-verify-${result.status.replaceAll(" ", "-")}`;
    badge.textContent = label;
    badge.title = result.match_by === "hash"
      ? `Corrispondenza per hash${result.hash_kind ? ` (${result.hash_kind.toUpperCase()})` : ""}`
      : result.match_by === "name" ? "Corrispondenza solo per nome" : "";
    box.append(document.createElement("br"), badge);
  } catch {
    box.querySelector(".rom-verify")?.remove();
  }
});
