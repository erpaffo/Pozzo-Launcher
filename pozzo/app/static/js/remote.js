"use strict";
/* Pozzo Launcher - frontend: telefono e streaming. Script classico: ambito globale condiviso con gli altri file di js/ (ordine in index.html). */

/* ---- telefono e streaming */
let phoneTimer = 0;
const EMU_DSU = [
  ["Cemu (Wii U)", "Opzioni › Impostazioni di input › scheda del controller › Movimento: «DSU» (cemuhook), 127.0.0.1:26760."],
  ["Ryujinx (Switch)", "Opzioni › Impostazioni › Input › Configura › Movimento: «CemuHook compatible», server 127.0.0.1, porta 26760, slot del giocatore."],
  ["Dolphin (Wii)", "Controller › Sorgenti di input alternative › DSU Client: attiva, 127.0.0.1:26760; poi nel Wii Remote scegli il dispositivo DSUClient."],
  ["Azahar / Citra (3DS)", "Emulazione › Configura › Controlli › Movimento/Touch: «CemuhookUDP», 127.0.0.1:26760."],
];
async function loadRemote() {
  clearTimeout(phoneTimer);
  let ph, sun;
  try { [ph, sun] = await Promise.all([api("/api/phone"), api("/api/sunshine")]); } catch (e) { return toast(e.message, true); }
  $("#ph-on").checked = ph.enabled;
  const mins = ph.code_until ? Math.max(0, Math.round((ph.code_until - Date.now() / 1000) / 60)) : 0;
  $("#ph-box").innerHTML = !ph.enabled ? "" : ph.error ? `<p class="status-bad">${esc(ph.error)}</p>` : !ph.running ? `<p class="muted">Avvio…</p>` : `
    <h4>🔒 Certificato del PC (una volta sola)</h4>
    <p class="muted small">Con un certificato «autofirmato» il telefono mostra <i>connessione non privata</i> e il browser
      <b>rifiuta di installare l'app</b>. Installando invece la CA di questo PC l'avviso sparisce, l'app si installa e
      funziona anche senza rete.</p>
    <div class="ph-pair"${ph.ca_installed ? " hidden" : ""}>
      <div class="ph-qr">${ph.qr_ca || ""}</div>
      <div class="ph-steps">
        <b>Installa il certificato sul telefono</b>
        <ol>
          <li>Inquadra il QR (o apri <code>${esc(ph.ca_url || "")}</code>) e accetta l'avviso <i>Avanzate › Procedi</i>:
            è l'ultima volta che compare.</li>
          <li><b>Android</b>: Impostazioni › Sicurezza › Crittografia e credenziali › Installa un certificato ›
            <i>Certificato CA</i> › «Avvisa comunque» › scegli <code>PozzoLauncher-CA.crt</code>.</li>
          <li><b>iPhone/iPad</b>: Impostazioni › Generali › VPN e gestione dispositivi › installa il profilo; poi
            Impostazioni › Generali › Info › <i>Impostazioni attendibilità certificati</i> › attiva «Pozzo Launcher CA».</li>
          <li>Chiudi e riapri la pagina: niente avviso, e in alto compare <b>⬇ Installa</b> (su iPhone/iPad:
            <i>Condividi › Aggiungi alla schermata Home</i>).</li>
        </ol>
        <p class="muted small">Se il PC cambia indirizzo IP il certificato del server viene rifatto da solo, ma la CA resta
          la stessa: non serve reinstallare niente. La chiave <code>ca.key</code> resta nella cartella <code>certs</code> del PC.<br>
          Se il telefono non riesce a scaricarlo (download bloccato per l'avviso di sicurezza), salvalo sul PC con
          <a href="/api/phone/ca" download="PozzoLauncher-CA.crt">questo link</a> e passalo al telefono con cavo, e-mail o cloud.</p>
      </div>
    </div>
    <label class="small"><input type="checkbox" id="ph-ca-ok"${ph.ca_installed ? " checked" : ""}>
      Ho già installato il certificato sul telefono (nascondi il QR)</label>
    <div class="ph-pair">
      <div class="ph-qr">${ph.qr}</div>
      <div class="ph-steps">
        <b>Abbina un telefono</b>
        <ol>
          <li>Collega il telefono alla stessa rete Wi-Fi del PC.</li>
          <li>Inquadra il QR con la fotocamera, oppure apri <code>${esc(ph.urls[0] || "")}</code> e inserisci il codice
            <span class="ph-code">${esc(ph.code || "")}</span> <span class="muted small">(valido ancora ${mins} min, <a href="#" id="ph-newcode">nuovo codice</a>)</span></li>
          <li>Se compare ancora «non privata», manca il certificato del PC (punto sopra).</li>
        </ol>
        <p class="muted small">La prima volta Windows può chiedere di consentire Pozzo Launcher sulle reti private: rispondi Sì.</p>
      </div>
    </div>
    <h4>Telefoni abbinati</h4>
    ${ph.devices.length ? `<table class="emu">${ph.devices.map((d) => `<tr><td>📱 ${esc(d.name)}</td>
      <td class="muted small">abbinato ${new Date(d.created * 1000).toLocaleDateString("it")} · ultimo uso ${new Date(d.last * 1000).toLocaleString("it", { dateStyle: "short", timeStyle: "short" })}</td>
      <td><button class="btn" data-revoke="${esc(d.id)}">Revoca</button></td></tr>`).join("")}</table>` : `<p class="muted small">Nessuno.</p>`}
    <h4>Controller dal telefono</h4>
    <p class="small">${ph.vigem ? "✅ Controller virtuale Xbox pronto (ViGEmBus)" : `❌ ${esc(ph.vigem_error)} — <a href="#" data-open="https://github.com/nefarius/ViGEmBus/releases">scarica ViGEmBus</a>`}<br>
      ${ph.dsu ? "✅ Giroscopio per gli emulatori: server DSU attivo su 127.0.0.1:26760" : `❌ ${esc(ph.dsu_error || "Server DSU non attivo")}`}</p>
    ${ph.controllers.length ? `<div class="lobby small">${[0, 1, 2, 3].map((slot) => {
      const c = ph.controllers.find((x) => x.slot === slot);
      return `<div class="lb-seat" style="--pc:${c ? c.color : "#555"}"><b>Giocatore ${c ? c.player : slot + 1}</b>
        <span>${c ? `📱 ${esc(c.name)}${c.motion ? " · 🌀" : ""}` : `<i class="muted">libero</i>`}</span>
        ${c ? `<select data-swap="${slot}"><option value="">Sposta al posto…</option>${[0, 1, 2, 3].filter((s) => s !== slot)
          .map((s) => `<option value="${s}">${s + 1}</option>`).join("")}</select>` : ""}</div>`;
    }).join("")}</div>` : ""}
    <h4>Controller speciali</h4>
    <div class="row wrap small">
      <label class="chk"><input type="checkbox" id="ph-mouse" ${ph.mouse ? "checked" : ""}> Il telefono può muovere il mouse del PC
        <span class="muted">(pistola ottica / touchpad: dà il controllo del mouse a chi ha un telefono abbinato)</span></label>
      <label class="chk"><input type="checkbox" id="ph-touch" ${ph.touchscreen ? "checked" : ""}> Il telefono fa da schermo touch nei giochi DS e 3DS
        <span class="muted">(se è collegato all'avvio: sul PC solo lo schermo superiore, il touch sul telefono; con melonDS, Citra, Azahar, Lime3DS)</span></label>
      <label class="chk">Se il telefono non si usa per <input class="field" id="ph-touch-idle" type="number" min="5" max="600" step="5" value="${ph.screen_idle || 30}" style="width:70px"> secondi
        lo schermo inferiore ricompare sul PC
        <span class="muted">(prima resta nascosto dietro lo schermo superiore; se il telefono si scollega torna dopo pochi secondi)</span></label>
    </div>
    <div class="row wrap small">
      <label>Microfono del telefono (SingStar) → uscita del PC
        <select class="field" id="ph-mic"><option value="">Automatica (cavo virtuale, es. VB-Cable)</option>
          ${ph.mic_devices.map((d) => `<option ${d === ph.mic_device ? "selected" : ""}>${esc(d)}</option>`).join("")}</select></label>
      ${ph.mic_devices.some((d) => /CABLE|VB-Audio/i.test(d)) ? "" : `<span class="muted">Nessun cavo virtuale: <a href="#" data-open="https://vb-audio.com/Cable/">installa VB-Cable</a> (gratis), poi in PCSX2 scegli «CABLE Output» come microfono.</span>`}
    </div>
    <div class="row wrap small emusetup">
      <label>Telefoni <input class="field" id="es-n" type="number" min="1" max="4" value="${Math.max(1, ph.controllers.length)}" style="width:60px"></label>
      <button class="btn" data-es="pcsx2_buzz">🔴 Configura PCSX2 per Buzz!</button>
      <button class="btn" data-es="pcsx2_guitar">🎸 Configura PCSX2 per la chitarra</button>
      <button class="btn" data-es="dolphin_wii">🎮 Configura Dolphin per il Wii Remote</button>
    </div>
    <p class="muted small">Scrive le impostazioni dell'emulatore (chiudilo prima) e ne fa una copia accanto all'originale.
      Buzz!: porta USB 1 = Buzz Controller, telefono N = giocatore N. Chitarra: le porte 1..N diventano chitarre.
      Dolphin: Wii Remote 1..N = telefono 1..N, con Nunchuk, tasti e movimento dal server DSU.
      <a href="#" data-esundo="pcsx2_buzz">Annulla PCSX2</a> · <a href="#" data-esundo="dolphin_wii">Annulla Dolphin</a></p>
    <details class="small"><summary>Come attivare il giroscopio negli emulatori</summary>
      <ul>${EMU_DSU.map(([n, t]) => `<li><b>${n}</b>: ${t}</li>`).join("")}</ul>
      <p class="muted">Per i giochi senza giroscopio, nell'app del telefono scegli 🎯 <b>Mira</b>: inclinando il telefono si muove la levetta destra.</p>
    </details>`;
  const s = sun;
  if (document.activeElement.id !== "ph-public") $("#ph-public").value = ph.public_url || "";
  if (document.activeElement.id !== "ph-video") $("#ph-video").value = ph.video_addr || "";
  const inv = ph.invite || {};
  const gmin = inv.until ? Math.max(0, Math.round((inv.until - Date.now() / 1000) / 60)) : 0;
  $("#guest-box").innerHTML = `<p class="small">${inv.code
    ? `Manda all'amico il link <code>${esc(inv.link)}</code> e il codice <span class="ph-code">${esc(inv.code)}</span>
       <span class="muted small">(vale ancora ${gmin} min, per un ospite solo)</span>`
    : `<span class="muted">Nessun invito attivo: l'ospite non può entrare.</span>`}
    <button class="btn primary" id="ph-invite">${inv.code ? "Nuovo invito" : "Crea invito per un amico"}</button></p>
    <p class="muted small">Il video va con Moonlight: l'amico scrive l'indirizzo qui sopra e il PIN che Moonlight gli
      mostra, e il PC li conferma (serve un utente e una password di Sunshine salvati qui sotto).</p>
    ${(ph.guests || []).length ? `<h4>Ospiti</h4><table class="emu">${ph.guests.map((d) => `<tr><td>🙋 ${esc(d.name)}</td>
      <td class="muted small">entrato ${new Date(d.created * 1000).toLocaleString("it", { dateStyle: "short", timeStyle: "short" })}</td>
      <td><button class="btn" data-revoke="${esc(d.id)}">Togli</button></td></tr>`).join("")}</table>` : ""}`;
  $("#sun-box").innerHTML = !s.installed ? `<p>Sunshine non è installato. <a href="#" data-open="https://github.com/LizardByte/Sunshine/releases">Scaricalo</a>, poi riapri questa scheda.</p>`
    : `<p class="small">${s.service === "running"
      ? `✅ Sunshine è in esecuzione${s.start_mode && s.start_mode !== "auto" ? ` · ⚠ ma non parte con Windows: dopo un riavvio Moonlight non troverà il PC. <button class="btn" id="sun-start">Avvia sempre con Windows</button>` : ""}`
      : s.service === "stopped"
      ? `⏸ Sunshine è installato ma fermo: Moonlight non può trovare il PC. <button class="btn primary" id="sun-start">▶ Avvia Sunshine (anche con Windows)</button> <span class="muted">(chiede una volta i permessi di amministratore)</span>` : "Sunshine installato"}
      · <a href="#" data-open="${esc(s.web)}">interfaccia web di Sunshine</a> (per abbinare Moonlight con il PIN)</p>
    <div class="row wrap">
      <label>Utente di Sunshine <input class="field" id="sun-user" value="${esc(s.user)}" autocomplete="off"></label>
      <label>Password <input class="field" id="sun-pass" type="password" placeholder="${s.has_password ? "già salvata" : ""}" autocomplete="new-password"></label>
      <label>Giochi da pubblicare <input class="field" id="sun-count" type="number" min="0" max="100" value="${s.count}" style="width:80px"></label>
      <button class="btn primary" id="sun-pub">📡 Pubblica in Moonlight</button>
    </div>
    ${s.error ? `<p class="status-bad small">${esc(s.error)}</p>` : ""}
    <p class="muted small">Verranno pubblicati: <b>Pozzo Launcher Big Picture</b> (da lì scegli qualsiasi gioco col controller),
      <b>▶ Gioco in corso</b> (lo schermo del PC: per entrare nel gioco avviato dall'app del telefono con «Gioca su questo telefono»)
      ${s.preview.length ? ` e ${s.preview.length} giochi (in corso, preferiti, recenti): ${esc(s.preview.slice(0, 8).join(", "))}${s.preview.length > 8 ? "…" : ""}` : ""}.
      Le altre app di Sunshine non vengono toccate.</p>
    ${s.last ? `<p class="small">Ultima pubblicazione: ${new Date(s.last.time * 1000).toLocaleString("it", { dateStyle: "short", timeStyle: "short" })} · ${s.last.published} app</p>` : ""}
    ${s.apps ? `<p class="small muted">App in Moonlight ora: ${esc(s.apps.map((a) => a.name).join(" · "))}</p>` : ""}`;
  api("/api/stream/optimize").then((o) => {
    const ico = { ok: "✓", warn: "⚠", info: "ℹ" };
    $("#stream-opt").innerHTML = `<div class="health">` + o.checks.map((x) => `<div class="hl-row hl-${x.level === "info" ? "ok" : x.level}">`
      + `<span class="hl-ico">${ico[x.level] || "•"}</span><div class="hl-txt"><b>${esc(x.title)}</b>${x.detail ? `<div class="muted small">${esc(x.detail)}</div>` : ""}</div></div>`).join("") + `</div>`;
  }).catch(() => {});
  if (ph.enabled && (SET.tab === "controller" || SET.tab === "streaming") && settingsOpen()) phoneTimer = setTimeout(loadRemote, ph.running ? 5000 : 1000);
}
async function phoneSet(body) {
  try { await api("/api/phone", { body }); } catch (e) { toast(e.message, true); }
  loadRemote();
}
