import test from "node:test";
import assert from "node:assert/strict";
import { waitForChrome } from "./chrome-ready.mjs";

function fixture() {
  let clock = 0;
  return { readPort: async () => "9911\nZZpath", exited: () => false,
    probe: async () => [{ type: "page", webSocketDebuggerUrl: "ws://127.0.0.1:9911/devtools/page/ZZ" }],
    sleep: async (ms) => { clock += ms; }, now: () => clock, timeoutMs: 60000 };
}

test("waits past former30second deadline and validates actual page readiness", async () => {
  const f = fixture();
  const original = f.readPort;
  f.readPort = async () => f.now() < 35000 ? "" : original();
  const result = await waitForChrome(f);
  assert.equal(result.port, "9911");
  assert.equal(f.now(), 35000);
});

test("partial port and early endpoint/page races do not terminate startup", async () => {
  const f = fixture();
  f.readPort = async () => f.now() < 100 ? "" : "9911\nZZ";
  f.probe = async () => {
    if (f.now() < 200) throw new Error("ZZtransient");
    return f.now() < 300 ? [] : [{ type: "page", webSocketDebuggerUrl: "ws://127.0.0.1:9911/ZZ" }];
  };
  assert.equal((await waitForChrome(f)).port, "9911");
  assert.equal(f.now(), 300);
});

test("single startup deadline fails closed without sensitive diagnostics", async () => {
  const f = fixture();
  f.readPort = async () => { throw new Error("ZZsecret"); };
  await assert.rejects(waitForChrome(f), /readiness timeout: port-file-unavailable/);
  assert.equal(f.now(), 60000);
});

test("process exit and untrusted websocket endpoints are rejected", async () => {
  const f = fixture();
  f.exited = () => true;
  await assert.rejects(waitForChrome(f), /exited before readiness/);
  for (const url of ["ws://ZZ.invalid:9911/x", "ws://127.0.0.1:9912/x", "wss://127.0.0.1:9911/x"]) {
    const g = fixture();
    g.timeoutMs = 200;
    g.probe = async () => [{ type: "page", webSocketDebuggerUrl: url }];
    await assert.rejects(waitForChrome(g), /readiness timeout/);
  }
});

test("late probe readiness is rejected and remaining budget is clamped", async () => {
  let clock = 0;
  const f = fixture();
  f.now = () => clock;
  f.readPort = async () => { clock = 59900; return "9911\nZZ"; };
  f.probe = async (_, budget) => {
    assert.equal(budget, 100);
    clock += 900;
    return [{ type: "page", webSocketDebuggerUrl: "ws://127.0.0.1:9911/ZZ" }];
  };
  await assert.rejects(waitForChrome(f), /readiness timeout/);
});

test("truncated numeric port does not probe and final sleep is clamped", async () => {
  let clock = 0;
  const f = fixture();
  f.now = () => clock;
  f.timeoutMs = 150;
  f.readPort = async () => "9911";
  f.probe = async () => assert.fail("incomplete port must not be probed");
  const sleeps = [];
  f.sleep = async (ms) => { sleeps.push(ms); clock += ms; };
  await assert.rejects(waitForChrome(f), /port-file-incomplete/);
  assert.deepEqual(sleeps, [100, 50]);
});

test("timeout and exit retain capped synthetic diagnostics", async () => {
  for (const exit of [false, true]) {
    const f = fixture();
    f.timeoutMs = 100;
    f.exited = () => exit;
    f.readPort = async () => "";
    f.diagnostics = () => "x".repeat(5000) + "ZZsynthetic-stderr\x01";
    await assert.rejects(waitForChrome(f), (e) => {
      assert.match(e.message, /ZZsynthetic-stderr\?/);
      assert.ok(e.message.length < 4300);
      return true;
    });
  }
});
