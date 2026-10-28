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
    await assert.rejects(navigateAndWaitForLoad(ws, async () => result, "https://127.0.0.1:1/x"));
    assert.equal(ws.count(), 0);
  }
});
