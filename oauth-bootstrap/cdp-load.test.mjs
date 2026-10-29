import test from "node:test";
import assert from "node:assert/strict";
import { navigateAndWaitForLoad } from "./cdp-load.mjs";

// A fake CDP socket: events are delivered in the order a test chooses.
function fakeSocket() {
  const listeners = new Set();
  return {
    addEventListener: (_, fn) => listeners.add(fn),
    removeEventListener: (_, fn) => listeners.delete(fn),
    emit: (method, params) => {
      for (const fn of [...listeners]) fn({ data: JSON.stringify({ method, params }) });
    },
    count: () => listeners.size,
  };
}

// Bounded: a removed rejection fails within the guard instead of hanging to the job cap.
async function rejectsWithin(promise, ms = 500) {
  let timer;
  const guard = new Promise((resolve) => {
    timer = setTimeout(() => resolve("pending past guard"), ms);
  });
  const outcome = await Promise.race([
    promise.then(() => "resolved", (error) => error), guard]);
  clearTimeout(timer);
  assert.ok(outcome instanceof Error, "expected a rejection, got: " + String(outcome));
  return outcome;
}

const settled = (promise) => Promise.race([
  promise.then(() => "resolved"),
  new Promise((r) => setTimeout(() => r("pending"), 20)),
]);

test("a stale load from an earlier navigation does not resolve the wait", async () => {
  const ws = fakeSocket();
  const cdp = async (method) => {
    assert.equal(method, "Page.navigate");
    // The previous document (the POST landing) finishes loading while the new
    // navigation is being started: the race seen in CI.
    ws.emit("Page.loadEventFired", { timestamp: 1 });
    ws.emit("Page.lifecycleEvent", { frameId: "F1", loaderId: "OLD", name: "load" });
    return { frameId: "F1", loaderId: "NEW" };
  };
  const wait = navigateAndWaitForLoad(ws, cdp, "https://127.0.0.1:1/x");
  assert.equal(await settled(wait), "pending");
  ws.emit("Page.lifecycleEvent", { frameId: "F2", loaderId: "NEW", name: "load" });
  ws.emit("Page.lifecycleEvent", { frameId: "F1", loaderId: "NEW", name: "DOMContentLoaded" });
  assert.equal(await settled(wait), "pending");
  ws.emit("Page.lifecycleEvent", { frameId: "F1", loaderId: "NEW", name: "load" });
  assert.equal(await settled(wait), "resolved");
  assert.equal(ws.count(), 0);
});

test("a load that arrives before Page.navigate returns is not missed", async () => {
  const ws = fakeSocket();
  const cdp = async () => {
    ws.emit("Page.lifecycleEvent", { frameId: "F1", loaderId: "NEW", name: "load" });
    return { frameId: "F1", loaderId: "NEW" };
  };
  assert.equal(await settled(navigateAndWaitForLoad(ws, cdp, "https://127.0.0.1:1/x")),
    "resolved");
});

test("navigation errors and missing ids fail closed", async () => {
  for (const result of [{ frameId: "F1", loaderId: "N", errorText: "net::ERR_FAILED" },
    { frameId: "F1" }, { loaderId: "N" }, {}]) {
    const ws = fakeSocket();
    await rejectsWithin(navigateAndWaitForLoad(ws, async () => result, "https://127.0.0.1:1/x"));
    assert.equal(ws.count(), 0);
  }
});


test("rejectsWithin fails promptly on a never-settling promise (#274)", async () => {
  const started = Date.now();
  await assert.rejects(rejectsWithin(new Promise(() => {}), 50), /expected a rejection/);
  await assert.rejects(rejectsWithin(Promise.resolve(1), 50), /expected a rejection, got: resolved/);
  assert.ok(Date.now() - started < 1000);
});

// #276: errorText and id-type guards isolated. Each case emits the matching load
// first, so a removed guard resolves (and fails the assertion) instead of hanging.

test("errorText rejects even when a matching load already arrived", async () => {
  const ws = fakeSocket();
  const cdp = async () => {
    ws.emit("Page.lifecycleEvent", { frameId: "F1", loaderId: "N", name: "load" });
    return { frameId: "F1", loaderId: "N", errorText: "net::ERR_ZZ" };
  };
  await assert.rejects(navigateAndWaitForLoad(ws, cdp, "https://127.0.0.1:1/x"),
    /navigation failed/);
  assert.equal(ws.count(), 0);
});

test("non-string frame or loader ids reject even when a matching load arrived", async () => {
  for (const [frameId, loaderId] of [[7, "N"], [null, "N"], ["F1", 7], ["F1", null]]) {
    const ws = fakeSocket();
    const cdp = async () => {
      ws.emit("Page.lifecycleEvent", { frameId, loaderId, name: "load" });
      return { frameId, loaderId };
    };
    await assert.rejects(navigateAndWaitForLoad(ws, cdp, "https://127.0.0.1:1/x"),
      /no frame\/loader id/);
    assert.equal(ws.count(), 0);
  }
});


// #273: bounded helper with cleanup; never-settling regressions.

test("never-settling navigate or load rejects with a fixed value-free timeout", { timeout: 2000 }, async () => {
  const cases = [
    () => new Promise(() => {}),
    async () => ({ frameId: "F1", loaderId: "N" }),
  ];
  for (const cdp of cases) {
    const ws = fakeSocket();
    const started = Date.now();
    const error = await navigateAndWaitForLoad(ws, cdp,
      "https://127.0.0.1:1/x?code=ZZSECRET", { timeoutMs: 50 }).then(() => null, (e) => e);
    assert.ok(error instanceof Error);
    assert.equal(error.message, "navigation load timeout");
    assert.ok(Date.now() - started < 1000);
    assert.equal(ws.count(), 0);
  }
});

test("a successful load clears the timer", async () => {
  const ws = fakeSocket();
  const cdp = async () => {
    ws.emit("Page.lifecycleEvent", { frameId: "F1", loaderId: "N", name: "load" });
    return { frameId: "F1", loaderId: "N" };
  };
  const realClear = globalThis.clearTimeout;
  let cleared = 0;
  globalThis.clearTimeout = (t) => { cleared += 1; return realClear(t); };
  try {
    await navigateAndWaitForLoad(ws, cdp, "https://127.0.0.1:1/x", { timeoutMs: 3000 });
  } finally {
    globalThis.clearTimeout = realClear;
  }
  assert.equal(cleared, 1);
  assert.equal(ws.count(), 0);
});

test("invalid timeouts are refused before navigating", async () => {
  for (const timeoutMs of [0, -1, 1.5, "50", null]) {
    const ws = fakeSocket();
    await assert.rejects(navigateAndWaitForLoad(ws, () => assert.fail("navigated"),
      "https://127.0.0.1:1/x", { timeoutMs }), /invalid navigation timeout/);
    assert.equal(ws.count(), 0);
  }
});
