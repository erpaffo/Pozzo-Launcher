"use strict";
// Helper puri di extensions/media-locale/logica.js e player.js (ESM, importati via copia .mjs).
const assert = require("assert"), fs = require("fs"), os = require("os"), path = require("path"), { pathToFileURL } = require("url");
const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "med-"));
const tmp = path.join(tmpDir, "logica.mjs");
fs.copyFileSync(path.join(__dirname, "../extensions/media-locale/logica.js"), tmp);
const playerSrc = fs.readFileSync(path.join(__dirname, "../extensions/media-locale/player.js"), "utf8")
  .replace("./logica.js", "./logica.mjs");
const tmpPlayer = path.join(tmpDir, "player.mjs");
fs.writeFileSync(tmpPlayer, playerSrc);

Promise.all([import(pathToFileURL(tmp).href), import(pathToFileURL(tmpPlayer).href)]).then(async ([L, P]) => {
  // 1. formatDuration(sec)
  assert.strictEqual(L.formatDuration(0), "0:00");
  assert.strictEqual(L.formatDuration(5), "0:05");
  assert.strictEqual(L.formatDuration(75), "1:15");
  assert.strictEqual(L.formatDuration(599), "9:59");
  assert.strictEqual(L.formatDuration(3600), "1:00:00");
  assert.strictEqual(L.formatDuration(3665), "1:01:05");
  assert.strictEqual(L.formatDuration(null), "");
  assert.strictEqual(L.formatDuration(undefined), "");
  assert.strictEqual(L.formatDuration(""), "");
  assert.strictEqual(L.formatDuration(-10), "");
  assert.strictEqual(L.formatDuration("invalid"), "");

  // 2. resumeOf(item) -> % 0..100
  assert.strictEqual(L.resumeOf(null), 0);
  assert.strictEqual(L.resumeOf({}), 0);
  assert.strictEqual(L.resumeOf({ duration: 100, resume_pos: 45 }), 45);
  assert.strictEqual(L.resumeOf({ duration: 200, resume_pos: 50 }), 25);
  assert.strictEqual(L.resumeOf({ seen: true }), 100);
  assert.strictEqual(L.resumeOf({ seen: 1 }), 100);
  assert.strictEqual(L.resumeOf({ seen: true, duration: 100, resume_pos: 0 }), 100);
  assert.strictEqual(L.resumeOf({ seen: false, duration: 100, resume_pos: 30 }), 30);
  assert.strictEqual(L.resumeOf({ duration: 100, resume_pos: 150 }), 100);
  assert.strictEqual(L.resumeOf({ duration: 100, resume_pos: -10 }), 0);
  assert.strictEqual(L.resumeOf({ duration: 0, resume_pos: 50 }), 0);

  // 3. isSeen(item) (seen o >=90%)
  assert.strictEqual(L.isSeen(null), false);
  assert.strictEqual(L.isSeen({}), false);
  assert.strictEqual(L.isSeen({ seen: true }), true);
  assert.strictEqual(L.isSeen({ seen: 1 }), true);
  assert.strictEqual(L.isSeen({ seen: "true" }), true);
  assert.strictEqual(L.isSeen({ seen: false, duration: 100, resume_pos: 50 }), false);
  assert.strictEqual(L.isSeen({ duration: 100, resume_pos: 89 }), false);
  assert.strictEqual(L.isSeen({ duration: 100, resume_pos: 90 }), true);
  assert.strictEqual(L.isSeen({ duration: 100, resume_pos: 95 }), true);
  assert.strictEqual(L.isSeen({ duration: 0, resume_pos: 0 }), false);

  // 4. groupEpisodes(items) -> serie->stagioni->episodi ordinati
  assert.deepStrictEqual(L.groupEpisodes([]), {});
  assert.deepStrictEqual(L.groupEpisodes(null), {});
  const sample = [
    { id: "e3", series: "Serie A", season: 2, episode: 1, title: "S2E1" },
    { id: "e1", series: "Serie A", season: 1, episode: 2, title: "S1E2" },
    { id: "e2", series: "Serie A", season: 1, episode: 1, title: "S1E1" },
    { id: "b1", series: "Serie B", season: 1, episode: 1, title: "B1" },
    { id: "f1", kind: "film", title: "Solo Film" }
  ];
  const grouped = L.groupEpisodes(sample);
  assert.deepStrictEqual(Object.keys(grouped), ["Serie A", "Serie B"]);
  assert.strictEqual(grouped["Serie A"][1].length, 2);
  assert.strictEqual(grouped["Serie A"][1][0].id, "e2");
  assert.strictEqual(grouped["Serie A"][1][1].id, "e1");
  assert.strictEqual(grouped["Serie A"][2].length, 1);
  assert.strictEqual(grouped["Serie A"][2][0].id, "e3");
  assert.strictEqual(grouped["Serie B"][1][0].id, "b1");
  assert.strictEqual(grouped["Solo Film"], undefined);

  // 5. nextEpisode(items, currentId)
  assert.strictEqual(L.nextEpisode(sample, "e2")?.id, "e1");
  assert.strictEqual(L.nextEpisode(sample, "e1")?.id, "e3");
  assert.strictEqual(L.nextEpisode(sample, "e3"), null);
  assert.strictEqual(L.nextEpisode(sample, "b1"), null);
  assert.strictEqual(L.nextEpisode(sample, "non-existent"), null);
  assert.strictEqual(L.nextEpisode([], "e1"), null);
  assert.strictEqual(L.nextEpisode(null, "e1"), null);

  // 6. compositeKey(item)
  assert.strictEqual(L.compositeKey(null), "");
  assert.strictEqual(L.compositeKey(undefined), "");
  assert.strictEqual(L.compositeKey({}), "");
  assert.strictEqual(L.compositeKey({ id: null }), "");
  assert.strictEqual(L.compositeKey({ id: "" }), "");
  assert.strictEqual(L.compositeKey({ id: "   " }), "");
  assert.strictEqual(L.compositeKey({ id: "null" }), "");
  assert.strictEqual(L.compositeKey({ id: "undefined" }), "");
  assert.strictEqual(L.compositeKey({ id: 42 }), "media-locale:42");
  assert.strictEqual(L.compositeKey({ id: "m1", source: "media-locale" }), "media-locale:m1");
  assert.strictEqual(L.compositeKey({ id: "j1", source: "jellyfin" }), "jellyfin:j1");
  assert.strictEqual(L.compositeKey({ id: "p1", source: "plex" }), "plex:p1");
  assert.strictEqual(L.compositeKey({ id: "w1", source: "ricette-web" }), "ricette-web:w1");

  // 7. sourceBadge(source)
  assert.deepStrictEqual(L.sourceBadge("media-locale"), { id: "locale", label: "Disco Locale", icon: "📁" });
  assert.deepStrictEqual(L.sourceBadge("locale"), { id: "locale", label: "Disco Locale", icon: "📁" });
  assert.deepStrictEqual(L.sourceBadge("  LOCALE  "), { id: "locale", label: "Disco Locale", icon: "📁" });
  assert.deepStrictEqual(L.sourceBadge("jellyfin"), { id: "jellyfin", label: "Jellyfin", icon: "🌐" });
  assert.deepStrictEqual(L.sourceBadge("plex"), { id: "plex", label: "Plex", icon: "🟠" });
  assert.deepStrictEqual(L.sourceBadge("kodi"), { id: "kodi", label: "Kodi Addon", icon: "🧩" });
  assert.deepStrictEqual(L.sourceBadge("kodi-mediaset"), { id: "kodi", label: "Kodi Addon", icon: "🧩" });
  assert.deepStrictEqual(L.sourceBadge("stream4me"), { id: "web", label: "Stream4me", icon: "🧩" });
  assert.deepStrictEqual(L.sourceBadge("stream4me-ita"), { id: "web", label: "Stream4me", icon: "🧩" });
  assert.deepStrictEqual(L.sourceBadge("s4me"), { id: "web", label: "Stream4me", icon: "🧩" });
  assert.deepStrictEqual(L.sourceBadge("ricette-web"), { id: "web", label: "Web / Streaming", icon: "📡" });
  assert.deepStrictEqual(L.sourceBadge(""), { id: "web", label: "Web / Streaming", icon: "📡" });
  assert.deepStrictEqual(L.sourceBadge(null), { id: "web", label: "Web / Streaming", icon: "📡" });

  // 8. filterHubItems(items, options)
  const hubSample = [
    { id: "1", title: "Inception", kind: "film", source: "media-locale", overview: "Sogni dentro sogni", genre: "Sci-Fi", year: 2010 },
    { id: "2", title: "Interstellar", kind: "film", source: "jellyfin", overview: "Spazio e buchi neri", year: 2014 },
    { id: "3", title: "Breaking Bad S01E01", kind: "episodio", series: "Breaking Bad", source: "plex" },
    { id: "4", title: "Bohemian Rhapsody", kind: "brano", album: "A Night at the Opera", source: "locale" },
    { id: "5", title: "Kodi Live", kind: "film", source: "kodi-tv", overview: "Canale streaming" },
    { id: "6", title: "Ricetta Torta", kind: "video", source: "ricette-web", overview: "Cucina facile" }
  ];

  // tab filter
  assert.strictEqual(L.filterHubItems(hubSample, { tab: "tutti" }).length, 6);
  assert.strictEqual(L.filterHubItems(hubSample, { tab: "film" }).length, 3);
  assert.strictEqual(L.filterHubItems(hubSample, { tab: "serie" }).length, 1);
  assert.strictEqual(L.filterHubItems(hubSample, { tab: "musica" }).length, 1);
  assert.strictEqual(L.filterHubItems(hubSample, { tab: "web" }).length, 2);
  assert.strictEqual(L.filterHubItems(hubSample, { tab: "stream4me" }).length, 2);

  // serie tab with item having series set (even if kind !== "episodio", as long as kind !== "brano")
  const seriesSample = [
    ...hubSample,
    { id: "7", title: "One Piece 1050", kind: "anime", series: "One Piece", source: "stream4me" },
    { id: "8", title: "Track with Artist", kind: "brano", series: "Queen", source: "locale" }
  ];
  assert.strictEqual(L.filterHubItems(seriesSample, { tab: "serie" }).length, 2);
  assert.strictEqual(L.filterHubItems(seriesSample, { tab: "stream4me" }).length, 3);

  // sourceFilter
  assert.strictEqual(L.filterHubItems(hubSample, { sourceFilter: "all" }).length, 6);
  assert.strictEqual(L.filterHubItems(hubSample, { sourceFilter: "locale" }).length, 2);
  assert.strictEqual(L.filterHubItems(hubSample, { sourceFilter: "server" }).length, 2);
  assert.strictEqual(L.filterHubItems(hubSample, { sourceFilter: "web" }).length, 2);

  // query filter (case-insensitive across title, series, album, overview, genre, year)
  assert.strictEqual(L.filterHubItems(hubSample, { query: "sogni" }).length, 1);
  assert.strictEqual(L.filterHubItems(hubSample, { query: "breaking" }).length, 1);
  assert.strictEqual(L.filterHubItems(hubSample, { query: "opera" }).length, 1);
  assert.strictEqual(L.filterHubItems(hubSample, { query: "cucina" }).length, 1);
  assert.strictEqual(L.filterHubItems(hubSample, { query: "sci-fi" }).length, 1);
  assert.strictEqual(L.filterHubItems(hubSample, { query: "2010" }).length, 1);
  assert.strictEqual(L.filterHubItems(hubSample, { query: "non-esiste" }).length, 0);

  // onlyFavs filter
  const favSet = new Set(["media-locale:1", "series:Breaking Bad"]);
  const favRes = L.filterHubItems(hubSample, { onlyFavs: true, favs: favSet });
  assert.strictEqual(favRes.length, 2);
  assert.strictEqual(favRes[0].id, "1");
  assert.strictEqual(favRes[1].id, "3");

  const favById = new Set(["2"]);
  const favByIdRes = L.filterHubItems(hubSample, { onlyFavs: true, favs: favById });
  assert.strictEqual(favByIdRes.length, 1);
  assert.strictEqual(favByIdRes[0].id, "2");

  // edge cases for filterHubItems
  assert.deepStrictEqual(L.filterHubItems(null), []);
  assert.deepStrictEqual(L.filterHubItems([null, undefined]), []);

  // 9. mergeContinueWatching(liveItems, cachedItems, limit)
  const live = [
    { id: "1", source: "media-locale", duration: 100, resume_pos: 30, seen: false },
    { id: "2", source: "media-locale", duration: 100, resume_pos: 95, seen: false }, // seen via >= 90%
    { id: "3", source: "media-locale", duration: 100, resume_pos: 0, seen: false },  // pos <= 0, not in progress
    { id: "4", source: "jellyfin", duration: 100, resume_pos: 60, seen: false }
  ];
  const cached = [
    { id: "1", source: "media-locale", duration: 100, resume_pos: 15, seen: false }, // superseded by live
    { id: "2", source: "media-locale", duration: 100, resume_pos: 50, seen: false }, // live says seen -> MUST be excluded
    { id: "3", source: "media-locale", duration: 100, resume_pos: 40, seen: false }, // live says pos 0 -> MUST NOT be pulled from cache
    { id: "5", source: "plex", duration: 100, resume_pos: 50, seen: false },         // only in cache -> kept
    { id: "6", source: "plex", duration: 100, resume_pos: 0, seen: false }          // pos 0 in cache -> excluded
  ];

  const merged = L.mergeContinueWatching(live, cached, 10);
  assert.strictEqual(merged.length, 3);
  assert.strictEqual(merged[0].id, "1");
  assert.strictEqual(merged[0].resume_pos, 30); // live version kept
  assert.strictEqual(merged[1].id, "4");
  assert.strictEqual(merged[2].id, "5");

  // test limit
  assert.strictEqual(L.mergeContinueWatching(live, cached, 1).length, 1);

  // 10. pickHeroItem(items, resumeItems)
  const itemsWithHero = [
    { id: "h1", title: "Plain" },
    { id: "h2", title: "With Backdrop", backdrop: "/img/bg.jpg" },
    { id: "h3", title: "With Poster", poster: "/img/post.jpg" }
  ];
  assert.strictEqual(L.pickHeroItem(itemsWithHero, [{ id: "r1" }])?.id, "r1");
  assert.strictEqual(L.pickHeroItem(itemsWithHero, [])?.id, "h2");
  assert.strictEqual(L.pickHeroItem([{ id: "p1" }], [])?.id, "p1");
  assert.strictEqual(L.pickHeroItem([], []), null);
  assert.strictEqual(L.pickHeroItem(null, null), null);

  // 11. federatedList(gs, options) with parallel requests, timeout, and deduplication
  const requestedUrls = [];
  const fakeGs = {
    api: async (url) => {
      requestedUrls.push(url);
      if (url.startsWith("/plugin-api/media-locale/list")) {
        return [{ id: "loc1", title: "Loc 1", source: "media-locale" }];
      }
      if (url.startsWith("/plugin-api/media-server/list")) {
        return { items: [{ id: "srv1", title: "Srv 1", source: "jellyfin" }] };
      }
      if (url.startsWith("/plugin-api/ricette-web/list")) {
        // Slow provider simulating timeout
        await new Promise((r) => setTimeout(r, 100));
        return [{ id: "web1", title: "Web 1", source: "ricette-web" }];
      }
      return [];
    }
  };

  const fedRes = await L.federatedList(fakeGs, { kind: "film", query: "test", timeoutMs: 30 });
  assert.strictEqual(fedRes.sourcesStatus["media-locale"], true);
  assert.strictEqual(fedRes.sourcesStatus["media-server"], true);
  assert.strictEqual(fedRes.sourcesStatus["ricette-web"], false); // timed out
  assert.strictEqual(fedRes.items.length, 2);
  assert.strictEqual(fedRes.items[0].id, "loc1");
  assert.strictEqual(fedRes.items[1].id, "srv1");
  assert(requestedUrls[0].includes("kind=film"));
  assert(requestedUrls[0].includes("query=test"));
  assert(requestedUrls[0].includes("q=test"));
  assert(requestedUrls[0].includes("limit=2000"));

  // Collision test in federatedList: same compositeKey deduplicated
  const fakeGsDuplicates = {
    api: async (url) => {
      if (url.startsWith("/plugin-api/media-locale/list")) {
        return [
          { id: "dup1", title: "Item 1", source: "media-locale" },
          { id: "dup1", title: "Item 1 Dup", source: "media-locale" }
        ];
      }
      return [];
    }
  };
  const dupFedRes = await L.federatedList(fakeGsDuplicates, { timeoutMs: 50 });
  assert.strictEqual(dupFedRes.items.length, 1);
  assert.strictEqual(dupFedRes.items[0].title, "Item 1");

  // 12. player.js: loadContinueCache & saveContinueCache
  let mockStore = {};
  const mockStorage = {
    getItem: (k) => mockStore[k] ?? null,
    setItem: (k, v) => { mockStore[k] = String(v); },
    removeItem: (k) => { delete mockStore[k]; }
  };

  // Corrupted / missing localStorage handling
  assert.deepStrictEqual(P.loadContinueCache(null), []);
  assert.deepStrictEqual(P.loadContinueCache(mockStorage), []);

  mockStore[P.CONTINUE_KEY] = "INVALID_JSON{{";
  assert.deepStrictEqual(P.loadContinueCache(mockStorage), []);

  mockStore[P.CONTINUE_KEY] = JSON.stringify("not an array");
  assert.deepStrictEqual(P.loadContinueCache(mockStorage), []);

  // Save to continue cache
  const saved1 = P.saveContinueCache({ id: "item1", title: "Item 1", source: "locale" }, 45.2, false, 100, mockStorage);
  assert.strictEqual(saved1.length, 1);
  assert.strictEqual(saved1[0].id, "item1");
  assert.strictEqual(saved1[0].resume_pos, 45.2);
  assert.strictEqual(saved1[0].duration, 100);

  // Update existing item
  const saved2 = P.saveContinueCache({ id: "item1", title: "Item 1", source: "locale" }, 60, false, 100, mockStorage);
  assert.strictEqual(saved2.length, 1);
  assert.strictEqual(saved2[0].resume_pos, 60);

  // Marked as seen -> removed from cache
  const saved3 = P.saveContinueCache({ id: "item1", title: "Item 1", source: "locale" }, 95, false, 100, mockStorage);
  assert.strictEqual(saved3.length, 0);

  // Seen = true -> removed from cache
  P.saveContinueCache({ id: "item2", title: "Item 2", source: "locale" }, 30, false, 100, mockStorage);
  assert.strictEqual(P.loadContinueCache(mockStorage).length, 1);
  P.saveContinueCache({ id: "item2", title: "Item 2", source: "locale" }, 30, true, 100, mockStorage);
  assert.strictEqual(P.loadContinueCache(mockStorage).length, 0);

  // Position <= 0 not added
  P.saveContinueCache({ id: "item3", title: "Item 3", source: "locale" }, 0, false, 100, mockStorage);
  assert.strictEqual(P.loadContinueCache(mockStorage).length, 0);

  // Invalid item ignored
  P.saveContinueCache(null, 10, false, 100, mockStorage);
  P.saveContinueCache({ id: "" }, 10, false, 100, mockStorage);
  assert.strictEqual(P.loadContinueCache(mockStorage).length, 0);

  // Maximum 20 items capped
  for (let i = 0; i < 25; i++) {
    P.saveContinueCache({ id: `bulk_${i}`, title: `Bulk ${i}`, source: "locale" }, 10, false, 100, mockStorage);
  }
  assert.strictEqual(P.loadContinueCache(mockStorage).length, 20);

  // 13. openExternal(gs, item, target, apiPrefix)
  const extCalls = [];
  let toastMsg = null;
  const mockExternalGs = {
    api: async (url, opts) => {
      extCalls.push({ url, opts });
      if (url === "/api/fail_ext") {
        throw new Error("fail_ext");
      }
    },
    toast: (msg) => { toastMsg = msg; }
  };

  // HTTP-only url -> tries /plugin-api/media-locale/external
  await P.openExternal(mockExternalGs, { id: "ex1" }, { url: "https://example.com/live.m3u8" });
  assert.strictEqual(extCalls[0].url, "/plugin-api/media-locale/external");
  assert.strictEqual(extCalls[0].opts.body.id, "ex1");

  // HTTP-only fallback to /api/open when external fails
  const mockFallbackGs = {
    api: async (url, opts) => {
      extCalls.push({ url, opts });
      if (url.includes("/external")) throw new Error("external fail");
    },
    toast: (msg) => { toastMsg = msg; }
  };
  await P.openExternal(mockFallbackGs, { id: "ex2" }, { url: "https://example.com/fallback.m3u8" });
  assert.strictEqual(extCalls[extCalls.length - 1].url, "/api/open");
  assert.strictEqual(extCalls[extCalls.length - 1].opts.body.url, "https://example.com/fallback.m3u8");

  // Local path -> directly calls external
  await P.openExternal(mockExternalGs, { id: "loc1" }, { path: "C:\\videos\\film.mkv" });
  assert.strictEqual(extCalls[extCalls.length - 1].url, "/plugin-api/media-locale/external");

  // 14. Existing player.js tests: isBrowserPlayable + attachPlay / play
  assert.strictEqual(P.isBrowserPlayable(null), false);
  assert.strictEqual(P.isBrowserPlayable({ path: "/video/film.mp4" }), true);
  assert.strictEqual(P.isBrowserPlayable({ path: "/video/film.mkv" }), false);
  assert.strictEqual(P.isBrowserPlayable({ url: "https://vixcloud.example/playlist/1.m3u8?token=x&expires=2" }), true);
  assert.strictEqual(P.isBrowserPlayable({ url: "https://x/y.m3u8", external: true }), false);
  assert.strictEqual(P.isBrowserPlayable({ path: "/video/film.mp4", external: true }), false);
  assert.strictEqual(P.isBrowserPlayable({ url: "https://example.com/stream", mime: "audio/flac" }), true);

  const calls = [];
  const gsMock = {
    api: async (url) => {
      calls.push(url);
      return { path: "/video/test.mp4", mime: "video/mp4", resume_pos: 12 };
    },
    toast: () => {},
  };
  const playFn = P.attachPlay(gsMock);
  const resLocal = await playFn({ id: "loc1", title: "Test", source: "locale" });
  assert.strictEqual(resLocal.browserPlayable, true);
  assert.strictEqual(calls[0], "/plugin-api/media-locale/play_target?id=loc1");

  await playFn({ id: "jf:42", title: "Remoto", source: "jellyfin" });
  assert.strictEqual(calls[1], "/plugin-api/media-server/play_target?id=jf%3A42&source=jellyfin");

  // 15. Watchlist constants & normalizeWatchlistEntry
  assert.strictEqual(L.WATCHLIST_STATUSES.plan_to_watch.order, 1);
  assert.strictEqual(L.WATCHLIST_STATUSES.watching.order, 2);
  assert.strictEqual(L.WATCHLIST_STATUSES.on_hold.order, 3);
  assert.strictEqual(L.WATCHLIST_STATUSES.completed.order, 4);
  assert.strictEqual(L.WATCHLIST_STATUSES.dropped.order, 5);
  assert.strictEqual(L.WATCHLIST_PRIORITIES.high.weight, 3);
  assert.strictEqual(L.WATCHLIST_PRIORITIES.medium.weight, 2);
  assert.strictEqual(L.WATCHLIST_PRIORITIES.low.weight, 1);

  const norm1 = L.normalizeWatchlistEntry(
    { status: "watching", priority: "high", rating: 15, notes: "Bellissimo" },
    { id: "f10", source: "jellyfin", title: "Dune", kind: "film", year: "2021", genre: "Sci-Fi", overview: "Arrakis" }
  );
  assert.strictEqual(norm1.item_key, "jellyfin:f10");
  assert.strictEqual(norm1.item_id, "f10");
  assert.strictEqual(norm1.source, "jellyfin");
  assert.strictEqual(norm1.title, "Dune");
  assert.strictEqual(norm1.year, 2021);
  assert.strictEqual(norm1.genre, "Sci-Fi");
  assert.strictEqual(norm1.overview, "Arrakis");
  assert.strictEqual(norm1.status, "watching");
  assert.strictEqual(norm1.priority, "high");
  assert.strictEqual(norm1.rating, 10); // clamped 0..10
  assert.strictEqual(norm1.notes, "Bellissimo");

  const normDefaults = L.normalizeWatchlistEntry({ id: "loc9", status: "invalid", priority: "invalid", rating: -5 });
  assert.strictEqual(normDefaults.item_key, "media-locale:loc9");
  assert.strictEqual(normDefaults.status, "plan_to_watch");
  assert.strictEqual(normDefaults.priority, "medium");
  assert.strictEqual(normDefaults.rating, 0);
  assert.strictEqual(normDefaults.notes, "");

  // 16. sortAndFilterWatchlist & watchlistStats
  const wlSample = [
    { item_key: "media-locale:1", title: "Zeta Movie", status: "plan_to_watch", priority: "low", rating: 6, updated_at: 100, genre: "Action", notes: "Guardare nel weekend" },
    { item_key: "media-locale:2", title: "Alpha Series", series: "Alpha", status: "watching", priority: "high", rating: 9, updated_at: 200, overview: "Fantascienza spaziale" },
    { item_key: "jellyfin:3", title: "Beta Film", status: "completed", priority: "high", rating: 10, updated_at: 500, notes: "Capolavoro assoluto" },
    { item_key: "plex:4", title: "Gamma Anime", status: "on_hold", priority: "medium", rating: 7, updated_at: 300, genre: "Anime" },
    { item_key: "media-locale:5", title: "Delta Doc", status: "dropped", priority: "low", rating: 3, updated_at: 400, notes: "Noioso" },
    { item_key: "media-locale:6", title: "Charlie Film", status: "plan_to_watch", priority: "high", rating: 8, updated_at: 350 }
  ];

  // Stats
  const stats = L.watchlistStats(wlSample);
  assert.deepStrictEqual(stats, {
    total: 6,
    plan_to_watch: 2,
    watching: 1,
    on_hold: 1,
    completed: 1,
    dropped: 1,
    high_priority: 3,
  });

  // Filter by status
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { status: "all" }).length, 6);
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { status: "plan_to_watch" }).length, 2);
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { status: "watching" }).length, 1);
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { status: "active" }).length, 4); // excludes completed & dropped

  // Filter by priority
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { priority: "high" }).length, 3);
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { priority: "medium" }).length, 1);
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { priority: "low" }).length, 2);

  // Filter by query (title, series, notes, genre, overview)
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { query: "weekend" }).length, 1);
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { query: "spaziale" }).length, 1);
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { query: "anime" }).length, 1);
  assert.strictEqual(L.sortAndFilterWatchlist(wlSample, { query: "alpha" }).length, 1);

  // Sort by priority (default): active before finished, then weight DESC, then updated_at DESC, then title A-Z
  const byPrio = L.sortAndFilterWatchlist(wlSample, { sortBy: "priority" });
  assert.deepStrictEqual(byPrio.map((x) => x.item_key), [
    "media-locale:6", // active, high, updated 350
    "media-locale:2", // active, high, updated 200
    "plex:4",         // active, medium, updated 300
    "media-locale:1", // active, low, updated 100
    "jellyfin:3",     // finished (completed), high, updated 500
    "media-locale:5", // finished (dropped), low, updated 400
  ]);

  // Sort by status: status.order ASC, then priority weight DESC
  const byStatus = L.sortAndFilterWatchlist(wlSample, { sortBy: "status" });
  assert.deepStrictEqual(byStatus.map((x) => x.item_key), [
    "media-locale:6", // plan_to_watch (1), high
    "media-locale:1", // plan_to_watch (1), low
    "media-locale:2", // watching (2), high
    "plex:4",         // on_hold (3), medium
    "jellyfin:3",     // completed (4), high
    "media-locale:5", // dropped (5), low
  ]);

  // Sort by rating: rating DESC, then priority weight DESC
  const byRating = L.sortAndFilterWatchlist(wlSample, { sortBy: "rating" });
  assert.deepStrictEqual(byRating.map((x) => x.item_key), [
    "jellyfin:3",     // 10
    "media-locale:2", // 9
    "media-locale:6", // 8
    "plex:4",         // 7
    "media-locale:1", // 6
    "media-locale:5", // 3
  ]);

  // Sort by recent: updated_at DESC
  const byRecent = L.sortAndFilterWatchlist(wlSample, { sortBy: "recent" });
  assert.deepStrictEqual(byRecent.map((x) => x.item_key), [
    "jellyfin:3",     // 500
    "media-locale:5", // 400
    "media-locale:6", // 350
    "plex:4",         // 300
    "media-locale:2", // 200
    "media-locale:1", // 100
  ]);

  // Sort by title: A-Z
  const byTitle = L.sortAndFilterWatchlist(wlSample, { sortBy: "title" });
  assert.deepStrictEqual(byTitle.map((x) => x.title), [
    "Alpha Series",
    "Beta Film",
    "Charlie Film",
    "Delta Doc",
    "Gamma Anime",
    "Zeta Movie",
  ]);

  console.log("ok");
}).catch((e) => { console.error(e); process.exit(1); });
