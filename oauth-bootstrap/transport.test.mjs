import test from "node:test";
import assert from "node:assert/strict";
import { Miniflare, convertV4MiniflareOptions } from "miniflare";
import { build } from "esbuild";
import sodium from "libsodium-wrappers";

test("workerd production entry exercises all external paths without native fetch binding or redirect errors", async () => {
  await sodium.ready;
  const pair = sodium.crypto_box_keypair();
  const calls = [];
  const bundled = await build({
    entryPoints: ["worker.mjs"],
    bundle: true,
    format: "esm",
    write: false,
    platform: "browser",
  });
  for (const discovery of [false, true]) {
  for (const redirectAt of (discovery ? [0, -1, 4, 5] : [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10])) {
    calls.length = 0;
    const mf = new Miniflare(
      convertV4MiniflareOptions({
        workers: [
          {
            name: "zz-bootstrap",
            modules: [
              {
                type: "ESModule",
                path: process.cwd() + "/zz-worker.mjs",
                contents: bundled.outputFiles[0].text,
              },
            ],
            compatibilityDate: "2026-10-01",
            durableObjects: {
              OAUTH_STATES: { className: "OneTimeState", useSQLite: true },
            },
            bindings: {
              CALLBACK_ORIGIN: "https://example.invalid",
              ALLOWED_GITHUB_ID: "12345",
              SESSION_SIGNING_KEY: "a".repeat(64),
              GITHUB_LOGIN_CLIENT_ID: "ZZLOGINCLIENT",
              GITHUB_LOGIN_CLIENT_SECRET: "ZZLOGINSECRET",
              GENI_CLIENT_ID: "ZZCLIENT",
              GENI_APP_SECRET: "ZZSECRET",
              ...(discovery ? { DISCOVERY_ONLY: "true" } : { GITHUB_WRITER: "ZZWRITER" }),
            },
            outboundService: async (req) => {
              const u = new URL(req.url);
              calls.push(req.method + " " + u.hostname + u.pathname);
              if (redirectAt > 0 && calls.length === redirectAt)
                return new Response(null, {
                  status: 302,
                  headers: { Location: "https://evil.invalid/ZZSENSITIVE" },
                });
              if (
                u.hostname === "github.com" &&
                u.pathname === "/login/oauth/access_token"
              )
                return Response.json({
                  access_token: "ZZTOKEN",
                  scope: "",
                  token_type: "bearer",
                });
              if (u.hostname === "api.github.com" && u.pathname === "/user")
                return Response.json({ id: 12345, type: "User" });
              if (u.pathname === "/applications/ZZLOGINCLIENT/token")
                return new Response(null, { status: 204 });
              if (
                u.hostname === "www.geni.com" &&
                u.pathname === "/platform/oauth/request_token"
              )
                return Response.json({
                  access_token: "ZZACCESS",
                  refresh_token: "ZZREFRESH",
                  expires_in: 300,
                });
              if (u.hostname === "www.geni.com" && u.pathname === "/api/profile") {
                assert.equal(discovery, true);
                assert.equal(req.method, "GET");
                assert.equal(req.headers.get("Authorization"), "Bearer ZZACCESS");
                assert.equal(u.search, "?fields=id,first_name,last_name,merge_pending,merged_into");
                return Response.json({id:"profile-99123",first_name:"ZZRoot",last_name:"ZZPerson",...(redirectAt === -1 ? {} : {merge_pending:false})});
              }
              if (discovery) assert.fail("discovery attempted writer request");
              if (u.pathname.endsWith("/public-key"))
                return Response.json({
                  key: sodium.to_base64(
                    pair.publicKey,
                    sodium.base64_variants.ORIGINAL,
                  ),
                  key_id: "ZZKEY",
                });
              if (
                req.method === "PUT" &&
                u.pathname.includes("/actions/secrets/")
              )
                return new Response(null, { status: 204 });
              assert.fail("unexpected external request");
            },
          },
        ],
      }),
    );
    try {
      const origin = "https://example.invalid";
      const begin = await mf.dispatchFetch(origin + "/login", {
        method: "POST",
        headers: { Origin: origin },
        redirect: "manual",
      });
      assert.equal(begin.status, 303, await begin.text());
      const b = new URL(begin.headers.get("location"));
      const bind = begin.headers.get("set-cookie").split(";")[0];
      const login = await mf.dispatchFetch(
        origin +
          "/login/callback?code=ZZCODE&state=" +
          b.searchParams.get("state"),
        { headers: { Cookie: bind }, redirect: "manual" },
      );
      if (redirectAt <= 3 && redirectAt > 0) {
        assert.equal(login.status, 400);
        assert.equal(calls.length, redirectAt === 2 ? 3 : redirectAt);
        assert.doesNotMatch(await login.text(), /ZZSENSITIVE|evil.invalid/);
        continue;
      }
      assert.equal(login.status, 303, await login.text());
      const session = login.headers
        .getSetCookie()
        .find((x) => x.startsWith("__Host-bootstrap-session="))
        .split(";")[0];
      const start = await mf.dispatchFetch(origin + (discovery ? "/discover/start" : "/start"), {
        method: "POST",
        headers: { Origin: origin, Cookie: session },
        redirect: "manual",
      });
      assert.equal(start.status, 303, await start.text());
      const g = new URL(start.headers.get("location"));
      const gbind = start.headers.get("set-cookie").split(";")[0];
      const done = await mf.dispatchFetch(
        origin + "/callback?code=ZZCODE&state=" + g.searchParams.get("state"),
        { headers: { Cookie: session + "; " + gbind }, redirect: "manual" },
      );
      if (redirectAt >= 4) {
        assert.equal(done.status, 400);
        assert.equal(calls.length, redirectAt === 2 ? 3 : redirectAt);
        assert.doesNotMatch(await done.text(), /ZZSENSITIVE|evil.invalid/);
        continue;
      }
      if (discovery) {
        assert.equal(done.status,200);
        const text=await done.text();
        assert.match(text,/Identity discovered, not connected/);
        assert.match(text,/profile-99123/);
        if (redirectAt === -1) { assert.match(text,/merge status not supplied by Geni/); assert.doesNotMatch(text,/Pending merge: false/); }
        assert.doesNotMatch(text,/ZZACCESS|ZZREFRESH|ZZCODE/);
        assert.deepEqual(calls,["POST github.com/login/oauth/access_token","GET api.github.com/user","DELETE api.github.com/applications/ZZLOGINCLIENT/token","POST www.geni.com/platform/oauth/request_token","GET www.geni.com/api/profile"]);
        continue;
      }
      assert.equal(done.status, 303, await done.text());
      assert.deepEqual(calls, [
        "POST github.com/login/oauth/access_token",
        "GET api.github.com/user",
        "DELETE api.github.com/applications/ZZLOGINCLIENT/token",
        "POST www.geni.com/platform/oauth/request_token",
        "GET api.github.com/repos/reihlinstinct/geni-uploader/actions/secrets/public-key",
        "PUT api.github.com/repos/reihlinstinct/geni-uploader/actions/secrets/GENI_OAUTH_REFRESH_BUNDLE",
        "GET api.github.com/repos/reihlinstinct/geni-uploader/actions/secrets/public-key",
        "PUT api.github.com/repos/reihlinstinct/geni-uploader/actions/secrets/GENI_ACCESS_TOKEN",
        "GET api.github.com/repos/reihlinstinct/geni-uploader/actions/secrets/public-key",
        "PUT api.github.com/repos/reihlinstinct/geni-uploader/actions/secrets/GENI_OAUTH_REFRESH_BUNDLE",
      ]);
    } finally {
      await mf.dispose();
    }
  }
  }
});
