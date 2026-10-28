import test from "node:test";
import assert from "node:assert/strict";
import sodium from "libsodium-wrappers";
import { generateKeyPair, SignJWT, createLocalJWKSet, exportJWK } from "jose";
import { handle, OneTimeState, verifyIdentityToken } from "./worker.mjs";
const origin = "https://example.invalid";
const env = {
  CALLBACK_ORIGIN: origin,
  ACCESS_TEAM: "https://zzteam.cloudflareaccess.com",
  ACCESS_AUD: "ZZAUD",
  ALLOWED_EMAIL: "zz@example.invalid",
  GENI_CLIENT_ID: "ZZCLIENT",
  GENI_APP_SECRET: "ZZSECRET",
  GITHUB_WRITER: "ZZWRITER",
};
const request = (path, init) => new Request(origin + path, init);
const verify = async () => "ZZSUB";
function states() {
  const entries = new Map();
  const storage = {
    get: async (k) => entries.get(k),
    put: async (k, v) => entries.set(k, v),
    delete: async (k) => entries.delete(k),
    setAlarm: async () => {},
    deleteAll: async () => entries.clear(),
    transaction: async (fn) => fn(storage),
  };
  const one = new OneTimeState({ storage });
  return {
    idFromName: (x) => x,
    get: () => ({ fetch: (u, o) => one.fetch(new Request(u, o)) }),
    entries,
    one,
  };
}
function setup() {
  return { ...env, OAUTH_STATES: states() };
}
const nofetch = () => assert.fail("unexpected fetch");
test("missing identity JWT fails closed", async () => {
  const r = await handle(request("/"), setup());
  assert.equal(r.status, 400);
  assert.doesNotMatch(await r.text(), /ZZSECRET/);
});
test("config rejects wrong origin before authorization", async () => {
  const r = await handle(
    request("/"),
    { ...setup(), CALLBACK_ORIGIN: "http://example.invalid" },
    { verify, fetcher: nofetch },
  );
  assert.equal(r.status, 400);
});
test("start requires same-origin POST", async () => {
  const r = await handle(
    request("/start", {
      method: "POST",
      headers: { Origin: "https://evil.invalid" },
    }),
    setup(),
    { verify, fetcher: nofetch },
  );
  assert.equal(r.status, 400);
});
async function begin(e) {
  const r = await handle(
    request("/start", { method: "POST", headers: { Origin: origin } }),
    e,
    { verify, fetcher: nofetch },
  );
  assert.equal(r.status, 303);
  const target = new URL(r.headers.get("location"));
  assert.equal(target.origin, "https://www.geni.com");
  assert.equal(target.searchParams.get("response_type"), "code");
  const cookie = r.headers.get("set-cookie").split(";")[0];
  assert.match(r.headers.get("set-cookie"), /Secure; HttpOnly; SameSite=Lax/);
  return { state: target.searchParams.get("state"), cookie };
}
test("wrong browser binding does not consume state", async () => {
  const e = setup();
  const { state } = await begin(e);
  const r = await handle(
    request("/callback?code=ZZCODE&state=" + state, {
      headers: { Cookie: "__Host-oauth-bind=" + "a".repeat(64) },
    }),
    e,
    { verify, fetcher: nofetch },
  );
  assert.equal(r.status, 400);
  assert.ok(e.OAUTH_STATES.entries.get("entry"));
});
test("subject mismatch and expired state refuse", async () => {
  const e = setup();
  const { state, cookie } = await begin(e);
  let r = await handle(
    request("/callback?code=ZZCODE&state=" + state, {
      headers: { Cookie: cookie },
    }),
    e,
    { verify: async () => "ZZOTHER", fetcher: nofetch },
  );
  assert.equal(r.status, 400);
  e.OAUTH_STATES.entries.get("entry").expires = 0;
  r = await handle(
    request("/callback?code=ZZCODE&state=" + state, {
      headers: { Cookie: cookie },
    }),
    e,
    { verify, fetcher: nofetch },
  );
  assert.equal(r.status, 400);
});
test("code flow seals secrets, consumes state once, never leaks", async () => {
  await sodium.ready;
  const key = sodium.crypto_box_keypair();
  const writes = [];
  const e = setup();
  const { state, cookie } = await begin(e);
  const fetcher = async (u, o) => {
    assert.equal(o.redirect, "error");
    if (u.endsWith("request_token")) {
      assert.equal(o.method, "POST");
      assert.equal(o.body.get("code"), "ZZCODE");
      return Response.json({
        access_token: "ZZACCESS",
        refresh_token: "ZZREFRESH",
        expires_in: 300,
      });
    }
    if (u.endsWith("/public-key"))
      return Response.json({
        key: sodium.to_base64(key.publicKey, sodium.base64_variants.ORIGINAL),
        key_id: "ZZKEY",
      });
    assert.equal(o.method, "PUT");
    const d = JSON.parse(o.body);
    const clear = sodium.crypto_box_seal_open(
      sodium.from_base64(d.encrypted_value, sodium.base64_variants.ORIGINAL),
      key.publicKey,
      key.privateKey,
    );
    writes.push([u, new TextDecoder().decode(clear)]);
    return new Response(null, { status: 204 });
  };
  const r = await handle(
    request("/callback?code=ZZCODE&state=" + state, {
      headers: { Cookie: cookie },
    }),
    e,
    { verify, fetcher },
  );
  assert.equal(r.status, 303);
  assert.equal(writes.length, 3);
  assert.equal(JSON.parse(writes[0][1]).refresh_token, "ZZREFRESH");
  assert.equal(writes[1][1], "ZZACCESS");
  assert.equal(JSON.parse(writes[2][1]).pending_access_token, undefined);
  assert.doesNotMatch(await r.text(), /ZZ/);
  const replay = await handle(
    request("/callback?code=ZZCODE&state=" + state, {
      headers: { Cookie: cookie },
    }),
    e,
    { verify, fetcher: nofetch },
  );
  assert.equal(replay.status, 400);
});
test("duplicate codes or cancel stop before token request", async () => {
  const e = setup();
  const { state, cookie } = await begin(e);
  for (const q of ["code=A&code=B", "code=A&error=denied"]) {
    const r = await handle(
      request("/callback?" + q + "&state=" + state, {
        headers: { Cookie: cookie },
      }),
      e,
      { verify, fetcher: nofetch },
    );
    assert.equal(r.status, 400);
  }
});
test("transport errors and secret writer failures never leak", async () => {
  const e = setup();
  const { state, cookie } = await begin(e);
  const r = await handle(
    request("/callback?code=ZZCODE&state=" + state, {
      headers: { Cookie: cookie },
    }),
    e,
    {
      verify,
      fetcher: () => {
        throw Error("ZZSECRET");
      },
    },
  );
  assert.equal(r.status, 400);
  assert.doesNotMatch(await r.text(), /ZZSECRET|ZZCODE/);
});

test("real signed JWT verifies issuer audience identity algorithm and expiry", async () => {
  const { publicKey, privateKey } = await generateKeyPair("RS256");
  const jwk = await exportJWK(publicKey);
  jwk.kid = "ZZKEY";
  const keys = createLocalJWKSet({ keys: [jwk] });
  const cfg = { team: env.ACCESS_TEAM };
  async function signed(
    overrides = {},
    issuer = env.ACCESS_TEAM,
    audience = env.ACCESS_AUD,
    expiry = "5m",
  ) {
    return new SignJWT({ email: env.ALLOWED_EMAIL, ...overrides })
      .setProtectedHeader({ alg: "RS256", kid: "ZZKEY" })
      .setSubject("ZZSUB")
      .setIssuer(issuer)
      .setAudience(audience)
      .setIssuedAt()
      .setExpirationTime(expiry)
      .sign(privateKey);
  }
  assert.equal(
    await verifyIdentityToken(await signed(), env, cfg, keys),
    "ZZSUB",
  );
  for (const token of [
    await signed({ email: "wrong@example.invalid" }),
    await signed({}, "https://wrong.invalid"),
    await signed({}, env.ACCESS_TEAM, "ZZWRONG"),
    await signed({}, env.ACCESS_TEAM, env.ACCESS_AUD, "-1m"),
    "bad.jwt.data",
  ]) {
    await assert.rejects(() => verifyIdentityToken(token, env, cfg, keys));
  }
  const { privateKey: other } = await generateKeyPair("RS256");
  const forged = await new SignJWT({ email: env.ALLOWED_EMAIL })
    .setProtectedHeader({ alg: "RS256", kid: "ZZKEY" })
    .setSubject("ZZSUB")
    .setIssuer(env.ACCESS_TEAM)
    .setAudience(env.ACCESS_AUD)
    .setExpirationTime("5m")
    .sign(other);
  await assert.rejects(() => verifyIdentityToken(forged, env, cfg, keys));
});
