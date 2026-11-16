"""Offline provenance check for the pinned uploader image (issue #100).

The upload workflow runs a container image pinned by digest. Nothing used to
tie that digest to the reviewed engine code: a fix could merge while the
workflow kept running an older image. This checker compares a release
descriptor (docs/image-release.md) with the repository:

* the descriptor digest is the IMAGE pin of the upload workflow;
* every file the Dockerfile COPYs is listed with the sha256 of the repo file;
* the descriptor lists no file the Dockerfile does not COPY;
* ENTRYPOINT and the entrypoint.sh destination match the descriptor;
* every `docker run` in the upload workflow targets "$IMAGE" and only calls
  /opt scripts the image contains;
* engine_revision is a full commit whose blobs hash to the descriptor, when
  that commit is available locally (fail closed when it is not, unless the
  caller allows it explicitly).

Standard library only. It reads files and, for the revision check, runs
`git show` on the local repository. No network, registry, Docker or Geni.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

SCHEMA = 1
IMAGE_RE = re.compile(r"^ghcr\.io/reihlinstinct/geni-uploader@sha256:[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
WORKFLOW = ".github/workflows/geni-upload.yml"
DESCRIPTOR_KEYS = {"schema", "image", "engine_revision", "entrypoint", "files"}


class ProvenanceError(Exception):
    """A descriptor does not match the repository. Messages carry no file content."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _logical_lines(text: str) -> list[str]:
    """Join backslash-continued lines, as the shell would."""
    out: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        out.append(buf + line)
        buf = ""
    if buf:
        out.append(buf)
    return out


def dockerfile_layout(text: str) -> tuple[dict[str, str], str]:
    """Return ({image path: repo path} for COPY, ENTRYPOINT path)."""
    copies: dict[str, str] = {}
    entrypoint = None
    for line in _logical_lines(text):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        word, _, rest = stripped.partition(" ")
        word = word.upper()
        if word in ("COPY", "ADD"):
            parts = shlex.split(rest)
            if word == "ADD" or any(p.startswith("--") for p in parts) or len(parts) != 2:
                raise ProvenanceError(f"unsupported {word} form; use plain 'COPY <file> <path>'")
            src, dest = parts
            if dest in copies:
                raise ProvenanceError(f"duplicate COPY destination {dest}")
            copies[dest] = src
        elif word == "ENTRYPOINT":
            try:
                value = json.loads(rest)
            except json.JSONDecodeError:
                raise ProvenanceError("ENTRYPOINT must be exec (JSON) form") from None
            if not (isinstance(value, list) and len(value) == 1 and isinstance(value[0], str)):
                raise ProvenanceError("ENTRYPOINT must name exactly one executable")
            entrypoint = value[0]
    if entrypoint is None:
        raise ProvenanceError("Dockerfile has no ENTRYPOINT")
    return copies, entrypoint


def workflow_image(text: str) -> str:
    pins = re.findall(r"^\s*IMAGE:\s*(\S+)\s*$", text, flags=re.MULTILINE)
    if len(pins) != 1:
        raise ProvenanceError(f"expected exactly one IMAGE pin in {WORKFLOW}, found {len(pins)}")
    return pins[0].strip("'\"")


def _uncommented(text: str) -> list[str]:
    return [line for line in _logical_lines(text) if not line.lstrip().startswith("#")]


def workflow_runs(text: str) -> list[list[str]]:
    """One token list per `docker run`, so runs chained on one line are checked separately."""
    runs = []
    for line in _uncommented(text):
        tokens = line.split()
        starts = [i for i in range(len(tokens) - 1) if tokens[i:i + 2] == ["docker", "run"]]
        for n, start in enumerate(starts):
            end = starts[n + 1] if n + 1 < len(starts) else len(tokens)
            runs.append(tokens[start:end])
    return runs


def check_runs(runs: list[list[str]], image_paths: set[str]) -> None:
    if not runs:
        raise ProvenanceError("upload workflow has no docker run")
    for tokens in runs:
        targets = [t for t in tokens if t in ('"$IMAGE"', '"${IMAGE}"')]
        if len(targets) != 1:
            raise ProvenanceError("every docker run must target the pinned \"$IMAGE\" once")
        if any(re.search(r"(ghcr\.io|docker\.io)/|@sha256:|:latest\b", t) for t in tokens):
            raise ProvenanceError("docker run names an image other than the pinned \"$IMAGE\"")
        scripts = {t.strip("'\"") for t in tokens if re.fullmatch(r"['\"]?/opt/[\w.-]+['\"]?", t)}
        for script in sorted(scripts):
            if script not in image_paths:
                raise ProvenanceError(f"docker run calls {script}, which the image does not contain")
        if "--entrypoint" in tokens:
            at = tokens.index("--entrypoint")
            override = tokens[at + 1] if at + 1 < len(tokens) else None
            if override != "python" or not scripts:
                raise ProvenanceError("an --entrypoint override must be python with an /opt script")


def load_descriptor(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ProvenanceError("descriptor is missing or not valid JSON") from None
    if not isinstance(data, dict) or set(data) != DESCRIPTOR_KEYS:
        raise ProvenanceError(f"descriptor keys must be exactly {sorted(DESCRIPTOR_KEYS)}")
    if data["schema"] != SCHEMA:
        raise ProvenanceError(f"unsupported descriptor schema (expected {SCHEMA})")
    if not isinstance(data["image"], str) or not IMAGE_RE.fullmatch(data["image"]):
        raise ProvenanceError("descriptor image must be the uploader repository pinned by digest")
    rev = data["engine_revision"]
    if not isinstance(rev, str) or not REVISION_RE.fullmatch(rev):
        raise ProvenanceError("engine_revision must be a full 40-hex commit")
    if not isinstance(data["entrypoint"], str):
        raise ProvenanceError("descriptor entrypoint must be a path")
    files = data["files"]
    if not isinstance(files, dict) or not files:
        raise ProvenanceError("descriptor files must be a non-empty object")
    for dest, digest in files.items():
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            raise ProvenanceError(f"descriptor hash for {dest} is not a sha256 hex digest")
    return data


def _git_blob(root: Path, rev: str, path: str) -> bytes | None:
    proc = subprocess.run(
        ["git", "-C", str(root), "show", f"{rev}:{path}"],
        capture_output=True,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def _commit_available(root: Path, rev: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{rev}^{{commit}}"],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def check(
    root: Path,
    descriptor_path: Path,
    allow_missing_revision: bool = False,
    *,
    check_pin: bool = True,
) -> list[str]:
    """Raise ProvenanceError on the first mismatch; return value-free notes on success.

    ``check_pin=False`` is only for publish-image, which describes an image
    that is not pinned yet; every other check still runs.
    """
    desc = load_descriptor(descriptor_path)
    copies, entrypoint = dockerfile_layout((root / "Dockerfile").read_text(encoding="utf-8"))
    workflow = (root / WORKFLOW).read_text(encoding="utf-8")

    notes = []
    if not check_pin:
        notes.append("IMAGE pin NOT checked (image not pinned yet)")
    elif workflow_image(workflow) != desc["image"]:
        raise ProvenanceError("workflow IMAGE pin differs from the descriptor digest")

    listed, copied = set(desc["files"]), set(copies)
    if listed != copied:
        extra = sorted(listed - copied)
        missing = sorted(copied - listed)
        raise ProvenanceError(f"descriptor files differ from Dockerfile COPY: "
                              f"not copied {extra}, not described {missing}")

    if entrypoint != desc["entrypoint"]:
        raise ProvenanceError("Dockerfile ENTRYPOINT differs from the descriptor")
    if copies.get(entrypoint) != "entrypoint.sh":
        raise ProvenanceError("ENTRYPOINT is not the entrypoint.sh copied into the image")

    for dest, src in sorted(copies.items()):
        try:
            actual = sha256_bytes((root / src).read_bytes())
        except OSError:
            raise ProvenanceError(f"COPY source {src} is missing") from None
        if actual != desc["files"][dest]:
            raise ProvenanceError(f"{src} differs from the image's {dest}: the image is stale")

    runs = workflow_runs(workflow)
    check_runs(runs, copied)
    # An --entrypoint hidden in an argument array would bypass check_runs.
    in_runs = sum(tokens.count("--entrypoint") for tokens in runs)
    if sum(line.count("--entrypoint") for line in _uncommented(workflow)) != in_runs:
        raise ProvenanceError("--entrypoint may only appear literally on a docker run line")

    rev = desc["engine_revision"]
    if _commit_available(root, rev):
        for dest, src in sorted(copies.items()):
            blob = _git_blob(root, rev, src)
            if blob is None or sha256_bytes(blob) != desc["files"][dest]:
                raise ProvenanceError(f"{src} at engine_revision does not match the descriptor")
        notes.append("engine_revision verified against local git objects")
    elif allow_missing_revision:
        notes.append("engine_revision not available locally; revision blobs NOT verified")
    else:
        raise ProvenanceError("engine_revision is not available locally (fetch more history)")
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("descriptor", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--allow-missing-revision", action="store_true")
    args = parser.parse_args(argv)
    try:
        notes = check(args.root, args.descriptor, args.allow_missing_revision)
    except ProvenanceError as exc:
        print(f"image provenance: FAIL: {exc}", file=sys.stderr)
        return 1
    print("image provenance: OK" + "".join(f"\n- {n}" for n in notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
