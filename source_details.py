"""User-run existing-source metadata repair. No create/delete/citation endpoints."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import ExitStack
from pathlib import Path

import geni_upload as api

FIELDS = {"document": {"title", "description", "date", "labels"},
          "photo": {"title", "description", "date"}}
READ_FIELDS = {"id", "guid", "first_name", "middle_name", "last_name",
               "maiden_name", "display_name", "is_alive", "birth", "death", "burial"}


def load_records(path):
    """Reject unknown fields and incomplete records before network access."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(data) != {"schema_version", "items"} or data["schema_version"] != 1:
        raise api.ApiError("invalid source-details schema")
    if not isinstance(data["items"], list) or not data["items"]:
        raise api.ApiError("items must be a nonempty list")
    seen = set()
    for item in data["items"]:
        required = {"key", "kind", "object_id", "expect", "set", "targets", "manual_facts"}
        if not isinstance(item, dict) or set(item) not in (required, required | {"description_only"}):
            raise api.ApiError("invalid source-details item fields")
        description_only = item.get("description_only", False)
        if "description_only" in item and description_only is not True:
            raise api.ApiError("description_only must be true when present")
        kind = item["kind"]
        if kind not in FIELDS or not re.fullmatch(r"[0-9]+", str(item["object_id"])):
            raise api.ApiError("invalid existing source ID or kind")
        anchor = (kind, str(item["object_id"]))
        if anchor in seen:
            raise api.ApiError("duplicate existing source object")
        seen.add(anchor)
        if (not isinstance(item["expect"], dict) or not item["expect"]
                or not (set(item["expect"]) & {"title", "source_url"})
                or set(item["expect"]) - {"title", "source_url", "description_sha256"}
                or any(not isinstance(v, str) or not v for v in item["expect"].values())):
            raise api.ApiError("expected title or source URL required")
        old_hash = item["expect"].get("description_sha256")
        if old_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", old_hash):
            raise api.ApiError("invalid expected description hash")
        if description_only and old_hash is None:
            raise api.ApiError("description-only repair requires expected old description hash")
        if (not isinstance(item["set"], dict) or not item["set"]
                or set(item["set"]) - (FIELDS[kind] | {"description_en"})
                or any(not isinstance(v, str) or not v.strip() for v in item["set"].values())):
            raise api.ApiError("invalid metadata fields")
        if description_only and (set(item["set"]) - {"description_en", "description"}
                                 or "description_en" not in item["set"]):
            raise api.ApiError("description-only repair requires English description fields only")
        if "description" in item["set"] or "description_en" in item["set"]:
            # Author-declared English is mandatory for all newly written descriptions.
            api.render_description(item["set"])
        if not isinstance(item["targets"], list) or not item["targets"]:
            raise api.ApiError("explicit targets required")
        ids = set()
        for target in item["targets"]:
            if (not isinstance(target, dict) or set(target) != {"profile_id", "expect_name"}
                    or not re.fullmatch(r"[0-9]+", str(target["profile_id"]))
                    or len(str(target["expect_name"]).split()) < 2):
                raise api.ApiError("invalid target identity")
            if str(target["profile_id"]) in ids:
                raise api.ApiError("duplicate target")
            ids.add(str(target["profile_id"]))
        if not isinstance(item["manual_facts"], list):
            raise api.ApiError("manual_facts must be a list")
    return data["items"]


def object_read(token, kind, oid):
    obj = api.execute("GET", kind, f"{api.API_BASE}/{kind}-{oid}", token)
    if isinstance(obj, dict) and str(obj.get("id")) == f"{kind}-{oid}":
        return obj
    # Never guess that a website GUID is an API node ID, nor invent a
    # document-g/photo-g resolution contract. User-supplied node ID required.
    raise api.ApiError("existing source node identity not confirmed")


def deceased_target(token, target):
    pid, _ = api.verify_profile(token, str(target["profile_id"]), target["expect_name"])
    pid = str(pid).removeprefix("profile-")
    if not pid.isdigit():
        raise api.ApiError("invalid served target ID")
    obj = api.execute("GET", "profile", f"{api.API_BASE}/profile-{pid}", token)
    if not isinstance(obj, dict) or obj.get("is_alive") is not False:
        raise api.ApiError("target not confirmed deceased")
    return pid


def matches_expect(obj, item):
    for key, value in item["expect"].items():
        if key == "description_sha256":
            text = obj.get("description")
            if not isinstance(text, str):
                return False
            old = hashlib.sha256(text.encode()).hexdigest() == value
            # Exact desired text permits idempotent GET-only verification.
            desired = item["set"].get("description")
            if "description_en" in item["set"]:
                desired = api.render_description(item["set"])
            if not old and text != desired:
                return False
        elif obj.get(key) != value:
            return False
    return True


def checked_plan(items, token):
    """All identities and old metadata checked before the first mutation."""
    plan = []
    for item in items:
        obj = object_read(token, item["kind"], item["object_id"])
        if not matches_expect(obj, item):
            raise api.ApiError("existing source precondition mismatch")
        targets = [deceased_target(token, t) for t in item["targets"]]
        resolved_item = dict(item)
        resolved_item["object_id"] = obj["id"].split("-", 1)[1]
        desired = dict(item["set"])
        if "description_en" in desired:
            desired["description"] = api.render_description(desired)
            del desired["description_en"]
        resolved_item["set"] = desired
        plan.append((resolved_item, obj, targets))
    return plan


def normalized_tag(value):
    return str(value).rstrip("/").split("/")[-1]


def apply_plan(plan, token, state_path, sync_state=False):
    """One POST at a time; no retry or replacement on an uncertain result."""
    if any(item.get("description_only") for item, _, _ in plan):
        if not all(item.get("description_only") for item, _, _ in plan):
            raise api.ApiError("description-only and tag-changing repairs cannot be mixed")
        return apply_description_plan(plan, token, state_path, sync_state)
    state = Path(state_path)
    if state.exists():
        prior = json.loads(state.read_text(encoding="utf-8"))
        if prior.get("status") != "verified":
            raise api.ApiError("unresolved prior repair; manual reconciliation required")
    def checkpoint(status):
        fd, name = tempfile.mkstemp(dir=state.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"status": status}, stream)
            os.replace(name, state)
            if sync_state:
                # Persist the pending marker BEFORE any mutation. Failure stops.
                root = subprocess.check_output(
                    ["git", "rev-parse", "--show-toplevel"], text=True).strip()
                rel = state.resolve().relative_to(Path(root).resolve())
                subprocess.run(["git", "add", "--", str(rel)], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
                if diff.returncode == 1:
                    subprocess.run(["git", "-c", "user.name=source-details",
                                    "-c", "user.email=source-details@localhost",
                                    "commit", "--only", "-qm", "Record source repair checkpoint", "--", str(rel)],
                                   check=True, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                    branch = os.environ.get("GENI_UPLOAD_REF")
                    if not branch:
                        raise api.ApiError("state sync requires explicit branch")
                    subprocess.run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"],
                                   check=True, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                elif diff.returncode != 0:
                    raise api.ApiError("state sync failed")
        finally:
            if os.path.exists(name):
                os.unlink(name)
    checkpoint("pending")
    for item, before, targets in plan:
        kind, oid = item["kind"], item["object_id"]
        desired = item["set"]
        if any(before.get(k) != v for k, v in desired.items()):
            api.execute("POST", f"{kind}_update", f"{api.API_BASE}/{kind}-{oid}/update",
                        token, desired)
            after = object_read(token, kind, oid)
            if any(after.get(k) != v for k, v in desired.items()):
                raise api.VerificationError("metadata readback not confirmed; stop")
            if not set(map(normalized_tag, before.get("tags", []))).issubset(
                    set(map(normalized_tag, after.get("tags", [])))):
                raise api.VerificationError("existing tags changed; stop")
        for pid in targets:
            current = object_read(token, kind, oid)
            tag = f"profile-{pid}"
            if tag in set(map(normalized_tag, current.get("tags", []))):
                continue
            api.execute("POST", f"{kind}_tag",
                        f"{api.API_BASE}/{kind}-{oid}/tag/{tag}", token)
            after = object_read(token, kind, oid)
            if tag not in set(map(normalized_tag, after.get("tags", []))):
                raise api.VerificationError("profile tag readback not confirmed; stop")
    # This is deliberately never called complete: fact citations are manual.
    checkpoint("verified")
    print("metadata and tags verified; fact citations remain manual")


def _sync_description_state(state):
    root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    rel = state.resolve().relative_to(Path(root).resolve())
    subprocess.run(["git", "add", "--", str(rel)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 1:
        subprocess.run(["git", "-c", "user.name=source-details",
                        "-c", "user.email=source-details@localhost", "commit", "--only", "-qm",
                        "Record description repair checkpoint", "--", str(rel)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif diff.returncode != 0:
        raise api.ApiError("description state sync failed")
    branch = os.environ.get("GENI_UPLOAD_REF")
    if not branch:
        raise api.ApiError("description state sync requires explicit branch")
    # Even an unchanged local checkpoint must reach remote before any POST.
    subprocess.run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def apply_description_plan(plan, token, state_path, sync_state=False):
    """Exact existing objects only. Pending writes reconcile by GET, never replay.

    Readback lag is a STOP, not permission to issue another update. A fresh
    user-triggered repair may clear pending only when desired metadata and
    unchanged tags are GET-proven. No tag/create/delete endpoints are used.
    """
    state = Path(state_path)
    binding = hashlib.sha256(json.dumps([item for item, _, _ in plan],
                                       sort_keys=True).encode()).hexdigest()
    journal = {"version": 1, "binding": binding, "items": {}}
    if state.exists():
        journal = json.loads(state.read_text())
        if (journal.get("version") != 1 or journal.get("binding") != binding
                or not isinstance(journal.get("items"), dict)):
            raise api.ApiError("description repair journal binding mismatch")
    def checkpoint():
        fd, name = tempfile.mkstemp(dir=state.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(journal, out, ensure_ascii=False, sort_keys=True)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, state)
            directory_fd = os.open(state.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            if sync_state:
                _sync_description_state(state)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    def preserved(obj):
        # Store only metadata actually needing protection, privately in the journal.
        if not isinstance(obj.get("tags"), list):
            raise api.ApiError("description repair requires explicit tag-list readback")
        return {k: obj[k] for k in ("title", "date", "source_url", "tags") if k in obj}
    def verify(obj, item, before):
        if obj.get("description") != item["set"]["description"] or preserved(obj) != before:
            raise api.VerificationError("description or preserved metadata readback pending; stop")
    # Reconcile ALL pending/verified entries before allowing any untouched write.
    for item, before, _ in plan:
        key = item["kind"] + "-" + str(item["object_id"])
        rec = journal["items"].get(key)
        if rec is not None:
            if (not isinstance(rec, dict) or rec.get("phase") not in ("pending", "verified")
                    or not isinstance(rec.get("preserved"), dict)):
                raise api.ApiError("invalid description repair journal")
            current = object_read(token, item["kind"], item["object_id"])
            verify(current, item, rec["preserved"])
            rec["phase"] = "verified"
        else:
            preserved(before)  # reject malformed tags before any write
    checkpoint()
    for item, _, _ in plan:
        key = item["kind"] + "-" + str(item["object_id"])
        if key in journal["items"]:
            continue
        # Refresh exact identity and preconditions immediately before mutation.
        current = object_read(token, item["kind"], item["object_id"])
        if not matches_expect(current, item):
            raise api.ApiError("description precondition changed; stop")
        before = preserved(current)
        if current.get("description") == item["set"]["description"]:
            journal["items"][key] = {"phase": "verified", "preserved": before}
            checkpoint()
            continue
        journal["items"][key] = {"phase": "pending", "preserved": before}
        checkpoint()  # durable intent before the only permitted update
        api.execute("POST", item["kind"] + "_update",
                    f"{api.API_BASE}/{key}/update", token,
                    {"description": item["set"]["description"]})
        after = object_read(token, item["kind"], item["object_id"])
        verify(after, item, before)
        journal["items"][key]["phase"] = "verified"
        checkpoint()
    print("existing descriptions verified; no tags changed; fact citations remain manual")


def private_json(path, data):
    dest = Path(path)
    if dest.exists():
        raise api.ApiError("output already exists; refusing overwrite")
    fd, tmp = tempfile.mkstemp(dir=dest.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        # Hard link prevents a racing overwrite and retains mode0600.
        os.link(tmp, dest)
    finally:
        os.unlink(tmp)


def snapshot(items, token, output):
    rows = []
    seen = set()
    for item in items:
        for target in item["targets"]:
            pid = deceased_target(token, target)
            if pid in seen:
                continue
            seen.add(pid)
            obj = api.execute("GET", "profile", f"{api.API_BASE}/profile-{pid}", token)
            if obj.get("is_alive") is not False:
                raise api.ApiError("target no longer confirmed deceased")
            # No relatives, notes, payload wrappers or arbitrary nested data.
            safe = {k: v for k, v in obj.items()
                    if k in READ_FIELDS and isinstance(v, (str, bool, int, float))}
            rows.append(safe)
    private_json(output, {"profiles": rows, "citations": "unsupported"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["validate", "plan", "repair", "snapshot"])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--token-file")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--output")
    parser.add_argument("--state")
    parser.add_argument("--sync-state", action="store_true")
    args = parser.parse_args()
    stack = ExitStack()
    try:
        items = load_records(args.manifest)
        if args.mode == "validate":
            print("source-details schema valid")
            return 0
        if args.mode == "repair" and args.confirm != "YES":
            raise api.ApiError("repair requires explicit confirmation")
        if args.mode == "snapshot" and not args.output:
            raise api.ApiError("snapshot requires private output path")
        if args.mode == "repair" and not args.state:
            raise api.ApiError("repair requires durable state path")
        # A local flock protects direct user runs as well as workflow concurrency.
        if args.mode == "repair":
            lock = stack.enter_context(
                Path(args.state + ".lock").open("w", encoding="utf-8")  # noqa: SIM115
            )
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        token = api.get_token(args)
        api.ALLOWLIST.update({("GET", "document"), ("GET", "photo"),
                              ("POST", "document_update"), ("POST", "photo_update")})
        if args.mode == "snapshot":
            snapshot(items, token, args.output)
        else:
            plan = checked_plan(items, token)
            if args.mode == "repair":
                apply_plan(plan, token, args.state, args.sync_state)
            else:
                print("source identity and target checks passed; no writes")
        return 0
    except (api.ApiError, OSError, ValueError, TypeError, subprocess.SubprocessError):
        # Fixed public-safe output; never print response payloads or identifiers.
        print("source-details stopped; inspect private input and verification state")
        return 1
    finally:
        stack.close()


if __name__ == "__main__":
    raise SystemExit(main())
