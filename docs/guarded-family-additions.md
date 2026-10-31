# Guarded family addition core

This is effect-injected offline code only. It has no credentials, HTTP adapter,
CLI or workflow. It cannot run live from a dispatch. Transport wiring, immutable
private source loading and approval checks require a separate reviewed change.

The core models either one additional female parent or an ordered batch of four
siblings. Each plan pins the owner, existing parent payloads, union and children.
All names are bilingual; living/private fields are mandatory. Dates, places,
photos, merges and unrelated edits are excluded by the payload schema.

Before a create it checks the owner and parents, then the exact union membership.
Each item has a stable payload-bound consume marker, independent of expiry or run
ID. The store must implement atomic create-only markers and immutable encrypted
receipts. Consumption precedes any possible send. The returned ID is saved before
readback. Raw parsed responses are captured through the encrypted save seam before
validation or another effect. Storage failure stops further effects.

After each create, exact profile fields and union partners/children must pass
before the next entry. Failure stops the batch immediately. Prior successful
items remain created; no automatic retry, repair, rollback, deletion or resumption
exists. A new run must not reset or replace old markers.

The vendor's choice of parent union is a live experiment, not proved by docs.
Wrong-union responses stop without repair. Each final approval must name every
create, ordered payload hashes, source/executor/config pins, expiry, possible
hidden duplicate risk, requested-but-unproved privacy and union-selection risk.
The protected run also needs human deployment approval. Offline PASS grants no
permission to execute.
