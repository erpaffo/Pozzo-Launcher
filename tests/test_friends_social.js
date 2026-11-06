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

  console.log("ok test_friends_social.js");
}

runTests();
