"""Enforce the repository layout contract in .repo-layout.yml (version 2).

Reads .repo-layout.yml (JSON syntax, which is also valid YAML) and the
tracked file list, then fails on:
  - a missing required root file or directory (community standards);
  - a tracked top-level directory not listed in the contract;
  - a root file matching a deny pattern or no allow pattern;
  - a file inside a listed directory matching one of its deny patterns or
    none of its allow patterns (deny always wins);
  - a directory's required file that is missing, untracked, a link, not a
    regular file, outside the repository or unreadable.

The contract schema is validated fail-closed: unknown keys, duplicate JSON
keys, wrong types and unsupported versions are contract errors. A version 1
contract is converted by the explicit migrate_v1_to_v2() step; a version 2
contract is never read as version 1. Design: docs/repo-layout-v2-design.md.

Standard library only; no network. Usage:
  python3 tools/check_repo_layout.py [--root DIR]
Exit 0 when the layout conforms, 1 with one line per violation (paths and
rule categories only, sorted), 2 on a contract or repository error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

CONTRACT_NAME = ".repo-layout.yml"
SUPPORTED_VERSIONS = (1, 2)

TOP_KEYS_REQUIRED = {"version", "required", "root", "directories"}
TOP_KEYS_OPTIONAL = {"comment"}
ROOT_KEYS_REQUIRED = {"allow"}
ROOT_KEYS_OPTIONAL = {"deny"}
DIR_KEYS_V1 = {"allow"}
DIR_KEYS_REQUIRED = {"allow"}
DIR_KEYS_OPTIONAL = {"deny", "required"}

# Repository-location variables that would redirect git away from --root.
# Configuration variables (GIT_CONFIG_*, HOME, ...) are kept, so safe git
# configuration such as safe.directory still applies.
GIT_LOCATION_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_PREFIX",
    "GIT_GRAFT_FILE",
    "GIT_SHALLOW_FILE",
    "GIT_INTERNAL_SUPER_PREFIX",
    "GIT_REPLACE_REF_BASE",
    "GIT_NO_REPLACE_OBJECTS",
)

GLOB_CHARS = frozenset("*?[")
REGULAR_MODES = frozenset({"100644", "100755"})


class LayoutError(Exception):
    """A contract or repository error: the check cannot run."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise LayoutError(f"duplicate key in {CONTRACT_NAME}: {key!r}")
        out[key] = value
    return out


def parse_contract(text: str) -> dict[str, Any]:
    """Parse contract JSON, rejecting duplicate keys at any depth."""
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise LayoutError(f"{CONTRACT_NAME} is not valid JSON: {exc.msg}") from None
    if not isinstance(data, dict):
        raise LayoutError(f"{CONTRACT_NAME} must be a JSON object")
    return data


def _check_keys(obj: Any, where: str, required: set[str], optional: set[str]) -> None:
    if not isinstance(obj, dict):
        raise LayoutError(f"{where} must be an object")
    unknown = sorted(set(obj) - required - optional)
    if unknown:
        raise LayoutError(f"unknown key(s) in {where}: {', '.join(unknown)}")
    missing = sorted(required - set(obj))
    if missing:
        raise LayoutError(f"missing key(s) in {where}: {', '.join(missing)}")


def _string_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise LayoutError(f"{where} must be a list of non-empty strings")
    return list(value)


def _check_relative_path(path: str, where: str, allow_dir_slash: bool = False) -> None:
    """Reject absolute paths, empty components, . / .. segments and backslashes."""
    body = path[:-1] if allow_dir_slash and path.endswith("/") else path
    if "\\" in path:
        raise LayoutError(f"{where}: backslash in path {path!r}")
    if body.startswith("/") or not body:
        raise LayoutError(f"{where}: absolute or empty path {path!r}")
    for part in body.split("/"):
        if part in ("", ".", ".."):
            raise LayoutError(f"{where}: empty, '.' or '..' component in {path!r}")


def _matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pat) for pat in patterns)


def validate_v1(contract: dict[str, Any]) -> None:
    """Validate a version 1 contract (directory entries carry only allow)."""
    _check_keys(contract, CONTRACT_NAME, TOP_KEYS_REQUIRED, TOP_KEYS_OPTIONAL)
    _string_list(contract["required"], "required")
    _check_keys(contract["root"], "root", ROOT_KEYS_REQUIRED, ROOT_KEYS_OPTIONAL)
    if not isinstance(contract["directories"], dict):
        raise LayoutError("directories must be an object")
    for name, entry in contract["directories"].items():
        where = f"directories.{name}"
        _check_keys(entry, where, DIR_KEYS_V1, set())
        _string_list(entry["allow"], f"{where}.allow")


def migrate_v1_to_v2(contract: dict[str, Any]) -> dict[str, Any]:
    """Explicit, in-memory v1 -> v2 migration; never edits the contract file.

    Every v1 rule keeps its meaning: global required and root rules are
    copied, each directory keeps its allow list and gains empty deny and
    required lists.
    """
    if contract.get("version") != 1:
        raise LayoutError("migrate_v1_to_v2 expects a version 1 contract")
    validate_v1(contract)
    migrated: dict[str, Any] = {
        "version": 2,
        "required": list(contract["required"]),
        "root": {
            "allow": list(contract["root"]["allow"]),
            "deny": list(contract["root"].get("deny", [])),
        },
        "directories": {
            name: {"allow": list(entry["allow"]), "deny": [], "required": []}
            for name, entry in contract["directories"].items()
        },
    }
    if "comment" in contract:
        migrated["comment"] = contract["comment"]
    return migrated


def validate_v2(contract: dict[str, Any]) -> dict[str, Any]:
    """Validate a version 2 contract and return it with optional lists filled."""
    _check_keys(contract, CONTRACT_NAME, TOP_KEYS_REQUIRED, TOP_KEYS_OPTIONAL)
    if contract["version"] != 2:
        raise LayoutError("validate_v2 expects a version 2 contract")
    if "comment" in contract and not isinstance(contract["comment"], str):
        raise LayoutError("comment must be a string")
    required = _string_list(contract["required"], "required")
    for path in required:
        _check_relative_path(path, "required", allow_dir_slash=True)
    root = contract["root"]
    _check_keys(root, "root", ROOT_KEYS_REQUIRED, ROOT_KEYS_OPTIONAL)
    norm_root = {
        "allow": _string_list(root["allow"], "root.allow"),
        "deny": _string_list(root.get("deny", []), "root.deny"),
    }
    dirs = contract["directories"]
    if not isinstance(dirs, dict):
        raise LayoutError("directories must be an object")
    norm_dirs: dict[str, dict[str, list[str]]] = {}
    for name, entry in dirs.items():
        where = f"directories.{name}"
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise LayoutError(f"{where}: not a top-level directory name")
        _check_keys(entry, where, DIR_KEYS_REQUIRED, DIR_KEYS_OPTIONAL)
        allow = _string_list(entry["allow"], f"{where}.allow")
        deny = _string_list(entry.get("deny", []), f"{where}.deny")
        req = _string_list(entry.get("required", []), f"{where}.required")
        for path in req:
            if GLOB_CHARS & set(path):
                raise LayoutError(f"{where}.required: glob in exact path {path!r}")
            _check_relative_path(path, f"{where}.required")
            base = path.rsplit("/", 1)[-1]
            if _matches(base, deny):
                raise LayoutError(f"{where}.required: required file is denied: {path!r}")
            if not _matches(base, allow):
                raise LayoutError(f"{where}.required: required file is not allowed: {path!r}")
        norm_dirs[name] = {"allow": allow, "deny": deny, "required": req}
    return {
        "version": 2,
        "required": required,
        "root": norm_root,
        "directories": norm_dirs,
    }


def load_contract(root: Path) -> dict[str, Any]:
    """Read the contract and return a validated, normalized version 2 contract."""
    contract_path = root / CONTRACT_NAME
    try:
        text = contract_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise LayoutError(f"missing layout contract: {CONTRACT_NAME}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise LayoutError(f"unreadable layout contract: {exc.__class__.__name__}") from None
    contract = parse_contract(text)
    version = contract.get("version")
    if type(version) is not int or version not in SUPPORTED_VERSIONS:
        raise LayoutError(f"unsupported {CONTRACT_NAME} version: {version!r}")
    if version == 1:
        contract = migrate_v1_to_v2(contract)
    return validate_v2(contract)


def git_env() -> dict[str, str]:
    """The environment for git: repository-location variables removed."""
    env = dict(os.environ)
    for key in GIT_LOCATION_ENV:
        env.pop(key, None)
    return env


def _git(root: Path, *args: str) -> bytes:
    try:
        out = subprocess.run(
            ["git", *args], cwd=root, env=git_env(),
            check=False, capture_output=True,
        )
    except OSError as exc:
        raise LayoutError(f"cannot run git: {exc.__class__.__name__}") from None
    if out.returncode != 0:
        raise LayoutError(f"git {args[0]} failed: missing or unreadable git metadata at --root")
    return out.stdout


def verify_toplevel(root: Path) -> None:
    """Fail unless root is the top level of its git work tree."""
    raw = _git(root, "rev-parse", "--show-toplevel").rstrip(b"\n")
    top = Path(os.fsdecode(raw)).resolve()
    if top != root.resolve():
        raise LayoutError("--root is not the git top-level directory")


def tracked_entries(root: Path) -> dict[str, str]:
    """Return {tracked path: index mode}, from NUL-delimited git output."""
    out = _git(root, "ls-files", "-s", "-z")
    entries: dict[str, str] = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        mode = meta.split(b" ", 1)[0].decode("ascii")
        entries[os.fsdecode(raw_path)] = mode
    return entries


def tracked_files(root: Path) -> list[str]:
    """Return the repository's tracked file paths, sorted."""
    return sorted(tracked_entries(root))


def display(path: str) -> str:
    """Render a path on one output line: escape backslash and control chars."""
    out = []
    for ch in path:
        code = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif code < 0x20 or code == 0x7F:
            out.append(f"\\x{code:02x}")
        elif 0xDC80 <= code <= 0xDCFF:  # undecodable byte (surrogateescape)
            out.append(f"\\x{code - 0xDC00:02x}")
        else:
            out.append(ch)
    return "".join(out)


def _within(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def check_required_file(root: Path, rel: str, entries: dict[str, str]) -> str | None:
    """Return the violation category for one directory-required file, or None."""
    abs_root = root.resolve()
    target = root / rel
    # Containment before any read: the resolved path must stay in the repository.
    if not _within(Path(os.path.realpath(target)), abs_root):
        return "required file escapes repository"
    mode = entries.get(rel)
    if mode is None:
        if os.path.lexists(target):
            return "required file untracked"
        return "required file missing"
    if mode == "120000":
        return "required file is a tracked link"
    if mode not in REGULAR_MODES:
        return "required file is not a tracked regular file"
    try:
        st = os.lstat(target)
    except FileNotFoundError:
        return "required file missing"
    except OSError:
        return "required file unreadable"
    if stat.S_ISLNK(st.st_mode):
        return "required file is a link"
    if not stat.S_ISREG(st.st_mode):
        return "required file is not a regular file"
    try:
        fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.read(fd, 1)
        finally:
            os.close(fd)
    except OSError:
        return "required file unreadable"
    return None


def check(root: Path) -> list[str]:
    """Return one line per layout violation (sorted), empty when the tree conforms."""
    verify_toplevel(root)
    contract = load_contract(root)
    entries = tracked_entries(root)
    files = sorted(entries)
    tracked = set(files)
    violations: list[str] = []

    for required in contract["required"]:
        if required.endswith("/"):
            if not (root / required.rstrip("/")).is_dir():
                violations.append(f"required directory missing: {display(required)}")
        elif required not in tracked or not (root / required).is_file():
            violations.append(f"required file missing: {display(required)}")

    dirs = contract["directories"]
    root_rules = contract["root"]

    for path in files:
        parts = path.split("/")
        shown = display(path)
        if len(parts) == 1:
            name = parts[0]
            if _matches(name, root_rules["deny"]):
                violations.append(f"denied at repository root: {shown}")
            elif not _matches(name, root_rules["allow"]):
                violations.append(f"not allowed at repository root: {shown}")
            continue
        top = parts[0]
        if top not in dirs:
            violations.append(f"unlisted top-level directory: {display(top)}/ (via {shown})")
            continue
        name = parts[-1]
        rules = dirs[top]
        if _matches(name, rules["deny"]):
            violations.append(f"denied in {display(top)}/: {shown}")
        elif not _matches(name, rules["allow"]):
            violations.append(f"type not allowed in {display(top)}/: {shown}")

    for top in sorted(dirs):
        for rel in dirs[top]["required"]:
            full = f"{top}/{rel}"
            category = check_required_file(root, full, entries)
            if category:
                violations.append(f"{category} in {display(top)}/: {display(full)}")
    return sorted(violations)


def main() -> int:
    """Run the layout check; print violations and return the exit code."""
    summary = (__doc__ or "").splitlines()[0]
    parser = argparse.ArgumentParser(description=summary)
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    args = parser.parse_args()
    try:
        violations = check(Path(args.root).resolve())
    except LayoutError as exc:
        sys.stderr.write(f"layout error: {exc}\n")
        return 2
    out = sys.stdout
    for violation in violations:
        out.write(f"layout violation: {violation}\n")
    if violations:
        count = len(violations)
        msg = f"{count} layout violation(s); see .repo-layout.yml and CONTRIBUTING.md"
        out.write(msg + "\n")
        return 1
    out.write("layout OK\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
