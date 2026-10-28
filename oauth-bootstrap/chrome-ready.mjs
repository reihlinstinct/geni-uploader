// Synthetic loopback test startup only. No retry/relaunch or skipped assertions.
export async function waitForChrome({ readPort, probe, exited, sleep, now,
  diagnostics = () => "", timeoutMs = 60000 }) {
  const start = now();
  let state = "port-file-unavailable";
  const remaining = () => Math.max(0, timeoutMs - (now() - start));
  const failure = (reason) => new Error("Synthetic Chrome " + reason + ": " + state +
    "; " + String(diagnostics()).replace(/[\x00-\x08\x0b-\x1f\x7f]/g, "?").slice(-4096));
  const bounded = async (work) => {
    const budget = remaining();
    if (!budget) throw failure("readiness timeout");
    let timer;
    try {
      const value = await Promise.race([work(budget), new Promise((_, reject) => {
        timer = setTimeout(() => reject(failure("readiness timeout")), budget);
      })]);
      if (!remaining()) throw failure("readiness timeout");
      return value;
    } finally { clearTimeout(timer); }
  };
  while (remaining()) {
    if (exited()) throw failure("exited before readiness");
    try {
      const raw = await bounded(() => readPort());
      const port = raw.split("\n")[0];
      if (/^[1-9][0-9]{0,4}\n/.test(raw) && Number(port) <= 65535) {
        state = "devtools-endpoint-unavailable";
        const tabs = await bounded((budget) => probe(port, Math.min(1000, budget)));
        const page = Array.isArray(tabs) && tabs.find((x) => x.type === "page");
        if (page && typeof page.webSocketDebuggerUrl === "string") {
          const url = new URL(page.webSocketDebuggerUrl);
          if (url.protocol === "ws:" && url.hostname === "127.0.0.1" && url.port === port
              && !url.username && !url.password && remaining() && !exited()) return { port, page };
        }
        state = "page-target-unavailable";
      } else state = "port-file-incomplete";
    } catch {
      if (!remaining()) throw failure("readiness timeout");
    }
    if (remaining()) await bounded((budget) => sleep(Math.min(100, budget)));
  }
  throw failure("readiness timeout");
}
