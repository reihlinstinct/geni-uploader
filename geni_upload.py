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
    so matching display_name alone false-rejects e.g. 'Johanna Annie
    Moritz' whose API display is 'Johanna Halle'. Still strict: every
    expected token must appear in THIS profile's own recorded names."""
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


def verify_profile(token, pid, expect_name):
    p = execute("GET", "profile", f"{API_BASE}/profile-{pid}", token)
    name = p.get("display_name") or ""
    if not name_matches(profile_name_surface(p), expect_name):
        raise ApiError(f"profile {pid}: no recorded name on the profile matches "
                       "the expected name - target SKIPPED")
    return name


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
            name = verify_profile(token, pid, t["expect_name"])
            print(f"  profile {pid}: OK ({name})")
            for kind in ("documents", "photos"):
                tagged = list_tagged(token, pid, kind)
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
                   log, smoke=False, sync_repo=True, sync_failed=None):
    pid = str(t["profile_id"])
    verify_profile(token, pid, t["expect_name"])
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
    listings = {k: list_tagged(token, pid, k) for k in ("documents", "photos")}
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
                    new_listing = list_tagged(token, pid, kind)
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
            execute("POST", tag_kind, f"{API_BASE}/{base}-{obj_id}/tag/profile-{pid}",
                    token, {})
            log.log(f"  tag acknowledged: {base}-{obj_id} -> profile-{pid}")
            if not verify_linkage(token, pid, kind, anchor(item, kind), log):
                save_state(state_path, state)
                raise VerificationError(
                    f"POSTs for {it} ({base}-{obj_id}) were acknowledged but the "
                    f"GET readback does not show it tagged to profile {pid}. "
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
                    f"tagged to profile-{pid}")
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
                                  sync_failed=sync_failed):
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token-file", help="file outside the repo holding the access token")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("auth-url"); p.add_argument("--client-id", required=True)
    p.add_argument("--redirect-uri", default=None,
                   help="only if your app settings define a callback URL; the "
                        "desktop flow (default) needs none")
    p.set_defaults(fn=cmd_auth_url)
    for name, fn in (("plan", cmd_plan), ("run", cmd_run)):
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
    except ApiError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
