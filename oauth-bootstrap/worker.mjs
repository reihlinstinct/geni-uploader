import { jwtVerify, createRemoteJWKSet } from "jose";
import sodium from "libsodium-wrappers";

const GENI = "https://www.geni.com/platform/oauth/";
const GH =
  "https://api.github.com/repos/reihlinstinct/geni-uploader/actions/secrets";
const COOKIE = "__Host-oauth-bind";
const secureHeaders = {
  "cache-control": "no-store",
  "referrer-policy": "no-referrer",
  "content-security-policy":
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
  "content-type": "text/html; charset=utf-8",
  "x-content-type-options": "nosniff",
};
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
  const team = new URL(env.ACCESS_TEAM);
  if (
    origin.protocol !== "https:" ||
    origin.origin !== env.CALLBACK_ORIGIN ||
    team.protocol !== "https:" ||
    !team.hostname.endsWith(".cloudflareaccess.com") ||
    team.origin !== env.ACCESS_TEAM ||
    !env.ACCESS_AUD ||
    !env.ALLOWED_EMAIL
  )
    fail();
  credential(env.GENI_CLIENT_ID);
  credential(env.GENI_APP_SECRET);
  credential(env.GITHUB_WRITER);
  return {
    origin: origin.origin,
    redirect: origin.origin + "/callback",
    team: team.origin,
  };
}

async function identity(request, env, cfg) {
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) fail();
  const keys = createRemoteJWKSet(new URL(cfg.team + "/cdn-cgi/access/certs"));
  return verifyIdentityToken(token, env, cfg, keys);
}

export async function verifyIdentityToken(token, env, cfg, keys) {
  const { payload } = await jwtVerify(token, keys, {
    issuer: cfg.team,
    audience: env.ACCESS_AUD,
    algorithms: ["RS256"],
  });
  if (
    payload.email !== env.ALLOWED_EMAIL ||
    typeof payload.sub !== "string" ||
    !payload.sub
  )
    fail();
  return payload.sub;
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

async function writeSecret(name, value, env, fetcher) {
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
  await sodium.ready;
  const encrypted = sodium.to_base64(
    sodium.crypto_box_seal(
      new TextEncoder().encode(value),
      sodium.from_base64(key.key, sodium.base64_variants.ORIGINAL),
    ),
    sodium.base64_variants.ORIGINAL,
  );
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
        !/^[a-f0-9]{64}$/.test(data.binding)
      )
        fail();
      const accepted = await this.state.storage.transaction(async (txn) => {
        if (await txn.get("entry")) return false;
        await txn.put("entry", {
          subject: data.subject,
          binding: data.binding,
          expires: now + 300000,
        });
        return true;
      });
      await this.state.storage.setAlarm(now + 300000);
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
        return true;
      });
      return new Response(null, { status: accepted ? 204 : 403 });
    }
    return new Response("", { status: 404 });
  }
  async alarm() {
    await this.state.storage.deleteAll();
  }
}

async function stateRequest(env, nonce, action, subject, binding) {
  if (!/^[a-f0-9]{64}$/.test(nonce)) fail();
  const stub = env.OAUTH_STATES.get(env.OAUTH_STATES.idFromName(nonce));
  const r = await stub.fetch("https://state.invalid/" + action, {
    method: "POST",
    body: JSON.stringify({ subject, binding }),
  });
  if (!r.ok) fail();
}

// Dependency injection is for offline tests; exported handler always uses real verification.
export async function handle(
  request,
  env,
  deps = { verify: identity, fetcher: fetch },
) {
  try {
    const cfg = config(env);
    const url = new URL(request.url);
    if (url.origin !== cfg.origin) fail();
    const subject = await deps.verify(request, env, cfg);
    if (request.method === "GET" && url.pathname === "/") {
      return page(
        '<h1>Connect OAuth</h1><p>Confirm the correct Geni account in your own browser. Login and 2FA stay with Geni. No family data is read here.</p><form method="post" action="/start"><button>Connect to Geni</button></form>',
      );
    }
    if (request.method === "POST" && url.pathname === "/start") {
      if (request.headers.get("Origin") !== cfg.origin) fail();
      const nonce = random();
      const cookie = random();
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
          "; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=300",
      });
    }
    if (request.method === "GET" && url.pathname === "/callback") {
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
      await stateRequest(
        env,
        url.searchParams.get("state"),
        "consume",
        subject,
        await digest(cookie),
      );
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
      );
      await writeSecret(
        "GENI_ACCESS_TOKEN",
        token.access_token,
        env,
        deps.fetcher,
      );
      delete bundle.pending_access_token;
      delete bundle.pending_expires_at;
      await writeSecret(
        "GENI_OAUTH_REFRESH_BUNDLE",
        JSON.stringify(bundle),
        env,
        deps.fetcher,
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
      "Stopped. No credentials displayed. Check setup; do not share the address or retry blindly.",
      400,
    );
  }
}
export default { fetch: (request, env) => handle(request, env) };
