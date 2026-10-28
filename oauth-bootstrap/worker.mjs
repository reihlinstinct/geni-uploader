import sealedbox from "tweetnacl-sealedbox-js";
import { jwtVerify, SignJWT } from "jose";

const GENI = "https://www.geni.com/platform/oauth/";
const GH =
  "https://api.github.com/repos/reihlinstinct/geni-uploader/actions/secrets";
const COOKIE = "__Host-oauth-bind";
const LOGIN_COOKIE = "__Host-login-bind";
const SESSION_COOKIE = "__Host-bootstrap-session";
const secureHeaders = {
  "cache-control": "no-store",
  "referrer-policy": "no-referrer",
  "content-security-policy":
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self' https://github.com https://www.geni.com",
  "content-type": "text/html; charset=utf-8",
  "x-content-type-options": "nosniff",
};
const STAGES = new Set([
  "setup",
  "github-origin",
  "github-state-issue",
  "github-cookie",
  "github-parameters",
  "github-state",
  "github-exchange",
  "github-token-shape",
  "github-user",
  "github-revoke",
  "github-identity",
  "github-session",
  "geni-session",
  "geni-origin",
  "geni-state-issue",
  "geni-parameters",
  "geni-state",
  "geni-exchange",
  "geni-token-shape",
  "writer-key",
  "writer-bundle",
  "writer-access",
  "writer-finalize",
]);
const fail = () => {
  throw new Error("rejected");
};
const credential = (v) =>
  typeof v === "string" &&
  v.length > 0 &&
  v.length <= 16384 &&
  !/\s|[\x00-\x1f]/.test(v)
    ? v
    : fail();
const random = () =>
  Array.from(crypto.getRandomValues(new Uint8Array(32)), (x) =>
    x.toString(16).padStart(2, "0"),
  ).join("");
const digest = async (v) =>
  Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(v)),
    ),
    (x) => x.toString(16).padStart(2, "0"),
  ).join("");
const page = (body, status = 200, extra = {}) =>
  new Response(body, { status, headers: { ...secureHeaders, ...extra } });

function config(env) {
  const origin = new URL(env.CALLBACK_ORIGIN);
  if (
    origin.protocol !== "https:" ||
    origin.origin !== env.CALLBACK_ORIGIN ||
    !/^[1-9][0-9]{0,19}$/.test(env.ALLOWED_GITHUB_ID) ||
    !/^[a-f0-9]{64}$/.test(env.SESSION_SIGNING_KEY)
  )
    fail();
  for (const name of [
    "GENI_CLIENT_ID",
    "GENI_APP_SECRET",
    "GITHUB_WRITER",
    "GITHUB_LOGIN_CLIENT_ID",
    "GITHUB_LOGIN_CLIENT_SECRET",
  ])
    credential(env[name]);
  return {
    origin: origin.origin,
    redirect: origin.origin + "/callback",
    loginRedirect: origin.origin + "/login/callback",
  };
}

function cookieValue(request, name) {
  const items = (request.headers.get("Cookie") || "")
    .split(";")
    .map((x) => x.trim())
    .filter((x) => x.startsWith(name + "="));
  if (items.length !== 1) fail();
  return credential(items[0].slice(name.length + 1));
}
const cookieHeader = (name, value, age = 600) =>
  name +
  "=" +
  value +
  "; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=" +
  age;
const sessionKey = (env) => new TextEncoder().encode(env.SESSION_SIGNING_KEY);
async function identity(request, env, cfg) {
  const { payload } = await jwtVerify(
    cookieValue(request, SESSION_COOKIE),
    sessionKey(env),
    {
      algorithms: ["HS256"],
      issuer: cfg.origin,
      audience: "bootstrap-session",
      maxTokenAge: "10m",
      requiredClaims: ["exp", "iat", "sub", "jti"],
    },
  );
  if (
    payload.sub !== env.ALLOWED_GITHUB_ID ||
    !/^[a-f0-9]{64}$/.test(payload.jti)
  )
    fail();
  return payload.sub + ":" + payload.jti;
}
async function loginCallback(request, env, cfg, url, fetcher, diagnostic) {
  diagnostic.stage = "github-cookie";
  const cookie = cookieValue(request, LOGIN_COOKIE);
  if (!/^[a-f0-9]{64}$/.test(cookie)) fail();
  diagnostic.stage = "github-parameters";
  const code = callbackCode(url);
  diagnostic.stage = "github-state";
  const stored = await stateRequest(
    env,
    url.searchParams.get("state"),
    "consume",
    "github-login",
    await digest(cookie),
  );
  const verifier = stored.verifier;
  if (!/^[a-f0-9]{64}$/.test(verifier)) fail();
  diagnostic.stage = "github-exchange";
  const token = await responseJson(
    await fetcher("https://github.com/login/oauth/access_token", {
      method: "POST",
      redirect: "error",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        Accept: "application/json",
      },
      body: new URLSearchParams({
        client_id: env.GITHUB_LOGIN_CLIENT_ID,
        client_secret: env.GITHUB_LOGIN_CLIENT_SECRET,
        code,
        redirect_uri: cfg.loginRedirect,
        code_verifier: verifier,
      }),
    }),
  );
  diagnostic.stage = "github-token-shape";
  credential(token.access_token);
  // This dedicated app requests no scopes. Refuse inherited or unexpected grants.
  let user;
  try {
    if (
      token.scope !== "" ||
      token.token_type !== "bearer" ||
      token.refresh_token
    )
      fail();
    diagnostic.stage = "github-user";
    user = await responseJson(
      await fetcher("https://api.github.com/user", {
        redirect: "error",
        headers: {
          Authorization: "Bearer " + token.access_token,
          Accept: "application/vnd.github+json",
          "User-Agent": "oauth-bootstrap",
        },
      }),
    );
  } finally {
    // Revoke the transient identity token. Never persist it or refresh it.
    const previousStage = diagnostic.stage;
    diagnostic.stage = "github-revoke";
    const revoked = await fetcher(
      "https://api.github.com/applications/" +
        env.GITHUB_LOGIN_CLIENT_ID +
        "/token",
      {
        method: "DELETE",
        redirect: "error",
        headers: {
          Authorization:
            "Basic " +
            btoa(
              env.GITHUB_LOGIN_CLIENT_ID + ":" + env.GITHUB_LOGIN_CLIENT_SECRET,
            ),
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "User-Agent": "oauth-bootstrap",
        },
        body: JSON.stringify({ access_token: token.access_token }),
      },
    );
    if (revoked.status !== 204) fail();
    diagnostic.stage = previousStage;
  }
  diagnostic.stage = "github-identity";
  if (
    !Number.isSafeInteger(user.id) ||
    String(user.id) !== env.ALLOWED_GITHUB_ID ||
    user.type !== "User"
  )
    fail();
  diagnostic.stage = "github-session";
  const session = await new SignJWT({})
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setIssuer(cfg.origin)
    .setAudience("bootstrap-session")
    .setSubject(String(user.id))
    .setJti(random())
    .setIssuedAt()
    .setExpirationTime("10m")
    .sign(sessionKey(env));
  const response = page("", 303, { location: cfg.origin + "/" });
  response.headers.append("set-cookie", cookieHeader(SESSION_COOKIE, session));
  response.headers.append("set-cookie", cookieHeader(LOGIN_COOKIE, "", 0));
  return response;
}
function callbackCode(url) {
  if (
    url.searchParams.getAll("state").length !== 1 ||
    url.searchParams.getAll("code").length !== 1 ||
    url.searchParams.has("error") ||
    url.searchParams.has("status")
  )
    fail();
  return credential(url.searchParams.get("code"));
}

async function responseJson(response) {
  if (!response.ok) fail();
  const raw = await response.text();
  if (raw.length > 65536) fail();
  const data = JSON.parse(raw);
  if (!data || typeof data !== "object" || Array.isArray(data) || data.error)
    fail();
  return data;
}

async function writeSecret(name, value, env, fetcher, diagnostic, writeStage) {
  diagnostic.stage = "writer-key";
  if (!["GENI_OAUTH_REFRESH_BUNDLE", "GENI_ACCESS_TOKEN"].includes(name))
    fail();
  const headers = {
    Authorization: "Bearer " + env.GITHUB_WRITER,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "oauth-bootstrap",
  };
  const key = await responseJson(
    await fetcher(GH + "/public-key", { headers, redirect: "error" }),
  );
  const rawKey = Uint8Array.from(atob(key.key), (c) => c.charCodeAt(0));
  if (rawKey.length !== 32) fail();
  const cipher = sealedbox.seal(new TextEncoder().encode(value), rawKey);
  const encrypted = btoa(String.fromCharCode(...cipher));
  diagnostic.stage = writeStage;
  const response = await fetcher(GH + "/" + name, {
    method: "PUT",
    headers,
    redirect: "error",
    body: JSON.stringify({ key_id: key.key_id, encrypted_value: encrypted }),
  });
  if (![201, 204].includes(response.status)) fail();
}

export class OneTimeState {
  constructor(state) {
    this.state = state;
  }
  async fetch(request) {
    const data = await request.json();
    const now = Date.now();
    if (new URL(request.url).pathname === "/issue") {
      if (
        typeof data.subject !== "string" ||
        !data.subject ||
        data.subject.length > 128 ||
        (data.payload?.verifier !== undefined &&
          !/^[a-f0-9]{64}$/.test(data.payload.verifier)) ||
        !/^[a-f0-9]{64}$/.test(data.binding)
      )
        fail();
      const accepted = await this.state.storage.transaction(async (txn) => {
        if (await txn.get("entry")) return false;
        await txn.put("entry", {
          subject: data.subject,
          binding: data.binding,
          expires: now + 600000,
          payload: data.payload || {},
        });
        return true;
      });
      await this.state.storage.setAlarm(now + 600000);
      return new Response("", { status: accepted ? 201 : 409 });
    }
    if (new URL(request.url).pathname === "/consume") {
      const accepted = await this.state.storage.transaction(async (txn) => {
        const item = await txn.get("entry");
        if (
          !item ||
          item.expires < now ||
          item.subject !== data.subject ||
          item.binding !== data.binding
        )
          return false;
        await txn.delete("entry");
        return item.payload;
      });
      return accepted
        ? Response.json(accepted)
        : new Response(null, { status: 403 });
    }
    return new Response("", { status: 404 });
  }
  async alarm() {
    await this.state.storage.deleteAll();
  }
}

async function stateRequest(
  env,
  nonce,
  action,
  subject,
  binding,
  payload = {},
) {
  if (!/^[a-f0-9]{64}$/.test(nonce)) fail();
  const stub = env.OAUTH_STATES.get(env.OAUTH_STATES.idFromName(nonce));
  const r = await stub.fetch("https://state.invalid/" + action, {
    method: "POST",
    body: JSON.stringify({ subject, binding, payload }),
  });
  if (!r.ok) fail();
  return action === "consume" ? await r.json() : undefined;
}

// Dependency injection is for offline tests; exported handler always uses real verification.
export async function handle(request, env, deps = { fetcher: fetch }) {
  const diagnostic = { stage: "setup" };
  try {
    const cfg = config(env);
    const url = new URL(request.url);
    if (url.origin !== cfg.origin) fail();
    if (request.method === "GET" && url.pathname === "/login/callback")
      return await loginCallback(
        request,
        env,
        cfg,
        url,
        deps.fetcher,
        diagnostic,
      );
    if (request.method === "POST" && url.pathname === "/login") {
      diagnostic.stage = "github-origin";
      if (request.headers.get("Origin") !== cfg.origin) fail();
      const nonce = random(),
        binding = random(),
        verifier = random();
      diagnostic.stage = "github-state-issue";
      await stateRequest(
        env,
        nonce,
        "issue",
        "github-login",
        await digest(binding),
        { verifier },
      );
      const hash = await crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(verifier),
      );
      const challenge = btoa(String.fromCharCode(...new Uint8Array(hash)))
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replace(/=+$/, "");
      const target = new URL("https://github.com/login/oauth/authorize");
      target.search = new URLSearchParams({
        client_id: env.GITHUB_LOGIN_CLIENT_ID,
        redirect_uri: cfg.loginRedirect,
        scope: "",
        state: nonce,
        code_challenge: challenge,
        code_challenge_method: "S256",
        allow_signup: "false",
        prompt: "select_account",
      });
      return page("", 303, {
        location: target.href,
        "set-cookie": cookieHeader(LOGIN_COOKIE, binding),
      });
    }
    diagnostic.stage = "geni-session";
    let subject;
    try {
      subject = await identity(request, env, cfg);
    } catch {
      if (request.method !== "GET" || url.pathname !== "/" || url.search)
        fail();
      return page(
        '<h1>Identity check</h1><p>Sign in at GitHub using the approved account. No password or 2FA is collected here.</p><form method="post" action="/login"><button>Sign in with GitHub</button></form>',
        200,
        {
          "set-cookie": cookieHeader(SESSION_COOKIE, "", 0),
          "referrer-policy": "strict-origin",
        },
      );
    }
    if (request.method === "GET" && url.pathname === "/" && !url.search) {
      return page(
        '<h1>Connect OAuth</h1><p>Confirm the correct Geni account in your own browser. Login and 2FA stay with Geni. No family data is read here.</p><form method="post" action="/start"><button>Connect to Geni</button></form>',
        200,
        { "referrer-policy": "strict-origin" },
      );
    }
    if (request.method === "POST" && url.pathname === "/start") {
      diagnostic.stage = "geni-origin";
      if (request.headers.get("Origin") !== cfg.origin) fail();
      const nonce = random();
      const cookie = random();
      diagnostic.stage = "geni-state-issue";
      await stateRequest(env, nonce, "issue", subject, await digest(cookie));
      const target = new URL(GENI + "authorize");
      target.search = new URLSearchParams({
        client_id: env.GENI_CLIENT_ID,
        response_type: "code",
        redirect_uri: cfg.redirect,
        state: nonce,
      });
      return page("", 303, {
        location: target.href,
        "set-cookie":
          COOKIE +
          "=" +
          cookie +
          "; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=600",
      });
    }
    if (request.method === "GET" && url.pathname === "/callback") {
      diagnostic.stage = "geni-parameters";
      const cookies = (request.headers.get("Cookie") || "")
        .split(";")
        .map((x) => x.trim())
        .filter((x) => x.startsWith(COOKIE + "="));
      if (
        cookies.length !== 1 ||
        url.searchParams.getAll("state").length !== 1 ||
        url.searchParams.getAll("code").length !== 1 ||
        url.searchParams.has("error") ||
        url.searchParams.has("status")
      )
        fail();
      const cookie = cookies[0].slice(COOKIE.length + 1);
      if (!/^[a-f0-9]{64}$/.test(cookie)) fail();
      const code = credential(url.searchParams.get("code"));
      diagnostic.stage = "geni-state";
      await stateRequest(
        env,
        url.searchParams.get("state"),
        "consume",
        subject,
        await digest(cookie),
      );
      diagnostic.stage = "geni-exchange";
      const token = await responseJson(
        await deps.fetcher(GENI + "request_token", {
          method: "POST",
          redirect: "error",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            Accept: "application/json",
          },
          body: new URLSearchParams({
            client_id: env.GENI_CLIENT_ID,
            client_secret: env.GENI_APP_SECRET,
            redirect_uri: cfg.redirect,
            code,
            grant_type: "authorization_code",
          }),
        }),
      );
      diagnostic.stage = "geni-token-shape";
      credential(token.access_token);
      credential(token.refresh_token);
      if (!Number.isSafeInteger(token.expires_in) || token.expires_in <= 0)
        fail();
      const bundle = {
        schema: 1,
        client_id: env.GENI_CLIENT_ID,
        client_secret: env.GENI_APP_SECRET,
        redirect_uri: cfg.redirect,
        refresh_token: token.refresh_token,
        pending_access_token: token.access_token,
        pending_expires_at: Math.floor(Date.now() / 1000) + token.expires_in,
      };
      await writeSecret(
        "GENI_OAUTH_REFRESH_BUNDLE",
        JSON.stringify(bundle),
        env,
        deps.fetcher,
        diagnostic,
        "writer-bundle",
      );
      await writeSecret(
        "GENI_ACCESS_TOKEN",
        token.access_token,
        env,
        deps.fetcher,
        diagnostic,
        "writer-access",
      );
      delete bundle.pending_access_token;
      delete bundle.pending_expires_at;
      await writeSecret(
        "GENI_OAUTH_REFRESH_BUNDLE",
        JSON.stringify(bundle),
        env,
        deps.fetcher,
        diagnostic,
        "writer-finalize",
      );
      return page("", 303, {
        location: cfg.origin + "/complete",
        "set-cookie":
          COOKIE + "=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0",
      });
    }
    if (request.method === "GET" && url.pathname === "/complete")
      return page(
        "<h1>Authorization saved</h1><p>Next: a new human-approved plan. This page does not confirm account identity or upload safety.</p>",
      );
    return page("Not found", 404);
  } catch {
    return page(
      "Stopped. No credentials displayed. Check setup; do not share the address or retry blindly. Stage: " +
        (STAGES.has(diagnostic.stage) ? diagnostic.stage : "setup") +
        ".",
      400,
    );
  }
}
export default { fetch: (request, env) => handle(request, env) };
