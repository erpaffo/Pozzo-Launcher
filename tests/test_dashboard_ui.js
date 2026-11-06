require("./_i18n_stub");
"use strict";
// Test suite per il motore Dashboard, i widget integrati e la persistenza del layout.
// Esecuzione: `node tests/test_dashboard_ui.js`

const assert = require("assert");
const path = require("path");

// Configurazione ambiente storage finto prima del caricamento di dashboard.js
const storageMap = new Map();
global.localStorage = {
  getItem: (k) => (storageMap.has(k) ? storageMap.get(k) : null),
  setItem: (k, v) => storageMap.set(k, String(v)),
  removeItem: (k) => storageMap.delete(k),
  clear: () => storageMap.clear(),
};

// Mock globali minimi Pozzo
global.esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

global.hue = (s) => {
  let h = 0;
  for (let i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
};

global.platName = (p) => (String(p || "").startsWith("snes") ? "Super Nintendo" : p || "");

global.resumeLeftText = (sec) => {
  if (!(sec > 0)) return "";
  const m = Math.round(sec / 60);
  if (m < 60) return `circa ${Math.max(1, m)} min rimasti`;
  const h = Math.round(m / 60);
  return `circa ${h} h rimast${h === 1 ? "a" : "e"}`;
};

global.resumeSaveText = (save) => {
  if (!save || !save.time) return "";
  return "salvataggio di oggi 14:30";
};

// Carica dashboard.js
const dashboardPath = path.join(__dirname, "..", "pozzo", "app", "static", "js", "dashboard.js");
const dashboard = require(dashboardPath);

const {
  registerWidget,
  getDashboardLayout,
  saveDashboardLayout,
  getDefaultDashboardLayout,
  resetDashboardLayout,
  normalizeDashboardLayout,
  renderCustomDashboard,
  builtInWidgets,
} = dashboard;

// ============================================================================
// 1. REGISTRY DEI WIDGET (GS.ui.registerWidget)
// ============================================================================
{
  assert(global.GS && global.GS.ui && global.GS.ui.widgets instanceof Map, "GS.ui.widgets non inizializzato");

  // Verifica registrazione automatica dei 5 widget integrati
  const expectedBuiltIns = ["games:resume", "apps:launcher", "stats:overview", "games:favorites", "games:recent"];
  for (const id of expectedBuiltIns) {
    const w = global.GS.ui.widgets.get(id);
    assert(w, `Widget integrato mancante: ${id}`);
    assert.strictEqual(typeof w.render, "function", `Render non è funzione per ${id}`);
    assert(w.title && typeof w.title === "string", `Titolo mancante per ${id}`);
  }

  // Registrazione valida di un widget personalizzato
  const customDef = {
    id: "custom:test_widget",
    title: "Widget di prova",
    description: "Descrizione del widget di prova",
    category: "tools",
    defaultSpan: 2,
    render: () => '<div class="custom-widget">Contenuto</div>',
  };
  const registered = registerWidget(customDef);
  assert.strictEqual(registered.id, "custom:test_widget");
  assert.strictEqual(global.GS.ui.widgets.get("custom:test_widget"), registered);

  // Gestione errori per definizioni non valide
  assert.throws(() => registerWidget(null), /oggetto/, "Deve fallire con null");
  assert.throws(() => registerWidget("non un oggetto"), /oggetto/, "Deve fallire con stringa");
  assert.throws(() => registerWidget({}), /id/, "Deve fallire senza id");
  assert.throws(() => registerWidget({ id: "   ", title: "T", render: () => "" }), /id/, "Deve fallire con id vuoto");
  assert.throws(() => registerWidget({ id: "valid", title: "", render: () => "" }), /titolo/, "Deve fallire senza titolo");
  assert.throws(() => registerWidget({ id: "valid", title: "T", render: null }), /render/, "Deve fallire senza render");
  assert.throws(() => registerWidget({ id: "valid", title: "T", render: "non una funzione" }), /render/, "Deve fallire con render non funzione");

  console.log("ok  1. Widget registry: registrazione, recupero e gestione errori");
}

// ============================================================================
// 2. GESTIONE E PERSISTENZA DEL LAYOUT
// ============================================================================
{
  storageMap.clear();

  // Layout predefinito
  const def = getDefaultDashboardLayout();
  assert.strictEqual(def.length, 5, "Il layout predefinito deve avere 5 widget");
  assert.deepStrictEqual(
    def.map((w) => ({ id: w.widgetId, span: w.span })),
    [
      { id: "games:resume", span: 2 },
      { id: "apps:launcher", span: 1 },
      { id: "stats:overview", span: 1 },
      { id: "games:favorites", span: 2 },
      { id: "games:recent", span: "full" },
    ],
    "Spans e id del layout predefinito non corrispondono"
  );

  // Fallback al layout predefinito quando non c'è nulla in storage
  const initial = getDashboardLayout();
  assert.deepStrictEqual(initial, def, "In assenza di salvataggi deve restituire il predefinito");

  // Salvataggio e recupero layout valido
  const testLayout = [
    { instanceId: "w-1", widgetId: "games:resume", span: 2 },
    { instanceId: "w-2", widgetId: "stats:overview", span: 1 },
  ];
  saveDashboardLayout(testLayout);
  const loaded = getDashboardLayout();
  assert.strictEqual(loaded.length, 2);
  assert.strictEqual(loaded[0].instanceId, "w-1");
  assert.strictEqual(loaded[0].widgetId, "games:resume");
  assert.strictEqual(loaded[0].span, 2);

  // Salvataggio layout vuoto
  saveDashboardLayout([]);
  assert.deepStrictEqual(getDashboardLayout(), [], "Il layout vuoto deve essere preservato");

  // Persistenza per profilo specifico
  const profileLayout = [{ instanceId: "prof-1", widgetId: "games:favorites", span: 2 }];
  saveDashboardLayout(profileLayout, "user-alice");
  assert.strictEqual(getDashboardLayout("user-alice").length, 1);
  assert.strictEqual(getDashboardLayout("user-alice")[0].widgetId, "games:favorites");
  // Altro profilo usa il layout globale (attualmente vuoto)
  assert.deepStrictEqual(getDashboardLayout("user-bob"), []);

  // Ripristino del layout
  resetDashboardLayout();
  assert.deepStrictEqual(getDashboardLayout(), def, "resetDashboardLayout deve ripristinare il predefinito");

  // Ripristino con profileId
  resetDashboardLayout("user-alice");
  assert.deepStrictEqual(getDashboardLayout("user-alice"), def, "resetDashboardLayout(profileId) deve ripristinare il predefinito");

  // Recupero da dati corrotti (JSON non valido, tipi errati)
  storageMap.set("gs.dashboard.layout", "{corrupted json !!!");
  assert.deepStrictEqual(getDashboardLayout(), def, "JSON non valido deve ricadere sul predefinito");

  storageMap.set("gs.dashboard.layout", JSON.stringify("non un array"));
  assert.deepStrictEqual(getDashboardLayout(), def, "Stringa deve ricadere sul predefinito");

  storageMap.set("gs.dashboard.layout", JSON.stringify(12345));
  assert.deepStrictEqual(getDashboardLayout(), def, "Numero deve ricadere sul predefinito");

  storageMap.set("gs.dashboard.layout", JSON.stringify({ a: 1 }));
  assert.deepStrictEqual(getDashboardLayout(), def, "Oggetto deve ricadere sul predefinito");

  // Normalizzazione e gestione widget non installati / sconosciuti
  const layoutWithUnknown = [
    { instanceId: "w-known", widgetId: "games:resume", span: 2 },
    { instanceId: "w-unknown", widgetId: "uninstalled:external_plugin", span: 1 },
  ];
  const normalized = normalizeDashboardLayout(layoutWithUnknown);
  assert.strictEqual(normalized.length, 2, "I widget sconosciuti non devono essere scartati brutalmente");
  assert.strictEqual(normalized[1].widgetId, "uninstalled:external_plugin");

  console.log("ok  2. Layout persistence: predefinito, vuoto, profili, recupero dati corrotti e widget sconosciuti");
}

// ============================================================================
// 3. RENDERING DEI WIDGET INTEGRATI, ESCAPING E ZERO COLORI HARDCODED
// ============================================================================
{
  const mockState = {
    games: [
      {
        id: 1,
        title: 'Super <script>alert("xss")</script> & Fun "Bros"',
        platform: 'snes<img src=x onerror=1>',
        year: 1992,
        store: null,
        genres: "Platform, Action",
        grp: { primary: 1, last: 1700000000, playtime: 7200, status: "playing", favorite: 1 },
        remaining_secs: 3600,
        save: { time: 1700000000 },
      },
      {
        id: 2,
        title: 'Calcolatrice & Utility <safe>',
        platform: "pc",
        year: 2024,
        store: "manual",
        genres: "Applicazione",
        grp: { primary: 2, last: 1600000000, playtime: 1800, status: "done", favorite: 0 },
      },
      {
        id: 3,
        title: "Chrono Trigger",
        platform: "snes",
        year: 1995,
        store: null,
        genres: "RPG",
        grp: { primary: 3, last: 0, playtime: 0, status: "backlog", favorite: 1 },
      },
    ],
  };

  const context = { state: mockState };

  // 3a. games:resume
  const resumeWidget = global.GS.ui.widgets.get("games:resume");
  const resumeHtml = resumeWidget.render(context);
  assert(resumeHtml.includes('data-resume-play="1"'), "Deve contenere il bottone data-resume-play col gioco più recente");
  assert(resumeHtml.includes("▶ Riprendi"), "Deve contenere il testo del pulsante ▶ Riprendi");
  assert(resumeHtml.includes("/img/1/cover?w=640"), "Deve contenere l'immagine di copertina");
  assert(resumeHtml.includes("circa 1 h rimasta"), "Deve contenere il testo del tempo rimanente da resumeLeftText");
  assert(resumeHtml.includes("salvataggio di oggi 14:30"), "Deve contenere il timestamp del salvataggio da resumeSaveText");
  // Escaping rigoroso
  assert(!resumeHtml.includes("<script>"), "Tag script non escapato in resume");
  assert(resumeHtml.includes("&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;"), "Titolo gioco non escapato correttamente");
  assert(resumeHtml.includes("Super Nintendo"), "Nome piattaforma risolto");

  // 3b. apps:launcher
  const appsWidget = global.GS.ui.widgets.get("apps:launcher");
  const appsHtml = appsWidget.render(context);
  assert(appsHtml.includes('data-app-launch="2"'), "Deve includere l'applicazione con id 2");
  assert(!appsHtml.includes('data-app-launch="1"'), "Non deve includere giochi normali non app");
  assert(appsHtml.includes("＋ Aggiungi applicazione"), "Deve includere il pulsante per aggiungere applicazione");
  assert(appsHtml.includes('data-add-app="app"'), "Pulsante aggiungi deve avere data-add-app");
  // Escaping rigoroso
  assert(appsHtml.includes("Calcolatrice &amp; Utility &lt;safe&gt;"), "Titolo app non escapato");

  // 3c. games:favorites
  const favsWidget = global.GS.ui.widgets.get("games:favorites");
  const favsHtml = favsWidget.render(context);
  assert(favsHtml.includes('data-shelf-game="1"'), "Deve contenere il preferito id 1");
  assert(favsHtml.includes('data-shelf-game="3"'), "Deve contenere il preferito id 3");
  assert(!favsHtml.includes('data-shelf-game="2"'), "Non deve contenere il non preferito id 2");
  assert(favsHtml.includes("shelf-lane"), "Deve usare la corsia shelf-lane standard");

  // 3d. games:recent
  const recentWidget = global.GS.ui.widgets.get("games:recent");
  const recentHtml = recentWidget.render(context);
  assert(recentHtml.includes('data-shelf-game="1"'), "Deve contenere il recente id 1");
  assert(recentHtml.includes('data-shelf-game="2"'), "Deve contenere il recente id 2");
  assert(!recentHtml.includes('data-shelf-game="3"'), "Non deve contenere id 3 (mai avviato)");
  // Ordine decrescente di avvio (id 1 prima di id 2)
  const pos1 = recentHtml.indexOf('data-shelf-game="1"');
  const pos2 = recentHtml.indexOf('data-shelf-game="2"');
  assert(pos1 < pos2, "I giochi recenti devono essere ordinati decrescenti per last");

  // 3e. stats:overview
  const statsWidget = global.GS.ui.widgets.get("stats:overview");
  const statsHtml = statsWidget.render(context);
  assert(statsHtml.includes("Tempo di gioco"), "Etichetta Tempo di gioco presente");
  assert(statsHtml.includes("Giochi"), "Etichetta Giochi presente");
  assert(statsHtml.includes("Completati"), "Etichetta Completati presente");
  assert(statsHtml.includes("2 h 30 min"), "Tempo totale sommato (7200s + 1800s = 9000s = 2h 30m)");
  assert(statsHtml.includes(">3<"), "Totale giochi deve essere 3");
  assert(statsHtml.includes(">1<"), "Totale completati deve essere 1 (id 2 ha status 'done')");

  // 3f. Test rigoroso: nessun colore hardcoded in tutto l'HTML generato
  const allHtml = [resumeHtml, appsHtml, favsHtml, recentHtml, statsHtml].join("\n");
  const hexColorMatch = allHtml.match(/#([0-9a-fA-F]{3,8})\b/g);
  assert.strictEqual(hexColorMatch, null, `Trovati colori hex hardcoded: ${JSON.stringify(hexColorMatch)}`);

  const rgbColorMatch = allHtml.match(/rgba?\s*\(/gi);
  assert.strictEqual(rgbColorMatch, null, `Trovate funzioni rgb/rgba hardcoded: ${JSON.stringify(rgbColorMatch)}`);

  console.log("ok  3. Built-in widgets: HTML, dati filtrati, escaping e zero colori hardcoded");
}

// ============================================================================
// 4. RENDERER CUSTOM DASHBOARD E MODALITÀ MODIFICA
// ============================================================================
{
  storageMap.clear();

  // Mock Element minimale con supporto per click delegation
  class MockElement {
    constructor() {
      this.innerHTML = "";
      this._gsEditMode = false;
      this._gsShowAddModal = false;
      this.onclick = null;
    }

    // Helper per trovare selettori nell'innerHTML
    containsText(text) {
      return this.innerHTML.includes(text);
    }

    // Simula click delegato
    dispatchClick(attrs = {}) {
      const fakeTarget = {
        getAttribute: (k) => attrs[k] || null,
        dataset: Object.fromEntries(
          Object.entries(attrs).filter(([k]) => k.startsWith("data-")).map(([k, v]) => [
            k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase()),
            v,
          ])
        ),
        classList: {
          contains: (cls) => Boolean(attrs["class"] && attrs["class"].split(/\s+/).includes(cls)),
        },
        closest: (sel) => {
          if (sel.startsWith(".")) {
            const cls = sel.slice(1);
            if (attrs["class"] && attrs["class"].split(/\s+/).includes(cls)) return fakeTarget;
          }
          if (sel.startsWith("[") && sel.endsWith("]")) {
            const inner = sel.slice(1, -1);
            if (inner.includes("=")) {
              const [k, v] = inner.split("=");
              const cleanV = v.replace(/^["']|["']$/g, "");
              if (attrs[k] === cleanV) return fakeTarget;
            } else {
              if (attrs[inner] !== undefined) return fakeTarget;
            }
          }
          return null;
        },
      };

      if (typeof this.onclick === "function") {
        this.onclick({ target: fakeTarget });
      }
    }
  }

  const el = new MockElement();
  const ctx = {
    state: {
      games: [
        { id: 10, title: "Game 10", platform: "pc", grp: { primary: 10, last: 100 } },
      ],
    },
  };

  // Rendering iniziale in modalità visualizzazione
  renderCustomDashboard(el, ctx);
  assert(el.containsText("Dashboard"), "Titolo Dashboard presente");
  assert(el.containsText("✏️ Personalizza Dashboard"), "Pulsante Personalizza Dashboard presente");
  assert(!el.containsText("✓ Fine Modifica"), "Fine Modifica non deve apparire inizialmente");
  assert(!el.containsText(".gs-edit-bar"), "Edit bar non presente inizialmente");

  // Attiva modalità modifica
  el.dispatchClick({ "data-dashboard-toggle-edit": "" });
  assert.strictEqual(el._gsEditMode, true, "_gsEditMode deve essere true");
  assert(el.containsText("✓ Fine Modifica"), "Pulsante deve diventare Fine Modifica");
  assert(el.containsText("＋ Aggiungi Widget"), "Pulsante Aggiungi Widget presente in edit mode");
  assert(el.containsText("Ripristina layout predefinito"), "Pulsante Ripristina layout presente in edit mode");
  assert(el.containsText("data-widget-move"), "Controlli di spostamento presenti");
  assert(el.containsText("data-widget-span"), "Controlli di ridimensionamento presenti");
  assert(el.containsText("data-widget-remove"), "Controlli di eliminazione presenti");

  // Prova rimozione del primo widget
  const initialLayout = getDashboardLayout();
  const firstId = initialLayout[0].instanceId;
  el.dispatchClick({
    "class": "gs-widget-card",
    "data-instance-id": firstId,
    "data-widget-remove": "",
  });
  const afterRemove = getDashboardLayout();
  assert.strictEqual(afterRemove.length, initialLayout.length - 1, "Un widget deve essere stato rimosso");
  assert(!afterRemove.some((w) => w.instanceId === firstId), "Il widget rimosso non deve essere più presente");

  // Prova apertura modale Aggiungi Widget
  el.dispatchClick({ "data-dashboard-add-widget": "" });
  assert.strictEqual(el._gsShowAddModal, true, "_gsShowAddModal deve essere true");
  assert(el.containsText("Aggiungi Widget"), "Modale Aggiungi Widget aperta");

  // Prova aggiunta di un widget dalla modale
  el.dispatchClick({ "data-add-widget-id": "games:resume" });
  const afterAdd = getDashboardLayout();
  assert.strictEqual(afterAdd[afterAdd.length - 1].widgetId, "games:resume", "Il widget deve essere stato aggiunto in coda");
  assert.strictEqual(el._gsShowAddModal, false, "La modale deve chiudersi dopo l'aggiunta");

  // Prova ripristino layout predefinito
  el.dispatchClick({ "data-dashboard-reset": "" });
  assert.deepStrictEqual(getDashboardLayout(), getDefaultDashboardLayout(), "Il layout deve tornare al predefinito");

  // Chiudi modalità modifica
  el.dispatchClick({ "data-dashboard-toggle-edit": "" });
  assert.strictEqual(el._gsEditMode, false, "_gsEditMode deve essere tornato false");
  assert(el.containsText("✏️ Personalizza Dashboard"), "Pulsante tornato a Personalizza");

  // Rendering elegante con widget sconosciuti senza errori
  saveDashboardLayout([
    { instanceId: "w-gone", widgetId: "ghost:nonexistent", span: 1 },
  ]);
  assert.doesNotThrow(() => renderCustomDashboard(el, ctx), "Non deve lanciare eccezioni per widget sconosciuti");
  assert(el.containsText("Widget non disponibile: ghost:nonexistent"), "Mostra avviso pulito per widget sconosciuto");

  console.log("ok  4. Renderer Custom Dashboard: modalita' modifica, controlli, modale e fallback");
}

// ============================================================================
// 5. NUOVI WIDGET GIOCHI & STRUMENTI + CATEGORIE NEL MODALE
// ============================================================================
{
  const ids = ["games:roulette", "games:most_played", "games:backlog", "tools:quick_actions", "downloads:status"];
  for (const id of ids) assert(global.GS.ui.widgets.get(id), `Widget mancante: ${id}`);
  const W = (id) => global.GS.ui.widgets.get(id);
  assert.strictEqual(W("games:roulette").category, "games");
  assert.strictEqual(W("tools:quick_actions").category, "tools");

  // Libreria vuota: nessun crash, stato vuoto
  const empty = { state: { games: [] } };
  for (const id of ids) assert.doesNotThrow(() => W(id).render(empty), `Crash con libreria vuota: ${id}`);
  assert(W("games:roulette").render(empty).includes("gs-widget-empty"));
  assert(W("games:most_played").render(empty).includes("gs-widget-empty"));

  const ctx = { state: { games: [
    { id: 1, title: "A", grp: { primary: 1, playtime: 3600 } },
    { id: 2, title: "B", grp: { primary: 2, playtime: 7200 } },
    { id: 3, title: "C", critics: 0.9, grp: { primary: 3, playtime: 0 } },
    { id: 4, title: "D", critics: 0.5, grp: { primary: 4, playtime: 0 } },
    { id: 5, title: "Hidden", grp: { primary: 5, hidden: 1 } },
  ] } };

  // Roulette: il reroll cambia sempre scelta con più giochi
  const pickOf = (h) => h.match(/data-resume-play="(\d+)"/)[1];
  const first = pickOf(W("games:roulette").render(ctx));
  assert.notStrictEqual(first, "5", "Mai giochi nascosti");
  assert.strictEqual(pickOf(W("games:roulette").render(ctx)), first, "Scelta stabile tra render");
  dashboard.rerollRoulette(ctx);
  assert.notStrictEqual(pickOf(W("games:roulette").render(ctx)), first, "Il reroll deve cambiare gioco");

  // Più giocati: ordine decrescente e barre relative
  const mp = W("games:most_played").render(ctx);
  assert(mp.indexOf('data-shelf-game="2"') < mp.indexOf('data-shelf-game="1"'));
  assert(mp.includes("width:100%") && mp.includes("width:50%"));
  assert(!mp.includes('data-shelf-game="3"'), "Escludere 0 ore");

  // Backlog: solo 0 ore, ordinati per critica
  const bl = W("games:backlog").render(ctx);
  assert(bl.indexOf('data-shelf-game="3"') < bl.indexOf('data-shelf-game="4"'));
  assert(!bl.includes('data-shelf-game="1"') && !bl.includes('data-shelf-game="5"'));

  const qa = W("tools:quick_actions").render(ctx);
  for (const a of ["bigpicture", "reload", "add", "settings"]) assert(qa.includes(`data-quick-action="${a}"`));

  // Modale: schede categoria e filtro
  const el = { innerHTML: "", _gsEditMode: true, _gsShowAddModal: true, onclick: null };
  renderCustomDashboard(el, ctx);
  assert(el.innerHTML.includes("gs-category-tab") && el.innerHTML.includes("Strumenti"));
  assert(el.innerHTML.includes('data-add-widget-id="games:roulette"'));
  el.onclick({ target: { closest: (s) => (s === "[data-add-category]" ? { getAttribute: () => "tools" } : null) } });
  assert.strictEqual(el._gsAddCategory, "tools");
  assert(el.innerHTML.includes('data-add-widget-id="tools:quick_actions"'));
  assert(!el.innerHTML.includes('data-add-widget-id="games:roulette"'), "Filtro categoria non applicato");

  const all = [W("games:roulette").render(ctx), mp, bl, qa, W("downloads:status").render(ctx), el.innerHTML].join("\n");
  assert.strictEqual(all.match(/#([0-9a-fA-F]{3,8})\b|rgba?\s*\(/g), null, "Colori hardcoded");
  console.log("ok  5. Nuovi widget giochi/strumenti e filtro categorie");
}

// ============================================================================
// 6. DRAG AND DROP & OTTIMIZZAZIONE MEMORIA
// ============================================================================
{
  const ctx = {
    state: {
      games: Array.from({ length: 50 }, (_, i) => ({
        id: i + 1,
        title: `Gioco ${i + 1}`,
        grp: { primary: i + 1, last: i + 1 },
      })),
    },
  };

  // Ottimizzazione memoria: libraryGames memoizzato sul context
  const games1 = dashboard.builtInWidgets.find((w) => w.id === "games:recent").render(ctx);
  assert(ctx._cachedLibraryGames, "libraryGames deve memoizzare su context._cachedLibraryGames");
  const countMatches = (games1.match(/data-shelf-game=/g) || []).length;
  assert(countMatches <= 20, "games:recent deve limitare gli elementi a max 20 per ridurre la memoria");

  // Drag & drop
  const el = {
    innerHTML: "",
    _gsEditMode: true,
    querySelectorAll: () => [],
    ondragstart: null,
    ondragover: null,
    ondrop: null,
    ondragend: null,
  };
  saveDashboardLayout([
    { instanceId: "card-a", widgetId: "games:resume", span: 1 },
    { instanceId: "card-b", widgetId: "stats:overview", span: 1 },
  ]);
  renderCustomDashboard(el, ctx);

  assert(el.innerHTML.includes('draggable="true"'), "Le card in edit mode devono avere draggable='true'");
  assert(el.innerHTML.includes("gs-drag-handle"), "Le card in edit mode devono mostrare il drag handle");
  assert(typeof el.ondragstart === "function", "ondragstart definito");
  assert(typeof el.ondragover === "function", "ondragover definito");
  assert(typeof el.ondrop === "function", "ondrop definito");

  // Simula dragstart di card-a e dragover live su card-b
  const mockEventStart = {
    target: { closest: () => ({ getAttribute: () => "card-a", classList: { add() {} } }) },
    dataTransfer: { effectAllowed: "", setData() {} },
  };
  el.ondragstart(mockEventStart);

  const mockEventOver = {
    preventDefault() {},
    dataTransfer: { dropEffect: "" },
    target: { closest: () => ({ getAttribute: () => "card-b" }) },
  };
  el.ondragover(mockEventOver);

  const updatedLayoutOver = getDashboardLayout();
  assert.strictEqual(updatedLayoutOver[0].instanceId, "card-b", "card-b deve essere scambiata live durante dragover");
  assert.strictEqual(updatedLayoutOver[1].instanceId, "card-a", "card-a deve essere scambiata live durante dragover");

  const mockEventDrop = {
    preventDefault() {},
    target: { closest: () => ({ getAttribute: () => "card-b" }) },
  };
  el.ondrop(mockEventDrop);

  const updatedLayout = getDashboardLayout();
  assert.strictEqual(updatedLayout[0].instanceId, "card-b", "card-b deve rimanere prima di card-a dopo drop");
  assert.strictEqual(updatedLayout[1].instanceId, "card-a", "card-a deve rimanere dopo card-b dopo drop");

  // Test unitario della funzione flipAnimate (First, Last, Invert, Play)
  assert(typeof dashboard.flipAnimate === "function", "flipAnimate esportata");
  let flipRun = false;
  dashboard.flipAnimate(null, () => { flipRun = true; });
  assert.strictEqual(flipRun, true, "flipAnimate esegue la callback anche senza contenitore");

  const cardMock1 = { getAttribute: () => "c1", getBoundingClientRect: () => ({ left: 0, top: 0 }), style: {} };
  let c2Left = 200;
  const cardMock2 = { getAttribute: () => "c2", getBoundingClientRect: () => ({ left: c2Left, top: 0 }), style: {} };
  const mockGrid = { querySelectorAll: () => [cardMock1, cardMock2] };

  dashboard.flipAnimate(mockGrid, () => {
    c2Left = 0; // card2 si è mossa a sinistra di 200px
  });
  assert.strictEqual(cardMock2.style.transform, "translate3d(200px, 0px, 0)", "FLIP deve invertire il delta X (First - Last)");
  assert.strictEqual(cardMock2.style.transition, "none", "Invert iniziale deve disattivare la transizione");

  console.log("ok  6. Drag and Drop & animazioni FLIP fluide");
}

// ============================================================================
// 7. RIDIMENSIONAMENTO LIBERO E ADATTAMENTO SPAZIO WIDGET
// ============================================================================
{
  storageMap.clear();

  // Test normalizzazione di span 3 e altezze libere/preset
  const rawWithSizes = [
    { instanceId: "w-size-1", widgetId: "games:resume", span: 3, height: 350 },
    { instanceId: "w-size-2", widgetId: "tools:notes", span: 1, height: "lg" },
    { instanceId: "w-size-3", widgetId: "stats:overview", span: "full", height: "invalid_height" },
  ];
  const normalized = normalizeDashboardLayout(rawWithSizes);
  assert.strictEqual(normalized[0].span, 3, "Span 3 deve essere preservato");
  assert.strictEqual(normalized[0].height, 350, "Altezza numerica 350 deve essere preservata");
  assert.strictEqual(normalized[1].height, "lg", "Altezza preset 'lg' deve essere preservata");
  assert.strictEqual(normalized[2].height, undefined, "Altezza non valida non deve essere impostata");

  // Rendering con span 3, preset altezza e altezza numerica
  saveDashboardLayout([
    { instanceId: "w-custom-1", widgetId: "games:resume", span: 3, height: 420 },
    { instanceId: "w-custom-2", widgetId: "apps:launcher", span: 1, height: "sm" },
  ]);

  const el = {
    innerHTML: "",
    _gsEditMode: true,
    querySelectorAll: () => [],
    onclick: null,
    onpointerdown: null,
    onmousedown: null,
  };
  const ctx = { state: { games: [] } };
  renderCustomDashboard(el, ctx);

  assert(el.innerHTML.includes("span-3"), "Classe span-3 deve essere applicata");
  assert(el.innerHTML.includes("style=\"min-height:420px;\""), "Inline style min-height numerico deve essere applicato");
  assert(el.innerHTML.includes("height-sm"), "Classe height-sm deve essere applicata");
  assert(el.innerHTML.includes("data-widget-height=\"sm\""), "Pulsanti altezza devono essere presenti");
  assert(el.innerHTML.includes("data-widget-height=\"lg\""), "Pulsante altezza L deve essere presente");
  assert(el.innerHTML.includes("gs-widget-resize-handle"), "Maniglia di ridimensionamento deve essere presente in edit mode");

  // Verifica click su pulsante larghezza 3x
  const fakeSpanTarget = {
    closest(sel) {
      if (sel.includes("gs-widget-card")) return { getAttribute: () => "w-custom-2", dataset: { instanceId: "w-custom-2" } };
      if (sel.includes("data-widget-span")) return { getAttribute: () => "3", dataset: { widgetSpan: "3" } };
      return null;
    },
  };
  el.onclick({ target: fakeSpanTarget });
  assert.strictEqual(getDashboardLayout()[1].span, 3, "Click su 3x deve impostare span a 3");

  // Verifica click su pulsante altezza 'md'
  const fakeHeightTarget = {
    closest(sel) {
      if (sel.includes("gs-widget-card")) return { getAttribute: () => "w-custom-2", dataset: { instanceId: "w-custom-2" } };
      if (sel.includes("data-widget-height")) return { getAttribute: () => "md", dataset: { widgetHeight: "md" } };
      return null;
    },
  };
  el.onclick({ target: fakeHeightTarget });
  assert.strictEqual(getDashboardLayout()[1].height, "md", "Click su M deve impostare height a 'md'");

  // Verifica click su altezza 'auto' (resetta altezza)
  const fakeAutoTarget = {
    closest(sel) {
      if (sel.includes("gs-widget-card")) return { getAttribute: () => "w-custom-2", dataset: { instanceId: "w-custom-2" } };
      if (sel.includes("data-widget-height")) return { getAttribute: () => "auto", dataset: { widgetHeight: "auto" } };
      return null;
    },
  };
  el.onclick({ target: fakeAutoTarget });
  assert.strictEqual(getDashboardLayout()[1].height, undefined, "Click su Auto deve resettare height");

  // Verifica che senza modalità modifica la maniglia di resize non venga iniettata
  el._gsEditMode = false;
  renderCustomDashboard(el, ctx);
  assert(!el.innerHTML.includes("gs-widget-resize-handle"), "Maniglia di resize NON deve apparire se edit mode e' false");

  // Test interattivo di drag-to-resize con il mouse tramite maniglia
  el._gsEditMode = true;
  saveDashboardLayout([{ instanceId: "drag-card-1", widgetId: "games:resume", span: 1 }]);
  renderCustomDashboard(el, ctx);

  let mockClasses = ["card", "gs-widget-card", "span-1"];
  let mockDraggable = "true";
  const mockCardEl = {
    getAttribute: (name) => name === "data-instance-id" ? "drag-card-1" : null,
    dataset: { instanceId: "drag-card-1" },
    classList: {
      contains: (cls) => mockClasses.includes(cls),
      add: (cls) => { if (!mockClasses.includes(cls)) mockClasses.push(cls); },
      remove: (cls) => { mockClasses = mockClasses.filter(c => c !== cls); },
    },
    setAttribute: (name, val) => { if (name === "draggable") mockDraggable = val; },
    style: {},
    offsetWidth: 320,
    offsetHeight: 200,
    getBoundingClientRect: () => ({ width: 320, height: 200, left: 10, top: 10 }),
  };
  const mockHandleEl = {
    classList: { contains: (cls) => cls === "gs-widget-resize-handle" },
    closest: (sel) => sel.includes("gs-widget-card") ? mockCardEl : null,
  };

  el.querySelector = (sel) => sel === ".gs-dashboard-grid" ? { getBoundingClientRect: () => ({ width: 1200, left: 0 }) } : null;

  // Inizia drag resize
  el.onpointerdown({
    target: {
      closest: (sel) => sel.includes("gs-widget-resize-handle") ? mockHandleEl : (sel.includes("gs-widget-card") ? mockCardEl : null),
    },
    clientX: 100,
    clientY: 100,
    preventDefault: () => {},
    stopPropagation: () => {},
  });
  assert(mockClasses.includes("gs-resizing"), "Card deve avere classe gs-resizing durante il drag");
  assert.strictEqual(mockDraggable, "false", "Draggable deve essere disattivato durante il resize per non confliggere col DnD");

  // Simula pointermove
  if (global.window && typeof global.window._testEmitPointerMove === "function") {
    global.window._testEmitPointerMove({ clientX: 500, clientY: 300 });
  }

  console.log("ok  7. Ridimensionamento libero e adattamento spazio widget");
}

// ============================================================================
// 8. MODALITÀ GALLERIA WIDGET, ANTEPRIME LIVE E TRASCINAMENTO A SCHERMO
// ============================================================================
{
  storageMap.clear();

  const el = {
    innerHTML: "",
    _gsEditMode: true,
    _gsShowAddModal: true,
    querySelectorAll: () => [],
    ondragstart: null,
    ondragover: null,
    ondrop: null,
    ondragend: null,
  };
  const ctx = {
    state: {
      games: [
        { id: 1, title: "Zelda", platform: "switch", grp: { primary: 1, last: 500 } },
      ],
    },
  };

  saveDashboardLayout([
    { instanceId: "card-1", widgetId: "games:resume", span: 2 },
    { instanceId: "card-2", widgetId: "stats:overview", span: 1 },
  ]);

  renderCustomDashboard(el, ctx);

  // 1. Verifica elementi galleria e anteprime
  assert(el.innerHTML.includes("gs-gallery-modal"), "Modale deve usare il layout galleria gs-gallery-modal");
  assert(el.innerHTML.includes("gs-gallery-grid"), "Griglia della galleria presente");
  assert(el.innerHTML.includes("gs-gallery-preview"), "Anteprime grafiche dei widget presenti");
  assert(el.innerHTML.includes("data-gallery-widget-id"), "Ogni card galleria deve avere data-gallery-widget-id");
  assert(el.innerHTML.includes("draggable=\"true\""), "Le card della galleria devono essere trascinabili draggable=true");

  // 2. Verifica che l'anteprima contenga markup effettivo del widget
  assert(el.innerHTML.includes("gs-gallery-preview"), "Contenitore anteprima presente");

  // 3. Test trascinamento dalla galleria direttamente nella griglia (tra card-1 e card-2)
  const mockDragFromGallery = {
    target: {
      closest: (sel) => {
        if (sel === ".gs-gallery-card") {
          return {
            getAttribute: (a) => (a === "data-gallery-widget-id" ? "tools:notes" : null),
            classList: { add() {} },
          };
        }
        return null;
      },
    },
    dataTransfer: { effectAllowed: "", setData() {} },
  };
  el.ondragstart(mockDragFromGallery);
  assert.strictEqual(el._gsDraggedWidgetId, "tools:notes", "ID del widget in trascinamento memorizzato da galleria");

  // Simula hover sopra card-2
  const mockDragOverCard2 = {
    preventDefault() {},
    dataTransfer: { dropEffect: "" },
    target: {
      closest: (sel) => (sel === ".gs-widget-card" ? { getAttribute: (a) => (a === "data-instance-id" ? "card-2" : null), classList: { add() {} } } : null),
    },
  };
  el.ondragover(mockDragOverCard2);

  // Rilascia (drop) sopra card-2 per inserire tools:notes prima di card-2
  const mockDropOnCard2 = {
    preventDefault() {},
    target: {
      closest: (sel) => (sel === ".gs-widget-card" ? { getAttribute: (a) => (a === "data-instance-id" ? "card-2" : null) } : null),
    },
  };
  el.ondrop(mockDropOnCard2);

  const updatedLayout = getDashboardLayout();
  assert.strictEqual(updatedLayout.length, 3, "Il layout deve contenere 3 widget dopo l'inserimento");
  assert.strictEqual(updatedLayout[0].instanceId, "card-1", "Primo widget rimane card-1");
  assert.strictEqual(updatedLayout[1].widgetId, "tools:notes", "tools:notes inserito alla posizione del drop");
  assert.strictEqual(updatedLayout[2].instanceId, "card-2", "card-2 spostata dopo il widget inserito");
  assert.strictEqual(el._gsShowAddModal, false, "La galleria deve chiudersi dopo l'inserimento tramite drop");

  console.log("ok  8. Modalita' galleria widget, anteprime live e trascinamento a schermo");
}

console.log("test_dashboard_ui.js: ok");
