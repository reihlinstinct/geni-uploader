# Private runner progress journal (#345)

Dormant Node wrapper `runJournaledFatherJob` creates one exclusive private journal
directory and file before running the existing composition. It does not install a
workflow, acquire credentials or enable the service release gate. Directory 0700,
file 0600, exclusive creation, ordered/fsynced appends and a sequence/hash chain
retain progress after interruption. A reused directory blocks a fresh invocation.
The caller must arrange persistent private storage for that directory; temporary
runner disks are not durable across runner loss. No remote backup is promised.

Only fixed stage names, opaque Git hashes/ref-attempt flags, known created ID and
boolean status are accepted. Approval records, provider responses and credentials
are not journal fields. Before the sole service execute request the runner awaits
a fsynced execute-attempt record; similarly before completion. Failure after that
point is uncertain even if the service may not have received the request. There
is no create retry, reset or resume API. Read-only inspection verifies file mode,
bounds, sequence/hash chain and same run/config. Partial last line or tampering
blocks inspection rather than silently dropping evidence. A hash chain detects
accidental corruption, not hostile rewriting by someone who controls the disk.

Tests exercise concurrent queued appends, close/reopen, changed bytes, partial
last line, forbidden secret/provider fields and blocked fresh invocation. The
actual runner test journals all three private writers/two real age encryptions,
then inspects the journal and proves a second invocation sends no create request.
External HTTP remains mocked. No production configuration, deployment or call.

Still required: persistent private journal storage provisioning; read-only vendor
reconciliation under explicit recovery scope for lost service responses; complete
authenticated Worker/SQLite joined rehearsal. This local journal does not recover
private evidence the service never returned, prove a provider outcome, or declare
VERIFIED. Those are release blockers, not automatic recovery actions.
