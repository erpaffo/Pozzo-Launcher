"use strict";
// Test per il modulo Amici e Presenza Online (friends.js)
const assert = require("assert");
const fs = require("fs");
const path = require("path");

function runTests() {
  const code = fs.readFileSync(path.resolve(__dirname, "../pozzo/app/static/js/friends.js"), "utf8");
  assert(code.includes("SUPABASE_URL"), "Deve contenere SUPABASE_URL");
  assert(code.includes("SUPABASE_KEY"), "Deve contenere SUPABASE_KEY");
  assert(code.includes("realtime:pozzo_presence"), "Deve usare il canale presence pozzo");
  assert(code.includes("phx_join"), "Deve supportare join Phoenix");
  assert(code.includes("TRACK"), "Deve supportare presence TRACK");
  assert(code.includes("#PZ-"), "Codice amico deve avere prefisso #PZ-");

  // Mock localStorage and window environment
  const mockStorage = {};
  const fakeWindow = {
    localStorage: {
      getItem: (k) => mockStorage[k] || null,
      setItem: (k, v) => { mockStorage[k] = String(v); },
    },
    document: {
      addEventListener: () => {},
      readyState: "complete"
    },
    $: () => null
  };

  // Esegui in sandbox
  const vm = require("vm");
  const moduleObj = { exports: {} };
  const ctx = vm.createContext({
    localStorage: fakeWindow.localStorage,
    document: fakeWindow.document,
    window: fakeWindow,
    module: moduleObj,
    exports: moduleObj.exports,
    $: fakeWindow.$,
    fetch: async () => ({ ok: true, json: async () => [] }),
    WebSocket: class {
      constructor() {}
      send() {}
      close() {}
    },
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout: () => 1,
    clearTimeout: () => {},
    console
  });

  vm.runInContext(code, ctx);

  const Friends = ctx.Friends || fakeWindow.Friends || moduleObj.exports;
  assert(Friends, "Modulo Friends deve essere esportato");
  assert.strictEqual(typeof Friends.getMyProfile, "function", "getMyProfile deve essere una funzione");
  assert.strictEqual(typeof Friends.addFriendByCode, "function", "addFriendByCode deve essere una funzione");

  const me = Friends.getMyProfile();
  assert(me && me.id, "Profilo deve avere un id");
  assert(me.friend_code.startsWith("#PZ-"), `Friend code deve iniziare con #PZ-, trovato: ${me.friend_code}`);
  assert(me.username, "Profilo deve avere un username");

  // Second call must return the cached profile
  const me2 = Friends.getMyProfile();
  assert.strictEqual(me.id, me2.id, "Id deve essere persistito");
  assert.strictEqual(me.friend_code, me2.friend_code, "Friend code deve essere persistito");

  // Funzioni pure: riepilogo con interruttori, giochi in comune, tetto del registro attività
  const games = [{ title: "Zelda: BotW", minutes: 120, last: 5 }, { title: "Doom", minutes: 30, last: 6 }, { title: "Mai", minutes: 0 }];
  const ach = [{ title: "doom", unlocked: 3, total: 10 }];
  assert.strictEqual(Friends.buildSummary({ games, ach }), null, "tutto spento: niente da inviare");
  const st = Friends.buildSummary({ games, ach, time: true });
  assert.strictEqual(JSON.stringify(st.map((g) => g.k)), '["zeldabotw","doom"]');
  assert(st.every((g) => g.a === undefined), "senza il consenso gli obiettivi non escono");
  const sa = Friends.buildSummary({ games, ach, achievements: true });
  assert.strictEqual(JSON.stringify(sa.map((g) => [g.k, g.a, g.n, g.m])), '[["doom",3,10,null]]', "solo obiettivi: niente tempi");
  const sb = Friends.buildSummary({ games, ach, time: true, achievements: true, max: 1 });
  assert.strictEqual(sb.length, 1);
  const common = Friends.commonGames(st, [{ k: "doom", t: "Doom", m: 500 }, { k: "altro", t: "Altro", m: 9 }, { k: "zeldabotw", t: "Z" }]);
  assert.strictEqual(JSON.stringify(common.map((c) => [c.k, c.mine, c.theirs])), '[["doom",30,500],["zeldabotw",120,0]]');
  let log = [];
  for (let i = 0; i < 130; i++) log = Friends.pushActivity(log, { i });
  assert.strictEqual(log.length, 100);
  assert.strictEqual(log[0].i, 129);

  console.log("ok test_friends_social.js");
}

runTests();
