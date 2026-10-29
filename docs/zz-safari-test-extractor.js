// Run only as a user-created Safari Share Sheet Shortcut.
// Reads this Geni success URL only. No API, page-content or network access.
(function () {
  "use strict";
  const u = new URL(window.location.href);
  if (u.protocol !== "https:" || u.hostname !== "reihlinstinct.github.io" ||
      u.port !== "" || u.username !== "" || u.password !== "" ||
      u.pathname !== "/geni-uploader/zz-safari-test.html") {
    throw new Error("Stop: not the expected Geni success page.");
  }
  // Reject even a bare query delimiter; only the fragment-only route is supported.
  if (u.href.split("#", 1)[0].includes("?")) {
    throw new Error("Stop: unexpected query fields. Do not authorize again yet.");
  }
  const fragment = u.hash.slice(1);
  if (!fragment || fragment.startsWith("?")) {
    throw new Error("Stop: malformed return fields.");
  }
  const p = new Map();
  const allowed = new Set(["access_token", "expires_in", "token_type", "scope", "state"]);
  for (const segment of fragment.split("&")) {
    const equal = segment.indexOf("=");
    if (!segment || equal < 1) {
      throw new Error("Stop: malformed return fields.");
    }
    let key, value;
    try {
      key = decodeURIComponent(segment.slice(0, equal).replace(/\+/g, " "));
      value = decodeURIComponent(segment.slice(equal + 1).replace(/\+/g, " "));
    } catch (_) {
      throw new Error("Stop: malformed return fields.");
    }
    if (!allowed.has(key) || p.has(key)) {
      throw new Error("Stop: unexpected or duplicate return fields.");
    }
    p.set(key, value);
  }
  const token = p.get("access_token");
  // Supported subset only, not a verified vendor token-format specification.
  if (typeof token !== "string" || !/^[A-Za-z0-9._~+\/-]{20,4096}$/.test(token)) {
    throw new Error("Stop: no single supported access token returned.");
  }
  // Token is never printed, shown in an alert, saved or sent by this script.
  // URL clearing is not proof that browser history or page scripts never saw it.
  try {
    window.history.replaceState(null, "", u.pathname);
  } catch (_) {
    throw new Error("Stop: could not clear the success URL.");
  }
  completion(token);
}());
