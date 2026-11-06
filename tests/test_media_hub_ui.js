"use strict";
// Test per Media Hub UI: renderHeroHtml, renderCardHtml, renderCarouselHtml, renderDetailModal, renderSettingsModal, XSS escaping, e verifica style.css.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

async function main() {
  const frontendPath = path.resolve(__dirname, "../extensions/media-locale/frontend.js");
  const {
    renderHeroHtml,
    renderCardHtml,
    renderCarouselHtml,
    renderListHtml,
    renderDetailModal,
    renderSettingsModal,
    renderStream4meBrowserHtml,
    renderWatchlistControlsHtml,
    renderWatchlistViewHtml,
    safeMediaUrl,
    isHttpUrl,
    isAnimeItem,
    isStream4meItem,
    normalizePlayItem,
    deduplicateStream4meEpisodes,
    renderMediaWidgetHtml,
    createMediaWidgetDef,
    createExtraMediaWidgetDefs,
    registerMediaWidget,
    renderMediaContextMenuHtml,
  } = await import(pathToFileURL(frontendPath).href);

  const playerPath = path.resolve(__dirname, "../extensions/media-locale/player.js");
  const { removeFromContinueCache } = await import(pathToFileURL(playerPath).href);

  // ==========================================
  // a) Test renderHeroHtml (Spotlight Cinematografico Netflix)
  // ==========================================
  assert.strictEqual(typeof renderHeroHtml, "function", "renderHeroHtml deve essere esportata");
  assert.strictEqual(renderHeroHtml(null), "", "renderHeroHtml(null) deve restituire stringa vuota");
  assert.strictEqual(renderHeroHtml(undefined), "", "renderHeroHtml(undefined) deve restituire stringa vuota");

  const sampleHero = {
    id: "mov_42",
    title: "Interstellar",
    overview: "Un gruppo di esploratori viaggia attraverso un wormhole nello spazio.",
    source: "locale",
    poster: "/media/interstellar.jpg",
    backdrop: "/media/interstellar_wide.jpg",
    year: 2014,
    genre: "Fantascienza",
    duration: 10140,
  };

  const heroHtml = renderHeroHtml(sampleHero);
  assert(heroHtml.includes("pm-hero"), "Deve contenere classe .pm-hero");
  assert(heroHtml.includes("pm-hero-body"), "Deve contenere classe .pm-hero-body");
  assert(heroHtml.includes("pm-hero-title"), "Deve contenere classe .pm-hero-title");
  assert(heroHtml.includes("pm-hero-desc"), "Deve contenere classe .pm-hero-desc");
  assert(heroHtml.includes("pm-hero-gradient"), "Deve contenere gradiente di fusione .pm-hero-gradient");
  assert(heroHtml.includes("pm-source-badge"), "Deve contenere classe .pm-source-badge");
  assert(heroHtml.includes('data-play-key="locale:mov_42"'), "Deve contenere data-play-key corretto");
  assert(heroHtml.includes('data-detail-key="locale:mov_42"'), "Deve contenere pulsante Altre info con data-detail-key");
  assert(heroHtml.includes("Interstellar"), "Deve mostrare il titolo");
  assert(heroHtml.includes("Un gruppo di esploratori"), "Deve mostrare l'overview");
  assert(heroHtml.includes("pm-hero-backdrop"), "Deve includere .pm-hero-backdrop se presente immagine");
  assert(heroHtml.includes("/media/interstellar_wide.jpg"), "Deve includere URL backdrop");
  assert(heroHtml.includes("▶ Riproduci"), "Deve includere pulsante grande Riproduci");
  assert(heroHtml.includes("ℹ Altre info"), "Deve includere pulsante Altre info");
  assert(heroHtml.includes("HD"), "Deve mostrare il badge HD");

  // XSS test per renderHeroHtml
  const xssHero = {
    id: 'xss" onmouseover="alert(1)',
    title: '<script>alert("hero-xss")</script>',
    overview: '<img src=x onerror=alert("desc")>',
    source: '<script>badge</script>',
  };
  const heroXssHtml = renderHeroHtml(xssHero);
  assert(!heroXssHtml.includes("<script>alert("), "Tag <script> non deve essere presente in chiaro");
  assert(!heroXssHtml.includes("<img src=x"), "Tag <img onerror> non deve essere presente in chiaro");
  assert(heroXssHtml.includes("&lt;script&gt;alert("), "I caratteri speciali devono essere escapati in entità HTML");

  // ==========================================
  // b) Test renderCardHtml (Card Video Netflix con Hover Zoom)
  // ==========================================
  assert.strictEqual(typeof renderCardHtml, "function", "renderCardHtml deve essere esportata");
  assert.strictEqual(renderCardHtml(null), "", "renderCardHtml(null) deve restituire stringa vuota");

  const sampleCard = {
    id: "ep_7",
    title: "Ozymandias",
    series: "Breaking Bad",
    season: 5,
    episode: 14,
    source: "jellyfin",
    poster: "/media/bb_s5e14.jpg",
    duration: 2820,
  };

  const cardHtmlNotFav = renderCardHtml(sampleCard, false);
  assert(cardHtmlNotFav.includes("pm-card"), "Deve contenere classe .pm-card");
  assert(cardHtmlNotFav.includes("pm-source-badge"), "Deve contenere classe .pm-source-badge");
  assert(cardHtmlNotFav.includes('data-play-key="jellyfin:ep_7"'), "Deve contenere data-play-key con compositeKey");
  assert(cardHtmlNotFav.includes("Ozymandias"), "Deve contenere il titolo dell'episodio");
  assert(cardHtmlNotFav.includes("Breaking Bad"), "Deve contenere il nome della serie");
  assert(cardHtmlNotFav.includes("☆"), "Elemento non preferito deve mostrare icona non preferito");

  const cardHtmlFav = renderCardHtml(sampleCard, true);
  assert(cardHtmlFav.includes("★"), "Elemento preferito deve mostrare stella piena");
  assert(cardHtmlFav.includes('data-fav-key="jellyfin:ep_7"') || cardHtmlFav.includes('data-fav-id="ep_7"'), "Deve contenere data-fav-key o data-fav-id");

  // XSS test per renderCardHtml
  const xssCard = {
    id: '100<script>',
    title: '<script>alert("card-xss")</script>',
    series: '"><b onfocus=alert(1)></b>',
    source: 'web',
  };
  const cardXssHtml = renderCardHtml(xssCard);
  assert(!cardXssHtml.includes("<script>alert("), "Card non deve contenere <script> non escapato");
  assert(cardXssHtml.includes("&lt;script&gt;alert("), "Titolo card XSS deve essere sanitizzato");

  // ==========================================
  // c) Test renderCarouselHtml (Caroselli Orizzontali Netflix)
  // ==========================================
  assert.strictEqual(typeof renderCarouselHtml, "function", "renderCarouselHtml deve essere esportata");
  assert.strictEqual(renderCarouselHtml("Test", []), "", "Carosello vuoto deve restituire stringa vuota");
  assert.strictEqual(renderCarouselHtml("Test", null), "", "Carosello null deve restituire stringa vuota");

  const carouselItems = [
    { id: "m1", title: "Film Uno", source: "locale", poster: "/img/f1.jpg", kind: "film" },
    { id: "m2", title: "Film Due", source: "jellyfin", poster: "/img/f2.jpg", kind: "film" },
  ];
  const carHtml = renderCarouselHtml("🎬 Film", carouselItems);
  assert(carHtml.includes("pm-carousel"), "Deve contenere classe .pm-carousel");
  assert(carHtml.includes("pm-carousel-header"), "Deve contenere classe .pm-carousel-header");
  assert(carHtml.includes("pm-carousel-title"), "Deve contenere classe .pm-carousel-title");
  assert(carHtml.includes("pm-carousel-count"), "Deve contenere classe .pm-carousel-count");
  assert(carHtml.includes("pm-carousel-controls"), "Deve contenere classe .pm-carousel-controls");
  assert(carHtml.includes('data-carousel-scroll="-1"'), "Deve contenere freccia sinistra carosello");
  assert(carHtml.includes('data-carousel-scroll="1"'), "Deve contenere freccia destra carosello");
  assert(carHtml.includes("pm-carousel-row"), "Deve contenere classe .pm-carousel-row");
  assert(carHtml.includes("Film Uno"), "Deve mostrare i titoli delle card");
  assert(carHtml.includes("Film Due"), "Deve mostrare tutti gli elementi");

  // Carosello Continua a guardare (type: "resume")
  const resumeItems = [
    { id: "r1", title: "Inception", source: "locale", duration: 7200, resume_pos: 3600, backdrop: "/img/inc.jpg" },
  ];
  const carResumeHtml = renderCarouselHtml("🍿 Continua a guardare", resumeItems, { type: "resume" });
  assert(carResumeHtml.includes("pm-resume-card"), "Continua a guardare deve usare .pm-resume-card");
  assert(carResumeHtml.includes("pm-progress-bar"), "Deve mostrare la barra di progresso");
  assert(carResumeHtml.includes("50%"), "Deve mostrare la percentuale corretta (3600/7200 = 50%)");

  // Carosello Serie TV (type: "series")
  const seriesSummaries = [
    { name: "Stranger Things", count: 34, seasonsCount: 4, repItem: { poster: "/img/st.jpg", source: "locale" }, allSeen: false },
  ];
  const carSeriesHtml = renderCarouselHtml("📺 Serie TV", seriesSummaries, { type: "series" });
  assert(carSeriesHtml.includes("data-series-name=\"Stranger Things\""), "Deve includere data-series-name per l'apertura modale");
  assert(carSeriesHtml.includes("4 stagioni"), "Deve mostrare il numero di stagioni");
  assert(carSeriesHtml.includes("34 episodi"), "Deve mostrare il numero di episodi");

  // XSS test per renderCarouselHtml
  const xssCarHtml = renderCarouselHtml('<script>alert("car")</script>', [
    { id: 'x1', title: '<img src=x onerror=alert(1)>', source: 'locale' }
  ]);
  assert(!xssCarHtml.includes("<script>alert("), "Titolo carosello non deve contenere <script>");
  assert(!xssCarHtml.includes("<img src=x"), "Card non deve contenere <img src=x");

  // ==========================================
  // d) Test renderListHtml (Vista Elenco / Tabella Compatta)
  // ==========================================
  assert.strictEqual(typeof renderListHtml, "function", "renderListHtml deve essere esportata");
  assert(renderListHtml([]).includes("Nessun elemento da mostrare"), "Lista vuota deve mostrare messaggio vuoto");

  const sampleListItems = [
    { id: "item_1", title: "Inception", year: 2010, duration: 8880, source: "locale" },
    { id: "item_2", title: "One Piece 1015", series: "One Piece", season: 1, episode: 1015, duration: 1440, kind: "episodio", source: "locale" },
  ];
  const listHtml = renderListHtml(sampleListItems, { favs: new Set(["locale:item_1"]) });
  assert(listHtml.includes("pm-list"), "Deve contenere classe .pm-list");
  assert(listHtml.includes("pm-list-row"), "Deve contenere classe .pm-list-row");
  assert(listHtml.includes("Inception"), "Deve mostrare il titolo Inception");
  assert(listHtml.includes("One Piece"), "Deve mostrare la serie One Piece");
  assert(listHtml.includes("S1E1015"), "Deve mostrare il tag episodio S1E1015");
  assert(listHtml.includes("★"), "Item_1 deve avere stella preferito");
  assert(listHtml.includes("☆"), "Item_2 non preferito deve avere stella vuota");
  assert(listHtml.includes("▶ Riproduci"), "Deve contenere pulsante di riproduzione diretta");

  // ==========================================
  // e) Test renderDetailModal (Modale Dettagli Stile Netflix)
  // ==========================================
  assert.strictEqual(typeof renderDetailModal, "function", "renderDetailModal deve essere esportata");
  assert.strictEqual(renderDetailModal(null), "", "renderDetailModal(null) deve restituire stringa vuota");

  const seriesGroups = {
    "Attack on Titan": {
      "1": [
        { id: "aot_1", title: "A te, fra 2000 anni", episode: 1, season: 1, duration: 1440, overview: "L'attacco iniziale." },
        { id: "aot_2", title: "Quel giorno", episode: 2, season: 1, duration: 1440, overview: "La caduta del muro." },
      ],
      "2": [
        { id: "aot_26", title: "Il gigante bestia", episode: 1, season: 2, duration: 1440, overview: "Nuovi nemici." },
      ],
    },
  };

  const modalHtml = renderDetailModal("Attack on Titan", seriesGroups);
  assert(modalHtml.includes("pm-modal-overlay"), "Deve contenere classe .pm-modal-overlay");
  assert(modalHtml.includes("pm-modal-detail"), "Deve contenere classe .pm-modal-detail");
  assert(modalHtml.includes("pm-modal-close"), "Deve contenere pulsante di chiusura .pm-modal-close");
  assert(modalHtml.includes("Attack on Titan"), "Deve contenere il titolo della serie");
  assert(modalHtml.includes("pm-season-tabs"), "Deve contenere le tab delle stagioni");
  assert(modalHtml.includes("pm-episode-list"), "Deve contenere la lista degli episodi");
  assert(modalHtml.includes("A te, fra 2000 anni"), "Deve mostrare il primo episodio");
  assert(modalHtml.includes("pm-episode-card"), "Ogni episodio deve avere classe .pm-episode-card");

  // Test film singolo in modale
  const filmModalHtml = renderDetailModal(sampleHero);
  assert(filmModalHtml.includes("Interstellar"), "Deve mostrare il film singolo");
  assert(filmModalHtml.includes("▶ Riproduci"), "Deve includere il pulsante Riproduci");

  // XSS test per renderDetailModal
  const xssModal = renderDetailModal('<script>alert("modal")</script>', {
    '<script>alert("modal")</script>': {
      "1": [{ id: "x1", title: '<b onmouseover=alert(1)>Ep 1</b>', episode: 1 }]
    }
  });
  assert(!xssModal.includes("<script>alert("), "Modale non deve contenere <script> in chiaro");
  assert(!xssModal.includes("<b onmouseover="), "Titolo episodio non deve contenere listener HTML");

  // ==========================================
  // e) Test renderSettingsModal (Impostazioni Drawer / Modale ⚙)
  // ==========================================
  assert.strictEqual(typeof renderSettingsModal, "function", "renderSettingsModal deve essere esportata");
  const settingsData = {
    activeTab: "cartelle",
    roots: [{ path: "C:\\Media\\Film" }],
    installedAddons: [{ id: "plugin.video.stream4me", name: "Stream4me", version: "1.2.0" }],
    activeRecipes: [{ id: "raiplay", title: "RaiPlay" }],
  };
  const settingsHtml = renderSettingsModal(settingsData);
  assert(settingsHtml.includes("pm-settings-modal"), "Deve contenere classe .pm-settings-modal");
  assert(settingsHtml.includes("pm-settings-overlay"), "Deve contenere classe .pm-settings-overlay");
  assert(settingsHtml.includes("pm-settings-tabs"), "Deve contenere le tab di navigazione");
  assert(settingsHtml.includes("📁 Cartelle locali"), "Deve contenere tab Cartelle");
  assert(settingsHtml.includes("🧩 Kodi & Stream4me"), "Deve contenere tab Stream4me");
  assert(settingsHtml.includes("🌐 Server Jellyfin / Plex"), "Deve contenere tab Server");
  assert(settingsHtml.includes("🔍 Metadati"), "Deve contenere tab Metadati");
  assert(settingsHtml.includes("C:\\Media\\Film"), "Deve mostrare le cartelle configurate");

  // Test tab Stream4me + Gestione Provider
  const stream4meTabHtml = renderSettingsModal({
    ...settingsData,
    activeTab: "stream4me",
    providers: [{ id: "cb01", name: "CB01", host: "https://cb01.uno" }],
    availableInactiveProviders: [{ id: "guardaserie", name: "GuardaSerie" }],
  });
  assert(stream4meTabHtml.includes("Stream4me Installato"), "Deve indicare lo stato di Stream4me");
  assert(stream4meTabHtml.includes("pm-addon-input"), "Deve includere campo per addon custom");
  assert(stream4meTabHtml.includes("Aggiungi o Gestisci Provider Stream4me"), "Deve avere sezione gestione provider");
  assert(stream4meTabHtml.includes("pm-prov-name"), "Deve avere input nome provider");
  assert(stream4meTabHtml.includes("pm-prov-host"), "Deve avere input host provider");
  assert(stream4meTabHtml.includes("data-add-provider"), "Deve avere pulsante aggiungi provider");
  assert(stream4meTabHtml.includes("data-enable-provider"), "Deve avere pulsante attiva canale inattivo");
  assert(stream4meTabHtml.includes('data-remove-provider="cb01"'), "Deve avere pulsante rimuovi provider attivo");

  // Test tab Server
  const serverTabHtml = renderSettingsModal({ ...settingsData, activeTab: "server" });
  assert(serverTabHtml.includes("pm-server-url"), "Deve includere campo URL server");
  assert(serverTabHtml.includes("pm-server-token"), "Deve includere campo token");
  assert(serverTabHtml.includes("data-test-server"), "Deve includere tasto Test connessione");

  // Test tab Metadati
  const metaTabHtml = renderSettingsModal({ ...settingsData, activeTab: "metadati" });
  assert(metaTabHtml.includes("data-enrich-metadata"), "Deve includere pulsante arricchimento metadati");

  // ==========================================
  // f) Test anime, stream4me detector helpers & renderStream4meBrowserHtml (Kodi Navigator & Libreria)
  // ==========================================
  assert.strictEqual(isAnimeItem({ title: "One Piece", kind: "episodio" }), true, "One Piece deve essere riconosciuto come anime");
  assert.strictEqual(isAnimeItem({ title: "Il Padrino", kind: "film" }), false, "Il Padrino non è un anime");
  assert.strictEqual(isStream4meItem({ source: "stream4me" }), true, "source: stream4me riconosciuto");
  assert.strictEqual(isStream4meItem({ addon: "plugin.video.stream4me" }), true, "addon stream4me riconosciuto");
  assert.strictEqual(isStream4meItem({ id: "s4me:cb01:test" }), true, "id s4me: riconosciuto");

  assert.strictEqual(typeof renderStream4meBrowserHtml, "function", "renderStream4meBrowserHtml deve essere esportata");

  // 1. Non installato e nessun provider -> mostra banner installazione 1-click
  const s4mNotInstalledHtml = renderStream4meBrowserHtml({ installed: false, providers: [] });
  assert(s4mNotInstalledHtml.includes("data-install-stream4me"), "Se non installato mostra pulsante installazione");

  // 2. Directory dei Provider (activeProvider: null)
  const sampleProviders = [
    { id: "animesaturn", name: "AnimeSaturn", categories: ["anime"], menus: [{ label: "In corso", path: "incorso" }] },
    { id: "cb01", name: "CB01", categories: ["movie", "tvshow"], menus: [{ label: "Film", path: "film" }] },
  ];
  const s4mDirHtml = renderStream4meBrowserHtml({
    installed: true,
    providers: sampleProviders,
    activeProvider: null,
  });
  assert(s4mDirHtml.includes("pm-provider-grid"), "Directory provider deve contenere .pm-provider-grid");
  assert(s4mDirHtml.includes("pm-provider-card"), "Directory provider deve contenere .pm-provider-card");
  assert(s4mDirHtml.includes('data-open-provider="animesaturn"'), "Deve includere data-open-provider per AnimeSaturn");
  assert(s4mDirHtml.includes('data-open-provider="cb01"'), "Deve includere data-open-provider per CB01");
  assert(s4mDirHtml.includes("Apri catalogo →"), "Deve mostrare pulsante Apri catalogo →");

  // 3. Vista dentro un Provider selezionato (Navigazione stile Kodi + Libreria)
  const s4mInsideHtml = renderStream4meBrowserHtml({
    installed: true,
    providers: sampleProviders,
    activeProvider: sampleProviders[0],
    activePath: "incorso",
    browsedItems: [
      { id: "s4m:animesaturn:op", title: "One Piece Sub ITA", source: "stream4me", poster: "/img/op.jpg" },
      { id: "s4m:animesaturn:jjk", title: "Jujutsu Kaisen", source: "stream4me", poster: "/img/jjk.jpg" },
    ],
    pinnedIds: new Set(["s4m:animesaturn:jjk"]),
  });
  assert(s4mInsideHtml.includes("pm-provider-nav"), "Deve mostrare barra di navigazione .pm-provider-nav");
  assert(s4mInsideHtml.includes("data-close-provider"), "Deve avere pulsante ← Tutti i provider");
  assert(s4mInsideHtml.includes('data-provider-path="incorso"'), "Deve mostrare pill categorie del provider");
  assert(s4mInsideHtml.includes("One Piece Sub ITA"), "Deve mostrare gli elementi esplorati nel provider");
  assert(s4mInsideHtml.includes('data-pin-item="s4m:animesaturn:op"'), "Card Stream4me deve avere pulsante data-pin-item");
  assert(s4mInsideHtml.includes("＋ Libreria"), "Item non pinnato deve mostrare ＋ Libreria");
  assert(s4mInsideHtml.includes("✓ In Libreria"), "Item già pinnato deve mostrare ✓ In Libreria");
  assert(s4mInsideHtml.includes('data-wl-toggle="stream4me:s4m:animesaturn:op"'), "Card deve avere pulsante Watchlist rapido data-wl-toggle");

  // 4. Detail Modal per elemento Stream4me con pulsante Libreria, Watchlist e lista episodi
  const s4mModalHtml = renderDetailModal(
    { id: "s4m:animesaturn:op", title: "One Piece Sub ITA", source: "stream4me" },
    {},
    {
      pinnedIds: new Set(),
      episodes: [{ id: "s4m:animesaturn:op:1", title: "Episodio 1", episode: 1, source: "stream4me" }],
    }
  );
  assert(s4mModalHtml.includes("＋ Libreria"), "Modal dettaglio Stream4me deve avere pulsante ＋ Libreria");
  assert(s4mModalHtml.includes("Episodio 1"), "Modal dettaglio Stream4me deve elencare gli episodi caricati");
  assert(s4mModalHtml.includes("data-wl-add"), "Modal dettaglio deve includere controlli Watchlist");

  // 5. Deduplicazione episodi Stream4me & isolamento in renderDetailModal + standalone movie Stream4me + normalizePlayItem
  assert.strictEqual(typeof deduplicateStream4meEpisodes, "function", "deduplicateStream4meEpisodes deve essere esportata");
  assert.strictEqual(typeof normalizePlayItem, "function", "normalizePlayItem deve essere esportata");

  const rawS4meEps = [
    { id: "s4me:ep1_a", title: "Episodio 1 (720p)", season: 1, episode: 1 },
    { id: "s4me:ep1_b", title: "Episodio 1 (1080p duplicate)", season: 1, episode: 1 },
    { id: "s4me:ep2", title: "Episodio 2", season: 1, episode: 2 },
    { id: "s4me:s2ep1", title: "Stagione 2 Ep 1", season: 2, episode: 1 },
    { id: "s4me:s2ep1_dup", title: "Stagione 2 Ep 1 Dup", season: 2, episode: 1 },
  ];
  const s4mParent = { id: "s4me:animesaturn:jjk", title: "Jujutsu Kaisen", series: "Jujutsu Kaisen", source: "stream4me", poster: "/img/jjk.jpg" };
  const dedupedEps = deduplicateStream4meEpisodes(rawS4meEps, s4mParent);
  assert.strictEqual(dedupedEps.length, 3, "Gli episodi Stream4me con stessa stagione e numero episodio devono essere deduplicati");
  assert.strictEqual(dedupedEps[0].id, "s4me:ep1_a", "Deve mantenere il primo episodio per S1E1");
  assert.strictEqual(dedupedEps[1].episode, 2, "Secondo episodio deve essere S1E2");
  assert.strictEqual(dedupedEps[2].season, 2, "Terzo episodio deve essere S2E1");

  const s4mSeriesGroups = {
    "Jujutsu Kaisen": {
      "1": dedupedEps.filter((e) => e.season === 1),
      "2": dedupedEps.filter((e) => e.season === 2),
    },
  };
  const s4mDedupModalHtml = renderDetailModal(s4mParent, s4mSeriesGroups, { selectedSeason: "1" });
  assert(s4mDedupModalHtml.includes("2 stagioni"), "Modal serie Stream4me deduplicata deve mostrare 2 stagioni");
  assert(s4mDedupModalHtml.includes("3 episodi"), "Modal serie Stream4me deduplicata deve mostrare 3 episodi totali");
  assert(s4mDedupModalHtml.includes("Episodio 1 (720p)"), "Deve mostrare l'episodio S1E1 deduplicato");
  assert(!s4mDedupModalHtml.includes("Episodio 1 (1080p duplicate)"), "Non deve mostrare il duplicato di S1E1");

  // Standalone Stream4me movie item (0 episodes -> standalone playable modal without fake "1 stagione · 0/1 episodi" series header)
  const s4mStandaloneMovie = {
    id: "s4me:cb01:suzume",
    title: "Suzume",
    source: "stream4me",
    kind: "film",
    poster: "/img/suzume.jpg",
    overview: "Un viaggio attraverso il Giappone per chiudere le porte.",
  };
  const s4mMovieModalHtml = renderDetailModal(s4mStandaloneMovie, {}, { favs: new Set() });
  assert(s4mMovieModalHtml.includes("Suzume"), "Deve mostrare il titolo del film Stream4me standalone");
  assert(s4mMovieModalHtml.includes("▶ Riproduci"), "Deve mostrare il pulsante ▶ Riproduci diretto per film standalone Stream4me");
  assert(!s4mMovieModalHtml.includes("1 stagione"), "Film standalone Stream4me con 0 episodi non deve mostrare fake '1 stagione'");
  assert(!s4mMovieModalHtml.includes("pm-season-tabs"), "Film standalone Stream4me non deve avere tab stagioni");

  // Verifica normalizzazione source -> ricette-web per play_target
  assert.strictEqual(normalizePlayItem({ id: "s4me:cb01:1", source: "stream4me" }).source, "ricette-web", "source stream4me deve essere normalizzato a ricette-web per player.js");
  assert.strictEqual(normalizePlayItem({ id: "kodi:addon:1", source: "kodi" }).source, "ricette-web", "source kodi deve essere normalizzato a ricette-web per player.js");
  assert.strictEqual(normalizePlayItem({ id: "loc_1", source: "locale" }).source, "locale", "source locale non deve cambiare");

  // ==========================================
  // f2) Test Watchlist Renderers (renderWatchlistControlsHtml & renderWatchlistViewHtml)
  // ==========================================
  assert.strictEqual(typeof renderWatchlistControlsHtml, "function", "renderWatchlistControlsHtml deve essere esportata");
  assert.strictEqual(typeof renderWatchlistViewHtml, "function", "renderWatchlistViewHtml deve essere esportata");

  // 1. Controlli Watchlist quando NON in lista
  const wlCtrlAdd = renderWatchlistControlsHtml("locale:mov_42", null);
  assert(wlCtrlAdd.includes("pm-wl-controls"), "Deve contenere .pm-wl-controls");
  assert(wlCtrlAdd.includes('data-wl-add="locale:mov_42"'), "Deve avere pulsante data-wl-add");
  assert(wlCtrlAdd.includes("📋 ＋ Aggiungi alla Watchlist"), "Deve mostrare testo Aggiungi alla Watchlist");
  assert(wlCtrlAdd.includes("🔥 Alta") && wlCtrlAdd.includes("⚡ Media") && wlCtrlAdd.includes("💤 Bassa"), "Deve mostrare pulsanti rapidi priorità");

  // 2. Controlli Watchlist quando GIA' in lista
  const wlCtrlEdit = renderWatchlistControlsHtml("locale:mov_42", {
    item_key: "locale:mov_42",
    status: "watching",
    priority: "high",
    rating: 9,
    notes: "Episodio 4 minuto 12",
  });
  assert(wlCtrlEdit.includes('data-wl-status="locale:mov_42"'), "Deve avere select data-wl-status");
  assert(wlCtrlEdit.includes('data-wl-priority="locale:mov_42"'), "Deve avere select data-wl-priority");
  assert(wlCtrlEdit.includes('data-wl-rating="locale:mov_42"'), "Deve avere select data-wl-rating");
  assert(wlCtrlEdit.includes('data-wl-note-input="locale:mov_42"'), "Deve avere input nota data-wl-note-input");
  assert(wlCtrlEdit.includes("Episodio 4 minuto 12"), "Deve precompilare la nota personale");
  assert(wlCtrlEdit.includes('data-wl-save-note="locale:mov_42"'), "Deve avere pulsante Salva nota");
  assert(wlCtrlEdit.includes('data-wl-remove="locale:mov_42"'), "Deve avere pulsante Rimuovi");

  // 3. Vista pagina Watchlist completa
  const sampleWatchlist = [
    { item_key: "locale:m1", id: "m1", title: "Dune Parte Due", source: "locale", status: "plan_to_watch", priority: "high", rating: 9, year: 2024, notes: "Imax" },
    { item_key: "stream4me:s1", id: "s1", title: "Solo Leveling", source: "stream4me", status: "watching", priority: "medium", rating: 8, series: "Solo Leveling" },
    { item_key: "jellyfin:c1", id: "c1", title: "The Matrix", source: "jellyfin", status: "completed", priority: "low", rating: 10, year: 1999 },
  ];
  const wlViewHtml = renderWatchlistViewHtml(sampleWatchlist, { status: "all", priority: "all", sortBy: "priority" });
  assert(wlViewHtml.includes("pm-wl-stats"), "Deve mostrare barra statistiche .pm-wl-stats");
  assert(wlViewHtml.includes("pm-wl-stat-pill"), "Deve mostrare pill statistiche .pm-wl-stat-pill");
  assert(wlViewHtml.includes("pm-wl-toolbar"), "Deve mostrare toolbar filtri .pm-wl-toolbar");
  assert(wlViewHtml.includes("pm-wl-list"), "Deve mostrare lista .pm-wl-list");
  assert(wlViewHtml.includes("pm-wl-card"), "Deve mostrare card .pm-wl-card");
  assert(wlViewHtml.includes("pm-wl-priority-high"), "Deve mostrare badge priorità alta");
  assert(wlViewHtml.includes("Dune Parte Due") && wlViewHtml.includes("Solo Leveling") && wlViewHtml.includes("The Matrix"), "Deve elencare le voci");
  assert(wlViewHtml.indexOf("Dune Parte Due") < wlViewHtml.indexOf("The Matrix"), "Ordinamento per priorità mette gli attivi ad alta priorità prima dei completati");

  // 4. Filtro per stato nella vista Watchlist
  const wlWatchingHtml = renderWatchlistViewHtml(sampleWatchlist, { status: "watching" });
  assert(wlWatchingHtml.includes("Solo Leveling"), "Filtro watching deve mostrare Solo Leveling");
  assert(!wlWatchingHtml.includes("Dune Parte Due"), "Filtro watching non deve mostrare plan_to_watch");

  // 5. XSS test Watchlist
  const xssWlHtml = renderWatchlistViewHtml([
    { item_key: 'x" onload="alert(1)', title: '<script>alert("wl")</script>', notes: '<img src=x onerror=alert(2)>' }
  ]);
  assert(!xssWlHtml.includes("<script>alert("), "Watchlist view non deve contenere <script> in chiaro");
  assert(!xssWlHtml.includes("<img src=x"), "Watchlist view non deve contenere <img onerror> in chiaro");

  // ==========================================
  // g) Test Dashboard Widget Media Locale (media:continue)
  // ==========================================
  assert.strictEqual(typeof renderMediaWidgetHtml, "function", "renderMediaWidgetHtml deve essere esportata");
  assert.strictEqual(typeof createMediaWidgetDef, "function", "createMediaWidgetDef deve essere esportata");
  assert.strictEqual(typeof registerMediaWidget, "function", "registerMediaWidget deve essere esportata");

  // 1. Stato vuoto
  const emptyHtml = renderMediaWidgetHtml(null);
  assert(emptyHtml.includes("Nessun video in corso di riproduzione"), "Stato vuoto deve contenere testo esatto");
  assert(emptyHtml.includes("Apri Media locale"), "Stato vuoto deve avere pulsante Apri Media locale");
  assert(emptyHtml.includes("gs-media-open-btn"), "Pulsante stato vuoto deve avere classe gs-media-open-btn");
  assert(!/#([0-9a-fA-F]{3,8})\b/.test(emptyHtml), "Zero colori esadecimali hardcoded nello stato vuoto");

  const seenHtml = renderMediaWidgetHtml({ id: 1, title: "Finito", seen: true, resume_pos: 100, duration: 100 });
  assert(seenHtml.includes("Nessun video in corso di riproduzione"), "Video già visto deve mostrare stato vuoto");

  // 2. Video in corso di riproduzione
  const inProgressItem = {
    id: "m_42",
    title: "Inception",
    source: "locale",
    poster: "/posters/inception.jpg",
    backdrop: "/backdrops/inception.jpg",
    resume_pos: 1800,
    duration: 7200,
  };
  const widgetCardHtml = renderMediaWidgetHtml(inProgressItem);
  assert(widgetCardHtml.includes("Inception"), "Card deve contenere il titolo del video");
  assert(widgetCardHtml.includes("gs-progress-bar"), "Card deve contenere .gs-progress-bar");
  assert(widgetCardHtml.includes("width: 25%"), "Card deve calcolare la percentuale corretta (1800/7200 = 25%)");
  assert(widgetCardHtml.includes("▶ Riproduci"), "Card deve contenere pulsante ▶ Riproduci");
  assert(widgetCardHtml.includes("gs-media-play-btn"), "Pulsante play deve avere classe gs-media-play-btn");
  assert(widgetCardHtml.includes("/backdrops/inception.jpg"), "Card deve mostrare locandina/backdrop");
  assert(!/#([0-9a-fA-F]{3,8})\b/.test(widgetCardHtml), "Zero colori esadecimali hardcoded nella card in riproduzione");
  assert(widgetCardHtml.includes("var(--accent)") && widgetCardHtml.includes("var(--text)"), "Card deve usare variabili tema");

  // 3. Episodio serie TV con sottotitolo stagione/episodio
  const tvItem = {
    id: "ep_9",
    title: "Ozymandias",
    series: "Breaking Bad",
    season: 5,
    episode: 14,
    resume_pos: 1410,
    duration: 2820,
    source: "jellyfin",
  };
  const tvWidgetHtml = renderMediaWidgetHtml(tvItem);
  assert(tvWidgetHtml.includes("Ozymandias"), "Deve mostrare titolo episodio");
  assert(tvWidgetHtml.includes("Breaking Bad · S5E14"), "Deve mostrare serie, stagione ed episodio");
  assert(tvWidgetHtml.includes("width: 50%"), "Deve mostrare 50% di avanzamento");

  // 4. Protezione XSS
  const xssWidget = {
    id: 'xss" onfocus="alert(1)',
    title: '<script>alert("xss")</script>',
    series: '<b onmouseover="alert(2)">Evil</b>',
    resume_pos: 10,
    duration: 100,
  };
  const xssWidgetHtml = renderMediaWidgetHtml(xssWidget);
  assert(!xssWidgetHtml.includes("<script>alert("), "Nessun tag script non escapato");
  assert(xssWidgetHtml.includes("&lt;script&gt;alert("), "I caratteri speciali devono essere escapati");

  // 5. Metadati Widget Definition
  const def = createMediaWidgetDef();
  assert.strictEqual(def.id, "media:continue", "Widget id deve essere media:continue");
  assert.strictEqual(def.title, "Continua a guardare (Media)", "Widget title deve essere Continua a guardare (Media)");
  assert.strictEqual(def.description, "Ultimo film o serie tv in riproduzione", "Widget description corretta");
  assert.strictEqual(def.category, "extensions", "Widget category deve essere extensions");
  assert.strictEqual(def.defaultSpan, 2, "Widget defaultSpan deve essere 2");
  assert.strictEqual(typeof def.render, "function", "Widget def.render deve essere una funzione");

  // 6. Test render callback con mock container
  const mockContainer = { innerHTML: "", querySelectorAll: () => [], querySelector: () => null };
  await def.render(mockContainer, {
    gs: { api: async () => ({ items: [] }), esc: (s) => String(s || "") },
  });
  assert(mockContainer.innerHTML.includes("Nessun video in corso di riproduzione"), "Render con libreria vuota mostra empty state");

  // 7. Test registerMediaWidget helper
  let registeredDef = null;
  const mockGs = {
    ui: {
      registerWidget: (w) => { registeredDef = w; }
    }
  };
  const regOk = registerMediaWidget(mockGs);
  assert.strictEqual(regOk, true, "registerMediaWidget deve restituire true quando registrato con successo");
  assert.strictEqual(registeredDef?.id, "media:continue", "Deve aver registrato il widget media:continue");

  // 8. Widget extra: registrazione, stato vuoto, escaping
  const regIds = [];
  registerMediaWidget({ ui: { registerWidget: (w) => regIds.push(w.id) } });
  for (const id of ["media:spotlight", "media:watchlist", "media:next_episode", "media:favorites", "media:continue"]) {
    assert(regIds.includes(id), `Deve registrare ${id}`);
  }
  const extra = createExtraMediaWidgetDefs({ store: { get: (_k, fb) => fb } });
  const spans = { "media:spotlight": 2, "media:watchlist": 2, "media:next_episode": 1, "media:favorites": 2 };
  for (const w of extra) {
    assert.strictEqual(w.category, "media", `${w.id} category media`);
    assert.strictEqual(w.defaultSpan, spans[w.id], `${w.id} defaultSpan`);
    const box = { innerHTML: "" };
    const html = w.render(box, {});
    assert(typeof html === "string" && html.includes("gs-empty-widget"), `${w.id} stato vuoto`);
    assert.strictEqual(box.innerHTML, html, `${w.id} scrive nel container`);
    assert(!/#([0-9a-fA-F]{3,8})\b/.test(html), `${w.id} nessun colore hardcoded`);
  }
  const evil = '<script>alert(1)</script>';
  const wlDef = createExtraMediaWidgetDefs({ store: { get: (k, fb) => (k === "pm_watchlist" ? [{ id: "x1", title: evil }] : fb) } })
    .find((w) => w.id === "media:watchlist");
  const wlHtml = wlDef.render(null, {});
  assert(!wlHtml.includes(evil) && wlHtml.includes("&lt;script&gt;"), "Watchlist widget deve escapare il titolo");

  // ==========================================
  // g2) Test Menu Contestuale e Rimozione Cache
  // ==========================================
  assert.strictEqual(typeof renderMediaContextMenuHtml, "function", "renderMediaContextMenuHtml deve essere esportata");
  assert.strictEqual(renderMediaContextMenuHtml(null), "", "renderMediaContextMenuHtml(null) deve essere vuoto");

  const normalMedia = { id: "m42", title: "Test Movie", source: "locale" };
  const ctxNormal = renderMediaContextMenuHtml(normalMedia, { key: "locale:m42", isFav: false });
  assert(ctxNormal.includes("pm-ctx-item"), "Deve includere .pm-ctx-item");
  assert(ctxNormal.includes('data-ctx-play="locale:m42"'), "Include play");
  assert(ctxNormal.includes('data-ctx-detail="locale:m42"'), "Include detail");
  assert(ctxNormal.includes("☆ Aggiungi ai preferiti"), "Include preferiti non attivo");
  assert(!ctxNormal.includes("data-ctx-remove-continue"), "Non include remove-continue se non in visione");
  assert(!ctxNormal.includes("data-ctx-unpin-s4me"), "Non include unpin se non s4me");

  const continueMedia = { id: "c1", title: "Watching Now", source: "locale" };
  const ctxContinue = renderMediaContextMenuHtml(continueMedia, { key: "locale:c1", isContinueItem: true, isFav: true });
  assert(ctxContinue.includes("★ Rimuovi dai preferiti"), "Mostra stella piena se preferito");
  assert(ctxContinue.includes('data-ctx-remove-continue="locale:c1"'), "Include remove-continue per elementi in visione");

  const s4meItem = { id: "s4me:ch1:100", title: "Online Ep", source: "stream4me" };
  const ctxS4mePinned = renderMediaContextMenuHtml(s4meItem, { key: "stream4me:s4me:ch1:100", isS4me: true, isPinnedS4me: true });
  assert(ctxS4mePinned.includes('data-ctx-unpin-s4me="s4me:ch1:100"'), "Mostra opzione rimuovi da libreria se pinnato");

  const ctxS4meUnpinned = renderMediaContextMenuHtml(s4meItem, { key: "stream4me:s4me:ch1:100", isS4me: true, isPinnedS4me: false });
  assert(ctxS4meUnpinned.includes('data-ctx-pin-s4me="s4me:ch1:100"'), "Mostra opzione aggiungi alla libreria se non pinnato");

  // Test removeFromContinueCache
  assert.strictEqual(typeof removeFromContinueCache, "function", "removeFromContinueCache deve essere esportata");
  const memStore = {
    data: {
      "gs.pm_continue_watching": JSON.stringify([
        { id: "10", title: "Item 10", source: "locale" },
        { id: "20", title: "Item 20", source: "locale" },
      ]),
    },
    getItem(k) { return this.data[k] || null; },
    setItem(k, v) { this.data[k] = String(v); },
  };

  const afterRemoval = removeFromContinueCache("locale:10", memStore);
  assert.strictEqual(afterRemoval.length, 1, "Deve rimanere 1 elemento");
  assert.strictEqual(afterRemoval[0].id, "20", "L'elemento rimosso deve essere locale:10");
  assert.strictEqual(JSON.parse(memStore.getItem("gs.pm_continue_watching")).length, 1, "Storage deve essere aggiornato");

  // ==========================================
  // h) Test style.css (Regole Tassative Prefisso .pm- e Variabili Tema)
  // ==========================================
  const cssPath = path.join(__dirname, "../extensions/media-locale/style.css");
  assert(fs.existsSync(cssPath), "Il file style.css deve esistere");
  const rawCss = fs.readFileSync(cssPath, "utf8");

  // 1. Verifica che tutte le classi richieste siano definite
  const requiredClasses = [
    ".pm-netflix-home",
    ".pm-hero",
    ".pm-hero-body",
    ".pm-hero-title",
    ".pm-hero-desc",
    ".pm-hero-gradient",
    ".pm-carousel",
    ".pm-carousel-header",
    ".pm-carousel-row",
    ".pm-carousel-title",
    ".pm-carousel-count",
    ".pm-card",
    ".pm-modal-detail",
    ".pm-modal-close",
    ".pm-modal-overlay",
    ".pm-settings-modal",
    ".pm-settings-overlay",
    ".pm-source-badge",
    ".pm-source-select",
    ".pm-sources-grid",
    ".pm-wl-stats",
    ".pm-wl-stat-pill",
    ".pm-wl-toolbar",
    ".pm-wl-list",
    ".pm-wl-card",
    ".pm-wl-priority-badge",
    ".pm-wl-status-badge",
    ".pm-wl-note-input",
    ".pm-wl-controls",
    ".pm-ctx-menu",
    ".pm-ctx-item",
    ".pm-fullscreen-mode",
  ];
  for (const cls of requiredClasses) {
    const rx = new RegExp("(^|[\\s,{}>.])" + cls.replace(".", "\\.") + "([\\s,{:>]|$)");
    assert(rx.test(rawCss), `style.css deve definire la classe ${cls}`);
  }

  // 2. Verifica che non usi altre variabili CSS oltre alle 8 consentite
  const allowedVars = new Set([
    "--bg",
    "--bg-2",
    "--bg-3",
    "--panel",
    "--line",
    "--text",
    "--muted",
    "--accent",
  ]);
  const varMatches = [...rawCss.matchAll(/var\(\s*(--[a-zA-Z0-9_-]+)/g)].map((m) => m[1]);
  assert(varMatches.length > 0, "style.css deve utilizzare le variabili tema");
  for (const v of varMatches) {
    assert(allowedVars.has(v), `Variabile CSS non consentita in style.css: ${v}`);
  }

  // 3. Verifica hover zoom elegante su .pm-card
  assert(rawCss.includes("scale(1.08)"), ".pm-card deve avere hover zoom scale(1.08)");
  assert(rawCss.includes("box-shadow"), ".pm-card deve avere ombra elegante");

  // 4. Verifica che TUTTI i selettori abbiano il prefisso .pm-
  const cleanCss = rawCss.replace(/\/\*[\s\S]*?\*\//g, "");

  const selectors = [];
  let depth = 0;
  let current = "";
  for (let i = 0; i < cleanCss.length; i++) {
    const char = cleanCss[i];
    if (char === "{") {
      const trimmed = current.trim();
      if (depth === 0) {
        if (!trimmed.startsWith("@")) {
          selectors.push(trimmed);
        }
      } else if (depth === 1) {
        // All'interno di @media
        selectors.push(trimmed);
      }
      current = "";
      depth++;
    } else if (char === "}") {
      current = "";
      depth--;
    } else {
      current += char;
    }
  }

  const individualSelectors = [];
  for (const selGroup of selectors) {
    for (const s of selGroup.split(",")) {
      const t = s.trim();
      if (t) individualSelectors.push(t);
    }
  }

  assert(individualSelectors.length > 0, "Nessun selettore trovato in style.css");
  for (const sel of individualSelectors) {
    assert(
      sel.startsWith(".pm-"),
      `Tutti i selettori devono iniziare con .pm-, trovato invece: "${sel}"`
    );
  }

  console.log("ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
