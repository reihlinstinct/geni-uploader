"""User-run existing-source metadata repair. No create/delete/citation endpoints."""
import argparse
import fcntl
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
        if not isinstance(item, dict) or set(item) != required:
            raise api.ApiError("invalid source-details item fields")
        kind = item["kind"]
        if kind not in FIELDS or not re.fullmatch(r"[0-9]+", str(item["object_id"])):
            raise api.ApiError("invalid existing source ID or kind")
        anchor = (kind, str(item["object_id"]))
        if anchor in seen:
            raise api.ApiError("duplicate existing source object")
        seen.add(anchor)
        if (not isinstance(item["expect"], dict) or not item["expect"]
                or set(item["expect"]) - {"title", "source_url"}
                or any(not isinstance(v, str) or not v for v in item["expect"].values())):
            raise api.ApiError("expected title or source URL required")
        if (not isinstance(item["set"], dict) or not item["set"]
                or set(item["set"]) - FIELDS[kind]
                or any(not isinstance(v, str) or not v.strip() for v in item["set"].values())):
            raise api.ApiError("invalid metadata fields")
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


def checked_plan(items, token):
    """All identities and old metadata checked before the first mutation."""
    plan = []
    for item in items:
        obj = object_read(token, item["kind"], item["object_id"])
        if any(obj.get(k) != v for k, v in item["expect"].items()):
            raise api.ApiError("existing source precondition mismatch")
        targets = [deceased_target(token, t) for t in item["targets"]]
        resolved_item = dict(item)
        resolved_item["object_id"] = obj["id"].split("-", 1)[1]
        plan.append((resolved_item, obj, targets))
    return plan


def normalized_tag(value):
    return str(value).rstrip("/").split("/")[-1]


def apply_plan(plan, token, state_path, sync_state=False):
    """One POST at a time; no retry or replacement on an uncertain result."""
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
