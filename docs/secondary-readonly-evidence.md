# Isolated secondary read-only evidence run

Preparation only. No live request is made by merging this PR. A separately
approved operator may dispatch exactly one reviewed run after the release audit
and exact run plan below. This is a narrow exception to human-only operation,
not a general permission to run Geni, refresh credentials or create profiles.

## What it does

Uses only GENI_SECONDARY_ACCESS_TOKEN and private
SECONDARY_PROBE_CONNECTION_JSON. No primary or refresh secret is referenced.
The configuration is the existing connection schema (canonical owner, exact
expected returned name and isolated connection ID); real values stay secret,
never public source or workflow inputs. The runner checks token-self, declared
owner and family focus agree, then bounded observed unions. No guessed IDs,
redirects, proxies or response URLs. At most 20 fixed GET requests, each at
least 10 seconds apart, each at most 1MiB and 30 seconds. No retry or refresh.
401/429/challenge/invalid graph stops. No write method or Geni mutation exists.

Default STRICT requires explicit merge_pending:false. Choosing
ALLOW_UNKNOWN_READ_ONLY explicitly permits only BOTH merge_pending and
merged_into absent, only for this read-only collection. Present null/false-like
invalid merge_pending, true pending or any merge target still stops. Missing
flags stay absent in encrypted output, hence UNKNOWN in the offline reviewer.
Custody opt-in is not read and never supplies this choice. Creation remains
false; hidden-parent completeness, slots, privacy-create and locale remain
unproved. No parents returned does not prove there are none.

A checksum-pinned age binary encrypts the minimal response in memory to the
reviewed PUBLIC recipient. The private key is never supplied to this run.
Only ciphertext is written or uploaded, retained one day. Logs contain fixed
status only, not provider responses/names/IDs/token. GitHub public run metadata,
recipient, policy choice and fixed verdict are public. A recipient reveals a
correlation identifier; no family identity belongs in its label or other inputs.
A failed run may leave an empty temp directory, never raw evidence. A rerun
attempt is refused; a new run requires a fresh deliberate approval.

## Release audit before execution

- Exact merged commit and all referenced actions/binary checksum reviewed.
- Verify environment secondary-readonly-evidence restricts master BRANCH, not
  tags, requires human reviewer reihl, administrator bypass disabled. The agent
  may dispatch only the exact approved plan; the human approves that run after
  inspecting its commit. An actor name is not proof of human authorship.
- Audit that only the intended secondary token is selected. Current repository
  secret scope allows other workflows to use it; this PR does not fix or widen
  that existing residual risk. Never claim per-secret environment isolation for
  a token that remains repository-scoped. Moving it is a separate custody change.
- Save canonical connection/name privately under the environment config secret,
  only after separate authority to configure it. Verify actual saved rules and
  secret metadata. This PR changes no settings or secrets.
- Confirm age PUBLIC recipient and that the human can retain/recover its private
  key. Never paste private key or token into chat, code or dispatch input.
- Show exact commit, owner/connection (privately), recipient, merge policy,
  bounded request plan, no writes/refresh/retries and known account risk.
- Check subsequent activity to prevent duplicate collection; dispatch once only
  after the authorized operator has seen the exact plan. Keep the protected
  environment review pending until the human decides. Do not bypass it.

## Guided steps, delivered one at a time

1. Confirm tools and generate/retain the age key locally. Send only age1 public
   recipient. Stop if tools are missing until a reviewed install path is chosen.
2. Review exact run plan privately, including explicit STRICT versus
   ALLOW_UNKNOWN_READ_ONLY choice and live account pin. No create approval asked.
3. Authorized operator dispatches reviewed master commit once. Human approves
   the protected environment's exact run. The agent cannot substitute for that.
4. Inspect fixed verdict, encrypted artifact presence and metadata. Human decrypts
   with private key locally through an approved route. Never request the key.
   Any disclosure of decrypted data to a reviewer needs the existing private
   evidence-review scope. Missing key means ciphertext is not readable proof.
5. Stop on error or uncertainty; no automatic rerun. Report what remains unproved.

No upload/create Plan or production readiness is released by this collection.
