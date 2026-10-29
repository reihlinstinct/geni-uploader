import sodium from "libsodium-wrappers";
import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import net from "node:net";

test(
  "actual Workers runtime imports Worker without top-level randomness",
  { timeout: 45000 },
  async () => {
    const server = net.createServer();
    server.listen(0, "127.0.0.1");
    await once(server, "listening");
    const port = server.address().port;
    await new Promise((resolve) => server.close(resolve));
    const child = spawn(
      process.execPath,
      [
        "node_modules/wrangler/bin/wrangler.js",
        "dev",
        "runtime-fixture.mjs",
        "--local",
        "--port",
        String(port),
        "--inspector-port",
        "0",
        "--persist-to",
        "/tmp/zz-oauth-runtime-test",
        "--log-level",
        "error",
      ],
      {
        env: { ...process.env, CLOUDFLARE_SEND_METRICS: "false", CI: "true" },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let output = "";
    child.stdout.on("data", (x) => (output += x));
    child.stderr.on("data", (x) => (output += x));
    const exited = once(child, "exit");
    try {
      let response;
      for (let i = 0; i < 100; i++) {
        if (child.exitCode !== null) break;
        try {
          response = await fetch("http://127.0.0.1:" + port);
          break;
        } catch {}
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
      assert.ok(response, "runtime did not start: " + output);
      assert.equal(response.status, 400);
      assert.match(await response.text(), /Stopped. No credentials displayed/);
      await sodium.ready;
      const pair = sodium.crypto_box_keypair();
      const sealed = await fetch("http://127.0.0.1:" + port + "/zz-seal", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          publicKey: sodium.to_base64(
            pair.publicKey,
            sodium.base64_variants.ORIGINAL,
          ),
        }),
      });
      assert.equal(sealed.status, 200);
      const ciphertext = sodium.from_base64(
        await sealed.text(),
        sodium.base64_variants.ORIGINAL,
      );
      const plain = sodium.crypto_box_seal_open(
        ciphertext,
        pair.publicKey,
        pair.privateKey,
      );
      assert.equal(new TextDecoder().decode(plain), "ZZSYNTHETIC");
      assert.doesNotMatch(
        output,
        /No secure random number generator|top-level|Uncaught Error/,
      );
    } finally {
      child.kill("SIGTERM");
      await exited;
    }
  },
);

// #233: real local SQLite persistence/concurrency, never a production service.
import './intent-local-runtime.test.mjs';

// Fixed-issuer trust boundary uses mocked fetch and synthetic signing keys only.
import './trusted-workload-jwks.test.mjs';

// Isolate global fetch/clock mocks from concurrent Workers runtime checks.
for (const suite of ['protected-father-runner.test.mjs','post-write-job-handoff.test.mjs','durable-father-executor.test.mjs','owner-preflight.test.mjs','bounded-upload-descriptors.test.mjs','private-approval-writer.test.mjs','live-protected-capture.test.mjs','protected-approval-service.test.mjs','immutable-prewrite-evidence.test.mjs',
 'postwrite-ledger-admission.test.mjs','father-intent-service.test.mjs','approval-admission.test.mjs','ciphertext-private-writer.test.mjs','reviewed-release-boundary.test.mjs']) {
 test(suite+' runs in an isolated process',{timeout:65000}, async () => {
  const {runIsolatedSuite}=await import('./isolated-test-runner.mjs');
  runIsolatedSuite(suite);
 });
}

import './isolated-test-runner.test.mjs';
