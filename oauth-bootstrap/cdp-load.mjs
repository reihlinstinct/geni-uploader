// Test support: wait for the load of exactly the navigation this call started.
// A Page.loadEventFired listener also sees a late load from an earlier navigation
// (for example the form POST landing), which can resolve before the new document
// exists. Match the lifecycle "load" event by the navigation's own frame and loader.
export async function navigateAndWaitForLoad(ws, cdp, url) {
  const seen = new Set();
  let wanted = null;
  let resolveLoad;
  const loaded = new Promise((resolve) => { resolveLoad = resolve; });
  const listener = (e) => {
    const m = JSON.parse(e.data);
    if (m.method !== "Page.lifecycleEvent" || m.params?.name !== "load") return;
    const key = m.params.frameId + " " + m.params.loaderId;
    seen.add(key);
    if (key === wanted) resolveLoad();
  };
  ws.addEventListener("message", listener);
  try {
    const result = await cdp("Page.navigate", { url });
    if (result.errorText) throw new Error("navigation failed: " + result.errorText);
    if (typeof result.frameId !== "string" || typeof result.loaderId !== "string") {
      throw new Error("navigation returned no frame/loader id");
    }
    wanted = result.frameId + " " + result.loaderId;
    if (seen.has(wanted)) resolveLoad();
    await loaded;
  } finally {
    ws.removeEventListener("message", listener);
  }
}
