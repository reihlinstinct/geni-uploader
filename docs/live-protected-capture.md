# Static-plan and live protected capture service join

Unreleased integration. No production route, permission or dispatch is installed.
The service no longer requires the whole post-gate approval record in pre-run
configuration. It fetches immutable private record bytes, validates v2 invariants,
recomputes the static plan fingerprint and correlates the record's human decision
against live fixed GitHub API reads for the exact configured run.

The static plan excludes only dynamic run/attempt/time and human capture. It
keeps expected human identity, agent sources, all static pins, risk, revocation,
exclusions and the fixed attempt-one/window policy. A cross-language regression
compares JavaScript to the existing Python collector's exact fingerprint.

The collector and service now share a stable decision binding: repository, run,
attempt, actual job ID, environment, reviewer, dispatcher, executor/workflow path,
static plan, risk and canonical review-response content hash. The service derives
that binding independently from its own live API reads. Raw response hashes and
capture-config hashes remain diagnostic only; API formatting or later mutable
run fields cannot become the human decision identity.

Eight fixed bounded GETs check run identity, current rules and branch policy,
exact one-human review, exactly one in-progress attempt-one job showing the plan,
risk and run, exact immutable reviewed workflow bytes, then current rules again.
The record must bind both human roles to that exact live decision. No timestamp
or job association is invented inside the review API. Single-gate attempt-one
correlation and shared human/application identity remain accepted limits.
Historical rule enforcement and independent-review provenance are not proved by
current settings or workflow hashes. Returned results keep POST disabled.

The actual local workerd SQLite rehearsal joins workload JWT, private v2 bytes,
live capture correlation, immutable pre-write bytes and permanent owner consume
across concurrency/restart. HTTP sources are mocked with synthetic data. The
standalone collector writes only a local private file; authenticated private
record persistence is still required. Real emitted OIDC compatibility, token-self
owner/current graph proof, durable cumulative accounting, fixed one-POST result
handling, exact readback and separately approved release/deployment remain open.

## Private record persistence rehearsal

A local protected-job writer now takes the static plan fingerprint rather than
an unknowable pre-run final-record digest. It writes the captured v2 record only
to fixed reviewed private Git storage, add-only root path, non-force ref update,
with exact immutable remote byte readback. Its returned source matches the
existing private admission descriptor. Eleven response-loss boundaries retain
partial IDs/ref-attempt state and never retry. No live Git write was executed.
The writer invokes the existing full Python v2 validator before write. It still
requires independent review, authenticated provisioning, bounded cumulative
accounting and joined job wiring.
It is not deployed and grants no owner or POST authority.
