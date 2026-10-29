import test from "node:test";
import assert from "node:assert/strict";
import sodium from "libsodium-wrappers";
import { SignJWT } from "jose";
import { handle, OneTimeState } from "./worker.mjs";
const origin = "https://example.invalid";
const env = {
  CALLBACK_ORIGIN: origin,
  ALLOWED_GITHUB_ID: "12345",
  GITHUB_LOGIN_CLIENT_ID: "ZZLOGINCLIENT",
  GITHUB_LOGIN_CLIENT_SECRET: "ZZLOGINSECRET",
  SESSION_SIGNING_KEY: "a".repeat(64),
  GENI_CLIENT_ID: "ZZCLIENT",
  GENI_APP_SECRET: "ZZSECRET",
  GITHUB_WRITER: "ZZWRITER",
};
const request = (path, init) => new Request(origin + path, init);
async function session(
  sub = env.ALLOWED_GITHUB_ID,
  exp = "5m",
  key = env.SESSION_SIGNING_KEY,
  jti = "a".repeat(64),
) {
  const token = await new SignJWT({})
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(sub)
    .setIssuer(origin)
    .setAudience("bootstrap-session")
    .setJti(jti)
    .setIssuedAt()
    .setExpirationTime(exp)
    .sign(new TextEncoder().encode(key));
  return "__Host-bootstrap-session=" + token;
}
const verify = undefined;
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
test("public landing page has only GitHub login, protected start fails closed", async () => {
  const r = await handle(request("/"), setup());
  assert.equal(r.status, 200);
  assert.match(await r.text(), /Sign in with GitHub/);
  const start = await handle(
    request("/start", { method: "POST", headers: { Origin: origin } }),
    setup(),
  );
  assert.equal(start.status, 400);
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
    request("/start", {
      method: "POST",
      headers: { Origin: origin, Cookie: await session() },
    }),
    e,
    { verify, fetcher: nofetch },
  );
  assert.equal(r.status, 303);
  const target = new URL(r.headers.get("location"));
  assert.equal(target.origin, "https://www.geni.com");
  assert.equal(target.searchParams.get("response_type"), "code");
  const cookie =
    r.headers.get("set-cookie").split(";")[0] + "; " + (await session());
  assert.match(r.headers.get("set-cookie"), /Secure; HttpOnly; SameSite=Lax/);
  return { state: target.searchParams.get("state"), cookie };
}
test("wrong browser binding does not consume state", async () => {
  const e = setup();
  const { state } = await begin(e);
  const r = await handle(
    request("/callback?code=ZZCODE&state=" + state, {
      headers: {
        Cookie: (await session()) + "; __Host-oauth-bind=" + "a".repeat(64),
      },
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
      headers: {
        Cookie: cookie.replace(
          /__Host-bootstrap-session=.*/,
          await session("99999"),
        ),
      },
    }),
    e,
    { fetcher: nofetch },
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
    assert.equal(o.redirect, "manual");
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

test("session signature expiry subject and binding id are verified", async () => {
  for (const cookie of [
    await session("9999"),
    await session(env.ALLOWED_GITHUB_ID, "-1m"),
    await session(env.ALLOWED_GITHUB_ID, "5m", "b".repeat(64)),
    await session(
      env.ALLOWED_GITHUB_ID,
      "5m",
      env.SESSION_SIGNING_KEY,
      "invalid",
    ),
    "__Host-bootstrap-session=bad.jwt.value",
  ]) {
    const r = await handle(
      request("/start", {
        method: "POST",
        headers: { Origin: origin, Cookie: cookie },
      }),
      setup(),
      { fetcher: nofetch },
    );
    assert.equal(r.status, 400);
  }
});
async function loginBegin(e) {
  const r = await handle(
    request("/login", { method: "POST", headers: { Origin: origin } }),
    e,
    { fetcher: nofetch },
  );
  assert.equal(r.status, 303);
  const u = new URL(r.headers.get("location"));
  assert.equal(u.origin, "https://github.com");
  assert.equal(u.searchParams.get("code_challenge_method"), "S256");
  assert.match(u.searchParams.get("code_challenge"), /^[A-Za-z0-9_-]{43}$/);
  assert.equal(u.searchParams.get("scope"), "");
  return {
    state: u.searchParams.get("state"),
    cookie: r.headers.get("set-cookie").split(";")[0],
    challenge: u.searchParams.get("code_challenge"),
  };
}
function loginFetcher(calls, options = {}) {
  return async (u, o) => {
    calls.push(u);
    assert.equal(o.redirect, "manual");
    if (u === "https://github.com/login/oauth/access_token") {
      assert.equal(o.body.get("redirect_uri"), origin + "/login/callback");
      assert.match(o.body.get("code_verifier"), /^[a-f0-9]{64}$/);
      return Response.json({
        access_token: "ZZLOGINTOKEN",
        scope: options.scope || "",
        token_type: "bearer",
      });
    }
    if (u === "https://api.github.com/user")
      return Response.json({ id: options.id || 12345, type: "User" });
    assert.equal(u, "https://api.github.com/applications/ZZLOGINCLIENT/token");
    assert.equal(o.method, "DELETE");
    return new Response(null, { status: options.revokeStatus || 204 });
  };
}
test("GitHub PKCE identity check creates short signed session and revokes transient token", async () => {
  const e = setup(),
    b = await loginBegin(e),
    calls = [];
  const r = await handle(
    request("/login/callback?code=ZZCODE&state=" + b.state, {
      headers: { Cookie: b.cookie },
    }),
    e,
    { fetcher: loginFetcher(calls) },
  );
  assert.equal(r.status, 303);
  assert.equal(calls.length, 3);
  const cookies = r.headers.get("set-cookie");
  assert.match(cookies, /__Host-bootstrap-session=/);
  assert.match(cookies, /HttpOnly/);
  assert.doesNotMatch(cookies, /ZZLOGINTOKEN/);
  const replay = await handle(
    request("/login/callback?code=ZZCODE&state=" + b.state, {
      headers: { Cookie: b.cookie },
    }),
    e,
    { fetcher: nofetch },
  );
  assert.equal(replay.status, 400);
});
test("wrong GitHub account or unrevoked token cannot create a session", async () => {
  for (const options of [
    { id: 9999 },
    { revokeStatus: 500 },
    { scope: "repo" },
  ]) {
    const e = setup(),
      b = await loginBegin(e),
      calls = [];
    const r = await handle(
      request("/login/callback?code=ZZCODE&state=" + b.state, {
        headers: { Cookie: b.cookie },
      }),
      e,
      { fetcher: loginFetcher(calls, options) },
    );
    assert.equal(r.status, 400);
    assert.equal(r.headers.get("set-cookie"), null);
  }
});
test("login CSRF wrong cookie duplicates cancellation and expiry never reach network", async () => {
  const e = setup(),
    b = await loginBegin(e);
  for (const path of [
    "/login/callback?code=A&code=B&state=" + b.state,
    "/login/callback?error=denied&state=" + b.state,
  ]) {
    assert.equal(
      (
        await handle(request(path, { headers: { Cookie: b.cookie } }), e, {
          fetcher: nofetch,
        })
      ).status,
      400,
    );
  }
  const wrong = await handle(
    request("/login/callback?code=A&state=" + b.state, {
      headers: { Cookie: "__Host-login-bind=" + "f".repeat(64) },
    }),
    e,
    { fetcher: nofetch },
  );
  assert.equal(wrong.status, 400);
  assert.ok(e.OAUTH_STATES.entries.get("entry"));
  e.OAUTH_STATES.entries.get("entry").expires = 0;
  assert.equal(
    (
      await handle(
        request("/login/callback?code=A&state=" + b.state, {
          headers: { Cookie: b.cookie },
        }),
        e,
        { fetcher: nofetch },
      )
    ).status,
    400,
  );
});

test("stale landing session offers login while protected endpoints stay closed", async () => {
  const cookie = await session(env.ALLOWED_GITHUB_ID, "-1m");
  const landing = await handle(
    request("/", { headers: { Cookie: cookie } }),
    setup(),
    { fetcher: nofetch },
  );
  assert.equal(landing.status, 200);
  assert.match(await landing.text(), /Sign in with GitHub/);
  assert.match(landing.headers.get("set-cookie"), /Max-Age=0/);
  assert.match(
    landing.headers.get("content-security-policy"),
    /form-action 'self' https:\/\/github.com https:\/\/www.geni.com/,
  );
  const protectedResponse = await handle(
    request("/callback?code=ZZCODE&state=" + "a".repeat(64), {
      headers: { Cookie: cookie },
    }),
    setup(),
    { fetcher: nofetch },
  );
  assert.equal(protectedResponse.status, 400);
});
test("state and session budget is ten minutes and session is reusable", async () => {
  const e = setup(),
    b = await loginBegin(e),
    calls = [];
  const expires = e.OAUTH_STATES.entries.get("entry").expires;
  assert.ok(expires - Date.now() > 590000 && expires - Date.now() <= 600000);
  const r = await handle(
    request("/login/callback?code=ZZCODE&state=" + b.state, {
      headers: { Cookie: b.cookie },
    }),
    e,
    { fetcher: loginFetcher(calls) },
  );
  assert.match(r.headers.get("set-cookie"), /Max-Age=600/);
  const match = r.headers
    .get("set-cookie")
    .match(/__Host-bootstrap-session=([^;]+)/);
  for (let i = 0; i < 2; i++)
    assert.equal(
      (
        await handle(request("/", { headers: { Cookie: match[0] } }), setup(), {
          fetcher: nofetch,
        })
      ).status,
      200,
    );
});

test("only query-free form pages use strict-origin; callbacks and rejects retain no-referrer", async () => {
  for (const headers of [{}, { Cookie: await session() }]) {
    const form = await handle(request("/", { headers }), setup());
    assert.equal(form.status, 200);
    assert.equal(form.headers.get("referrer-policy"), "strict-origin");
    const query = await handle(
      request("/?code=ZZSYNTHETIC", { headers }),
      setup(),
    );
    assert.ok(query.status >= 400);
    assert.equal(query.headers.get("referrer-policy"), "no-referrer");
  }
  for (const path of ["/login/callback", "/callback", "/start"]) {
    const r = await handle(request(path), setup());
    assert.equal(r.status, 400);
    assert.equal(r.headers.get("referrer-policy"), "no-referrer");
  }
  for (const value of ["null", "https://evil.invalid"]) {
    for (const path of ["/login", "/start"]) {
      const r = await handle(
        request(path, {
          method: "POST",
          headers: { Origin: value, Cookie: await session() },
        }),
        setup(),
      );
      assert.equal(r.status, 400);
      assert.equal(r.headers.get("referrer-policy"), "no-referrer");
    }
  }
  const redirect = await handle(
    request("/login", { method: "POST", headers: { Origin: origin } }),
    setup(),
  );
  assert.equal(redirect.status, 303);
  assert.equal(redirect.headers.get("referrer-policy"), "no-referrer");
});

test("fixed stage diagnostics contain no request or provider values", async () => {
  const seen = new Set();
  const check = async (r, stage) => {
    assert.equal(r.status, 400);
    const body = await r.text();
    assert.equal(
      body,
      "Stopped. No credentials displayed. Check setup; do not share the address or retry blindly. Stage: " +
        stage +
        ".",
    );
    assert.equal(r.headers.get("referrer-policy"), "no-referrer");
    assert.equal(r.headers.get("cache-control"), "no-store");
    assert.doesNotMatch(body, /ZZ|https:|Cookie|secret=|code=/);
    seen.add(stage);
  };
  await check(await handle(request("/"), {}), "setup");
  await check(
    await handle(
      request("/login", { method: "POST", headers: { Origin: "null" } }),
      setup(),
    ),
    "github-origin",
  );
  const broken = setup();
  broken.OAUTH_STATES.get = () => ({
    fetch: () => {
      throw Error("ZZSENSITIVE");
    },
  });
  await check(
    await handle(
      request("/login", { method: "POST", headers: { Origin: origin } }),
      broken,
    ),
    "github-state-issue",
  );
  await check(
    await handle(
      request("/login/callback?code=ZZSENSITIVE&state=" + "a".repeat(64)),
      setup(),
    ),
    "github-cookie",
  );
  for (const stage of [
    "github-parameters",
    "github-state",
    "github-exchange",
    "github-token-shape",
    "github-user",
    "github-revoke",
    "github-identity",
  ]) {
    const e = setup(),
      b = await loginBegin(e);
    let path = "/login/callback?code=ZZSENSITIVE&state=" + b.state;
    if (stage === "github-parameters") path += "&code=ZZEXTRA";
    if (stage === "github-state") e.OAUTH_STATES.entries.clear();
    const base = loginFetcher(
      [],
      stage === "github-identity" ? { id: 9999 } : {},
    );
    const fetcher = async (u, o) => {
      if (stage === "github-exchange" && u.includes("access_token"))
        throw Error("ZZSENSITIVE");
      if (stage === "github-token-shape" && u.includes("access_token"))
        return Response.json({
          access_token: "ZZTOKEN",
          scope: "repo",
          token_type: "bearer",
        });
      if (stage === "github-user" && u.endsWith("/user"))
        throw Error("ZZSENSITIVE");
      if (stage === "github-revoke" && o.method === "DELETE")
        return new Response("ZZSENSITIVE", { status: 500 });
      return base(u, o);
    };
    await check(
      await handle(request(path, { headers: { Cookie: b.cookie } }), e, {
        fetcher,
      }),
      stage === "github-exchange" ? "github-exchange-transport" : stage,
    );
  }
  await check(
    await handle(request("/callback?code=ZZSENSITIVE"), setup()),
    "geni-session",
  );
  await check(
    await handle(
      request("/start", {
        method: "POST",
        headers: { Origin: "null", Cookie: await session() },
      }),
      setup(),
    ),
    "geni-origin",
  );
  await check(
    await handle(
      request("/start", {
        method: "POST",
        headers: { Origin: origin, Cookie: await session() },
      }),
      broken,
    ),
    "geni-state-issue",
  );
  await sodium.ready;
  const key = sodium.crypto_box_keypair();
  for (const stage of [
    "geni-parameters",
    "geni-state",
    "geni-exchange",
    "geni-token-shape",
    "writer-key",
    "writer-bundle",
    "writer-access",
    "writer-finalize",
  ]) {
    const e = setup(),
      b = await begin(e);
    let path = "/callback?code=ZZSENSITIVE&state=" + b.state;
    let writes = 0;
    if (stage === "geni-parameters") path += "&code=ZZEXTRA";
    if (stage === "geni-state") e.OAUTH_STATES.entries.clear();
    const fetcher = async (u, o) => {
      if (u.endsWith("request_token")) {
        if (stage === "geni-exchange") throw Error("ZZSENSITIVE");
        return Response.json({
          access_token: "ZZACCESS",
          refresh_token: stage === "geni-token-shape" ? "" : "ZZREFRESH",
          expires_in: 300,
        });
      }
      if (u.endsWith("/public-key")) {
        if (stage === "writer-key") throw Error("ZZSENSITIVE");
        return Response.json({
          key: sodium.to_base64(key.publicKey, sodium.base64_variants.ORIGINAL),
          key_id: "ZZKEY",
        });
      }
      writes++;
      const failed = {
        "writer-bundle": 1,
        "writer-access": 2,
        "writer-finalize": 3,
      }[stage];
      return new Response(writes === failed ? "ZZSENSITIVE" : null, {
        status: writes === failed ? 500 : 204,
      });
    };
    await check(
      await handle(request(path, { headers: { Cookie: b.cookie } }), e, {
        fetcher,
      }),
      stage,
    );
  }
  assert.equal(seen.size, 22);
});

test("GitHub exchange maps only fixed outcomes and sets server User-Agent", async () => {
  const cases = [
    [
      "transport",
      () => {
        throw Error("ZZSENSITIVE");
      },
    ],
    ["http", () => new Response("ZZSENSITIVE", { status: 403 })],
    ["format", () => new Response("ZZSENSITIVE")],
    ["format", () => new Response("x".repeat(65537))],
    ["format", () => Response.json([])],
    ["format", () => Response.json(null)],
    [
      "credentials",
      () =>
        Response.json({
          error: "incorrect_client_credentials",
          error_description: "ZZSENSITIVE",
        }),
    ],
    [
      "redirect",
      () =>
        Response.json(
          { error: "redirect_uri_mismatch", error_description: "ZZSENSITIVE" },
          { status: 400 },
        ),
    ],
    [
      "code",
      () =>
        Response.json({
          error: "bad_verification_code",
          error_description: "ZZSENSITIVE",
        }),
    ],
    [
      "provider",
      () =>
        Response.json({
          error: "ZZSENSITIVE",
          error_description: "ZZSENSITIVE",
        }),
    ],
    ["provider", () => Response.json({ error: { unexpected: "ZZSENSITIVE" } })],
  ];
  for (const [label, respond] of cases) {
    const e = setup(),
      b = await loginBegin(e);
    let calls = 0;
    const r = await handle(
      request("/login/callback?code=ZZSENSITIVE&state=" + b.state, {
        headers: { Cookie: b.cookie },
      }),
      e,
      {
        fetcher: async (u, o) => {
          calls++;
          assert.equal(u, "https://github.com/login/oauth/access_token");
          assert.equal(o.method, "POST");
          assert.equal(o.redirect, "manual");
          assert.equal(o.headers["User-Agent"], "oauth-bootstrap");
          assert.equal(o.headers.Accept, "application/json");
          assert.equal(o.body.get("redirect_uri"), origin + "/login/callback");
          assert.match(o.body.get("code_verifier"), /^[a-f0-9]{64}$/);
          return respond();
        },
      },
    );
    assert.equal(calls, 1);
    assert.equal(r.status, 400);
    assert.equal(
      await r.text(),
      "Stopped. No credentials displayed. Check setup; do not share the address or retry blindly. Stage: github-exchange-" +
        label +
        ".",
    );
    assert.equal(r.headers.get("cache-control"), "no-store");
    assert.equal(r.headers.get("referrer-policy"), "no-referrer");
    assert.equal(e.OAUTH_STATES.entries.size, 0);
  }
});

async function beginConnection(e, destination) {
  const r = await handle(request('/connections/' + destination + '/start', {
    method: 'POST', headers: { Origin: origin, Cookie: await session() },
  }), e, { fetcher: nofetch });
  assert.equal(r.status, 303);
  const u = new URL(r.headers.get('location'));
  assert.equal(u.searchParams.get('redirect_uri'), origin + '/callback');
  return { state: u.searchParams.get('state'),
    cookie: r.headers.get('set-cookie').split(';')[0] + '; ' + await session() };
}

for (const destination of ['secondary', 'tertiary']) {
  test(destination + ' writes only its fixed isolated destination after owner proof', async () => {
    await sodium.ready;
    const key = sodium.crypto_box_keypair();
    const e = { ...setup(), PRIMARY_OWNER_NODE: 'profile-99000', SECONDARY_OWNER_NODE: 'profile-99123', TERTIARY_OWNER_NODE: 'profile-99124' };
    const b = await beginConnection(e, destination);
    const writes = [], calls = [];
    const owner = destination === 'secondary' ? e.SECONDARY_OWNER_NODE : e.TERTIARY_OWNER_NODE;
    const fetcher = async (u, o) => {
      calls.push(u);
      assert.equal(o.redirect, 'manual');
      if (u.endsWith('request_token')) return Response.json({ access_token:'ZZACCESS', refresh_token:'ZZREFRESH', expires_in:300 });
      if (u.startsWith('https://www.geni.com/api/profile?')) {
        assert.equal(o.method, 'GET');
        assert.equal(o.headers.Authorization, 'Bearer ZZACCESS');
        return Response.json({ id: owner, merge_pending:false });
      }
      if (u.endsWith('/public-key')) return Response.json({ key:sodium.to_base64(key.publicKey, sodium.base64_variants.ORIGINAL), key_id:'ZZKEY' });
      assert.equal(o.method, 'PUT');
      writes.push(u.split('/').at(-1));
      return new Response(null,{status:204});
    };
    const r = await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}), e,{fetcher});
    assert.equal(r.status,303);
    const prefix = destination.toUpperCase();
    assert.deepEqual(writes, ['GENI_'+prefix+'_OAUTH_REFRESH_BUNDLE','GENI_'+prefix+'_ACCESS_TOKEN','GENI_'+prefix+'_OAUTH_REFRESH_BUNDLE']);
    assert.ok(calls[1].startsWith('https://www.geni.com/api/profile?'));
    assert.doesNotMatch(await r.text(), /ZZACCESS|ZZREFRESH|9912/);
    const replay = await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:nofetch});
    assert.equal(replay.status,400);
  });
}

test('missing additional owner configuration stops before state or exchange', async () => {
  const e = setup();
  const r = await handle(request('/connections/secondary/start',{method:'POST',headers:{Origin:origin,Cookie:await session()}}),e,{fetcher:nofetch});
  assert.equal(r.status,400);
  assert.equal(e.OAUTH_STATES.entries.size,0);
});

for (const owner of [{id:'profile-99555',merge_pending:false}, {id:'profile-99123'},
  {id:'profile-99123',merge_pending:true}, {id:'profile-99123',merge_pending:false,merged_into:'profile-2'},
  {id:'profile-99123',merge_pending:false,results:[]}]) {
  test('unverified additional owner never writes any secret '+JSON.stringify(owner), async () => {
    const e = {...setup(),PRIMARY_OWNER_NODE:'profile-99000',SECONDARY_OWNER_NODE:'profile-99123'};
    const b = await beginConnection(e,'secondary');
    const calls = [];
    const r = await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:async(u)=>{
      calls.push(u);
      if(u.endsWith('request_token')) return Response.json({access_token:'ZZACCESS',refresh_token:'ZZREFRESH',expires_in:300});
      assert.ok(u.startsWith('https://www.geni.com/api/profile?'));
      return Response.json(owner);
    }});
    assert.equal(r.status,400); assert.equal(calls.length,2);
    assert.doesNotMatch(await r.text(),/ZZ|99123|99555/);
  });
}

for(const path of ['/connections/unknown/start','/connections/primary/start','/connections/secondary/start?destination=primary']) {
  test('unregistered or query-selected destination rejected '+path,async()=>{
    const r=await handle(request(path,{method:'POST',headers:{Origin:origin,Cookie:await session()}}),{...setup(),PRIMARY_OWNER_NODE:'profile-99000',SECONDARY_OWNER_NODE:'profile-99123'},{fetcher:nofetch});
    assert.equal(r.status,400);
  });
}

test('callback destination injection cannot redirect primary state',async()=>{
  const e=setup(); const b=await begin(e);
  const r=await handle(request('/callback?code=ZZCODE&state='+b.state+'&destination=secondary',{headers:{Cookie:b.cookie}}),e,{fetcher:nofetch});
  assert.equal(r.status,400);
});

test('additional configuration requires distinct pinned primary owner', async()=>{
  for(const pins of [{SECONDARY_OWNER_NODE:'profile-99123'},
    {PRIMARY_OWNER_NODE:'profile-99123',SECONDARY_OWNER_NODE:'profile-99123'}]) {
    const r=await handle(request('/'),{...setup(),...pins},{fetcher:nofetch});
    assert.equal(r.status,400);
  }
});

test('wrong additional account on primary button cannot overwrite primary',async()=>{
  const e={...setup(),PRIMARY_OWNER_NODE:'profile-99000',SECONDARY_OWNER_NODE:'profile-99123'};
  const b=await begin(e); const calls=[];
  const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:async(u)=>{
    calls.push(u);
    if(u.endsWith('request_token'))return Response.json({access_token:'ZZACCESS',refresh_token:'ZZREFRESH',expires_in:300});
    assert.ok(u.startsWith('https://www.geni.com/api/profile?'));
    return Response.json({id:'profile-99123',merge_pending:false});
  }});
  assert.equal(r.status,400);assert.equal(calls.length,2);
});

async function beginDiscovery(e) {
  const r = await handle(request('/discover/start', {method:'POST', headers:{Origin:origin, Cookie:await session()}}), e, {fetcher:nofetch});
  assert.equal(r.status,303);
  const url = new URL(r.headers.get('location'));
  assert.equal(url.origin,'https://www.geni.com');
  assert.equal(url.searchParams.get('redirect_uri'),origin+'/callback');
  return {state:url.searchParams.get('state'), cookie:r.headers.get('set-cookie').split(';')[0]+'; '+await session()};
}
const discoveryEnv = () => ({...setup(),DISCOVERY_ONLY:'true',GITHUB_WRITER:undefined});
const discovered = {id:'profile-99123',first_name:'ZZRoot',last_name:'ZZPerson',merge_pending:false};
function discoveryFetcher(owner, calls) {
  return async (u,o) => {
    calls.push(u);
    if(u === 'https://www.geni.com/platform/oauth/request_token') return Response.json({access_token:'ZZACCESS',refresh_token:'ZZREFRESH',expires_in:600});
    assert.equal(u,'https://www.geni.com/api/profile?fields=id,first_name,last_name,merge_pending,merged_into');
    assert.equal(o.method,'GET');assert.equal(o.redirect,'manual');
    assert.equal(o.headers.Authorization,'Bearer ZZACCESS');assert.ok(!u.includes('ZZACCESS'));
    return owner instanceof Response ? owner : Response.json(owner);
  };
}
test('discovery-only needs no writer, displays escaped minimal identity and never writes or retains token',async()=>{
 const e=discoveryEnv(),b=await beginDiscovery(e),calls=[];
 const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:discoveryFetcher({...discovered,first_name:'<script>ZZ&"\'',unexpected:'ZZPRIVATE'},calls)});
 assert.equal(r.status,200);const text=await r.text();
 assert.match(text,/profile-99123/);assert.match(text,/&lt;script&gt;ZZ&amp;&quot;&#39;/);
 for(const x of ['<script>','ZZPRIVATE','ZZACCESS','ZZREFRESH','ZZCODE','ZZSECRET']) assert.ok(!text.includes(x));
 assert.equal(calls.length,2);assert.equal(e.OAUTH_STATES.entries.size,0);
 assert.equal(r.headers.get('cache-control'),'no-store');assert.equal(r.headers.get('referrer-policy'),'no-referrer');
 assert.match(r.headers.get('set-cookie'),/Max-Age=0/);
 const replay=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:nofetch});assert.equal(replay.status,400);
});
test('discovery deployment disables every connection start and normal deployment disables discovery',async()=>{
 for(const path of ['/start','/connections/secondary/start','/connections/tertiary/start']) {
  const e=discoveryEnv();const r=await handle(request(path,{method:'POST',headers:{Origin:origin,Cookie:await session()}}),e,{fetcher:nofetch});assert.equal(r.status,400);assert.equal(e.OAUTH_STATES.entries.size,0);
 }
 const r=await handle(request('/discover/start',{method:'POST',headers:{Origin:origin,Cookie:await session()}}),setup(),{fetcher:nofetch});assert.equal(r.status,400);
 const landing=await handle(request('/',{headers:{Cookie:await session()}}),discoveryEnv(),{fetcher:nofetch});const text=await landing.text();assert.match(text,/Discover current/);assert.ok(!text.includes('Connect primary'));
});
test('discovery requires identity, same origin, query-free POST and valid config',async()=>{
 for(const [path,method,headers] of [['/discover/start','POST',{Origin:origin}],['/discover/start','POST',{Origin:'https://evil.invalid',Cookie:await session()}],['/discover/start?purpose=connect','POST',{Origin:origin,Cookie:await session()}],['/discover/start','GET',{Cookie:await session()}]]) {
 const r=await handle(request(path,{method,headers}),discoveryEnv(),{fetcher:nofetch});assert.ok(r.status>=400); }
 for(const value of ['false','TRUE','']) {const r=await handle(request('/'),{...setup(),DISCOVERY_ONLY:value},{fetcher:nofetch});assert.equal(r.status,400);}
});
test('purpose cannot be injected at callback, changed across deployment or omitted from old state',async()=>{
 for(const extra of ['&purpose=connect','&destination=primary','&connection=secondary']) {
  const e=discoveryEnv(),b=await beginDiscovery(e);const r=await handle(request('/callback?code=ZZCODE&state='+b.state+extra,{headers:{Cookie:b.cookie}}),e,{fetcher:nofetch});assert.equal(r.status,400);
 }
 for(const [e,fn,changed] of [[discoveryEnv(),beginDiscovery,{DISCOVERY_ONLY:undefined,GITHUB_WRITER:'ZZWRITER'}],[setup(),begin,{DISCOVERY_ONLY:'true'}]]) {
  const b=await fn(e);const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),{...e,...changed},{fetcher:nofetch});assert.equal(r.status,400);
 }
 const e=setup(),b=await begin(e);e.OAUTH_STATES.entries.get('entry').payload={destination:'primary'};
 const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:nofetch});assert.equal(r.status,400);
});
for(const owner of [{...discovered,id:99123},{...discovered,id:'99123'},{...discovered,merge_pending:true},{...discovered,merge_pending:undefined,merged_into:null},{...discovered,merged_into:'profile-99555'},{...discovered,results:[]},{...discovered,first_name:''},{...discovered,first_name:[]},{...discovered,last_name:3},{...discovered,first_name:'x'.repeat(201)},new Response('',{status:302,headers:{location:'https://evil.invalid'}}),new Response('ZZSENSITIVE',{status:500}),new Response('not json')]) {
 test('malformed merged or redirected discovery identity fails without writer '+JSON.stringify(owner),async()=>{
 const e=discoveryEnv(),b=await beginDiscovery(e),calls=[];const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:discoveryFetcher(owner,calls)});assert.equal(r.status,400);assert.equal(calls.length,2);const text=await r.text();assert.ok(!text.includes('ZZSENSITIVE'));assert.ok(!text.includes('ZZACCESS'));
 });
}
test('state object rejects invalid or mixed purpose at issuance',async()=>{
 for(const payload of [{purpose:'unknown'},{purpose:'discover',destination:'primary'},{purpose:'connect'},{purpose:'connect',destination:'unknown'}]) {
  const one=states().one;await assert.rejects(one.fetch(new Request('https://state.invalid/issue',{method:'POST',body:JSON.stringify({subject:'ZZSUBJECT',binding:'a'.repeat(64),payload})})));
 }
});
test('discovery cannot claim authorization saved through complete route',async()=>{
 const r=await handle(request('/complete',{headers:{Cookie:await session()}}),discoveryEnv(),{fetcher:nofetch});assert.equal(r.status,404);assert.doesNotMatch(await r.text(),/Authorization saved/);
 const normal=await handle(request('/complete',{headers:{Cookie:await session()}}),setup(),{fetcher:nofetch});assert.equal(normal.status,200);
 const query=await handle(request('/complete?purpose=discover',{headers:{Cookie:await session()}}),setup(),{fetcher:nofetch});assert.equal(query.status,404);
});
for(const [label,value] of [
 ['transport',new Error('ZZSENSITIVE')],['http',new Response('ZZSENSITIVE',{status:403})],
 ['http',new Response('',{status:302,headers:{location:'https://evil.invalid/ZZSENSITIVE'}})],
 ['format',new Response('ZZSENSITIVE')],['format',new Response('x'.repeat(65537))],
 ['format',Response.json([])],['format',Response.json(null)],
 ['provider',{...discovered,error:'ZZSENSITIVE'}],['id',{...discovered,id:3}],
 ['merge-missing',{...discovered,merge_pending:undefined,merged_into:null}],
 ['merge-status',{...discovered,merge_pending:true}],['merge-status',{...discovered,merge_pending:'false'}],
 ['merge-status',{...discovered,merge_pending:null}],['merged',{...discovered,merged_into:'profile-99555'}],
 ['wrapper',{...discovered,results:[]}],['name',{...discovered,first_name:''}],['name',{...discovered,last_name:5}]
])test('safe discovery diagnostic '+label+' '+JSON.stringify(value),async()=>{
 const e=discoveryEnv(),b=await beginDiscovery(e),calls=[];
 const original=discoveryFetcher(value,calls);
 const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:async(u,o)=>{
  if(u.startsWith('https://www.geni.com/api/profile?') && value instanceof Error)throw value;
  return original(u,o);
 }});
 assert.equal(r.status,400);const text=await r.text();assert.match(text,new RegExp('Stage: discovery-owner-'+label+'\\.'));
 assert.doesNotMatch(text,/ZZSENSITIVE|ZZACCESS|ZZREFRESH|ZZCODE|ZZSECRET|evil.invalid|profile-99555/);
 assert.ok(calls.length<=2);assert.equal(e.OAUTH_STATES.entries.size,0);
});
test('discovery only accepts both merge fields absent with explicit unknown warning, never false claim',async()=>{
 const e=discoveryEnv(),b=await beginDiscovery(e),calls=[];const owner={id:'profile-99123',first_name:'ZZRoot',last_name:'ZZPerson'};
 const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:discoveryFetcher(owner,calls)});
 assert.equal(r.status,200);const text=await r.text();assert.match(text,/profile-99123/);assert.match(text,/ZZRoot ZZPerson/);assert.match(text,/Warning: merge status not supplied by Geni \(unknown\)/);assert.match(text,/identity evidence only/);assert.doesNotMatch(text,/Pending merge: false|ZZACCESS|ZZREFRESH/);assert.equal(calls.length,2);assert.equal(e.OAUTH_STATES.entries.size,0);
});
for(const value of [null,'','profile-99555',false,[],{}])test('unknown merge flag plus any present merge target stops '+JSON.stringify(value),async()=>{
 const e=discoveryEnv(),b=await beginDiscovery(e),calls=[];const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:discoveryFetcher({id:'profile-99123',first_name:'ZZRoot',merged_into:value},calls)});assert.equal(r.status,400);assert.match(await r.text(),/discovery-owner-merge-missing/);assert.equal(calls.length,2);
});
for(const change of [{first_name:''},{first_name:null},{id:'99123'},{results:[]}])test('unknown merge still validates id name wrapper '+JSON.stringify(change),async()=>{
 const e=discoveryEnv(),b=await beginDiscovery(e);const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:discoveryFetcher({id:'profile-99123',first_name:'ZZRoot',...change},[])});assert.equal(r.status,400);
});
test('missing merge flag still rejects pinned credential storage before writer',async()=>{
 const e={...setup(),PRIMARY_OWNER_NODE:'profile-99123',SECONDARY_OWNER_NODE:'profile-99555'},b=await beginConnection(e,'secondary');let calls=0;
 const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:async u=>{calls++;if(u.includes('request_token'))return Response.json({access_token:'ZZACCESS',refresh_token:'ZZREFRESH',expires_in:600});assert.equal(u,'https://www.geni.com/api/profile?fields=id,merge_pending,merged_into');return Response.json({id:'profile-99555'});}});assert.equal(r.status,400);assert.equal(calls,2);
});
const custodyEnv = () => ({...setup(),PRIMARY_OWNER_NODE:'profile-99000',SECONDARY_OWNER_NODE:'profile-99123',SECONDARY_ALLOW_UNKNOWN_MERGE:'true'});
async function custodyCallback(e, owner, destination='secondary', failWrite=0) {
 await sodium.ready;const key=sodium.crypto_box_keypair(),b=destination==='primary'?await begin(e):await beginConnection(e,destination),writes=[],calls=[];
 const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),e,{fetcher:async(u,o)=>{
 calls.push(u);assert.equal(o.redirect,'manual');
 if(u.endsWith('request_token'))return Response.json({access_token:'ZZACCESS',refresh_token:'ZZREFRESH',expires_in:600});
 if(u.startsWith('https://www.geni.com/api/profile?')){assert.equal(o.headers.Authorization,'Bearer ZZACCESS');return Response.json(owner);}
 if(u.endsWith('/public-key'))return Response.json({key:sodium.to_base64(key.publicKey,sodium.base64_variants.ORIGINAL),key_id:'ZZKEY'});
 assert.equal(o.method,'PUT');const body=JSON.parse(o.body);const raw=sodium.crypto_box_seal_open(sodium.from_base64(body.encrypted_value,sodium.base64_variants.ORIGINAL),key.publicKey,key.privateKey);writes.push({name:u.split('/').at(-1),value:new TextDecoder().decode(raw)});
 return new Response(null,{status:writes.length===failWrite?500:204});
 }});return {r,writes,calls};
}
test('opted-in exact secondary unknown custody preserves attestation in pending and finalized encrypted bundles',async()=>{
 const {r,writes}=await custodyCallback(custodyEnv(),{id:'profile-99123'});assert.equal(r.status,303);
 assert.deepEqual(writes.map(x=>x.name),['GENI_SECONDARY_OAUTH_REFRESH_BUNDLE','GENI_SECONDARY_ACCESS_TOKEN','GENI_SECONDARY_OAUTH_REFRESH_BUNDLE']);
 const pending=JSON.parse(writes[0].value),final=JSON.parse(writes[2].value);assert.deepEqual(pending.owner_attestation,final.owner_attestation);const a=final.owner_attestation;
 assert.deepEqual(Object.keys(a).sort(),['credential_storage_only','merge_status','observed_at','owner_node','policy_version','upload_ready']);assert.equal(a.owner_node,'profile-99123');assert.equal(a.merge_status,'unknown');assert.equal(a.credential_storage_only,true);assert.equal(a.upload_ready,false);assert.equal(a.policy_version,'pinned-secondary-custody-v1');assert.ok(Number.isFinite(Date.parse(a.observed_at)));assert.equal(pending.pending_access_token,'ZZACCESS');assert.ok(!Object.hasOwn(final,'pending_access_token'));
});
test('secondary explicit false custody is marked as observed, never readiness',async()=>{
 const {r,writes}=await custodyCallback(custodyEnv(),{id:'profile-99123',merge_pending:false});assert.equal(r.status,303);const a=JSON.parse(writes[2].value).owner_attestation;assert.equal(a.merge_status,'explicit_false');assert.equal(a.upload_ready,false);
});
for(const owner of [{id:'profile-99555'},{id:'profile-99123',merge_pending:null},{id:'profile-99123',merge_pending:true},{id:'profile-99123',merge_pending:'false'},{id:'profile-99123',merge_pending:0},{id:'profile-99123',merged_into:null},{id:'profile-99123',merged_into:''},{id:'profile-99123',merged_into:'profile-99555'},{id:'profile-99123',results:[]}])test('secondary unknown opt-in still rejects invalid owner evidence '+JSON.stringify(owner),async()=>{
 const {r,writes,calls}=await custodyCallback(custodyEnv(),owner);assert.equal(r.status,400);assert.equal(writes.length,0);assert.equal(calls.length,2);
});
test('unknown custody requires explicit opt-in and is never applied to primary or tertiary',async()=>{
 const e=custodyEnv();delete e.SECONDARY_ALLOW_UNKNOWN_MERGE;const strict=await custodyCallback(e,{id:'profile-99123'});assert.equal(strict.r.status,400);assert.equal(strict.writes.length,0);
 for(const destination of ['primary','tertiary']){const result=await custodyCallback({...custodyEnv(),TERTIARY_OWNER_NODE:'profile-99124'},{id:destination==='primary'?'profile-99000':'profile-99124'},destination);assert.equal(result.r.status,400);assert.equal(result.writes.length,0);}
});
test('primary strict success retains existing bundle schema without secondary attestation',async()=>{
 const {r,writes}=await custodyCallback(custodyEnv(),{id:'profile-99000',merge_pending:false},'primary');assert.equal(r.status,303);assert.ok(writes.every(x=>!x.name.includes('SECONDARY')));assert.ok(!Object.hasOwn(JSON.parse(writes[2].value),'owner_attestation'));
});
for(const n of [1,2,3])test('secondary custody partial write stops, attestation remains in attempted bundles '+n,async()=>{
 const {r,writes}=await custodyCallback(custodyEnv(),{id:'profile-99123'},'secondary',n);assert.equal(r.status,400);assert.equal(writes.length,n);assert.equal(JSON.parse(writes[0].value).owner_attestation.merge_status,'unknown');
});
test('custody opt-in rejects invalid configuration and discovery mode',async()=>{
 for(const e of [{...custodyEnv(),SECONDARY_ALLOW_UNKNOWN_MERGE:'false'},{...custodyEnv(),SECONDARY_OWNER_NODE:undefined},{...custodyEnv(),DISCOVERY_ONLY:'true'}]){const r=await handle(request('/'),e,{fetcher:nofetch});assert.equal(r.status,400);}
});
test('secondary-only rollout hides and rejects primary and tertiary including in-flight state',async()=>{
 const e={...custodyEnv(),SECONDARY_ONLY:'true'};const landing=await handle(request('/',{headers:{Cookie:await session()}}),e,{fetcher:nofetch});const text=await landing.text();assert.match(text,/Primary connection is disabled/);assert.doesNotMatch(text,/Connect primary|Connect tertiary/);
 for(const path of ['/start','/connections/tertiary/start']){const r=await handle(request(path,{method:'POST',headers:{Origin:origin,Cookie:await session()}}),e,{fetcher:nofetch});assert.equal(r.status,400);}
 const old=custodyEnv(),b=await begin(old);const r=await handle(request('/callback?code=ZZCODE&state='+b.state,{headers:{Cookie:b.cookie}}),{...old,SECONDARY_ONLY:'true'},{fetcher:nofetch});assert.equal(r.status,400);
 const result=await custodyCallback(e,{id:'profile-99123'});assert.equal(result.r.status,303);assert.ok(result.writes.every(w=>w.name.startsWith('GENI_SECONDARY_')));
});

// Storage-only candidate tests, no Worker route or binding.
import "./create-intent-candidate.test.mjs";

// Offline workload JWT validation with synthetic keys only.
import "./intent-workload-verifier.test.mjs";
