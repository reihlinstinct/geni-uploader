"""Fake GitHub JSON responses only. No remote ledger or credentials."""

import copy
import hashlib

import pytest

from geni_uploader.core.merge_request import InvalidMergeRequest
from geni_uploader.workflow.merge_claims import PrivateGitClaims
from geni_uploader.workflow.merge_git_store import GitHubClaimBackend

SIGNATURE = "-----BEGIN PGP SIGNATURE-----\nZZ synthetic only\n-----END PGP SIGNATURE-----\n"


class GitAPI:
    def __init__(self):
        self.head = "a" * 40
        self.entries = []
        self.calls = []
        self.private = True
        self.truncated = False
        self.verified = True
        self.contended = False
        self.ambiguous = False
        self.payload = None
        self.pending_entry = None

    @property
    def tree(self):
        raw = b"".join(
            b"100644 " + entry["path"].encode() + b"\0" + bytes.fromhex(entry["sha"])
            for entry in sorted(self.entries, key=lambda entry: entry["path"])
        )
        return hashlib.sha1(b"tree %d\0" % len(raw) + raw).hexdigest()

    def __call__(self, method, path, body):
        self.calls.append((method, path, copy.deepcopy(body)))
        suffix = path.removeprefix("/repos/ZZOwner/ZZLedger")
        if method == "GET":
            if suffix == "":
                return {"full_name": "ZZOwner/ZZLedger", "private": self.private}
            if suffix == "/git/ref/heads/ZZ-ledger":
                return {
                    "ref": "refs/heads/ZZ-ledger",
                    "object": {"type": "commit", "sha": self.head},
                }
            if suffix == "/git/commits/" + self.head:
                return {"sha": self.head, "tree": {"sha": self.tree}}
            if suffix == "/git/trees/" + self.tree:
                return {
                    "sha": self.tree,
                    "tree": copy.deepcopy(self.entries),
                    "truncated": self.truncated,
                }
        if method == "POST" and suffix == "/git/trees":
            assert body["base_tree"] == self.tree
            assert len(body["tree"]) == 1
            self.pending_entry = {k: v for k, v in body["tree"][0].items() if k != "content"}
            content = body["tree"][0]["content"].encode()
            self.pending_entry["sha"] = hashlib.sha1(
                b"blob %d\0" % len(content) + content
            ).hexdigest()
            entries = sorted(self.entries + [self.pending_entry], key=lambda entry: entry["path"])
            raw = b"".join(
                b"100644 " + entry["path"].encode() + b"\0" + bytes.fromhex(entry["sha"])
                for entry in entries
            )
            self.pending_tree = hashlib.sha1(b"tree %d\0" % len(raw) + raw).hexdigest()
            return {"sha": self.pending_tree}
        if method == "POST" and suffix == "/git/commits":
            assert body["parents"] == [self.head]
            assert body["signature"] == SIGNATURE
            headers, message = self.payload.split("\n\n", 1)
            raw = (
                headers
                + "\ngpgsig "
                + SIGNATURE.rstrip("\n").replace("\n", "\n ")
                + "\n\n"
                + message
            ).encode()
            self.pending_commit = hashlib.sha1(b"commit %d\0" % len(raw) + raw).hexdigest()
            return {
                "sha": self.pending_commit,
                "tree": {"sha": body["tree"]},
                "parents": [{"sha": self.head}],
                "verification": {
                    "verified": self.verified,
                    "payload": self.payload,
                    "signature": SIGNATURE,
                },
            }
        if method == "PATCH" and suffix == "/git/refs/heads/ZZ-ledger":
            assert body == {"sha": self.pending_commit, "force": False}
            if self.contended:
                raise OSError("ZZ conflict")
            self.head = self.pending_commit
            self.entries.append(self.pending_entry)
            if self.ambiguous:
                raise OSError("ZZ lost response after accepted reference")
            return {"ref": "refs/heads/ZZ-ledger", "object": {"sha": self.head}}
        raise AssertionError("ZZ unexpected request")


def backend(api):
    def sign(payload):
        api.payload = payload.decode()
        return SIGNATURE

    return GitHubClaimBackend(
        api,
        sign,
        "ZZOwner/ZZLedger",
        "ZZ-ledger",
        {"name": "ZZSigner", "email": "ZZ@example.invalid"},
        lambda: 1800000000,
    )


# Section: Signed append, restart exclusion and ambiguous responses


def test_append_is_hash_only_signed_and_never_forced():
    api = GitAPI()
    assert PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64)
    assert api.entries[0]["path"] == "1" * 64 + ".json"
    tree_request = next(
        body for method, path, body in api.calls if method == "POST" and path.endswith("/trees")
    )
    assert '"binding_sha256":"' + "2" * 64 in tree_request["tree"][0]["content"]
    assert "author ZZSigner <ZZ@example.invalid> 1800000000 +0000" in api.payload
    assert api.payload.endswith("\n\nClaim explicit merge operation\n")
    assert PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64) is False
    assert sum(method == "PATCH" for method, _, _ in api.calls) == 1


def test_lost_ref_response_keeps_claim_after_restart_without_retry():
    api = GitAPI()
    api.ambiguous = True
    with pytest.raises(InvalidMergeRequest):
        PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64)
    api.ambiguous = False
    assert PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64) is False
    assert sum(method == "PATCH" for method, _, _ in api.calls) == 1


def test_contention_is_terminal_without_force_or_retry():
    api = GitAPI()
    api.contended = True
    with pytest.raises(InvalidMergeRequest):
        PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64)
    assert sum(method == "PATCH" for method, _, _ in api.calls) == 1
    assert not api.entries


# Section: Fail-closed object and signing checks


@pytest.mark.parametrize("field", ["private", "truncated", "verified"])
def test_bad_privacy_tree_or_signature_never_moves_ref(field):
    api = GitAPI()
    setattr(api, field, field == "truncated")
    with pytest.raises(InvalidMergeRequest):
        PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64)
    assert not any(method == "PATCH" for method, _, _ in api.calls)


def test_extra_or_malformed_tree_entry_blocks_without_writes():
    api = GitAPI()
    api.entries = [
        {"mode": "100644", "type": "blob", "path": "ZZ-unexpected.json", "sha": "c" * 40}
    ]
    with pytest.raises(InvalidMergeRequest):
        PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64)
    assert all(method == "GET" for method, _, _ in api.calls)


def test_signature_payload_mismatch_never_moves_ref():
    api = GitAPI()
    store = backend(api)

    def wrong_sign(payload):
        api.payload = "ZZ altered"
        return SIGNATURE

    store.signer = wrong_sign
    with pytest.raises(InvalidMergeRequest):
        PrivateGitClaims(store).claim("1" * 64, "2" * 64)
    assert not any(method == "PATCH" for method, _, _ in api.calls)


def test_consumed_snapshot_cannot_append_again():
    api = GitAPI()
    store = backend(api)
    head, _ = store.snapshot()
    assert store.compare_and_append(
        head, "1" * 64, {"binding_sha256": "2" * 64, "phase": "CLAIMED"}
    )
    count = len(api.calls)
    with pytest.raises(InvalidMergeRequest):
        store.compare_and_append(head, "3" * 64, {"binding_sha256": "2" * 64, "phase": "CLAIMED"})
    assert sum(method == "PATCH" for method, _, _ in api.calls) == 1

    assert len(api.calls) == count


# Section: Isolated response guards and content-addressed object checks


def _entry(**changes):
    return {
        "mode": "100644",
        "type": "blob",
        "path": "3" * 64 + ".json",
        "sha": "c" * 40,
        **changes,
    }


@pytest.mark.parametrize(
    "suffix,change",
    [
        ("", {"full_name": "ZZOther/ZZLedger"}),
        ("/git/ref/heads/ZZ-ledger", {"ref": "refs/heads/ZZ-other"}),
        ("/git/ref/heads/ZZ-ledger", {"object": None}),
        ("/git/ref/heads/ZZ-ledger", {"object": {"type": "blob", "sha": "a" * 40}}),
        ("/git/ref/heads/ZZ-ledger", {"object": {"type": "commit", "sha": "ZZ-invalid"}}),
        ("/git/commits/" + "a" * 40, {"sha": "f" * 40}),
        ("/git/commits/" + "a" * 40, {"tree": None}),
        ("/git/commits/" + "a" * 40, {"tree": {"sha": "ZZ-invalid"}}),
        ("/git/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904", {"sha": "f" * 40}),
        ("/git/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904", {"tree": None}),
        (
            "/git/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            {"tree": [_entry(path=f"{i:064x}.json") for i in range(1001)]},
        ),
        ("/git/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904", {"tree": [_entry(mode="100755")]}),
        ("/git/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904", {"tree": [_entry(type="tree")]}),
        ("/git/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904", {"tree": [_entry(), _entry()]}),
        (
            "/git/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904",
            {"tree": [_entry(sha="ZZ-invalid")]},
        ),
        ("/git/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904", {"tree": [None]}),
    ],
)
def test_each_snapshot_response_guard_prevents_all_writes(suffix, change):
    api = GitAPI()

    def altered(method, path, body):
        result = api(method, path, body)
        if method == "GET" and path == "/repos/ZZOwner/ZZLedger" + suffix:
            result.update(change)
        return result

    store = backend(api)
    store.api = altered
    with pytest.raises(InvalidMergeRequest):
        store.snapshot()
    assert all(method == "GET" for method, _, _ in api.calls)
    assert store.cached is None


@pytest.mark.parametrize(
    "method,suffix,change,patches",
    [
        ("POST", "/git/trees", {"sha": "b" * 40}, 0),
        ("POST", "/git/trees", {"sha": "ZZ-invalid"}, 0),
        ("POST", "/git/commits", {"sha": "f" * 40}, 0),
        ("POST", "/git/commits", {"verification": None}, 0),
        (
            "POST",
            "/git/commits",
            {"verification": {"verified": True, "payload": "ZZ-other", "signature": SIGNATURE}},
            0,
        ),
        ("POST", "/git/commits", {"tree": {"sha": "f" * 40}}, 0),
        ("POST", "/git/commits", {"tree": None}, 0),
        ("POST", "/git/commits", {"tree": "ZZ-other"}, 0),
        ("POST", "/git/commits", {"parents": None}, 0),
        ("POST", "/git/commits", {"parents": []}, 0),
        ("POST", "/git/commits", {"parents": [{"sha": "f" * 40}]}, 0),
        ("POST", "/git/commits", {"parents": [None]}, 0),
        ("POST", "/git/commits", {"parents": ["ZZ-other"]}, 0),
        ("PATCH", "/git/refs/heads/ZZ-ledger", {"ref": "refs/heads/ZZ-other"}, 1),
        ("PATCH", "/git/refs/heads/ZZ-ledger", {"object": {"sha": "f" * 40}}, 1),
        ("PATCH", "/git/refs/heads/ZZ-ledger", {"object": None}, 1),
    ],
)
def test_each_append_response_guard_stops_without_retry(method, suffix, change, patches):
    api = GitAPI()

    def altered(verb, path, body):
        result = api(verb, path, body)
        if verb == method and path.endswith(suffix):
            result.update(change)
        return result

    store = backend(api)
    store.api = altered
    signed = []
    original_signer = store.signer

    def sign(payload):
        signed.append(payload)
        return original_signer(payload)

    store.signer = sign
    head, _ = store.snapshot()
    with pytest.raises(InvalidMergeRequest):
        store.compare_and_append(head, "1" * 64, {"binding_sha256": "2" * 64, "phase": "CLAIMED"})
    assert sum(verb == "PATCH" for verb, _, _ in api.calls) == patches
    assert store.cached is None
    if suffix == "/git/trees":
        assert not signed
        assert not any(
            verb == "POST" and path.endswith("/git/commits") for verb, path, _ in api.calls
        )


def test_response_signature_mismatch_stops_before_patch():
    api = GitAPI()

    def altered(method, path, body):
        result = api(method, path, body)
        if method == "POST" and path.endswith("/git/commits"):
            result["verification"]["signature"] = "ZZ-other"
        return result

    store = backend(api)
    store.api = altered
    with pytest.raises(InvalidMergeRequest):
        PrivateGitClaims(store).claim("1" * 64, "2" * 64)
    assert not any(method == "PATCH" for method, _, _ in api.calls)


@pytest.mark.parametrize("kind", ["head", "present", "cap"])
def test_snapshot_preconditions_make_no_append_requests(kind):
    api = GitAPI()
    if kind == "present":
        api.entries = [_entry(path="1" * 64 + ".json")]
    if kind == "cap":
        api.entries = [_entry(path=f"{i:064x}.json") for i in range(1000)]
    store = backend(api)
    head, _ = store.snapshot()
    count = len(api.calls)
    with pytest.raises(InvalidMergeRequest):
        store.compare_and_append(
            "f" * 40 if kind == "head" else head,
            "1" * 64,
            {"binding_sha256": "2" * 64, "phase": "CLAIMED"},
        )
    assert len(api.calls) == count


@pytest.mark.parametrize(
    "signature",
    [
        None,
        "ZZ-bad",
        "-----BEGIN PGP SIGNATURE-----\nZZ-bad",
        SIGNATURE.replace("\n", "\r\n"),
        SIGNATURE.replace("ZZ synthetic", "ZZ\r synthetic"),
        SIGNATURE.replace("ZZ synthetic", "ZZ\x00 synthetic"),
    ],
)
def test_bad_signature_armor_stops_before_commit(signature):
    api = GitAPI()
    store = backend(api)
    store.signer = lambda payload: signature
    with pytest.raises(InvalidMergeRequest):
        PrivateGitClaims(store).claim("1" * 64, "2" * 64)
    assert not any(
        method == "PATCH" or path.endswith("/git/commits") for method, path, _ in api.calls
    )


def test_signer_exception_is_fixed_and_stops_before_commit():
    api = GitAPI()
    store = backend(api)

    def fail(payload):
        raise OSError("ZZ-private-error")

    store.signer = fail
    head, _ = store.snapshot()
    with pytest.raises(InvalidMergeRequest, match="^private merge ledger signing failed$"):
        store.compare_and_append(head, "1" * 64, {"binding_sha256": "2" * 64, "phase": "CLAIMED"})
    assert not any(
        method == "PATCH" or path.endswith("/git/commits") for method, path, _ in api.calls
    )


def test_object_hash_vectors_match_git_hash_object():
    # Frozen vectors independently generated with git hash-object -t KIND --stdin.
    # No Git executable is needed in the test image.
    from geni_uploader.workflow.merge_git_store import _object_sha, _signed_commit_sha, _tree_sha

    assert _object_sha("blob", b"ZZ-record\n") == "2c69f6189beafc03409c250f49fb515e3470e560"
    assert _tree_sha({"1" * 64: "c" * 40}) == "2a2bfef50a3d56cdef00c8bc93c4b5272b5c02aa"
    payload = (
        "tree "
        + "a" * 40
        + "\nparent "
        + "b" * 40
        + "\nauthor ZZSigner <ZZ@example.invalid> 1800000000 +0000"
        + "\ncommitter ZZSigner <ZZ@example.invalid> 1800000000 +0000\n\nZZ-claim\n"
    ).encode()
    assert _signed_commit_sha(payload, SIGNATURE) == "8370d9e87400367b4c060757ea53a9968983d171"


def test_append_tree_includes_existing_records_in_sorted_order():
    api = GitAPI()
    api.entries = [_entry(path="f" * 64 + ".json"), _entry(path="0" * 64 + ".json")]
    assert PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64)
    assert len(api.entries) == 3
    assert PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64) is False


def test_omitted_existing_claim_listing_blocks_before_any_write():
    api = GitAPI()
    assert PrivateGitClaims(backend(api)).claim("1" * 64, "2" * 64)
    prior_calls = len(api.calls)

    def omit(method, path, body):
        result = api(method, path, body)
        if method == "GET" and "/git/trees/" in path:
            result["tree"] = []
        return result

    store = backend(api)
    store.api = omit
    with pytest.raises(InvalidMergeRequest):
        PrivateGitClaims(store).claim("1" * 64, "2" * 64)
    assert all(method == "GET" for method, _, _ in api.calls[prior_calls:])
    assert sum(method == "PATCH" for method, _, _ in api.calls) == 1
    assert store.cached is None


def test_snapshot_cap_is_independent_of_duplicates_and_hash_binding():
    api = GitAPI()
    api.entries = [_entry(path=f"{i:064x}.json") for i in range(1001)]
    store = backend(api)
    with pytest.raises(InvalidMergeRequest):
        store.snapshot()
    assert store.cached is None
    assert all(method == "GET" for method, _, _ in api.calls)
