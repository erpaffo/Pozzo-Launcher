// Ricette web: motore e catalogo multimediale da fonti web lecite ed RSS/JSON.

export const safeUrl = (u) => {
  const s = String(u || "").trim();
  return /^https?:\/\//i.test(s) || s.startsWith("/") ? s : "";
};

export const formatDuration = (sec) => {
  const n = Number(sec);
  if (!n || isNaN(n) || n <= 0) return "";
  const h = Math.floor(n / 3600);
  const m = Math.floor((n % 3600) / 60);
  const s = Math.floor(n % 60);
  if (h > 0) return `${h}h ${m ? m + "m" : ""}`.trim();
  return `${m}m ${s ? s + "s" : ""}`.trim();
};

export default function (gs, ctx) {
  const pluginId = ctx?.id || "ricette-web";
  const apiBase = `/plugin-api/${pluginId}`;
  const esc = (s) => (gs?.esc ? gs.esc(s) : String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c])));

  const openUrl = async (url) => {
    const clean = safeUrl(url);
    if (!clean) return;
    try {
      await gs.api("/api/open", { body: { url: clean } });
    } catch (e) {
      if (typeof gs?.toast === "function") gs.toast(`Impossibile aprire il link: ${e.message}`, true);
    }
  };

  gs.addSidebarItem({ id: "ricette-web", label: "Ricette web", icon: "🌐", view: "ricette-web" });

  gs.registerView("ricette-web", {
    title: "Ricette web",
    async render(root) {
      if (!root) return;
      root.innerHTML = "";
      root.classList.add("rw-view");

      let recipes = [];
      let activeRecipeId = "";
      let activeTab = "items"; // "items" | "recipe_preview"
      let currentQuery = "";
      let items = [];
      let selectedItemId = null;
      let selectedItemDetail = null;
      let loading = false;
      let loadToken = 0;

      // Elementi strutturali
      const toolbar = document.createElement("div");
      toolbar.className = "rw-toolbar";

      const sourcesBar = document.createElement("div");
      sourcesBar.className = "rw-sources-bar";

      const content = document.createElement("div");
      content.className = "rw-content";

      root.append(toolbar, sourcesBar, content);

      // Carica elenco ricette
      async function loadRecipes() {
        try {
          const res = await gs.api(`${apiBase}/recipes`);
          recipes = Array.isArray(res?.recipes) ? res.recipes : [];
        } catch {
          recipes = [];
        }
      }

      // Carica lista elementi
      async function loadItems() {
        loading = true;
        const myToken = ++loadToken;
        renderContent();

        const q = new URLSearchParams();
        if (activeRecipeId) q.set("recipe", activeRecipeId);
        if (currentQuery) q.set("query", currentQuery);
        q.set("limit", "200");

        try {
          const res = await gs.api(`${apiBase}/list?${q.toString()}`);
          if (myToken !== loadToken) return;
          items = Array.isArray(res) ? res : [];
        } catch {
          if (myToken !== loadToken) return;
          items = [];
        } finally {
          if (myToken === loadToken) {
            loading = false;
            renderContent();
          }
        }
      }

      // Carica dettaglio elemento
      async function loadDetail(itemId) {
        selectedItemId = itemId;
        selectedItemDetail = null;
        loading = true;
        renderContent();

        try {
          const res = await gs.api(`${apiBase}/detail?id=${encodeURIComponent(itemId)}`);
          selectedItemDetail = res && typeof res === "object" ? res : null;
        } catch (e) {
          selectedItemDetail = null;
          if (typeof gs?.toast === "function") gs.toast(`Dettaglio non disponibile: ${e.message}`, true);
        } finally {
          loading = false;
          renderContent();
        }
      }

      // Riproduce elemento o episodio
      async function playItem(itemId) {
        try {
          const target = await gs.api(`${apiBase}/play_target?id=${encodeURIComponent(itemId)}`);
          if (target?.url) {
            await openUrl(target.url);
          } else {
            throw new Error("URL di riproduzione mancante");
          }
        } catch (e) {
          if (typeof gs?.toast === "function") {
            gs.toast(`Impossibile riprodurre: ${e.message}`, true);
          }
        }
      }

      // Disegna barra strumenti principale
      function renderToolbar() {
        toolbar.innerHTML = `
          <div class="rw-tabs" role="tablist">
            <button type="button" role="tab" class="rw-tab ${activeTab === 'items' ? 'rw-active' : ''}" data-tab="items">
              🎬 Contenuti
            </button>
            <button type="button" role="tab" class="rw-tab ${activeTab === 'recipe_preview' ? 'rw-active' : ''}" data-tab="recipe_preview">
              📋 Anteprima ricetta
            </button>
          </div>
          <div class="rw-search-box">
            <input type="search" class="rw-search" placeholder="Cerca nelle ricette…" value="${esc(currentQuery)}" aria-label="Cerca nelle ricette">
          </div>
        `;
      }

      // Disegna elenco sorgenti
      function renderSources() {
        if (!recipes.length) {
          sourcesBar.innerHTML = "";
          return;
        }
        const activeRec = recipes.find((r) => r.id === activeRecipeId);
        const siteBtn = activeRec?.start_url
          ? `<button type="button" class="rw-btn rw-sm rw-site-btn" data-open-url="${esc(safeUrl(activeRec.start_url))}" title="Apri sito originale">↗ Sito</button>`
          : "";

        sourcesBar.innerHTML = `
          <div class="rw-sources-label">Sorgenti:</div>
          <div class="rw-chips">
            <button type="button" class="rw-chip ${!activeRecipeId ? 'rw-active' : ''}" data-recipe="">Tutte</button>
            ${recipes.map((r) => `
              <button type="button" class="rw-chip ${r.id === activeRecipeId ? 'rw-active' : ''}" data-recipe="${esc(r.id)}">
                ${esc(r.name)}
              </button>
            `).join("")}
          </div>
          ${siteBtn}
        `;
      }

      // Disegna catalogo / lista pulita
      function renderItemsList() {
        if (loading) {
          return `<div class="rw-loading"><p class="muted">Caricamento in corso…</p></div>`;
        }
        if (!recipes.length) {
          return `
            <div class="rw-empty">
              <p class="muted">Nessuna ricetta disponibile o backend non raggiungibile.<br>Verifica che il plugin ricette-web sia attivo.</p>
            </div>
          `;
        }
        if (!items.length) {
          return `
            <div class="rw-empty">
              <p class="muted">Nessun elemento trovato per la ricerca o sorgente selezionata.</p>
            </div>
          `;
        }

        return `
          <div class="rw-grid">
            ${items.map((it) => {
              const poster = safeUrl(it.poster);
              const metaParts = [];
              if (it.year) metaParts.push(esc(it.year));
              if (it.duration) metaParts.push(esc(formatDuration(it.duration)));
              if (it.kind && it.kind !== 'film') metaParts.push(esc(it.kind));
              const icon = it.kind === 'brano' ? '🎵' : '🎬';

              return `
                <article class="rw-card ${it.seen ? 'rw-seen' : ''}" data-item-id="${esc(it.id)}" tabindex="0" role="button">
                  <div class="rw-poster">
                    ${poster ? `<img class="rw-poster-img" src="${esc(poster)}" alt="" loading="lazy">` : `<div class="rw-poster-placeholder">${icon}</div>`}
                    ${it.seen ? `<span class="rw-seen-badge">✓ Visto</span>` : ''}
                  </div>
                  <div class="rw-card-body">
                    <h4 class="rw-title" title="${esc(it.title)}">${esc(it.title)}</h4>
                    ${metaParts.length ? `<div class="rw-meta">${metaParts.join(" · ")}</div>` : ''}
                  </div>
                </article>
              `;
            }).join("")}
          </div>
        `;
      }

      // Disegna dettaglio con episodi
      function renderDetail() {
        if (loading && !selectedItemDetail) {
          return `<div class="rw-loading"><p class="muted">Caricamento dettagli…</p></div>`;
        }
        if (!selectedItemDetail) {
          return `
            <div class="rw-empty">
              <button type="button" class="rw-btn rw-back-btn" data-back-to-list>← Torna alla lista</button>
              <p class="muted" style="margin-top: 16px;">Elemento non trovato o non disponibile.</p>
            </div>
          `;
        }

        const det = selectedItemDetail;
        const poster = safeUrl(det.poster || det.backdrop);
        const icon = det.kind === 'brano' ? '🎵' : '🎬';
        const metaParts = [];
        if (det.year) metaParts.push(esc(det.year));
        if (det.duration) metaParts.push(esc(formatDuration(det.duration)));
        if (det.kind) metaParts.push(`<span class="rw-badge">${esc(det.kind)}</span>`);

        const episodes = Array.isArray(det.episodes) ? det.episodes : [];

        return `
          <div class="rw-detail">
            <div>
              <button type="button" class="rw-btn rw-back-btn" data-back-to-list>← Torna all'elenco</button>
            </div>
            <div class="rw-detail-header">
              <div class="rw-detail-poster">
                ${poster ? `<img class="rw-detail-poster-img" src="${esc(poster)}" alt="">` : `<div class="rw-poster-placeholder">${icon}</div>`}
              </div>
              <div class="rw-detail-info">
                <h2 class="rw-detail-title">${esc(det.title)}</h2>
                ${det.series ? `<div class="rw-detail-series">${esc(det.series)}</div>` : ''}
                <div class="rw-meta">${metaParts.join(" · ")}</div>
                ${det.overview ? `<p class="rw-detail-overview">${esc(det.overview)}</p>` : ''}
                <div class="rw-detail-actions">
                  <button type="button" class="rw-btn rw-primary" data-play-id="${esc(det.id)}">▶ Riproduci</button>
                  ${det.url ? `<button type="button" class="rw-btn" data-open-url="${esc(safeUrl(det.url))}">↗ Pagina originale</button>` : ''}
                </div>
              </div>
            </div>

            ${episodes.length ? `
              <div class="rw-episodes-section">
                <h3 class="rw-episodes-title">Episodi (${episodes.length})</h3>
                <div class="rw-episode-list">
                  ${episodes.map((ep, idx) => {
                    const epMeta = [];
                    if (ep.duration) epMeta.push(esc(formatDuration(ep.duration)));
                    const epNum = ep.episode != null ? `Ep. ${esc(ep.episode)}` : `#${idx + 1}`;
                    const seasonPrefix = ep.season != null ? `S${esc(ep.season)} ` : '';

                    return `
                      <div class="rw-episode-item" data-play-id="${esc(ep.id)}">
                        <div class="rw-episode-badge">${seasonPrefix}${epNum}</div>
                        <div class="rw-episode-info">
                          <h4 class="rw-episode-title" title="${esc(ep.title)}">${esc(ep.title)}</h4>
                          ${epMeta.length ? `<div class="rw-meta">${epMeta.join(" · ")}</div>` : ''}
                        </div>
                        <button type="button" class="rw-btn rw-sm rw-primary" data-play-id="${esc(ep.id)}">▶ Riproduci</button>
                      </div>
                    `;
                  }).join("")}
                </div>
              </div>
            ` : ''}
          </div>
        `;
      }

      // Disegna anteprima ricetta (campi estratti in tabella)
      function renderRecipePreview() {
        if (!recipes.length) {
          return `
            <div class="rw-empty">
              <p class="muted">Nessuna ricetta caricata o backend assente.</p>
            </div>
          `;
        }

        const targetRecipe = recipes.find((r) => r.id === activeRecipeId) || recipes[0];
        if (!targetRecipe) {
          return `<div class="rw-empty"><p class="muted">Ricetta non selezionata.</p></div>`;
        }

        // Righe per la tabella dei campi estratti
        const rows = [
          { sec: "Generale", field: "name", val: targetRecipe.name },
          { sec: "Generale", field: "host", val: targetRecipe.host },
          { sec: "Generale", field: "type", val: targetRecipe.type },
          { sec: "Generale", field: "start_url", val: targetRecipe.start_url, isUrl: true },
        ];

        if (targetRecipe.list) {
          for (const [k, v] of Object.entries(targetRecipe.list)) {
            rows.push({ sec: "[list]", field: k, val: v });
          }
        }
        if (targetRecipe.detail) {
          for (const [k, v] of Object.entries(targetRecipe.detail)) {
            rows.push({ sec: "[detail]", field: k, val: v });
          }
        }
        if (targetRecipe.episodes) {
          for (const [k, v] of Object.entries(targetRecipe.episodes)) {
            rows.push({ sec: "[episodes]", field: k, val: v });
          }
        }
        if (targetRecipe.pagination) {
          for (const [k, v] of Object.entries(targetRecipe.pagination)) {
            rows.push({ sec: "[pagination]", field: k, val: v });
          }
        }

        return `
          <div class="rw-preview">
            <div class="rw-preview-header">
              <div class="rw-preview-title-row">
                <h3 class="rw-preview-title">Ricetta: ${esc(targetRecipe.name)}</h3>
                <span class="rw-badge">${esc(String(targetRecipe.type || "").toUpperCase())}</span>
              </div>
              <div class="rw-meta">
                <span>Host: <strong>${esc(targetRecipe.host)}</strong></span>
                <span>·</span>
                <span>URL iniziale: <a href="#" class="rw-link" data-open-url="${esc(safeUrl(targetRecipe.start_url))}">${esc(targetRecipe.start_url)}</a></span>
              </div>
            </div>

            <h4 class="rw-section-subtitle">Regole di estrazione configurate</h4>
            <div class="rw-table-container">
              <table class="rw-table">
                <thead>
                  <tr>
                    <th>Sezione</th>
                    <th>Campo</th>
                    <th>Regola / Selettore estratto</th>
                  </tr>
                </thead>
                <tbody>
                  ${rows.map((r) => {
                    const valHtml = r.isUrl && safeUrl(r.val)
                      ? `<a href="#" class="rw-link" data-open-url="${esc(safeUrl(r.val))}">${esc(r.val)}</a>`
                      : `<code>${esc(typeof r.val === 'object' ? JSON.stringify(r.val) : String(r.val ?? ''))}</code>`;
                    return `
                      <tr>
                        <td><strong>${esc(r.sec)}</strong></td>
                        <td>${esc(r.field)}</td>
                        <td>${valHtml}</td>
                      </tr>
                    `;
                  }).join("")}
                </tbody>
              </table>
            </div>
          </div>
        `;
      }

      // Render generale del contenuto
      function renderContent() {
        renderToolbar();
        renderSources();

        if (activeTab === "recipe_preview") {
          content.innerHTML = renderRecipePreview();
        } else if (selectedItemId) {
          content.innerHTML = renderDetail();
        } else {
          content.innerHTML = renderItemsList();
        }
      }

      // Event delegation sul nodo radice
      root.onclick = async (e) => {
        // Apri URL esterno
        const openEl = e.target.closest("[data-open-url]");
        if (openEl) {
          e.preventDefault();
          e.stopPropagation();
          await openUrl(openEl.dataset.openUrl);
          return;
        }

        // Cambio tab
        const tabEl = e.target.closest("[data-tab]");
        if (tabEl) {
          e.stopPropagation();
          activeTab = tabEl.dataset.tab;
          selectedItemId = null;
          selectedItemDetail = null;
          renderContent();
          return;
        }

        // Cambio sorgente
        const chipEl = e.target.closest("[data-recipe]");
        if (chipEl) {
          e.stopPropagation();
          activeRecipeId = chipEl.dataset.recipe;
          selectedItemId = null;
          selectedItemDetail = null;
          if (activeTab === "items") {
            await loadItems();
          } else {
            renderContent();
          }
          return;
        }

        // Torna alla lista da dettaglio
        const backEl = e.target.closest("[data-back-to-list]");
        if (backEl) {
          e.stopPropagation();
          selectedItemId = null;
          selectedItemDetail = null;
          renderContent();
          return;
        }

        // Riproduzione
        const playBtn = e.target.closest("[data-play-id]");
        if (playBtn) {
          e.stopPropagation();
          await playItem(playBtn.dataset.playId);
          return;
        }

        // Clic su card per dettaglio
        const cardEl = e.target.closest("[data-item-id]");
        if (cardEl) {
          e.stopPropagation();
          await loadDetail(cardEl.dataset.itemId);
          return;
        }
      };

      // Supporto tastiera (Enter su card)
      root.onkeydown = async (e) => {
        if (e.key === "Enter" || e.key === " ") {
          const cardEl = e.target.closest("[data-item-id]");
          if (cardEl) {
            e.preventDefault();
            await loadDetail(cardEl.dataset.itemId);
          }
        }
      };

      // Ricerca con debounce
      let searchTimer;
      root.oninput = (e) => {
        if (e.target.classList.contains("rw-search")) {
          clearTimeout(searchTimer);
          searchTimer = setTimeout(() => {
            currentQuery = e.target.value.trim();
            selectedItemId = null;
            selectedItemDetail = null;
            loadItems();
          }, 300);
        }
      };

      // Avvio: carica ricette e primo set di elementi
      await loadRecipes();
      await loadItems();
    },
  });
}
