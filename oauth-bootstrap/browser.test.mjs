// Real Chrome form-navigation regression. Synthetic credentials, loopback only.
import test from "node:test";
import assert from "node:assert/strict";
import https from "node:https";
import { spawn, spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { once } from "node:events";
import { handle, OneTimeState } from "./worker.mjs";

test(
  "Chrome form POST preserves exact Origin on query-free landing",
  { timeout: 60000 },
  async () => {
    const dir = await mkdtemp(join(tmpdir(), "zz-oauth-browser-"));
    let chrome, ws, server;
    try {
      const cert = spawnSync(
        "openssl",
        [
          "req",
          "-x509",
          "-newkey",
          "rsa:2048",
          "-nodes",
          "-keyout",
          join(dir, "key"),
          "-out",
          join(dir, "cert"),
          "-subj",
          "/CN=localhost",
          "-days",
          "1",
        ],
        { stdio: "ignore" },
      );
      assert.equal(cert.status, 0);
      const entries = new Map();
      const storage = {
        get: async (k) => entries.get(k),
        put: async (k, v) => entries.set(k, v),
        delete: async (k) => entries.delete(k),
        setAlarm: async () => {},
        transaction: async (fn) => fn(storage),
      };
      const one = new OneTimeState({ storage });
      let origin, observed, resolvePost;
      const posted = new Promise((r) => (resolvePost = r));
      server = https.createServer(
        {
          key: await readFile(join(dir, "key")),
          cert: await readFile(join(dir, "cert")),
        },
        async (req, res) => {
          try {
            const env = {
              CALLBACK_ORIGIN: origin,
              ALLOWED_GITHUB_ID: "12345",
              GITHUB_LOGIN_CLIENT_ID: "ZZLOGINCLIENT",
              GITHUB_LOGIN_CLIENT_SECRET: "ZZLOGINSECRET",
              SESSION_SIGNING_KEY: "a".repeat(64),
              GENI_CLIENT_ID: "ZZCLIENT",
              GENI_APP_SECRET: "ZZSECRET",
              GITHUB_WRITER: "ZZWRITER",
              OAUTH_STATES: {
                idFromName: (x) => x,
                get: () => ({ fetch: (u, o) => one.fetch(new Request(u, o)) }),
              },
            };
            const out = await handle(
              new Request(origin + req.url, {
                method: req.method,
                headers: req.headers,
              }),
              env,
              { fetcher: () => assert.fail("external request forbidden") },
            );
            if (req.method === "POST") {
              observed = {
                origin: req.headers.origin,
                referer: req.headers.referer,
                status: out.status,
                location: out.headers.get("location"),
              };
              // Never follow OAuth redirect. Capture it and stop on loopback.
              res.writeHead(200, { "Content-Type": "text/plain" });
              res.end("ZZSTOP");
              resolvePost();
            } else {
              res.writeHead(out.status, Object.fromEntries(out.headers));
              res.end(await out.text());
            }
          } catch (e) {
            res.writeHead(500);
            res.end("ZZERROR");
            resolvePost?.();
          }
        },
      );
      await new Promise((r) => server.listen(0, "127.0.0.1", r));
      origin = "https://127.0.0.1:" + server.address().port;
      chrome = spawn(
        process.env.CHROME_BIN || "google-chrome",
        [
          "--headless=new",
          "--no-sandbox",
          "--disable-gpu",
          "--disable-background-networking",
          "--ignore-certificate-errors",
          "--remote-debugging-port=0",
          "--remote-debugging-address=127.0.0.1",
          "--user-data-dir=" + dir,
          "about:blank",
        ],
        { stdio: ["ignore", "ignore", "pipe"] },
      );
      let chromeError = "";
      chrome.on("error", (e) => {
        chromeError += e.message;
      });
      chrome.stderr.on("data", (x) => {
        chromeError = (chromeError + x).slice(-4096);
      });
      let port;
      for (let i = 0; i < 300; i++) {
        if (chrome.exitCode !== null || chromeError.includes("ENOENT")) break;
        try {
          port = (
            await readFile(join(dir, "DevToolsActivePort"), "utf8")
          ).split("\n")[0];
          break;
        } catch {}
        await new Promise((r) => setTimeout(r, 100));
      }
      assert.ok(port, "Synthetic Chrome did not start: " + chromeError);
      const tabs = await (
        await fetch("http://127.0.0.1:" + port + "/json/list")
      ).json();
      ws = new WebSocket(
        tabs.find((x) => x.type === "page").webSocketDebuggerUrl,
      );
      await new Promise((r) => ws.addEventListener("open", r, { once: true }));
      let seq = 0;
      const pending = new Map();
      ws.addEventListener("message", (e) => {
        const m = JSON.parse(e.data);
        if (m.id) {
          const p = pending.get(m.id);
          pending.delete(m.id);
          m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result);
        }
      });
      const cdp = (method, params = {}) =>
        new Promise((resolve, reject) => {
          const id = ++seq;
          pending.set(id, { resolve, reject });
          ws.send(JSON.stringify({ id, method, params }));
        });
      await cdp("Page.enable");
      const loaded = new Promise((r) => {
        const listener = (e) => {
          if (JSON.parse(e.data).method === "Page.loadEventFired") {
            ws.removeEventListener("message", listener);
            r();
          }
        };
        ws.addEventListener("message", listener);
      });
      await cdp("Page.navigate", { url: origin + "/" });
      await loaded;
      await cdp("Runtime.evaluate", {
        expression: 'document.querySelector("form").requestSubmit()',
        userGesture: true,
      });
      await posted;
      assert.equal(observed.origin, origin);
      assert.equal(observed.referer, origin + "/");
      assert.equal(observed.status, 303);
      assert.equal(new URL(observed.location).origin, "https://github.com");
      assert.equal(entries.size, 1);
      const stopped = new Promise((r) => {
        const listener = (e) => {
          if (JSON.parse(e.data).method === "Page.loadEventFired") {
            ws.removeEventListener("message", listener);
            r();
          }
        };
        ws.addEventListener("message", listener);
      });
      await cdp("Page.navigate", {
        url:
          origin + "/login/callback?code=ZZSENSITIVE&state=" + "a".repeat(64),
      });
      await stopped;
      const rendered = await cdp("Runtime.evaluate", {
        expression: "document.body.innerText",
      });
      assert.match(rendered.result.value, /Stage: github-cookie\./);
      assert.doesNotMatch(rendered.result.value, /ZZSENSITIVE|state=|https:/);
    } finally {
      ws?.close();
      if (chrome && chrome.exitCode === null) {
        const exited = once(chrome, "exit");
        chrome.kill("SIGKILL");
        await exited;
      }
      if (server)
        await new Promise((r) => {
          server.closeAllConnections();
          server.close(r);
        });
      await rm(dir, {
        recursive: true,
        force: true,
        maxRetries: 5,
        retryDelay: 100,
      });
    }
  },
);
