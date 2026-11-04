// Store estensioni: catalogo dalle fonti con anteprima screenshot, dettagli completi,
// guida all'uso (come funziona), filtri veloci e gestione installazione/aggiornamento/rimozione.

const BTN = { available: "⬇ Installa", update: "⬆ Aggiorna", installed: "Rimuovi", incompatible: "Non compatibile" };
const short = (link) => String(link || "").replace(/^https:\/\/(github\.com\/|raw\.githubusercontent\.com\/)?/, "").replace(/\/index\.json$/, "");

// Permessi (funzioni pure, testate in tests/test_ext_permissions_ui.js).
// Sensibili: scrittura (libreria:scrittura, file:scrittura), accesso ai file, avvio di programmi, rete:* (qualsiasi sito).
const PERM_SENSIBILI = /(^|:)(scrittura|\*)(:|$)|^(file|avvio)(:|$)/;
// Voci dei permessi dell'estensione: etichetta italiana se c'è, altrimenti l'id grezzo.
export function permessiVoci(x) {
  const etichette = new Map((Array.isArray(x.permissions_labels) ? x.permissions_labels : [])
    .filter((l) => l && typeof l.id === "string" && typeof l.label === "string")
    .map((l) => [l.id, l.label]));
  return (Array.isArray(x.permissions) ? x.permissions : []).map(String).map((id) => ({
    id, label: etichette.get(id) || id, sensibile: PERM_SENSIBILI.test(id),
  }));
}
// Cosa mostrare prima di installare: null = nessuna conferma. Su aggiornamento conta solo ciò che è nuovo, se si conoscono i permessi installati.
export function permessiConferma(x) {
  if (x.permissions_unknown) return { nonDichiarati: true, voci: [] };
  const gia = x.state === "update" && Array.isArray(x.installed_permissions) ? new Set(x.installed_permissions) : null;
  const voci = permessiVoci(x).filter((v) => !gia || !gia.has(v.id));
  return voci.length ? { nonDichiarati: false, voci } : null;
}

// Scopri: regole per id di estensione. Restituisce la ragione da mostrare, o null se non la consiglia.
// Un dato sconosciuto (ctx null: libreria o lista desideri non disponibili) fa valere la regola comunque.
const sconosciuto = (v) => v == null;
const REGOLE = {
  steamgriddb: () => ({ reason: "Copertine e artwork ad alta risoluzione per i tuoi giochi" }),
  diario: () => ({ reason: "Appunti, trucchi e cronologia delle sessioni per ogni gioco" }),
  obiettivi: () => ({ reason: "Sfide personali con distintivi da sbloccare giocando" }),
  statistiche: (c) => (sconosciuto(c.games) || c.games > 0 ? { reason: "Grafici del tempo di gioco per console e store" } : null),
  pulizia: (c) => (sconosciuto(c.games) || c.games > 200 ? { reason: `Hai ${c.games} giochi: trova duplicati e titoli dimenticati` } : null),
  minerva: (c) => (sconosciuto(c.consoles) ? { reason: "Archivi pronti per le console, con store preimpostati" }
    : c.consoles.length ? { reason: `Hai giochi ${c.consoles[0].toUpperCase()}: importa gli archivi per quella console` } : null),
  "calendario-uscite": (c) => (sconosciuto(c.wishlist) ? { reason: "Le prossime uscite dei generi che giochi di più" }
    : c.wishlist > 0 ? { reason: `Hai ${c.wishlist} giochi in lista desideri: scopri quando escono` } : null),
  "pc-adatto": (c) => (sconosciuto(c.consoles) ? { reason: "Scopri se il tuo PC regge i giochi e con quali impostazioni" }
    : c.consoles.length ? { reason: `Hai giochi ${c.consoles[0].toUpperCase()}: scopri se il tuo PC li emula bene` } : null),
  notizie: () => ({ reason: "Le notizie di case e siti, con quelle dei tuoi giochi in evidenza" }),
  sconti: (c) => (sconosciuto(c.wishlist) ? { reason: "Sconti, bundle e giochi gratis del momento" }
    : c.wishlist > 0 ? { reason: `Hai ${c.wishlist} giochi in lista desideri: guarda quali sono in sconto` } : null),
  recensioni: () => ({ reason: "Punteggi Metacritic, OpenCritic e Steam nel dettaglio di ogni gioco" }),
};

// Suggerimenti «Per te» tra le estensioni non installate, nell'ordine ricevuto. ctx: {consoles, games, wishlist}.
export function suggerimenti(entries, ctx = {}) {
  const c = { consoles: null, games: null, wishlist: null, ...ctx };
  return (Array.isArray(entries) ? entries : []).flatMap((x) => {
    const regola = REGOLE[x.id];
    const r = x.state === "available" && regola ? regola(c) : null;
    return r ? [{ ...x, reason: r.reason }] : [];
  });
}

// Sezioni della tab «Scopri». Novità: le più recenti per prime (nell'indice l'ultima voce è la più recente).
export function scopri(entries, ctx = {}) {
  const disponibili = (Array.isArray(entries) ? entries : []).filter((x) => x.state === "available");
  return {
    novita: [...disponibili].reverse(),
    consigliate: disponibili.filter((x) => x.featured),
    perTe: suggerimenti(disponibili, ctx),
  };
}

export default function (gs) {
  gs.addSidebarItem({ id: "estensioni", label: "Store estensioni", icon: "🧩", view: "estensioni" });

  gs.registerView("estensioni", {
    title: "Store estensioni",
    async render(el) {
      el.innerHTML = `
        <div class="es-page">
          <div class="es-header-desc">
            <p class="muted">Esplora, installa e gestisci le estensioni per arricchire Pozzo Launcher. Clicca su qualsiasi estensione per vederne <b>screenshot</b>, <b>funzionalità</b> e la <b>guida dettagliata</b>. Dopo ogni installazione o rimozione riavvia l'app.</p>
          </div>

          <div class="es-toolbar">
            <div class="es-search-wrap">
              <span class="es-search-ico">🔍</span>
              <input id="es-filter-input" class="field es-search-input" placeholder="Cerca estensione per nome, funzione o console…" autocomplete="off">
              <button id="es-filter-clear" class="es-clear-btn" type="button" title="Cancella ricerca" hidden>✕</button>
            </div>
            <div class="es-tabs" role="tablist">
              <button class="es-tab" data-tab="discover" type="button">Scopri</button>
              <button class="es-tab" data-tab="all" type="button">Tutte (<span id="es-cnt-all">0</span>)</button>
              <button class="es-tab" data-tab="available" type="button">Disponibili (<span id="es-cnt-avail">0</span>)</button>
              <button class="es-tab" data-tab="installed" type="button">Installate (<span id="es-cnt-inst">0</span>)</button>
            </div>
          </div>

          <details class="es-src">
            <summary>Fonti delle estensioni (<span id="es-src-count">1</span> configurate)</summary>
            <div id="es-sources"></div>
            <form id="es-add" class="es-add">
              <input class="field" name="link" placeholder="https://github.com/utente/repository o URL index.json" autocomplete="off" required>
              <button class="btn" type="submit">Aggiungi fonte</button>
            </form>
            <p class="muted small">Incolla il link GitHub di un'estensione o di un altro store. Le estensioni eseguono codice sul PC: aggiungi solo fonti di cui ti fidi.</p>
          </details>

          <div id="es-list" class="es-cards-grid">
            <p class="muted">Caricamento catalogo estensioni…</p>
          </div>
        </div>

        <!-- Modale Scheda Dettagli Estensione -->
        <dialog id="es-modal" class="es-modal">
          <div class="es-modal-chrome">
            <div class="es-modal-header">
              <div class="es-m-identity">
                <span id="es-m-icon" class="es-m-icon">🧩</span>
                <div>
                  <h2 id="es-m-title" class="es-m-title">Nome Estensione</h2>
                  <div class="es-m-meta">
                    <span id="es-m-version" class="es-pill-meta">v1.0</span>
                    <span id="es-m-author" class="muted small">di Pozzo Launcher</span>
                    <span id="es-m-minapp" class="muted small">· Richiede >= 0.7.1</span>
                    <span id="es-m-source" class="es-source-pill">Store ufficiale</span>
                  </div>
                </div>
              </div>
              <div class="es-m-actions">
                <div id="es-m-btn-box"></div>
                <button id="es-m-close" class="es-close-btn" type="button" aria-label="Chiudi finestra">✕</button>
              </div>
            </div>

            <div class="es-modal-body">
              <!-- Screenshot Showcase -->
              <div id="es-m-screenshot-wrap" class="es-m-screenshot-wrap">
                <!-- Immagine iniettata dinamicamente in openDetailModal -->
              </div>

              <!-- Descrizione & Funzionalità -->
              <div class="es-m-section">
                <h4>Descrizione completa</h4>
                <p id="es-m-longdesc" class="es-m-text"></p>
              </div>

              <!-- Come Funziona -->
              <div class="es-m-section">
                <h4>Come funziona e dove trovarla</h4>
                <div id="es-m-guide" class="es-m-guide-box"></div>
              </div>

              <!-- Caratteristiche -->
              <div id="es-m-features-sec" class="es-m-section">
                <h4>Caratteristiche principali</h4>
                <ul id="es-m-features" class="es-m-features-list"></ul>
              </div>

              <!-- Dettagli Tecnici -->
              <div class="es-m-section es-m-tech">
                <h4>Specifiche tecniche</h4>
                <div class="es-m-tech-grid">
                  <div><b>ID estensione:</b> <code id="es-m-id"></code></div>
                  <div><b>Stato attuale:</b> <span id="es-m-state"></span></div>
                  <div><b>File inclusi:</b> <span id="es-m-files" class="small muted"></span></div>
                  <div><b>Origine file:</b> <span id="es-m-origin" class="small muted"></span></div>
                  <div class="es-m-perms-row"><b>Permessi:</b> <span id="es-m-perms" class="es-m-perms"></span></div>
                </div>
              </div>
            </div>
          </div>
        </dialog>

        <!-- Conferma permessi prima di installare -->
        <dialog id="es-perm-modal" class="es-perm-modal">
          <form method="dialog" class="es-perm-form">
            <h3 id="es-perm-title">Questa estensione potrà:</h3>
            <div id="es-perm-body"></div>
            <div class="es-perm-actions">
              <button class="btn" value="cancel" type="submit">Annulla</button>
              <button class="btn primary" value="ok" type="submit">Installa</button>
            </div>
          </form>
        </dialog>
      `;

      const list = el.querySelector("#es-list");
      const srcBox = el.querySelector("#es-sources");
      const filterInput = el.querySelector("#es-filter-input");
      const filterClear = el.querySelector("#es-filter-clear");
      const tabBtns = el.querySelectorAll(".es-tab");
      const modal = el.querySelector("#es-modal");
      const permDlg = el.querySelector("#es-perm-modal");

      const permTag = (v) => `<span class="es-perm-tag${v.sensibile ? " sens" : ""}">${v.sensibile ? "⚠️ " : ""}${gs.esc(v.label)}</span>`;

      // Conferma permessi prima di installare: resolve(true) se l'utente sceglie «Installa»
      const confermaPermessi = (x) => {
        const c = permessiConferma(x);
        if (!c) return Promise.resolve(true);
        el.querySelector("#es-perm-body").innerHTML = c.nonDichiarati
          ? `<p class="es-perm-warn">⚠️ Questa estensione non dichiara i permessi: potrebbe accedere a tutto.</p>`
          : `<ul class="es-perm-list">${c.voci.map((v) => `<li class="${v.sensibile ? "sens" : ""}">${v.sensibile ? "⚠️" : "✓"} ${gs.esc(v.label)}</li>`).join("")}</ul>`;
        if (typeof permDlg.showModal !== "function")  // browser senza <dialog>: conferma testuale
          return Promise.resolve(confirm(c.nonDichiarati ? "Questa estensione non dichiara i permessi: potrebbe accedere a tutto. Installare?"
            : `Questa estensione potrà:\n${c.voci.map((v) => `• ${v.label}`).join("\n")}\n\nInstallare?`));
        permDlg.returnValue = "";
        return new Promise((resolve) => {
          permDlg.addEventListener("close", () => resolve(permDlg.returnValue === "ok"), { once: true });
          permDlg.showModal();
        });
      };

      let catalogData = { items: [], sources: [] };
      let currentFilterTab = null; // null: alla prima lettura, «Scopri» se ci sono estensioni da installare
      let searchQuery = "";
      let activeDetailItem = null;

      // Apertura Modale Dettagli Estensione
      const openDetailModal = (x) => {
        if (!x) return;
        activeDetailItem = x;

        // Apri subito il dialog per calcolare correttamente layout e dimensioni viewport
        if (typeof modal.showModal === "function") {
          if (!modal.open) modal.showModal();
        } else {
          modal.setAttribute("open", "");
        }

        el.querySelector("#es-m-icon").textContent = x.icon || "🧩";
        el.querySelector("#es-m-title").textContent = x.name || x.id;
        el.querySelector("#es-m-version").textContent = `v${x.version || "?"}`;
        el.querySelector("#es-m-author").textContent = x.author ? `di ${x.author}` : "";
        el.querySelector("#es-m-minapp").textContent = x.min_app ? `· Richiede PozzoLauncher >= ${x.min_app}` : "";
        
        const srcEl = el.querySelector("#es-m-source");
        if (x.official) {
          srcEl.textContent = "⭐ Store ufficiale";
          srcEl.className = "es-source-pill official";
        } else {
          srcEl.textContent = `🔗 da ${short(x.source)}`;
          srcEl.className = "es-source-pill third";
        }

        // Pulsante di azione dentro il modale
        const btnBox = el.querySelector("#es-m-btn-box");
        let btnHtml = "";
        if (x.state === "update" && !x.dev) {
          btnHtml = `<button class="btn primary" data-act="installa" data-id="${gs.esc(x.id)}" data-src="${gs.esc(x.source)}">${BTN.update}</button>`;
        } else if (x.state === "available") {
          btnHtml = `<button class="btn primary" data-act="installa" data-id="${gs.esc(x.id)}" data-src="${gs.esc(x.source)}">${BTN.available}</button>`;
        } else if (x.state === "incompatible") {
          btnHtml = `<button class="btn" disabled>${BTN.incompatible}</button>`;
        } else if ((x.state === "installed" || x.state === "update") && !x.dev) {
          btnHtml = `<button class="btn bad" data-act="rimuovi" data-id="${gs.esc(x.id)}">${BTN.installed}</button>`;
        } else if (x.state === "installed" && x.dev) {
          btnHtml = `<span class="es-badge dev">Copia di sviluppo</span>`;
        }
        btnBox.innerHTML = btnHtml;

        // Screenshot Showcase Dinamico ed Eager (senza problemi di lazy loading nei dialog)
        const wrap = el.querySelector("#es-m-screenshot-wrap");
        wrap.innerHTML = `
          <div class="es-m-screenshot-loading">
            <span class="es-spinner"></span>
            <span class="muted small">Caricamento anteprima…</span>
          </div>
        `;

        const img = document.createElement("img");
        img.className = "es-m-screenshot";
        img.alt = `Anteprima di ${x.name || x.id}`;

        const verParam = encodeURIComponent(x.version || "1");
        const staticUrl = `/static/extensions-preview/${encodeURIComponent(x.id)}.png?v=${verParam}`;
        const pluginUrl = `/plugins/${encodeURIComponent(x.id)}/screenshot.png?v=${verParam}`;
        const remoteUrl = x.base && x.screenshot ? (x.base.endsWith("/") ? x.base : x.base + "/") + x.screenshot : "";

        let triedPlugin = false;
        let triedRemote = false;

        img.onload = () => {
          if (activeDetailItem?.id !== x.id) return;
          wrap.innerHTML = "";
          wrap.appendChild(img);
        };

        img.onerror = () => {
          if (activeDetailItem?.id !== x.id) return;
          if (!triedPlugin) {
            triedPlugin = true;
            img.src = pluginUrl;
          } else if (!triedRemote && remoteUrl) {
            triedRemote = true;
            img.src = remoteUrl;
          } else {
            wrap.innerHTML = `
              <div class="es-m-screenshot-fallback">
                <span class="es-fallback-icon">${x.icon || "🖼️"}</span>
                <span class="muted">Nessuna immagine di anteprima disponibile</span>
              </div>
            `;
          }
        };

        // Avvio caricamento con URL primario
        img.src = staticUrl;

        // Se l'immagine è già in cache e completa, aggiungila subito
        if (img.complete && img.naturalWidth > 0) {
          wrap.innerHTML = "";
          wrap.appendChild(img);
        }

        // Descrizione completa
        const longDesc = x.long_description || x.description || "Nessuna descrizione dettagliata disponibile.";
        el.querySelector("#es-m-longdesc").textContent = longDesc;

        // Come funziona / Guida
        const guideBox = el.querySelector("#es-m-guide");
        if (x.how_it_works) {
          const steps = x.how_it_works.split(/\\n|\n/).filter((s) => s.trim().length > 0);
          guideBox.innerHTML = steps.map((s) => {
            const numMatch = s.match(/^(\d+)\.\s*(.*)$/);
            if (numMatch) {
              return `<div class="es-step-row"><span class="es-step-num">${numMatch[1]}</span><div>${gs.esc(numMatch[2])}</div></div>`;
            }
            return `<div class="es-step-row"><span class="es-step-bullet">▸</span><div>${gs.esc(s)}</div></div>`;
          }).join("");
          guideBox.closest(".es-m-section").hidden = false;
        } else {
          guideBox.innerHTML = `<p class="muted small">Questa estensione non richiede passaggi di configurazione aggiuntivi.</p>`;
        }

        // Caratteristiche
        const featSec = el.querySelector("#es-m-features-sec");
        const featList = el.querySelector("#es-m-features");
        if (Array.isArray(x.features) && x.features.length) {
          featSec.hidden = false;
          featList.innerHTML = x.features.map((f) => `<li><span class="es-feat-chk">✓</span> ${gs.esc(f)}</li>`).join("");
        } else {
          featSec.hidden = true;
        }

        // Specifiche tecniche
        el.querySelector("#es-m-id").textContent = x.id;
        let stLabel = "Non installata";
        if (x.state === "installed") stLabel = "Installata ed attiva al riavvio";
        else if (x.state === "update") stLabel = `Aggiornamento disponibile (installata: v${x.installed_version})`;
        else if (x.state === "incompatible") stLabel = `Non compatibile (richiede PozzoLauncher >= ${x.min_app})`;
        el.querySelector("#es-m-state").textContent = stLabel;

        const filesArr = Array.isArray(x.files) ? x.files : [];
        el.querySelector("#es-m-files").textContent = filesArr.length ? filesArr.join(", ") : "plugin.toml";
        el.querySelector("#es-m-origin").textContent = x.official ? "Repository ufficiale Pozzo Launcher" : (x.source || "Fonte esterna");

        const vociPerm = permessiVoci(x);
        el.querySelector("#es-m-perms").innerHTML = x.permissions_unknown
          ? `<span class="es-perm-tag sens">⚠️ Non dichiarati: potrebbe accedere a tutto</span>`
          : (vociPerm.length ? vociPerm.map(permTag).join("") : `<span class="muted">Nessuno</span>`);

        if (typeof modal.showModal === "function") {
          if (!modal.open) modal.showModal();  // gia' aperto sopra: una seconda showModal() lancia InvalidStateError
        } else {
          modal.setAttribute("open", "");
        }
      };

      const closeModal = () => {
        if (typeof modal.close === "function") modal.close();
        else modal.removeAttribute("open");
        activeDetailItem = null;
      };

      el.querySelector("#es-m-close").onclick = closeModal;
      modal.onclick = (e) => {
        if (e.target === modal) closeModal();
      };

      // Disegna elenco e filtra
      const draw = async () => {
        let d;
        try {
          d = await gs.api("/plugin-api/estensioni/catalogo");
          catalogData = d;
        } catch (e) {
          list.innerHTML = `<p class="status-bad">Impossibile caricare il catalogo delle estensioni: ${gs.esc(e.message)}</p>`;
          return;
        }

        // Aggiorna fonti
        el.querySelector("#es-src-count").textContent = String(d.sources.length);
        srcBox.innerHTML = d.sources.map((s) => `
          <div class="es-srow">
            <span>
              ${s.official ? "⭐ <b>Store ufficiale</b>" : "🔗"} 
              <span class="muted small">${gs.esc(short(s.link))}</span>
              <span class="muted small">· ${s.count} ${s.count === 1 ? "estensione" : "estensioni"}</span>
              ${s.errors.length ? `<div class="status-bad small">${s.errors.map(gs.esc).join("<br>")}</div>` : ""}
            </span>
            ${s.official ? "" : `<button class="btn" data-del="${gs.esc(s.link)}">Rimuovi fonte</button>`}
          </div>
        `).join("");

        // Calcola contatori tab
        const totalCount = d.items.length;
        const installedCount = d.items.filter((x) => x.state === "installed" || x.state === "update").length;
        const availableCount = d.items.filter((x) => x.state === "available" || x.state === "update").length;

        el.querySelector("#es-cnt-all").textContent = String(totalCount);
        el.querySelector("#es-cnt-inst").textContent = String(installedCount);
        el.querySelector("#es-cnt-avail").textContent = String(availableCount);

        if (currentFilterTab === null) {
          currentFilterTab = availableCount > 0 ? "discover" : "all";
          tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === currentFilterTab));
        }

        // Filtra elementi per tab e ricerca
        const discover = currentFilterTab === "discover";
        const q = searchQuery.toLowerCase().trim();
        const filtered = d.items.filter((x) => {
          if (discover && x.state !== "available") return false;
          if (currentFilterTab === "installed" && x.state !== "installed" && x.state !== "update") return false;
          if (currentFilterTab === "available" && x.state !== "available" && x.state !== "update") return false;

          if (q) {
            const corpus = [
              x.name, x.id, x.description, x.author, x.long_description,
              ...(Array.isArray(x.features) ? x.features : [])
            ].join(" ").toLowerCase();
            if (!corpus.includes(q)) return false;
          }
          return true;
        });

        list.classList.toggle("es-cards-grid", !discover); // la tab Scopri ha le sue sezioni, non una griglia sola
        if (!filtered.length && discover && !q) {
          list.innerHTML = `<div class="es-empty-state"><span class="es-empty-ico">🎉</span><p>Hai già installato tutto ciò che ti consiglio</p></div>`;
          return;
        }
        if (!filtered.length) {
          list.innerHTML = `
            <div class="es-empty-state">
              <span class="es-empty-ico">🔍</span>
              <p>Nessuna estensione corrisponde ai criteri di ricerca selezionati.</p>
              ${q ? `<button class="btn" id="es-reset-search">Mostra tutte le estensioni</button>` : ""}
            </div>
          `;
          const resetBtn = list.querySelector("#es-reset-search");
          if (resetBtn) {
            resetBtn.onclick = () => {
              searchQuery = "";
              filterInput.value = "";
              filterClear.hidden = true;
              currentFilterTab = "all";
              tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === "all"));
              draw();
            };
          }
          return;
        }

        const card = (x) => {
          const verParam = encodeURIComponent(x.version || "1");
          const shotUrl = `/static/extensions-preview/${encodeURIComponent(x.id)}.png?v=${verParam}`;
          const plugUrl = `/plugins/${encodeURIComponent(x.id)}/screenshot.png?v=${verParam}`;
          const featBadges = (Array.isArray(x.features) ? x.features.slice(0, 2) : [])
            .map((f) => `<span class="es-feat-pill">${gs.esc(f)}</span>`).join("");
          const vociPerm = permessiVoci(x);
          const permBadge = x.permissions_unknown
            ? `<span class="es-perm-count sens" title="Non dichiara i permessi">⚠️ permessi non dichiarati</span>`
            : (vociPerm.length
              ? `<span class="es-perm-count${vociPerm.some((v) => v.sensibile) ? " sens" : ""}" title="${gs.esc(vociPerm.map((v) => v.label).join(", "))}">🔐 ${vociPerm.length} ${vociPerm.length === 1 ? "permesso" : "permessi"}</span>`
              : "");

          return `
            <div class="es-card" data-card-id="${gs.esc(x.id)}" role="button" tabindex="0" aria-label="Dettagli di ${gs.esc(x.name || x.id)}">
              <!-- Thumbnail Anteprima -->
              <div class="es-card-thumb-wrap">
                <img src="${shotUrl}" alt="${gs.esc(x.name)}" class="es-card-thumb" onerror="if(this.src.indexOf('/plugins/')===-1){this.src='${plugUrl}';}else{this.style.display='none';}">
                <span class="es-card-icon-floating">${x.icon || "🧩"}</span>
              </div>

              <!-- Contenuto Testuale Card -->
              <div class="es-card-main">
                <div class="es-card-header-row">
                  <div class="es-card-title-group">
                    <h3 class="es-card-title">${gs.esc(x.name || x.id)}</h3>
                    <span class="es-pill-ver">v${gs.esc(x.version || "?")}</span>
                    ${x.installed_version && x.state === "update" ? `<span class="es-pill-update" title="Installata: v${gs.esc(x.installed_version)}">Aggiornamento v${gs.esc(x.version)}</span>` : ""}
                    ${x.state === "installed" ? `<span class="es-pill-inst">Installata</span>` : ""}
                  </div>
                  <div class="es-card-meta-sub">
                    ${x.author ? `<span class="muted small">di ${gs.esc(x.author)}</span>` : ""}
                    ${x.official ? `<span class="es-pill-src official">Store ufficiale</span>` : `<span class="es-pill-src third">da ${gs.esc(short(x.source))}</span>`}
                  </div>
                </div>

                <p class="es-card-desc">${gs.esc(x.description || "")}</p>
                ${x.reason ? `<p class="es-card-reason">💡 ${gs.esc(x.reason)}</p>` : ""}

                ${featBadges || permBadge ? `<div class="es-card-badges">${featBadges}${permBadge}</div>` : ""}

                ${x.state === "incompatible" ? `<div class="status-bad small">⚠️ Richiede Pozzo Launcher ${gs.esc(x.min_app)} o superiore</div>` : ""}
                ${x.dev ? `<div class="muted small">🛠️ Collegata alla cartella di sviluppo locale</div>` : ""}
              </div>

              <!-- Azioni -->
              <div class="es-card-actions">
                ${x.state === "update" && !x.dev ? `<button class="btn primary" data-act="installa" data-id="${gs.esc(x.id)}" data-src="${gs.esc(x.source)}">${BTN.update}</button>` : ""}
                ${x.state === "available" ? `<button class="btn primary" data-act="installa" data-id="${gs.esc(x.id)}" data-src="${gs.esc(x.source)}">${BTN.available}</button>` : ""}
                ${x.state === "incompatible" ? `<button class="btn" disabled>${BTN.incompatible}</button>` : ""}
                ${(x.state === "installed" || x.state === "update") && !x.dev ? `<button class="btn" data-act="rimuovi" data-id="${gs.esc(x.id)}">${BTN.installed}</button>` : ""}
                <button class="btn es-btn-details" data-detail-id="${gs.esc(x.id)}" type="button">ℹ️ Dettagli</button>
              </div>
            </div>
          `;
        };

        if (!discover) {
          list.innerHTML = filtered.map(card).join("");
          return;
        }
        // Scopri: libreria e lista desideri per «Per te»; se non disponibili, le regole valgono sempre
        const lib = gs.library?.();
        let wish = null;
        try { wish = (await gs.api("/api/wishlist")).items.length; } catch { /* nessuna lista: regole generiche */ }
        const posseduti = lib?.games ? lib.games.filter((g) => g.store !== "online") : null;
        const s = scopri(filtered, {
          consoles: posseduti && [...new Set(posseduti.map((g) => g.platform).filter((p) => p && p !== "pc" && p !== "windows"))],  // "windows" = giochi PC, non console
          games: posseduti && posseduti.length,
          wishlist: wish,
        });
        const sezione = (titolo, items, vuoto = "") => items.length || vuoto
          ? `<section class="es-discover-sec"><h3 class="es-discover-title">${titolo}</h3>${items.length
            ? `<div class="es-cards-grid">${items.map(card).join("")}</div>` : vuoto}</section>`
          : "";
        list.innerHTML = sezione("Novità", s.novita)
          + sezione("Consigliate", s.consigliate)
          + sezione("Per te", s.perTe, `<p class="muted small">${q ? "Nessun suggerimento per questa ricerca." : "Hai già installato tutto ciò che ti consiglio"}</p>`);
      };

      // Gestione click sulla lista (Card, Dettagli, Azioni)
      list.onclick = async (e) => {
        // 1. Azione installa / rimuovi
        const actBtn = e.target.closest("[data-act]");
        if (actBtn) {
          e.stopPropagation();
          const act = actBtn.dataset.act;
          const id = actBtn.dataset.id;
          const src = actBtn.dataset.src;
          if (act === "rimuovi" && !confirm("Rimuovere questa estensione? Le sue impostazioni salvate resteranno intatte.")) return;
          if (act === "installa" && !(await confermaPermessi(catalogData.items.find((x) => x.id === id) || {}))) return;
          actBtn.disabled = true;
          try {
            await gs.api(`/plugin-api/estensioni/${act}`, { body: { id, fonte: src } });
            gs.toast(act === "installa" ? "Estensione installata: riavvia l'app per usarla" : "Estensione rimossa: riavvia l'app per applicare");
          } catch (err) {
            gs.toast(err.message, true);
          }
          await draw();
          return;
        }

        // 2. Click su bottone Dettagli o sulla Card
        const detailBtn = e.target.closest("[data-detail-id]");
        const card = e.target.closest(".es-card");
        const targetId = detailBtn ? detailBtn.dataset.detailId : (card ? card.dataset.cardId : null);

        if (targetId) {
          const item = catalogData.items.find((x) => x.id === targetId);
          if (item) openDetailModal(item);
        }
      };

      // Supporto tastiera (Enter o Space su card)
      list.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") {
          const card = e.target.closest(".es-card");
          if (card && !e.target.closest("button")) {
            e.preventDefault();
            const item = catalogData.items.find((x) => x.id === card.dataset.cardId);
            if (item) openDetailModal(item);
          }
        }
      };

      // Azioni dall'interno del modale
      modal.onclick = async (e) => {
        if (e.target === modal) {
          closeModal();
          return;
        }
        const actBtn = e.target.closest("[data-act]");
        if (!actBtn) return;
        const act = actBtn.dataset.act;
        const id = actBtn.dataset.id;
        const src = actBtn.dataset.src;
        if (act === "rimuovi" && !confirm("Rimuovere questa estensione? Le sue impostazioni salvate resteranno intatte.")) return;
        if (act === "installa" && !(await confermaPermessi(activeDetailItem || {}))) return;
        actBtn.disabled = true;
        try {
          await gs.api(`/plugin-api/estensioni/${act}`, { body: { id, fonte: src } });
          gs.toast(act === "installa" ? "Estensione installata: riavvia l'app per usarla" : "Estensione rimossa: riavvia l'app per applicare");
          closeModal();
        } catch (err) {
          gs.toast(err.message, true);
          actBtn.disabled = false;
        }
        await draw();
      };

      // Gestione Ricerca e Filtri
      filterInput.oninput = (e) => {
        searchQuery = e.target.value;
        filterClear.hidden = !searchQuery;
        draw();
      };

      filterClear.onclick = () => {
        searchQuery = "";
        filterInput.value = "";
        filterClear.hidden = true;
        filterInput.focus();
        draw();
      };

      tabBtns.forEach((btn) => {
        btn.onclick = () => {
          tabBtns.forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          currentFilterTab = btn.dataset.tab;
          draw();
        };
      });

      // Aggiungi fonte
      el.querySelector("#es-add").onsubmit = async (e) => {
        e.preventDefault();
        const f = e.target;
        const link = f.link.value.trim();
        if (!confirm("Le estensioni di questa fonte potranno eseguire codice sul tuo PC. Aggiungerla?")) return;
        f.querySelector("button").disabled = true;
        try {
          await gs.api("/plugin-api/estensioni/fonti/aggiungi", { body: { link } });
          f.reset();
          gs.toast("Fonte aggiunta con successo");
        } catch (err) {
          gs.toast(err.message, true);
        }
        f.querySelector("button").disabled = false;
        draw();
      };

      // Rimuovi fonte
      srcBox.onclick = async (e) => {
        const b = e.target.closest("[data-del]");
        if (!b || !confirm("Togliere questa fonte? Le estensioni già installate resteranno sul PC.")) return;
        try {
          await gs.api("/plugin-api/estensioni/fonti/rimuovi", { body: { link: b.dataset.del } });
          gs.toast("Fonte rimossa");
        } catch (err) {
          gs.toast(err.message, true);
        }
        draw();
      };

      // Primo caricamento
      draw();
    },
  });
}
