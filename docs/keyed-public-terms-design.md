# Private keyed forbidden-term check (#733, separate security slice)

Status: proposal only. No terms, hashes, keys, workflow or scanner added.
This complements the pattern-only placeholder checker, not a replacement for it.

## Placement and custody

This document: `docs/keyed-public-terms-design.md`. Proposed later Python module stems (use the Python suffix in implementation):
`tools/check_private_terms`, `tests/test_private_terms`, and a separately
reviewed `.github/workflows/private-terms-check.yml`. Public tests use only
canonical synthetic persona fields. Real terms and key remain outside public Git.
No public unkeyed name hashes: low-entropy names can be guessed offline.

Prefer a private term policy plus private HMAC key held in a protected trusted
execution context. The public repository contains only algorithm/schema versions
and synthetic test vectors with a clearly public test key. A production key is
never copied into a PR build, artifact, cache, command argument or log.
Key creation/installation, private policy selection and gating are separate
owner decisions, not effects of this design or its merge.

## Threat boundary

Never check out or execute untrusted PR code with private terms/key available.
A pinned reviewed scanner runs from a trusted immutable revision; candidate
public files are data only. No imports, hooks, repository scripts, plugins,
submodules or symlink traversal from that candidate. Fixed file/byte/token caps
and a finite private policy bound runtime; cap failure blocks the scan.
Fork and ordinary PR CI have no secret and report 'not evaluated', never pass.
A trusted pre-merge result must bind the exact candidate tree and scanner/policy
versions before it can become a required gate. Design that binding before rollout;
never use pull_request_target to execute the PR's scanner with secrets.

## Matching contract

Define one versioned normalization for terms and candidate text: Unicode NFC,
case folding and explicit reviewed Hebrew diacritic/final-letter handling.
Do not guess transliterations; variants are private policy entries. Token and
bounded n-gram sequences handle multi-word terms; punctuation boundaries and
substring exceptions are explicit, not unrestricted substring matching.
Use HMAC-SHA256 with domain separation by policy version and token-sequence length.
Compare constant-time digests. No digest, normalized token or private policy
appears in output. Match output is only public file/line/token position plus a
fixed category. Even these locations can reveal a term by inference; keep full
findings private and emit only a fixed public blocked result for production.

## False positives and failures

Exceptions are private, exact-position and candidate-content-bound with a reason
and expiry; a common word is not globally exempt by accident. Missing policy/key,
wrong versions, stale exact-tree result and unreadable files stop, not bypass.
No automatic baseline growth, policy edits or suppression from document content.

## Acceptance and decisions before implementation

Synthetic tests cover normalization, multi-token boundaries, false positives,
path/byte limits, missing secrets, exact-tree binding and value-free failures.
Mutants disabling keyed hashing, limits, tree binding, fail-closed behavior or
redaction must be killed. Test that malicious candidate scripts never execute.
Owner must choose protected execution/custody and approve the narrow disclosure
surface before enabling a real gate. No live Geni, account or release action.
