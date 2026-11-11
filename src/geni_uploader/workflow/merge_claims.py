"""Private Git compare-and-append claim protocol. No remote transport is installed."""

import re

from geni_uploader.core.merge_request import InvalidMergeRequest

# Section: Atomic private ledger contract


class PrivateGitClaims:
    """Use a separately reviewed backend with atomic non-force reference updates.

    snapshot returns (head, claims). compare_and_append must append one hash-only
    record with parent=head, atomically fail on contention and never force, delete,
    overwrite or reset. Merely creating Git objects does not acquire a claim.
    Repository privacy/ref protection and trusted backend binding are release gates.
    """

    def __init__(self, backend):
        self.backend = backend

    def claim(self, operation_sha256, binding_sha256):
        for value in (operation_sha256, binding_sha256):
            if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
                raise InvalidMergeRequest("invalid merge claim")
        try:
            head, records = self.backend.snapshot()
            if type(head) is not str or not re.fullmatch(r"[a-f0-9]{40}", head):
                raise InvalidMergeRequest("invalid merge ledger head")
            if type(records) is not dict:
                raise InvalidMergeRequest("invalid merge ledger snapshot")
            if operation_sha256 in records:
                return False
            record = {"binding_sha256": binding_sha256, "phase": "CLAIMED"}
            # Contention is terminal for this run, not a reason to retry a write.
            return self.backend.compare_and_append(head, operation_sha256, record) is True
        except Exception:  # noqa: BLE001 - fixed-message private backend boundary
            raise InvalidMergeRequest("merge claim unavailable; stop") from None
