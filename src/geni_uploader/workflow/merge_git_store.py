"""Signed hash-only GitHub ledger append backend. No initialization or release wiring."""

import hashlib
import json
import re
from datetime import UTC, datetime

from geni_uploader.core.merge_request import InvalidMergeRequest

# Section: Strict remote object admission


def _require(condition):
    if not condition:
        raise InvalidMergeRequest("private merge ledger blocked")


def _sha(value, length=40):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{" + str(length) + r"}", value)


def _object_sha(kind, content):
    return hashlib.sha1(
        kind.encode() + b" " + str(len(content)).encode() + b"\0" + content
    ).hexdigest()


def _tree_sha(records):
    entries = b"".join(
        b"100644 " + (operation + ".json").encode() + b"\0" + bytes.fromhex(blob)
        for operation, blob in sorted(records.items())
    )
    return _object_sha("tree", entries)


def _signed_commit_sha(payload, signature):
    headers, message = payload.split(b"\n\n", 1)
    signed = headers + b"\ngpgsig " + signature.rstrip("\n").replace("\n", "\n ").encode()
    return _object_sha("commit", signed + b"\n\n" + message)


class GitHubClaimBackend:
    """Injected HTTP and signing functions, with no token lookup or automatic calls.

    api(method, relative_path, body) must use the pinned GitHub origin, reject
    redirects, bound response sizes and make no retries. signer receives exact
    Git commit bytes and returns an armored signature for the configured identity.
    Effective branch protection and authenticated config are release prerequisites.
    """

    def __init__(self, api, signer, repository, branch, identity, clock):
        _require(
            type(repository) is str and re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", repository)
        )
        _require(type(branch) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", branch))
        _require(type(identity) is dict and set(identity) == {"name", "email"})
        _require(
            all(
                type(v) is str and 0 < len(v) <= 200 and not any(c in v for c in "\n\r<>\x00")
                for v in identity.values()
            )
        )
        self.api, self.signer, self.clock = api, signer, clock
        self.root = "/repos/" + repository
        self.ref = "refs/heads/" + branch
        self.identity = dict(identity)
        self.cached = None

    def _request(self, method, suffix, body=None):
        try:
            result = self.api(method, self.root + suffix, body)
            _require(type(result) is dict)
            return result
        except Exception:  # noqa: BLE001 - fixed-message HTTP boundary
            raise InvalidMergeRequest("private merge ledger request failed") from None

    def snapshot(self):
        self.cached = None
        repository = self._request("GET", "")
        _require(repository.get("private") is True)
        _require(repository.get("full_name") == self.root.removeprefix("/repos/"))
        ref = self._request("GET", "/git/ref/" + self.ref.removeprefix("refs/"))
        _require(ref.get("ref") == self.ref)
        obj = ref.get("object")
        _require(type(obj) is dict and obj.get("type") == "commit" and _sha(obj.get("sha")))
        head = obj["sha"]
        commit = self._request("GET", "/git/commits/" + head)
        _require(commit.get("sha") == head)
        tree = commit.get("tree")
        _require(type(tree) is dict and _sha(tree.get("sha")))
        tree_sha = tree["sha"]
        served = self._request("GET", "/git/trees/" + tree_sha)
        _require(served.get("sha") == tree_sha and served.get("truncated") is False)
        entries = served.get("tree")
        _require(type(entries) is list and len(entries) <= 1000)
        records = {}
        for entry in entries:
            _require(
                type(entry) is dict
                and entry.get("mode") == "100644"
                and entry.get("type") == "blob"
            )
            path = entry.get("path")
            _require(type(path) is str and re.fullmatch(r"[a-f0-9]{64}\.json", path))
            _require(_sha(entry.get("sha")) and path[:-5] not in records)
            # The filename's existence alone blocks replay. Old provider bodies
            # never enter the coordinator and no per-record API fan-out is needed.
            records[path[:-5]] = entry["sha"]
        _require(_tree_sha(records) == tree_sha)
        self.cached = (head, tree_sha, dict(records))
        return head, records

    # Section: Single signed append and non-force reference claim

    def compare_and_append(self, head, operation, record):
        _require(self.cached is not None and self.cached[0] == head)
        _require(_sha(operation, 64) and operation not in self.cached[2])
        _require(type(record) is dict and set(record) == {"binding_sha256", "phase"})
        _require(_sha(record["binding_sha256"], 64) and record["phase"] == "CLAIMED")
        _require(len(self.cached[2]) < 1000)
        # Consume the snapshot even if object creation or ref update is uncertain.
        _, base_tree, records = self.cached
        self.cached = None
        content = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        expected_records = {**records, operation: _object_sha("blob", content.encode())}
        expected_tree = _tree_sha(expected_records)
        tree = self._request(
            "POST",
            "/git/trees",
            {
                "base_tree": base_tree,
                "tree": [
                    {
                        "path": operation + ".json",
                        "mode": "100644",
                        "type": "blob",
                        "content": content,
                    }
                ],
            },
        )
        _require(tree.get("sha") == expected_tree)
        stamp = self.clock()
        _require(type(stamp) is int and 0 < stamp < 2**31)
        date = datetime.fromtimestamp(stamp, UTC).isoformat()
        person = {**self.identity, "date": date}
        message = "Claim explicit merge operation\n"
        ident = self.identity["name"] + " <" + self.identity["email"] + ">"
        payload = (
            f"tree {tree['sha']}\nparent {head}\nauthor {ident} {stamp} +0000\n"
            f"committer {ident} {stamp} +0000\n\n{message}"
        ).encode()
        try:
            signature = self.signer(payload)
        except Exception:  # noqa: BLE001 - signing failure must reveal no secret
            raise InvalidMergeRequest("private merge ledger signing failed") from None
        _require(type(signature) is str and len(signature) <= 20000)
        _require(
            signature.startswith("-----BEGIN PGP SIGNATURE-----\n")
            and signature.endswith("-----END PGP SIGNATURE-----\n")
            and "\r" not in signature
            and "\x00" not in signature
        )
        expected_commit = _signed_commit_sha(payload, signature)
        commit = self._request(
            "POST",
            "/git/commits",
            {
                "tree": tree["sha"],
                "parents": [head],
                "message": message,
                "author": person,
                "committer": person,
                "signature": signature,
            },
        )
        _require(commit.get("sha") == expected_commit)
        _require(
            type(commit.get("verification")) is dict
            and commit["verification"].get("verified") is True
        )
        _require(commit["verification"].get("payload") == payload.decode())
        _require(commit["verification"].get("signature") == signature)
        _require(type(commit.get("tree")) is dict and commit["tree"].get("sha") == expected_tree)
        parents = commit.get("parents")
        _require(type(parents) is list and len(parents) == 1)
        _require(type(parents[0]) is dict and parents[0].get("sha") == head)
        updated = self._request(
            "PATCH",
            "/git/refs/" + self.ref.removeprefix("refs/"),
            {"sha": commit["sha"], "force": False},
        )
        _require(updated.get("ref") == self.ref)
        _require(
            type(updated.get("object")) is dict and updated["object"].get("sha") == expected_commit
        )
        return True
