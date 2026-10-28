// Synthetic loopback test startup only. No retry/relaunch or skipped assertions.
export async function waitForChrome({ readPort, probe, exited, sleep, now,
  timeoutMs = 60000 }) {
  const start = now();
  let state = "port-file-unavailable";
  while (now() - start < timeoutMs) {
    if (exited()) throw new Error("Synthetic Chrome exited before readiness");
    try {
      const raw = await readPort();
      const port = raw.split("\n")[0];
      if (/^[1-9][0-9]{0,4}$/.test(port) && Number(port) <= 65535) {
        state = "devtools-endpoint-unavailable";
        const tabs = await probe(port);
        const page = Array.isArray(tabs) && tabs.find((x) => x.type === "page");
        if (page && typeof page.webSocketDebuggerUrl === "string") {
          const url = new URL(page.webSocketDebuggerUrl);
          if (url.protocol === "ws:" && url.hostname === "127.0.0.1" && url.port === port
              && !url.username && !url.password) return { port, page };
        }
        state = "page-target-unavailable";
      } else state = "port-file-incomplete";
    } catch {}
    await sleep(100);
  }
  throw new Error("Synthetic Chrome readiness timeout: " + state);
}
