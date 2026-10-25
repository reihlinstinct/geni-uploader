#!/usr/bin/env python3
"""User-run Geni source upload tool. See DESIGN.md and CONTRACTS.md.

Safety model:
- Every network call passes through execute(), which hard-enforces ALLOWLIST
  on (method, kind) pairs, whatever GENI_API_BASE points at.
- GETs retry on transient errors. Mutating POSTs are NEVER blindly retried:
  a timeout/5xx/invalid-JSON after sending means the object may already exist
  (duplicate risk). The run reconciles via the listing endpoint once; if the
  object is not found there, it is marked 'uncertain' in upload-status.yaml
  and future runs REFUSE to touch it until manually resolved.
- Every acknowledged upload+tag is confirmed by a GET readback
  (verify_linkage, ~31s budget) before being recorded done - in the local
  state file AND in upload-status.yaml next to the manifest, which is
  committed+pushed back to the repo (best effort; a failed push is reported
  loudly with exit 5 and retried on the next run).
- Skip decisions require server proof: when the profile listing is
  available, only items present there are skipped; status/state entries that
  the listing does not confirm are treated as NOT uploaded.
- State file writes are atomic (temp + rename); a flock on the state dir
  refuses concurrent runs (exit 6).
- Logs never contain tokens, headers, payloads, or personal names/titles
  (items are logged as short hashes).
"""
import argparse, base64, fcntl, hashlib, http.client, json, os, subprocess, sys, tempfile, time, urllib.error
import urllib.parse, urllib.request

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
        self.f = open(path, "a", encoding="utf-8") if path else None

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
    budget = 5  # polls; sleeps 1+2+4+8+16 = 31s total
    for i in range(budget):
        listing = list_tagged(token, pid, kind)
        if listing is not None and expect_anchor in listing:
            return True
        log.log(f"    readback {i + 1}/{budget}: not yet visible in {kind} listing")
        _sleep(2 ** i)
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
    out = {"keys": sorted(str(k) for k in p.keys())}
    r = p.get("results")
    if r is not None:
        out["results_type"] = type(r).__name__
        if isinstance(r, (list, dict)):
            out["results_len"] = len(r)
    return json.dumps(out, sort_keys=True)


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
        return str(gobj["id"]), gobj.get("display_name") or ""
    raise ApiError(f"profile {pid}: not served as a node id and not "
                   "resolvable as a guid (profile-g) with a matching "
                   "identity - target SKIPPED")


def list_tagged(token, pid, kind):
    """Set of idempotency anchors already tagged to the profile.
    documents: (title, source_url); photos: (title,)."""
    ek = "profile_documents" if kind == "documents" else "profile_photos"
    url = f"{API_BASE}/profile-{pid}/{kind}"
    items = []
    pages = 0
    try:
        while url and pages < 10:
            res = execute("GET", ek, url, token)
            items.extend(res.get("results", res if isinstance(res, list) else []))
            url = res.get("next") if isinstance(res, dict) else None
            pages += 1
        if url:
            return None  # pagination incomplete: treat as unavailable
    except ApiError as e:
        if kind == "photos":
            return None  # listing unavailable: fall back to state file + warning
        raise
    out = set()
    for d in items:
        if isinstance(d, dict):
            out.add((d.get("title"), d.get("source_url")) if kind == "documents"
                    else (d.get("title"),))
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
    os.replace(tmp, path)


def repo_sync(manifest_path, log):
    """Best-effort commit+push of the status file so future runs anywhere
    skip verified items. Failures NEVER affect the run and never cause a
    re-upload: the Geni server listing and the local state file remain as
    duplicate guards."""
    try:
        cwd = os.path.dirname(os.path.abspath(manifest_path))
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                             capture_output=True, text=True, timeout=30)
        if top.returncode != 0:
            log.log("  repo sync: not inside a git repo; status kept in the "
                    "local file only")
            return None
        top = top.stdout.strip()
        rel = os.path.relpath(status_path(manifest_path), top)
        subprocess.run(["git", "add", "--", rel], cwd=top, check=True,
                       capture_output=True, timeout=30)
        subprocess.run(["git", "-c", "user.name=geni-upload (user-run)",
                        "-c", "user.email=geni-upload@localhost",
                        "commit", "-q", "-m",
                        "geni-upload: mark verified upload "
                        + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())],
                       cwd=top, check=True, capture_output=True, timeout=30)
        push = subprocess.run(["git", "push"], cwd=top, capture_output=True,
                              text=True, timeout=120)
        if push.returncode != 0:
            log.log("  repo sync: PUSH FAILED (read-only token or remote moved); "
                    "item stays protected by the Geni listing + local state, "
                    "and the next run on this machine will retry the sync")
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
            data = upload_payload(item, kind)
            try:
                res = execute("POST", add_kind, f"{API_BASE}/{base}/add", token, data)
            except UncertainWrite as e:
                # Reconcile once via the listing; never re-send the mutation.
                log.log(f"  UNCERTAIN write for {it}: {e}")
                _sleep(5)
                try:
                    new_listing = list_tagged(token, node_id, kind)
                except ThrottledError:
                    raise  # stop-on-throttle wins over reconciliation
                except ApiError:
                    new_listing = None
                if new_listing is not None and anchor(item, kind) in new_listing:
                    log.log("  reconciled via GET readback: object exists and is "
                            "tagged; recording as done")
                    state["uploaded"].append(key)
                    state.setdefault("objects", {})[key] = {"verified": True}
                    save_state(state_path, state)
                    continue
                status["items"][key] = {
                    "status": "uncertain",
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                save_status(manifest_path, status)
                state.setdefault("uncertain", [])
                if key not in state["uncertain"]:
                    state["uncertain"].append(key)
                save_state(state_path, state)
                if sync_repo:
                    repo_sync(manifest_path, log)
                raise UncertainWrite(
                    f"STOPPED after uncertain write of {it}. The object may "
                    "exist on Geni, possibly UNTAGGED. It is marked 'uncertain' "
                    "in upload-status.yaml and future runs will REFUSE to touch "
                    "it until you check Geni manually and resolve the entry. "
                    "The mutation was NOT retried.")
            obj_id = res.get("id")
            if not obj_id:
                save_state(state_path, state)
                raise ApiError(f"no id returned for {item['title']!r}; stopped")
            log.log(f"  upload acknowledged: {it} -> {base}-{obj_id}")
            execute("POST", tag_kind,
                    f"{API_BASE}/{base}-{obj_id}/tag/profile-{node_id}",
                    token, {})
            log.log(f"  tag acknowledged: {base}-{obj_id} -> profile-{node_id}")
            if not verify_linkage(token, node_id, kind, anchor(item, kind), log):
                save_state(state_path, state)
                raise VerificationError(
                    f"POSTs for {it} ({base}-{obj_id}) were acknowledged but the "
                    f"GET readback does not show it tagged to profile {node_id}. "
                    "NOT recorded as done. Check Geni manually; re-run skips only "
                    "verified items.")
            state["uploaded"].append(key)
            state.setdefault("objects", {})[key] = {"id": obj_id, "verified": True}
            save_state(state_path, state)
            status["items"][key] = {
                "status": "uploaded", "object_id": obj_id,
                "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "verified_by": "get-readback"}
            save_status(manifest_path, status)
            log.log(f"  VERIFIED via GET readback: {it} ({base}-{obj_id}) "
                    f"tagged to profile-{node_id}")
            tagged_ok = []
            extras = [str(x) for x in item.get("also_tag") or []]

            def _mark_uncertain(reason, key=key, obj_id=obj_id,
                                extras=extras, tagged_ok=tagged_ok):
                status["items"][key] = {
                    "status": "uncertain",
                    "object_id": obj_id,
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime()),
                    "also_tagged": tagged_ok[:],
                    "also_tag_pending": extras[len(tagged_ok):],
                    "reason": reason + " Resolve by setting the entry to "
                            "'resolved' once Geni shows the tags - do NOT "
                            "set 'not_found' (that uploads a NEW object)."}
                save_status(manifest_path, status)
                state.setdefault("uncertain", [])
                if key not in state["uncertain"]:
                    state["uncertain"].append(key)
                save_state(state_path, state)
                if sync_repo:
                    repo_sync(manifest_path, log)

            for extra_pid in extras:
                # One object, several profiles: tag the SAME object to each
                # extra manifest target, with the full identity guard per
                # profile. ANY interruption after the verified primary
                # upload - identity failure, tag/readback error, or 429 -
                # records the partial also_tagged list, marks the item
                # UNCERTAIN (never left 'uploaded', or a rerun would skip it
                # and the missing tags would silently never happen), and
                # stops the run. Nothing is retried automatically.
                xt = (targets_by_pid or {}).get(extra_pid)
                if xt is None:
                    raise ApiError(f"also_tag id {extra_pid} is not a manifest target "
                                   "(load_manifest rejects this; refusing)")

                try:
                    xnode, _xname = verify_profile(token, extra_pid,
                                                   xt["expect_name"])
                    via = (" (resolved via guid)" if xnode != extra_pid else "")
                    log.log(f"  also_tag target {extra_pid}: profile name "
                            f"verified{via}")
                    execute("POST", tag_kind,
                            f"{API_BASE}/{base}-{obj_id}/tag/profile-{xnode}",
                            token, {})
                    extra_ok = verify_linkage(token, xnode, kind,
                                              anchor(item, kind), log)
                    if not extra_ok:
                        raise ApiError("tag acknowledged but the GET readback "
                                       "does not confirm it")
                except ThrottledError:
                    # stop-on-throttle wins over everything: persist what is
                    # known, make NO further Geni calls, and stop.
                    _mark_uncertain(
                        f"primary upload+tag VERIFIED, but also_tag to "
                        f"{extra_pid} was interrupted by Geni rate limiting "
                        f"(HTTP 429). Object {base}-{obj_id} exists; "
                        f"{len(tagged_ok)} extra tag(s) verified, "
                        f"{len(extras) - len(tagged_ok)} NOT confirmed.")
                    raise
                except (ApiError, UncertainWrite) as e:
                    log.log(f"  also_tag to {extra_pid} failed: {e}")
                    _mark_uncertain(
                        f"primary upload+tag VERIFIED, but also_tag to "
                        f"{extra_pid} failed or is NOT confirmed. Object "
                        f"{base}-{obj_id} exists.")
                    raise UncertainWrite(
                        f"STOPPED: also_tag of {base}-{obj_id} to profile "
                        f"{extra_pid} failed or could not be verified "
                        f"({len(tagged_ok)} of {len(extras)} extra tags "
                        "confirmed). The object exists and the primary tag is "
                        "verified; the extra tag was NOT retried. Marked "
                        "'uncertain' in upload-status.yaml - check Geni "
                        "manually and resolve the entry.")
                tagged_ok.append(extra_pid)
                status["items"][key]["also_tagged"] = tagged_ok[:]
                save_status(manifest_path, status)
                log.log(f"  VERIFIED via GET readback: {base}-{obj_id} also "
                        f"tagged to profile-{xnode}")
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
    lock_fd = open(lock_path, "w")
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
    rc = 0
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
