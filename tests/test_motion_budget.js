const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "pozzo", "app", "static", "motion.js"),
  "utf8",
);

function harness({ deviceMemory = 8, hardwareConcurrency = 8, setting = null, getBattery } = {}) {
  const values = new Map();
  if (setting !== null) values.set("gs.motion", JSON.stringify(setting));
  const frames = [];
  const events = new Map();
  let now = 0;
  const root = {
    dataset: {},
    classList: { toggle() {} },
  };
  const batteryListeners = {};
  const navigator = { deviceMemory, hardwareConcurrency };
  if (getBattery) navigator.getBattery = getBattery(batteryListeners);
  const context = {
    document: {
      documentElement: root,
      body: {},
      hidden: false,
      addEventListener() {},
    },
    navigator,
    localStorage: {
      getItem(key) { return values.has(key) ? values.get(key) : null; },
      setItem(key, value) { values.set(key, String(value)); },
    },
    matchMedia() { return { matches: false, addEventListener() {} }; },
    requestAnimationFrame(callback) { frames.push(callback); },
    performance: { now() { return now; } },
    MutationObserver: class { observe() {} },
    Event: class { constructor(type) { this.type = type; } },
    addEventListener(type, callback) {
      if (!events.has(type)) events.set(type, []);
      events.get(type).push(callback);
    },
    dispatchEvent(event) {
      for (const callback of events.get(event.type) || []) callback(event);
    },
    getComputedStyle() {
      return { getPropertyValue() { return ""; } };
    },
    innerHeight: 900,
    innerWidth: 1400,
  };
  context.window = context;
  vm.runInNewContext(source, context, { filename: "motion.js" });

  return {
    context,
    root,
    values,
    batteryListeners,
    frameAt(intervalMs) {
      let iterations = 0;
      while (frames.length) {
        assert(iterations++ < 1000, "FPS campionati senza terminare");
        now += intervalMs;
        frames.shift()(now);
      }
    },
  };
}

async function settlePromises() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

async function main() {
  const fast = harness();
  fast.frameAt(1000 / 60);
  assert.equal(fast.context.GSMotionBudget.state.fpsMeasurement, "complete");
  assert(fast.context.GSMotionBudget.state.sampleDurationMs >= 1400);
  assert(fast.context.GSMotionBudget.state.sampleDurationMs <= 1500);
  assert(fast.context.GSMotionBudget.state.fps >= 55);
  assert.equal(fast.context.GSMotionBudget.state.reduced, false);
  assert.equal(fast.root.dataset.motion, undefined);

  const slow = harness();
  slow.frameAt(50);
  assert(slow.context.GSMotionBudget.state.fps < 30);
  assert.deepEqual(Array.from(slow.context.GSMotionBudget.state.reasons), ["low-fps"]);
  assert.equal(slow.root.dataset.motion, "reduced");

  const manual = harness({ deviceMemory: 2, hardwareConcurrency: 2, setting: "normal" });
  assert.equal(manual.context.GSMotionBudget.state.lowEnd, true);
  assert.equal(manual.context.GSMotionBudget.state.reduced, true);
  assert.equal(manual.root.dataset.motion, "normal", "la scelta manuale prevale sul budget automatico");
  manual.context.GSMotion.set("off");
  assert.equal(manual.root.dataset.motion, "off");
  assert.equal(manual.values.get("gs.motion"), '"off"');
  manual.context.GSMotion.set("unknown");
  assert.equal(manual.root.dataset.motion, "off");
  assert.equal(manual.values.get("gs.motion"), '"off"');

  const batteryDevice = {
    level: 0.15,
    charging: false,
    addEventListener(type, callback) { batteryListeners[type] = callback; },
  };
  let batteryListeners;
  const battery = harness({
    getBattery: (listeners) => {
      batteryListeners = listeners;
      return () => Promise.resolve(batteryDevice);
    },
  });
  await settlePromises();
  assert.equal(battery.context.GSMotionBudget.state.batteryAvailable, true);
  assert.equal(battery.context.GSMotionBudget.state.lowBattery, true);
  assert.equal(battery.context.GSMotionBudget.state.onBattery, true);
  assert.equal(battery.root.dataset.motion, "reduced");
  const batteryState = battery.context.GSMotionBudget.state;
  batteryDevice.level = 0.75;
  battery.batteryListeners.levelchange();
  assert.equal(batteryState.lowBattery, false);
  assert.equal(batteryState.reduced, true, "la modalità a batteria riduce il movimento anche sopra la soglia bassa");
  assert.equal(battery.root.dataset.motion, "reduced");
  batteryDevice.charging = true;
  battery.batteryListeners.chargingchange();
  assert.equal(batteryState.lowBattery, false);
  assert.equal(battery.root.dataset.motion, undefined);

  const rejectedBattery = harness({ getBattery: () => () => Promise.reject(new Error("not available")) });
  await settlePromises();
  assert.equal(rejectedBattery.context.GSMotionBudget.state.batteryAvailable, false);
  assert.equal(rejectedBattery.context.GSMotionBudget.state.reduced, false);

  const noBatteryApi = harness();
  assert.equal(noBatteryApi.context.GSMotionBudget.state.batteryChecked, true);
  assert.equal(noBatteryApi.context.GSMotionBudget.state.batteryAvailable, false);
  assert.equal(noBatteryApi.context.GSMotionBudget.state.fpsMeasurement, "measuring");

  console.log("ok  budget animazioni: FPS, hardware, batteria e precedenza manuale");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
