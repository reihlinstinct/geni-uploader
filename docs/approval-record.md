# Offline approval-record content check

For #256. Pure module `approval_record.py`. Design follows
`intent-storage-decisions.md` (Decision 1) and `intent-service-auth-design.md`.
No service, route, key, signing, deployment or gate change. Synthetic tests only.

## What it checks

`check(record, expected_pins, expected_approvals, now)` returns a fixed result
with `content_consistent: true`, `authenticated: false`, `post_permitted: false`,
`production_enabled: false` and the record's content hash, or raises `Blocked`.

- **Exact record keys:** `schema_version` (1), `mode`, `production_enabled`
  (False), `pins`, `exclusions` and `approvals`.
- **Pins,** each compared exactly to the caller's expected pins:
  - owner, connection and operation (`single_father_add_parent` only);
  - payload, graph, data, artifact and policy hashes, encryption recipient and
    nonce (64 lowercase hex each);
  - executor, workflow and service commit SHAs (40 hex each);
  - run ID, and run attempt (must be 1);
  - `issued_at` and `expires_at`.
- **Time:** integer seconds. The window must be positive and at most 900
  seconds, and the caller's `now` must satisfy `issued_at <= now < expires_at`.
  No clock is read inside the module.
- **Exclusions:** exactly the fixed list `EXCLUDED_ACTIONS`, which covers every
  write other than the single father add.
- **Approvals:** exactly two, in this order: `owner`, then `human_reviewer`.
  - Each carries an opaque approver reference and an evidence reference, and
    both must match the caller's expected values for that role.
  - The two roles must have different approvers (no self-review) and different
    evidence.

## What it does not prove

Who created the record, that the owner or reviewer really approved, protected
review settings, external provenance, freshness against a trusted clock, or
permission to send any request. Those remain service release blockers. The
record holds no names, tokens or raw data: references and hashes only.
