#!/usr/bin/env python3
"""User-run Geni source upload tool. See DESIGN.md and CONTRACTS.md.

Safety model:
- Every network call passes through execute(), which hard-enforces ALLOWLIST
  on (method, kind) pairs, whatever GENI_API_BASE points at.
- GETs retry on transient errors. POSTs are never blindly retried.
- A write-ahead journal is fsynced and pushed BEFORE every mutation. The
  acknowledged object ID and each tag result are checkpointed BEFORE readback.
  Push failure stops. A create intent without an ID requires manual review.
- Acknowledged tags resume through GET only; only not-yet-attempted tags are
  sent. Each target identity is verified. Interrupted tags/identities and429
  block further work until explicit reviewed reconciliation.
- Readback allows twelve30-second intervals, paced by the same rate limiter.
  A pending journal survives lag; an absent listing NEVER triggers recreation.
- Legacy status entries keep their fail-closed/manual reconciliation semantics.
- State file writes are atomic (temp + rename); a flock on the state dir
  refuses concurrent runs (exit 6).
- Logs never contain tokens, headers, payloads, or personal names/titles
  (items are logged as short hashes).
"""
import argparse
import base64
import fcntl
import hashlib
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

# GENI_API_BASE overrides the API root for end-to-end tests against a local
# fake server ONLY: it requires GENI_UPLOAD_E2E=1 and a loopback URL, so an
# untrusted repo or env can never redirect real calls or a real token.
_PROD_API = "https://www.geni.com/api"
API_BASE = os.environ.get("GENI_API_BASE", _PROD_API)
if API_BASE != _PROD_API:
    import urllib.parse as _up
    _h = _up.urlparse(API_BASE).hostname or ""
    if os.environ.get("GENI_UPLOAD_E2E") != "1" or \
            _h not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("refused: GENI_API_BASE may only point at a loopback "
                         "test server with GENI_UPLOAD_E2E=1")
elif os.environ.get("GENI_UPLOAD_E2E") == "1":
    raise SystemExit("refused: GENI_UPLOAD_E2E=1 with the production API base")
ALLOWLIST = {
    ("GET", "user"),  # whoami diagnostic: token-context probe (geni-uploader#11)
    ("GET", "user_managed_profiles"),  # contrast diagnostic: served-id probe (geni-uploader#11)
    ("GET", "profile"), ("GET", "profile_documents"), ("GET", "profile_photos"),
    ("POST", "document_add"), ("POST", "photo_add"),
    ("POST", "document_tag"), ("POST", "photo_tag"),
}
STATE_DEFAULT = "geni-upload-state.json"


def _sleep(seconds):
    # E2E mode (loopback fake server only) compresses backoff sleeps.
    time.sleep(0.01 if os.environ.get("GENI_UPLOAD_E2E") == "1" else seconds)
STATUS_NAME = "upload-status.yaml"


class ApiError(Exception):
    pass


class ThrottledError(ApiError):
    """HTTP 429. Distinct type so no retry/continue path can swallow it:
    the standing rule is STOP on throttle; any retry is a fresh,
    explicitly authorized decision by the operator."""


class UncertainWrite(ApiError):
    """A mutating POST was sent but its outcome is unknown. Exit code 3."""


class VerificationError(ApiError):
    """POST was acknowledged but the GET readback did not confirm the
    object linked to the profile. Exit code 4."""


def label(item):
    """Log-safe item label: no personal names/titles, just a short hash."""
    return "item#" + hashlib.sha1(item["title"].encode("utf-8")).hexdigest()[:8]


class RunLog:
    """Privacy-safe diagnostic log: timestamps, steps, ids, HTTP statuses,
    exit codes. NEVER logs tokens, Authorization headers, file contents or
    API response payloads. Default file sits next to the state file so it
    survives on the same durable mount; share it when reporting a problem."""
    def __init__(self, path=None):
        # Held open for the whole run and closed in close(): a context
        # manager cannot span the run loop.
        self.f = open(path, "a", encoding="utf-8") if path else None  # noqa: SIM115

    def log(self, msg):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
        print(line)
        if self.f:
            self.f.write(line + "\n")
            self.f.flush()

    def close(self):
        if self.f:
            self.f.close()


def load_manifest(path):
    import yaml  # PyYAML, already a repo dependency
    try:
        with open(path, encoding="utf-8") as f:
            m = yaml.safe_load(f)
    except FileNotFoundError:
        raise ApiError(
            f"manifest not found: {path} - check the path, and that "
            "GENI_UPLOAD_REF points at the branch containing the package "
            "(the default branch may not carry it)")
    if not isinstance(m, dict) or not isinstance(m.get("targets"), list) or not m["targets"]:
        raise ApiError("manifest must define a non-empty 'targets' list")
    pids = {str(t.get("profile_id")) for t in m["targets"]}
    for i, t in enumerate(m["targets"]):
        if not t.get("profile_id") or not t.get("expect_name"):
            raise ApiError(f"target #{i}: profile_id and expect_name are required")
        if len(str(t["expect_name"]).split()) < 2:
            raise ApiError(f"target #{i}: expect_name must be a distinctive full name, "
                           "not a bare first name")
        for kind in ("documents", "photos"):
            for j, item in enumerate(t.get(kind) or []):
                if not item.get("title"):
                    raise ApiError(f"target #{i} {kind}[{j}]: title is required")
                if kind == "documents" and not item.get("source_url") and not item.get("file"):
                    raise ApiError(f"target #{i} documents[{j}]: source_url or file required "
                                   "(idempotency anchor)")
                if kind == "photos" and not item.get("file"):
                    raise ApiError(f"target #{i} photos[{j}]: file is required")
                if item.get("file"):
                    # Containment: the repo is untrusted DATA; a manifest must
                    # never exfiltrate files outside its own tree (tokens,
                    # /run mounts, symlink targets).
                    base_dir = os.path.realpath(os.path.dirname(
                        os.path.abspath(path)))
                    real = os.path.realpath(item["file"]
                                            if os.path.isabs(item["file"])
                                            else os.path.join(os.path.dirname(
                                                os.path.abspath(path)),
                                                item["file"]))
                    if not (real == base_dir or
                            real.startswith(base_dir + os.sep)):
                        raise ApiError(f"target #{i} {kind}[{j}]: file escapes "
                                       f"the manifest directory: {item['file']}")
                    if not os.path.isfile(real):
                        raise ApiError(f"target #{i} {kind}[{j}]: file not found: "
                                       f"{item['file']}")
                    item["file"] = real
                extra = item.get("also_tag")
                if extra is not None:
                    if not isinstance(extra, list) or not extra or \
                            any(not isinstance(x, (str, int)) for x in extra):
                        raise ApiError(f"target #{i} {kind}[{j}]: also_tag must be a "
                                       "non-empty list of profile ids from this manifest")
                    if len({str(x) for x in extra}) != len(extra):
                        raise ApiError(f"target #{i} {kind}[{j}]: also_tag contains "
                                       "duplicates")
                    for x in extra:
                        xs = str(x)
                        if xs == str(t["profile_id"]):
                            raise ApiError(f"target #{i} {kind}[{j}]: also_tag must not "
                                           "repeat the item's own profile_id")
                        if xs not in pids:
                            raise ApiError(f"target #{i} {kind}[{j}]: also_tag id {xs} is "
                                           "not a target in this manifest (the identity "
                                           "guard needs its expect_name)")
    return m


def name_matches(display_name, expect_name):
    """Every token of the expected distinctive name must appear as a substring
    of the display name (case-insensitive). Stronger than one bare first name."""
    dn = (display_name or "").lower()
    return all(tok.lower() in dn for tok in str(expect_name).split())


# Client-side pacing. Geni paces via X-API-Rate-Limit / X-API-Rate-Remaining /
# X-API-Rate-Window response headers (public client evidence; defaults are a
# conservative assumption, not a documented guarantee). Before headers are
# seen, assume 1 request per 10 seconds. A 429 sets retry_after from the
# window; short fixed backoffs inside the window only re-trip the limit.
_RATE = {"min_interval": 10.0, "last": 0.0, "retry_after": 0.0}


def _pace():
    now = time.time()
    wait = max(_RATE["min_interval"] - (now - _RATE["last"]),
               _RATE["retry_after"] - now, 0.0)
    if wait > 0:
        _sleep(wait)
    _RATE["last"] = time.time()


def _update_rate(headers):
    """Adapt pacing from Geni's rate headers, when present."""
    if headers is None:
        return
    try:
        lim = headers.get("X-API-Rate-Limit")
        win = headers.get("X-API-Rate-Window")
        rem = headers.get("X-API-Rate-Remaining")
        if lim and win and float(lim) > 0:
            _RATE["min_interval"] = max(float(win) / float(lim), 1.0)
        if rem is not None and int(rem) <= 0 and win:
            _RATE["retry_after"] = time.time() + float(win)
    except (TypeError, ValueError):
        pass  # malformed headers: keep the conservative defaults


def execute(method, kind, url, token=None, data=None):
    """Single allowlisted call. GET: retries with backoff.
    POST: no blind retry — uncertain outcomes raise UncertainWrite."""
    if (method, kind) not in ALLOWLIST:
        raise ApiError(f"non-allowlisted call refused: {method} {kind}")
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    attempts = 3 if method == "GET" else 1
    for attempt in range(attempts):
        _pace()
        try:
            with urllib.request.urlopen(req, data=body, timeout=60) as r:
                _update_rate(getattr(r, "headers", None))
                try:
                    return json.loads(r.read().decode())
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    if method == "POST":
                        raise UncertainWrite(f"POST {url}: response not parseable "
                                             "after send; object may or may not exist")
                    raise ApiError(f"{method} {url}: invalid JSON response: {e}")
        except urllib.error.HTTPError as e:
            if e.headers:
                _update_rate(e.headers)
            if e.code == 429:
                # Throttled: record the server-declared cooldown for any
                # future authorized call, but STOP now - never auto-retry.
                # The user's standing rule is stop-on-throttle; a retry is
                # a fresh, explicitly authorized decision.
                try:
                    win = float(e.headers.get("X-API-Rate-Window"))                         if e.headers and e.headers.get("X-API-Rate-Window")                         else 15.0
                except (TypeError, ValueError):
                    win = 15.0
                _RATE["retry_after"] = max(_RATE["retry_after"],
                                           time.time() + win)
                raise ThrottledError(
                    f"{method} {url} -> HTTP 429 rate limit exceeded; "
                    "STOPPING (no automatic retry). Wait for the rate "
                    "window and re-run only as a fresh, deliberate attempt")
            if method == "GET" and e.code in (500, 502, 503) and attempt < attempts - 1:
                _sleep(2 ** attempt * 2)
                continue
            if method == "POST" and e.code >= 500:
                raise UncertainWrite(f"POST {url} -> HTTP {e.code} after send; "
                                     "object may or may not exist")
            raise ApiError(f"{method} {url} -> HTTP {e.code}: {e.read()[:200]!r}")
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                http.client.HTTPException) as e:
            if method == "GET" and attempt < attempts - 1:
                _sleep(2 ** attempt * 2)
                continue
            if method == "POST":
                raise UncertainWrite(f"POST {url}: network error after send ({e}); "
                                     "object may or may not exist")
            raise ApiError(f"GET {url}: network error: {e}")
    raise ApiError(f"{method} {url}: retries exhausted")


def get_token(args):
    tok = os.environ.get("GENI_ACCESS_TOKEN")
    if not tok and getattr(args, "token_file", None):
        with open(os.path.expanduser(args.token_file), encoding="utf-8") as f:
            tok = f.read().strip()
    return tok


def verify_linkage(token, pid, kind, expect_anchor, log):
    """GET readback after a mutation: poll the profile listing until the
    anchor appears (object exists AND is tagged to this profile)."""
    budget = 13  # immediate read + twelve 30s intervals; rate limiter still applies
    for i in range(budget):
        listing = list_tagged(token, pid, kind)
        if expect_anchor and expect_anchor[0] == "object-id":
            ids = sum(1 for x in listing or [] if x and x[0] == "object-id")
            log.log(f"    readback shape: available={listing is not None} object_ids={ids}")
        if listing is not None and expect_anchor in listing:
            return True
        log.log(f"    readback {i + 1}/{budget}: not yet visible in {kind} listing")
        if i < budget - 1:
            _sleep(30)
    return False


def profile_name_surface(p):
    """Every canonical name field of ONE profile: display_name is only
    first+last in Geni's schema (public client fixtures: middle_name,
    maiden_name, nicknames and per-language names are separate fields),
    so matching display_name alone false-rejects a person whose API
    display shows only the married name while the manifest's expected
    name includes the birth name. Still strict: every expected token
    must appear in THIS profile's own recorded names."""
    fields = [str(p.get(k)) for k in
              ("display_name", "name", "first_name", "middle_name",
               "last_name", "maiden_name")
              if isinstance(p.get(k), str)]
    for n in p.get("nicknames") or []:
        fields.append(str(n))
    for names in (p.get("names") or {}).values():
        if isinstance(names, dict):
            for v in names.values():
                if isinstance(v, str):
                    fields.append(v)
                elif isinstance(v, dict):
                    fields.extend(str(x) for x in v.values()
                                  if isinstance(x, str))
    return " ".join(fields)



def observed_name_fields(p):
    """Compact {field: value} map of ONLY the name fields
    profile_name_surface reads, for the mismatch diagnostic. The plan
    output carrying it is encrypted to the private log repository by the
    Action (and stays on the user's own terminal in local runs); the
    public Actions log never sees it. Names only - never the whole
    profile."""
    out = {}
    for k in ("display_name", "name", "first_name", "middle_name",
              "last_name", "maiden_name"):
        if isinstance(p.get(k), str):
            out[k] = p[k]
    if p.get("nicknames"):
        out["nicknames"] = [str(n) for n in p["nicknames"]]
    if p.get("names") and isinstance(p.get("names"), dict):
        out["names"] = p["names"]
    return json.dumps(out, ensure_ascii=False, sort_keys=True)


def observed_response_keys(p):
    """Structural shape of the profile response - never values.
    Top-level key NAMES plus, when a 'results' envelope is present, its
    TYPE and LENGTH only. Distinguishes an error envelope, an empty
    results set (id not resolving / not visible), a populated results
    wrapper (parser bug), and an unexpected profile schema - without
    carrying any personal data even into the encrypted log."""
    if not isinstance(p, dict):
        return json.dumps({"_type": type(p).__name__})
    out = {"keys": sorted(str(k) for k in p)}
    r = p.get("results")
    if r is not None:
        out["results_type"] = type(r).__name__
        if isinstance(r, (list, dict)):
            out["results_len"] = len(r)
    return json.dumps(out, sort_keys=True)


def profile_node_number(value):
    """Canonical numeric portion of a served API profile node, never a GUID."""
    node = str(value or "").removeprefix("profile-")
    if not node.isdigit():
        raise ApiError("invalid served profile node ID")
    return node


def verify_profile(token, pid, expect_name):
    """Verify a manifest target; return (node_id, display_name).

    Manifest profile_ids are website-URL numbers. Run 11 (pguid mode)
    proved for the manifest's three targets that such numbers can be
    GUIDS rather than node ids: the `profile-<N>` form then silently
    serves an empty result, while `profile-g<N>` serves the profile
    carrying a distinct node id. Resolution is fail-closed and never
    conflates the two spaces:

    1. `profile-<pid>` (node-id form, pre-existing semantics): a served
       profile whose recorded names match expect_name resolves to pid
       itself; a served profile that does NOT match raises immediately
       (a name mismatch never falls through to a second identity
       space); an empty result or HTTP error falls through to the guid
       form.
    2. `profile-g<pid>` (guid form): resolves ONLY when the served guid
       EQUALS pid, the served node id is nonempty, and the same strict
       name guard passes - then the SERVED node id (not pid) is what
       later calls must use.
    Anything else raises: an unresolved target is never guessed.
    """
    try:
        p = execute("GET", "profile", f"{API_BASE}/profile-{pid}", token)
    except ThrottledError:
        raise  # stop-on-throttle: never fall through to another call
    except ApiError:
        p = None
    if isinstance(p, dict) and p.get("results") == []:
        p = None  # silent-empty envelope on guids (run 11 / pguid)
    if p:
        name = p.get("display_name") or ""
        if not name_matches(profile_name_surface(p), expect_name):
            raise ApiError(f"profile {pid}: no recorded name on the profile "
                           "matches the expected name - target SKIPPED "
                           f"(observed name fields: {observed_name_fields(p)}; "
                           f"response keys: {observed_response_keys(p)})")
        return pid, name
    g = execute("GET", "profile", f"{API_BASE}/profile-g{pid}", token)
    gobj = g
    if isinstance(gobj, dict) and isinstance(gobj.get("results"), list):
        gobj = gobj["results"][0] if gobj["results"] else {}
    if (isinstance(gobj, dict)
            and str(gobj.get("guid") or "") == pid
            and str(gobj.get("id") or "")
            and name_matches(profile_name_surface(gobj), expect_name)):
        return profile_node_number(gobj["id"]), gobj.get("display_name") or ""
    raise ApiError(f"profile {pid}: not served as a node id and not "
                   "resolvable as a guid (profile-g) with a matching "
                   "identity - target SKIPPED")


def list_tagged(token, pid, kind):
    """Set of idempotency anchors already tagged to the profile.
    Legacy anchors plus (object-id, typed kind, numeric id) for durable proof."""
    ek = "profile_documents" if kind == "documents" else "profile_photos"
    url = f"{API_BASE}/profile-{pid}/{kind}"
    items = []
    pages = 0
    try:
        while url and pages < 10:
            res = execute("GET", ek, url, token)
            rows = res.get("results") if isinstance(res, dict) else res
            if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
                raise ApiError("invalid profile source listing")
            items.extend(rows)
            links = [res.get(k) for k in ("next", "next_page") if res.get(k)] if isinstance(res, dict) else []
            if any(not isinstance(x, str) for x in links):
                raise ApiError("invalid listing pagination")
            if len(set(links)) > 1:
                raise ApiError("conflicting listing pagination")
            url = links[0] if links else None
            if url:
                if not isinstance(url, str):
                    raise ApiError("invalid listing pagination")
                url = urllib.parse.urljoin(f"{API_BASE}/profile-{pid}/{kind}", url)
                parsed = urllib.parse.urlsplit(url)
                allowed = urllib.parse.urlsplit(f"{API_BASE}/profile-{pid}/{kind}")
                if (parsed.scheme, parsed.netloc, parsed.path) != (allowed.scheme, allowed.netloc, allowed.path) or parsed.fragment:
                    raise ApiError("listing pagination changed endpoint")
            pages += 1
        if url:
            return None  # pagination incomplete: treat as unavailable
    except ThrottledError:
        raise  # never suppress rate limits as an unavailable photo listing
    except ApiError:
        if kind == "photos":
            return None  # listing unavailable: fall back to state file + warning
        raise
    out = set()
    for d in items:
        if isinstance(d, dict):
            out.add((d.get("title"), d.get("source_url")) if kind == "documents"
                    else (d.get("title"),))
            base = "document" if kind == "documents" else "photo"
            value = str(d.get("id") or "").removeprefix(base + "-")
            if value.isascii() and value.isdigit():
                out.add(("object-id", base, value))
    return out


def anchor(item, kind):
    return (item["title"], item.get("source_url")) if kind == "documents" else (item["title"],)


def upload_payload(item, kind):
    data = {"title": item["title"]}
    for k in ("description", "source_url", "labels", "date", "text"):
        if item.get(k):
            data[k] = str(item[k])
    if item.get("file"):
        with open(item["file"], "rb") as f:
            data["file"] = base64.b64encode(f.read()).decode()
        data["file_name"] = os.path.basename(item["file"])
        data["content_type"] = item.get("content_type",
                                        "image/jpeg" if kind == "photos"
                                        else "application/octet-stream")
    return data


def load_state(path):
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"uploaded": []}


def save_state(path, state):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def status_path(manifest_path):
    return os.path.join(os.path.dirname(os.path.abspath(manifest_path)), STATUS_NAME)


def load_status(manifest_path):
    """Repo-backed per-item completion record, written next to the manifest.
    Items recorded here are treated as done by every future run, anywhere."""
    import yaml
    path = status_path(manifest_path)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            d = yaml.safe_load(f)
        if isinstance(d, dict) and isinstance(d.get("items"), dict):
            return d
    return {"items": {}}


def save_status(manifest_path, status):
    import yaml
    path = status_path(manifest_path)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(status, f, allow_unicode=True, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def repo_sync(manifest_path, log):
    """Commit/push the journal. New mutations require a successful push."""
    try:
        cwd = os.path.dirname(os.path.abspath(manifest_path))
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                             capture_output=True, text=True, timeout=30, check=False)
        if top.returncode != 0:
            log.log("  repo sync: not inside a git repo; status kept in the "
                    "local file only")
            return None
        top = top.stdout.strip()
        rel = os.path.relpath(status_path(manifest_path), top)
        subprocess.run(["git", "add", "--", rel], cwd=top, check=True,
                       capture_output=True, timeout=30)
        changed = subprocess.run(["git", "diff", "--cached", "--quiet", "--", rel],
                                 cwd=top, check=False, timeout=30)
        if changed.returncode:
            subprocess.run(["git", "-c", "user.name=geni-upload (user-run)",
                            "-c", "user.email=geni-upload@localhost",
                            "commit", "-q", "-m", "geni-upload: checkpoint source progress"],
                           cwd=top, check=True, capture_output=True, timeout=30)
        push = subprocess.run(["git", "push"], cwd=top, capture_output=True,
                              text=True, timeout=120, check=False)
        if push.returncode != 0:
            log.log("  repo sync: PUSH FAILED (read-only token or remote moved); "
                    "STOP; pending journal must be reconciled before further writes")
            return False
        log.log("  repo sync: status committed and pushed")
        return True
    except (OSError, subprocess.SubprocessError) as e:
        log.log(f"  repo sync: skipped ({e})")
        return None


def preflight_state_writable(path):
    """Refuse to start `run` unless the state file's directory is writable.
    A state-save failure AFTER a live Geni write would break idempotency,
    so this check must pass BEFORE any mutation (and before any GET)."""
    d = os.path.dirname(os.path.abspath(path))
    try:
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".preflight")
    except OSError as e:
        raise ApiError(
            f"state directory {d!r} is not writable ({e}). Fix --state or its "
            "mount BEFORE uploading: a failed state save after a live write "
            "would lose the idempotency record.")
    os.close(fd)
    os.unlink(tmp)


def plan_summary(m):
    lines = []
    for t in m["targets"]:
        pid = str(t["profile_id"])
        lines.append(f"profile {pid} (expect {t['expect_name']!r}): "
                     f"GET profile, GET profile/documents, GET profile/photos, then "
                     f"{len(t.get('documents') or [])} document uploads + tags, "
                     f"{len(t.get('photos') or [])} photo uploads + tags")
    return lines



def diagnose_whoami(token):
    """Shape-only probe of GET /api/user (the token's authenticated context).

    Returns {key: type-name} for the top-level response object. Values are
    never read into the log, so the diagnostic cannot leak identity fields;
    presence/type of keys such as id/guid separates a user-context token
    from an app-context one (geni-uploader#11). Grounded semantics:
    dmalch/go-geni user/client.go GET api/user returns the authenticated
    user behind the OAuth token.
    """
    res = execute("GET", "user", f"{API_BASE}/user", token)
    if not isinstance(res, dict):
        return {"<non-dict response>": type(res).__name__}
    return {str(k): type(v).__name__ for k, v in res.items()}


def cmd_whoami(args):
    token = get_token(args)
    if not token:
        raise ApiError("whoami: no token available "
                       "(use --token-file or GENI_ACCESS_TOKEN)")
    shape = diagnose_whoami(token)
    print("whoami response shape (keys -> types; values redacted): "
          + json.dumps(shape, sort_keys=True))
    print("No writes performed.")
    return 0


def _profile_payload_shape(res):
    """Shape-only summary of one profile-endpoint payload.

    Keys, list lengths and presence booleans only - never values - so the
    diagnostic cannot leak identity fields (same contract as whoami).
    Handles both the documented envelope form ({"results": [...]}) and the
    bare single-object form observed live from per_page=1.
    """
    if not isinstance(res, dict):
        return {"top_type": type(res).__name__}
    out = {"keys": sorted(str(k) for k in res)}
    results = res.get("results")
    if isinstance(results, list):
        out["results_len"] = len(results)
        if results:
            out["all_items_nonempty_id_name"] = all(
                isinstance(it, dict) and bool(it.get("id")) and bool(it.get("name"))
                for it in results)
    else:
        out["bare_nonempty_id_name"] = bool(res.get("id")) and bool(res.get("name"))
    return out


def _extract_served_id(res):
    """Pull one served profile id VALUE into memory (never logged).

    Accepts both the envelope form and the bare single-object form.
    """
    if not isinstance(res, dict):
        return None
    results = res.get("results")
    if isinstance(results, list) and results:
        item = results[0]
        if isinstance(item, dict) and item.get("id"):
            return str(item["id"])
        return None
    if res.get("id"):
        return str(res["id"])
    return None


def cmd_contrast(args):
    """geni-uploader#11: minimal endpoint contrast diagnostic (read-only).

    Three paced reads through execute() (same 10s+ rate limiter, same 429
    abort), shape-only output, values never logged:
      1. GET user/managed-profiles?fields=id&per_page=1 - one id the token
         provably serves, held in memory only.
      2. GET profile-<that served id> - does the singular profile endpoint
         serve ANY profile for this token?
      3. GET profile?ids=<all manifest targets> - does the documented bulk
         form serve targets the singular form misses?
    The verdict separates "singular endpoint misses for this token" (2 misses)
    from "these targets invisible to this token" (2 serves, 3 misses) from
    "path-form specific" (2 misses, 3 serves).
    """
    m = load_manifest(args.manifest)
    token = get_token(args)
    if not token:
        raise ApiError("contrast: no token available "
                       "(use --token-file or GENI_ACCESS_TOKEN)")
    pids = [str(t["profile_id"]) for t in m["targets"]]
    print(f"contrast: read-only endpoint discriminator over "
          f"{len(pids)} manifest target(s) (shapes only, values redacted)")
    mp = execute("GET", "user_managed_profiles",
                 f"{API_BASE}/user/managed-profiles?fields=id&per_page=1",
                 token)
    print("managed-profiles fields=id per_page=1: "
          + json.dumps(_profile_payload_shape(mp), sort_keys=True))
    served = _extract_served_id(mp)
    if served is None:
        print("singular GET of a served id: SKIPPED "
              "(no served id extracted from managed-profiles)")
    else:
        good = execute("GET", "profile", f"{API_BASE}/profile-{served}", token)
        print("singular GET of a served id: "
              + json.dumps(_profile_payload_shape(good), sort_keys=True))
    # Literal commas: the documented ids= form is comma-separated
    ids = urllib.parse.quote(",".join(pids), safe=",")
    bulk = execute("GET", "profile", f"{API_BASE}/profile?ids={ids}", token)
    print("bulk ids= form for all manifest targets: "
          + json.dumps(_profile_payload_shape(bulk), sort_keys=True))
    print("No writes performed.")
    return 0


def cmd_plan(args):
    m = load_manifest(args.manifest)
    token = get_token(args)
    # No verdict up front: VERIFIED is decided only AFTER every profile GET
    # actually succeeded (a 401 must never print under a VERIFIED header).
    print("PLAN:")
    for line in plan_summary(m):
        print(" ", line)
    if not token:
        print("verification: SKIPPED - no token; nothing was checked against Geni")
        return 0
    total = len(m["targets"])
    failed = 0
    for t in m["targets"]:
        pid = str(t["profile_id"])
        try:
            node_id, name = verify_profile(token, pid, t["expect_name"])
            via = " (resolved via guid)" if node_id != pid else ""
            print(f"  profile {pid}: OK ({name}){via}")
            for kind in ("documents", "photos"):
                tagged = list_tagged(token, node_id, kind)
                if tagged is None:
                    print(f"    WARNING: {kind} listing unavailable; "
                          "idempotency relies on state file only")
                    continue
                for item in t.get(kind) or []:
                    if anchor(item, kind) in tagged:
                        print(f"    SKIP (already tagged): {item['title']}")
        except ThrottledError:
            raise  # throttle aborts the whole plan: no further requests
        except ApiError as e:
            failed += 1
            print(f"  profile {pid}: {e}")
    if failed:
        print(f"verification: FAILED - {failed} of {total} profile(s) not "
              "confirmed; resolve before `run` (no writes were attempted)")
        return 1
    print(f"verification: OK - all {total} profile(s) confirmed with Geni")
    print("No writes performed in plan mode.")
    return 0


def durable_upload(item, kind, base, add_kind, tag_kind, pid, node_id,
                   token, key, state, state_path, status, manifest_path,
                   log, sync_repo, targets_by_pid):
    """Write-ahead journal: a create or tag with an intent is NEVER replayed.

    Acknowledged operations resume through GET only. Only tags with no intent
    may be sent; identity checks apply on every run. Pending records are pushed
    before AND after each mutation. A failed push stops, never hides behind a
    disposable container's local state.
    """
    data = upload_payload(item, kind)
    extras = [str(x) for x in item.get("also_tag") or []]
    binding = hashlib.sha256(json.dumps(
        {"payload": data, "primary": pid, "extras": extras},
        sort_keys=True).encode()).hexdigest()
    rec = status["items"].get(key)
    if rec and rec.get("journal_version") == 1:
        if (rec.get("binding") != binding
                or profile_node_number(rec.get("primary_node")) != node_id):
            raise ApiError("pending source/target precondition changed; manual review required")
        # Accept only exactly equivalent legacy node representation.
        # Preserve every object ID and operation phase; never clear an intent.
        rec["primary_node"] = node_id
    else:
        rec = {"journal_version": 1, "status": "pending", "binding": binding,
               "primary_node": node_id, "object_id": None, "tags": {},
               "also_tagged": [], "also_tag_pending": extras[:]}
        status["items"][key] = rec

    def checkpoint():
        state.setdefault("pending", {})[key] = dict(rec)
        save_state(state_path, state)
        save_status(manifest_path, status)
        if sync_repo and repo_sync(manifest_path, log) is not True:
            raise ApiError("durable journal push failed; STOP before further mutations")

    if rec.get("blocked"):
        tags = rec.get("tags")
        oid = str(rec.get("object_id") or "")
        if (rec.get("reconcile_readback") is not True
                or rec.get("reason") != "interrupted target/tag"
                or rec.get("create_intent") is not True
                or not oid.isascii() or not oid.isdigit()
                or not isinstance(tags, dict) or pid not in tags
                or any(target not in [pid] + extras or not isinstance(tag, dict)
                       or tag.get("phase") not in ("acknowledged", "verified")
                       for target, tag in tags.items())):
            raise UncertainWrite("journal blocked; reviewed acknowledged-tag reconciliation required")
        # Proof phase is read-only. Do not edit phases or unblock incrementally.
        for target, tag in tags.items():
            if target == pid:
                served = node_id
            else:
                xt = targets_by_pid.get(target)
                if xt is None:
                    raise UncertainWrite("reconciliation target absent; block retained")
                served, _ = verify_profile(token, target, xt["expect_name"])
            if profile_node_number(tag.get("node")) != served:
                raise UncertainWrite("reconciliation target changed; block retained")
            if not verify_linkage(token, served, kind, ("object-id", base, oid), log):
                raise VerificationError("reconciliation tag not proven; block retained")
        rec.pop("blocked")
        rec.pop("reason")
        rec.pop("reconcile_readback")
        rec["status"] = "pending"
        checkpoint()  # failure stops BEFORE further service mutations
        log.log("  acknowledged-tag reconciliation proven by GET; journal checkpointed")

    if not rec.get("object_id"):
        if rec.get("create_intent"):
            raise UncertainWrite("source create has an unresolved intent; manual reconciliation required")
        rec["create_intent"] = True
        checkpoint()
        try:
            res = execute("POST", add_kind, f"{API_BASE}/{base}/add", token, data)
        except (ApiError, UncertainWrite):
            rec["status"] = "uncertain"
            checkpoint()
            raise
        oid = str(res.get("id") or "").removeprefix(base + "-")
        if not oid.isdigit():
            raise UncertainWrite("source add returned no valid object ID; intent preserved")
        rec["object_id"] = oid
        checkpoint()  # acknowledged object ID durable BEFORE primary tag/readback
        log.log(f"  upload acknowledged: {label(item)} -> {base}-{oid}")
    oid = rec["object_id"]
    if not str(oid).isdigit():
        raise ApiError("invalid journal object ID; manual review required")
    try:
        for target in [pid] + extras:
            if target == pid:
                served = node_id
            else:
                xt = targets_by_pid.get(target)
                if xt is None:
                    raise ApiError("extra target missing; manual review required")
                served, _ = verify_profile(token, target, xt["expect_name"])
            tag = rec["tags"].get(target)
            if tag and profile_node_number(tag.get("node")) != served:
                raise ApiError("journal target identity changed; manual review required")
            if tag:
                tag["node"] = served
            if not tag:
                tag = {"node": served, "phase": "intent"}
                rec["tags"][target] = tag
                checkpoint()  # never resend a tag if its response is lost
                execute("POST", tag_kind,
                        f"{API_BASE}/{base}-{oid}/tag/profile-{served}", token, {})
                tag["phase"] = "acknowledged"
                checkpoint()
            if not verify_linkage(token, served, kind, ("object-id", base, str(oid)), log):
                raise VerificationError("source tag not visible; durable pending journal retained; "
                                        "next run verifies only, never recreates or repeats this tag")
            tag["phase"] = "verified"
            rec["also_tagged"] = [x for x in extras
                                  if rec["tags"].get(x, {}).get("phase") == "verified"]
            rec["also_tag_pending"] = [x for x in extras if x not in rec["also_tagged"]]
            checkpoint()
    except VerificationError:
        raise  # acknowledged lag is safe to resume through read-only checks
    except (ApiError, UncertainWrite) as exc:
        rec["status"] = "uncertain"
        rec["blocked"] = True
        rec["reason"] = "429" if isinstance(exc, ThrottledError) else "interrupted target/tag"
        log.log(f"  target/tag stop category: {type(exc).__name__}")
        checkpoint()
        if isinstance(exc, ThrottledError):
            raise
        raise UncertainWrite("target/tag interrupted; explicit reconciliation required") from exc
    rec["status"] = "uploaded"
    rec["verified_by"] = "get-readback"
    checkpoint()
    if key not in state["uploaded"]:
        state["uploaded"].append(key)
    state.setdefault("objects", {})[key] = {"id": oid, "verified": True}
    state.get("pending", {}).pop(key, None)
    save_state(state_path, state)


def process_target(t, token, state, state_path, status, manifest_path,
                   log, smoke=False, sync_repo=True, sync_failed=None,
                   targets_by_pid=None):
    pid = str(t["profile_id"])
    node_id, _display = verify_profile(token, pid, t["expect_name"])
    if node_id != pid:
        log.log(f"target {pid}: resolved via guid to the served node id")
    log.log(f"target {pid}: profile name verified")
    done_keys = {k for k, v in status["items"].items()
                 if v.get("status") in ("uploaded", "resolved")} \
        | set(state["uploaded"])
    # Reconcile local uncertain markers against the repo status: the marker
    # survives a failed push; only an EXPLICIT user resolution in the repo
    # file ("not_found" = retry, "resolved" = fixed on Geni) lifts it.
    state["uncertain"] = [
        k for k in state.get("uncertain", [])
        if status["items"].get(k, {}).get("status")
        not in ("not_found", "resolved", "uploaded")]
    for k, v in status["items"].items():
        if v.get("status") == "uncertain" and k.startswith(f"{pid}:"):
            log.log(f"  BLOCKED: {k.split(':', 2)[0]}:{k.split(':', 2)[1]} has an "
                    "UNCERTAIN outcome from an earlier run. Check Geni manually, "
                    "then set it to 'not_found' (retry) or 'resolved' (fixed "
                    "manually) in upload-status.yaml. Deleting the entry does "
                    "NOT unblock it (the local marker survives). Not touching it.")
    listings = {k: list_tagged(token, node_id, k) for k in ("documents", "photos")}
    for kind, add_kind, tag_kind, base in (
            ("documents", "document_add", "document_tag", "document"),
            ("photos", "photo_add", "photo_tag", "photo")):
        if listings[kind] is None:
            log.log(f"  WARNING: {kind} listing unavailable; state file is the only "
                    "duplicate guard for this kind")
        for item in t.get(kind) or []:
            key = f"{pid}:{kind}:{item['title']}"
            it = label(item)
            pending = state.get("pending", {}).get(key)
            if pending:
                status["items"][key] = pending
            if status["items"].get(key, {}).get("journal_version") == 1:
                durable_upload(item, kind, base, add_kind, tag_kind, pid, node_id,
                               token, key, state, state_path, status, manifest_path,
                               log, sync_repo, targets_by_pid or {})
                continue
            if status["items"].get(key, {}).get("status") == "not_found":
                pass  # user checked Geni: object absent -> safe to retry
            elif status["items"].get(key, {}).get("status") == "uncertain" or \
                    key in state.get("uncertain", []):
                log.log(f"  skip {it}: BLOCKED by an earlier uncertain outcome. "
                        "After checking Geni, set its upload-status.yaml entry "
                        "to 'not_found' (retry) or 'resolved' (fixed manually).")
                continue
            if listings[kind] is not None:
                if anchor(item, kind) in listings[kind]:
                    log.log(f"  skip {it}: present in server listing")
                    continue
                if key in done_keys:
                    # Status says done but the server cannot confirm it. NEVER
                    # re-upload automatically: the listing may be stale or the
                    # object may exist untagged. Mark uncertain and stop.
                    status["items"][key] = {
                        "status": "uncertain",
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "reason": "recorded done but missing from server listing"}
                    save_status(manifest_path, status)
                    state.setdefault("uncertain", [])
                    if key not in state["uncertain"]:
                        state["uncertain"].append(key)
                    save_state(state_path, state)
                    if sync_repo:
                        repo_sync(manifest_path, log)
                    raise UncertainWrite(
                        f"STOPPED: {it} is recorded as done but the server "
                        "listing does not show it. NOT re-uploaded (duplicate "
                        "risk). Check Geni manually and resolve the entry in "
                        "upload-status.yaml.")
            elif key in done_keys:
                log.log(f"  skip {it}: status/state only (server listing "
                        "unavailable)")
                continue
            durable_upload(item, kind, base, add_kind, tag_kind, pid, node_id,
                           token, key, state, state_path, status, manifest_path,
                           log, sync_repo, targets_by_pid or {})
            if (sync_repo and repo_sync(manifest_path, log) is False
        and sync_failed is not None):
                sync_failed.append(key)
            _sleep(1)
            if smoke:
                log.log("SMOKE MODE: stopping after the first verified upload. "
                        "Verify it on Geni, then re-run without --smoke.")
                return True
    return False


def cmd_run(args):
    if args.confirm != "YES":
        print("refused: pass --confirm YES after reviewing the plan", file=sys.stderr)
        return 2
    token = get_token(args)
    if not token:
        print("refused: no token (GENI_ACCESS_TOKEN or --token-file)", file=sys.stderr)
        return 2
    try:
        preflight_state_writable(args.state)
    except ApiError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    lock_path = os.path.join(os.path.dirname(os.path.abspath(args.state)),
                             ".geni-upload.lock")
    # The flock must be held until the process exits; a with-block would
    # release it after acquisition.
    lock_fd = open(lock_path, "w")  # noqa: SIM115
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"refused: another run holds {lock_path} (concurrent runs are "
              "not safe)", file=sys.stderr)
        return 6
    log_path = args.log or os.path.join(
        os.path.dirname(os.path.abspath(args.state)), "geni-upload-run.log")
    log = RunLog(log_path)
    log.log(f"run start: manifest={args.manifest} state={args.state} "
            f"log={log_path} smoke={bool(args.smoke)}")
    try:
        m = load_manifest(args.manifest)
        state = load_state(args.state)
        status = load_status(args.manifest)
        sync_failed = []
        if not args.no_repo_sync:
            missing = [k for k in state["uploaded"] if k not in status["items"]]
            if missing:
                log.log(f"repo sync: {len(missing)} item(s) verified in an earlier "
                        "run are not in the repo status (earlier push failed?); "
                        "retrying the sync now")
                for k in missing:
                    rec = {"status": "uploaded",
                           "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                        time.gmtime()),
                           "verified_by": "get-readback"}
                    obj = state.get("objects", {}).get(k)
                    if obj and obj.get("id"):
                        rec["object_id"] = obj["id"]
                    status["items"][k] = rec
                save_status(args.manifest, status)
                if repo_sync(args.manifest, log) is False:
                    sync_failed.extend(missing)
        for t in m["targets"]:
            try:
                if process_target(t, token, state, args.state, status,
                                  args.manifest, log, smoke=args.smoke,
                                  sync_repo=not args.no_repo_sync,
                                  sync_failed=sync_failed,
                                  targets_by_pid={str(x["profile_id"]): x
                                                  for x in m["targets"]}):
                    log.log("run end: smoke stop, exit 0")
                    return 0
            except UncertainWrite as e:
                log.log(f"error: {e}")
                log.log("run end: UNCERTAIN write stop, exit 3 (see message above; "
                        "no mutation was retried)")
                return 3
            except VerificationError as e:
                log.log(f"error: {e}")
                log.log("run end: verification failure, exit 4 (acknowledged POST "
                        "not confirmed by GET readback)")
                return 4
            except ApiError as e:
                log.log(f"error: {e}")
                log.log("run end: failure, exit 1")
                return 1
        done = len(state["uploaded"])
        if sync_failed:
            log.log(f"run complete: {done} item(s) VERIFIED on Geni, but "
                    f"{len(sync_failed)} repo-status push(es) FAILED, exit 5. "
                    "Duplicates are still guarded by the Geni listing; the next "
                    "run on this machine retries the sync automatically.")
            return 5
        log.log(f"run complete: {done} item(s) recorded as done, exit 0")
        return 0
    finally:
        log.close()


def cmd_auth_url(args):
    # Verified against Geni's documented Desktop App flow (implicit grant):
    # geni.com/platform/developer/help/oauth_desktop - response_type=token,
    # display=desktop, no redirect_uri needed; the token is shown on a page
    # the user copies manually.
    q = {"client_id": args.client_id, "response_type": "token",
         "display": "desktop"}
    if args.redirect_uri:
        q["redirect_uri"] = args.redirect_uri
    url = "https://www.geni.com/platform/oauth/authorize?" + urllib.parse.urlencode(q)
    print("Open in your browser and authorize:")
    print(url)
    print("Copy the access_token from the resulting page and save it as your "
          "Geni token file (mode 600), or set GENI_ACCESS_TOKEN.")
    return 0


def cmd_guidmap(args):
    """geni-uploader#11: bounded guid/id resolution diagnostic (read-only).

    Contrast (run 8) showed the singular profile GET serves an API-native id
    but both singular and bulk forms miss the manifest targets' website-URL
    numbers. Hypothesis under test: the URL numbers are guids, not node ids.

    Bounded scan: managed-profiles?fields=id,guid (per_page=50), count-
    first (page 1's total_count sizes the scan) with a hard cap of 10
    pages / 500 profiles. Each target's URL number is compared IN MEMORY
    against
    served id AND guid values; values are never logged. Every matched target
    is confirmed with a follow-up singular GET of the resolved id (shape
    only). ALL matches across the full budget are collected - first match
    never wins; >1 DISTINCT resolved id is reported AMBIGUOUS and the
    follow-up GET is skipped. Unmatched within budget is reported as
    UNKNOWN - a page-1/2 miss does NOT eliminate the hypothesis
    (pagination / management filter).
    """
    m = load_manifest(args.manifest)
    token = get_token(args)
    if not token:
        raise ApiError("guidmap: no token available "
                       "(use --token-file or GENI_ACCESS_TOKEN)")
    pids = [str(t["profile_id"]) for t in m["targets"]]
    # pid -> {"fields": set(), "ids": set()} - values held in memory only.
    # ALL matches are collected across the FULL page budget: first match
    # never wins; >1 DISTINCT resolved id means AMBIGUOUS and no follow-up.
    matches = {}
    max_pages = 10  # hard cap: 500 managed profiles scanned, never more
    print(f"guidmap: read-only guid/id resolution over {len(pids)} manifest "
          f"target(s), bounded to at most {max_pages} managed-profiles "
          "page(s) (shapes only, values redacted)")
    pages_to_scan = max_pages
    scanned = 0
    for page in range(1, max_pages + 1):
        if page > pages_to_scan:
            break
        res = execute("GET", "user_managed_profiles",
                      f"{API_BASE}/user/managed-profiles"
                      f"?fields=id,guid&per_page=50&page={page}", token)
        if page == 1 and isinstance(res, dict) and "total_count" in res:
            import math
            total = res["total_count"]
            # A single integer (size of the managed set) is logged to size
            # the bounded scan; it is not a profile value.
            print(f"managed-profiles total_count: {total}")
            if isinstance(total, int) and total >= 0:
                pages_to_scan = min(math.ceil(total / 50) or 1, max_pages)
        if not isinstance(res, dict):
            print(f"page {page}: "
                  f"{json.dumps(_profile_payload_shape(res), sort_keys=True)};"
                  " stopping scan")
            break
        scanned = page
        items = res.get("results")
        if isinstance(items, list):
            page_items = items
        elif res.get("id"):
            page_items = [res]  # bare single-object form
        else:
            page_items = []
        page_matches = 0
        for item in page_items:
            if not isinstance(item, dict):
                continue
            iid = str(item.get("id") or "")
            iguid = str(item.get("guid") or "")
            for pid in pids:
                if iguid and pid == iguid:
                    entry = matches.setdefault(pid, {"fields": set(),
                                                     "ids": set()})
                    entry["fields"].add("guid")
                    entry["ids"].add(iid)
                    page_matches += 1
                elif iid and pid == iid:
                    entry = matches.setdefault(pid, {"fields": set(),
                                                     "ids": set()})
                    entry["fields"].add("id")
                    entry["ids"].add(iid)
                    page_matches += 1
        has_next = bool(res.get("next_page"))
        print(f"page {page}: results_len {len(page_items)}, "
              f"matches {page_matches}, next_page {has_next}")
        if not page_items or not has_next:
            break
    for i, pid in enumerate(pids, 1):
        entry = matches.get(pid)
        if not entry:
            print(f"target #{i}: UNRESOLVED after scanning {scanned} page(s) "
                  f"({scanned * 50} managed profiles) - unknown, "
                  "not eliminated")
            continue
        distinct = {rid for rid in entry["ids"] if rid}
        if len(distinct) != 1:
            print(f"target #{i}: AMBIGUOUS - {len(distinct)} distinct "
                  "resolved id(s) across the scan; follow-up GET skipped")
            continue
        rid = next(iter(distinct))
        fields = "/".join(sorted(entry["fields"]))
        good = execute("GET", "profile", f"{API_BASE}/profile-{rid}", token)
        print(f"target #{i}: matched via {fields}; "
              "singular GET of resolved id: "
              + json.dumps(_profile_payload_shape(good), sort_keys=True))
    print("No writes performed.")
    return 0


def cmd_pguid(args):
    """geni-uploader#43: profile-g URL-number contrast (read-only, 3 reads).

    Run 8 showed the singular `profile-<N>` GET and bulk `?ids=` forms miss
    the manifest targets' website-URL numbers; runs 9/10 showed the numbers
    match neither id nor guid among the first 500 of 1054 managed profiles.
    Third-party evidence (dmalch/go-geni issue #71, live-probed there, NOT
    verified here) claims the API resolves a guid ONLY as
    `api/profile-g<guid>`. This diagnostic probes exactly that form: one
    paced singular GET per manifest target, `api/profile-g<URL number>`.

    Per target only booleans are logged - never values: api_id_nonempty,
    guid_nonempty, guid_equals_input, id_equals_input, name_match (strict
    manifest name guard). RESOLVED-MAPPED requires nonempty id AND strict
    name match AND guid_equals_input: serve+name alone does NOT prove the
    guid space, and an empty/error response does NOT kill the guid
    hypothesis universally (visibility rules remain possible). No writes;
    strict stop on 429 via execute's standing contract.
    """
    m = load_manifest(args.manifest)
    token = get_token(args)
    if not token:
        raise ApiError("pguid: no token available "
                       "(use --token-file or GENI_ACCESS_TOKEN)")
    targets = m["targets"]
    print(f"pguid: read-only profile-g contrast over {len(targets)} manifest "
          "target(s) (booleans only, values redacted)")
    for i, t in enumerate(targets, 1):
        pid = str(t["profile_id"])
        try:
            res = execute("GET", "profile", f"{API_BASE}/profile-g{pid}",
                          token)
        except ThrottledError:
            raise  # strict 429 stop: never continue to the next target
        except ApiError:
            print(f"target #{i}: HTTP error from profile-g GET - unknown, "
                  "not eliminated (guid hypothesis not excluded)")
            continue
        obj = res if isinstance(res, dict) else {}
        if isinstance(obj.get("results"), list):
            obj = obj["results"][0] if obj["results"] else {}
        if not isinstance(obj, dict) or not obj:
            print(f"target #{i}: empty response - unknown, not eliminated "
                  "(guid hypothesis not excluded)")
            continue
        iid = str(obj.get("id") or "")
        iguid = str(obj.get("guid") or "")
        nm = name_matches(profile_name_surface(obj), t["expect_name"])
        api_id_nonempty = bool(iid)
        guid_nonempty = bool(iguid)
        guid_eq = guid_nonempty and iguid == pid
        id_eq = api_id_nonempty and iid == pid
        resolved = api_id_nonempty and nm and guid_eq
        verdict = ("RESOLVED-MAPPED (nonempty id + strict name guard + "
                   "guid_equals_input)" if resolved
                   else "served-partial or mismatch - unknown preserved")
        print(f"target #{i}: {verdict}; api_id_nonempty={api_id_nonempty} "
              f"guid_nonempty={guid_nonempty} guid_equals_input={guid_eq} "
              f"id_equals_input={id_eq} name_match={nm}")
    print("No writes performed.")
    return 0

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token-file", help="file outside the repo holding the access token")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("auth-url"); p.add_argument("--client-id", required=True)
    p.add_argument("--redirect-uri", default=None,
                   help="only if your app settings define a callback URL; the "
                        "desktop flow (default) needs none")
    p.set_defaults(fn=cmd_auth_url)
    p = sub.add_parser("whoami"); p.set_defaults(fn=cmd_whoami)
    for name, fn in (("plan", cmd_plan), ("run", cmd_run),
                     ("contrast", cmd_contrast), ("guidmap", cmd_guidmap),
                     ("pguid", cmd_pguid)):
        p = sub.add_parser(name); p.add_argument("--manifest", required=True)
        p.set_defaults(fn=fn)
    sub.choices["run"].add_argument("--confirm", default="")
    for name in ("plan", "run"):
        sub.choices[name].add_argument(
            "--log", default=None,
            help="diagnostic log file (run default: geni-upload-run.log next to "
                 "the state file; plan default: stdout only)")
    sub.choices["run"].add_argument("--state", default=STATE_DEFAULT)
    sub.choices["run"].add_argument("--smoke", action="store_true",
                                    help="upload only the first item, then stop")
    sub.choices["run"].add_argument("--no-repo-sync", action="store_true",
                                    help="do not commit/push upload-status.yaml "
                                         "back to the repo")
    args = ap.parse_args()
    try:
        return args.fn(args)
    except ThrottledError:
        # Value-free stop line: the exception text embeds the request URL,
        # which can carry a private id. Shapes only, everywhere.
        print("error: throttled (HTTP 429) - stopped without automatic "
              "retry; re-run only as a fresh, deliberate attempt",
              file=sys.stderr)
        return 1
    except ApiError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
