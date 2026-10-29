"""Emit the release descriptor for a freshly built uploader image (issue #100).

publish-image.yml runs this after the push. The hashes come from inside the
built image (`docker run --entrypoint sha256sum "$TAG" <dest>...`), not from
the repository, so the descriptor records what the image actually carries.
Before writing, the descriptor goes through every image_provenance check
except the IMAGE pin (the new image is not pinned yet): the baked files must
hash to the repo files at the build revision, and the file set, entrypoint and
upload-workflow routing must match. The next IMAGE pin PR commits this exact
descriptor and CI runs the strict check against it.

Usage:
  python tools/image_descriptor.py --list-destinations
  python tools/image_descriptor.py --image <ref@sha256:...> --revision <40-hex>
      --hashes <sha256sum output> --out <descriptor.json>

Standard library only. No network, registry, Docker or Geni.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import image_provenance as ip

# `sha256sum` prints "<hex>  <path>" (text mode) or "<hex> *<path>" (binary).
HASH_LINE_RE = re.compile(r"^([0-9a-f]{64}) [ *](/\S+)$")


def destinations(root: Path) -> list[str]:
    copies, _ = ip.dockerfile_layout((root / "Dockerfile").read_text(encoding="utf-8"))
    return sorted(copies)


def parse_hashes(text: str, expected: list[str]) -> dict[str, str]:
    """Map each COPY destination to its baked sha256; refuse anything else."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        m = HASH_LINE_RE.fullmatch(line.strip())
        if not m:
            raise ip.ProvenanceError("hash list has a line that is not sha256sum output")
        digest, path = m.groups()
        if path in found:
            raise ip.ProvenanceError(f"hash list names {path} twice")
        found[path] = digest
    extra = sorted(set(found) - set(expected))
    missing = sorted(set(expected) - set(found))
    if extra or missing:
        raise ip.ProvenanceError(
            f"hash list differs from Dockerfile COPY: not copied {extra}, not hashed {missing}"
        )
    return found


def build(root: Path, image: str, revision: str, hashes_text: str) -> dict:
    _, entrypoint = ip.dockerfile_layout((root / "Dockerfile").read_text(encoding="utf-8"))
    return {
        "schema": ip.SCHEMA,
        "image": image,
        "engine_revision": revision,
        "entrypoint": entrypoint,
        "files": parse_hashes(hashes_text, destinations(root)),
    }


def emit(root: Path, image: str, revision: str, hashes_text: str, out: Path) -> list[str]:
    """Build, validate (all checks but the pin) and write the descriptor."""
    data = build(root, image, revision, hashes_text)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        notes = ip.check(root, Path(tmp), check_pin=False)
    finally:
        os.unlink(tmp)
    out.write_text(text, encoding="utf-8")
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--list-destinations", action="store_true")
    parser.add_argument("--image")
    parser.add_argument("--revision")
    parser.add_argument("--hashes", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.list_destinations:
            print("\n".join(destinations(args.root)))
            return 0
        if not (args.image and args.revision and args.hashes and args.out):
            parser.error("--image, --revision, --hashes and --out are required")
        try:
            hashes_text = args.hashes.read_text(encoding="utf-8")
        except OSError:
            raise ip.ProvenanceError("hash list is missing") from None
        notes = emit(args.root, args.image, args.revision, hashes_text, args.out)
    except ip.ProvenanceError as exc:
        print(f"image descriptor: FAIL: {exc}", file=sys.stderr)
        return 1
    print("image descriptor: OK" + "".join(f"\n- {n}" for n in notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
