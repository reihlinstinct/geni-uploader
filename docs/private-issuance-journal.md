# Private issuance-attempt exclusion journal (#382)

SUPERSEDED AUTHORITY: the private Git ref described below is evidence only.
The authoritative one-use issuance slot is the canonical owner SQLite state
specified in sqlite-issuance-authority.md. Do not use Git ref creation as the
issuer's permission to sign or retry. Existing code is dormant and must be
rewired to the authoritative receipt before installation.

Dormant module, no production caller. Before signing or changing service config,
a future reviewed issuer reserves one owner-global permanent slot in its fixed
private repository. The ref derives from owner identity ONLY, not plan/run/key.
It points at an orphan commit with one canonical name-free issuance-attempt
record binding operation/run/issuer source. Record metadata is private; it is
not encrypted. No bearer token, key, family names or raw approval enters it.

The module verifies repository numeric identity/private status, then creates
blob/tree/commit and uses create-ref, never PATCH/DELETE/force. Concurrent attempts
may leave unreachable Git objects, but only one ref creation can win. The winner
verifies commit, ref and remote blob bytes. Response loss, existing ref, deadline
or malformed readback stops without retry. Partial opaque IDs and an attempted
flag can be privately inspected; neither a partial nor successful receipt permits
signing/deployment/create by itself. No public stdout or live tests are included.

The slot records an ATTEMPT, not a signed grant or installed config. It is never
reset if later checks fail. A new run/grant cannot override it. Repository/ref
admin mutation can remove a Git slot, so this is not tamper-proof storage. Final
issuer provisioning must lock down ref deletion/update, verify the installed
protection and disclose credential scope limitations; Git write scope alone does
not prove append-only enforcement. The existing DO owner-global consume remains
a separate execution barrier. No private repository is created or touched here.

One operation, bounded <=10 API requests and <=64KiB responses, 10-second total
deadline. Free private storage/runner limits must be checked in the exact action.
A timeout after ref creation can mean the slot is spent. Inspect only; never
retry or infer absence from a failed read. Later explicit revocation may disable
the issuer but must preserve this slot and all intent/evidence state.
