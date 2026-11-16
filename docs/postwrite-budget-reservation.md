# Durable pre-upload ciphertext reservation (#354)

After the one executor response, the protected runner now requests `/reserve`
before age encryption/private Git upload. The same fixed workload JWT/run/plan
routes to the canonical owner object. An uncertain consumed intent and the existing
same-binding run/recipient ledger are required. One transaction derives total from
bounded unique evidence objects and reserves the maximum ciphertext size (1MiB)
only if it fits the 8MiB operation budget. Concurrent/repeated requests admit one
reservation; it survives SQLite restart. No request chooses the amount.

Postwrite immutable receipt admission requires that reservation, same recipient,
run/binding, unchanged prior total and actual ciphertext <= reserved limit. Its
ledger/receipt transaction replaces reserved bytes with actual accounted bytes.
Failed encryption/upload/admission leaves the reservation and consumed intent
intact. There is no release/retry/reset API. This is operation-local accounting,
not a quota over unrelated repositories, credentials, owners or historic runs.
Generic subsequent accounting cannot consume the reserved capacity. The deployed
composition must use only this reviewed runner, not call lower-level writers.

Synthetic actual authenticated runner + SQLite tests now exercise the reservation
between execute and upload, then immutable completion. Executor tests prove
concurrent reservation, restart persistence, duplicate exclusion, malformed ledger,
wrong run and overflow rejection. Provider/readback failures still never retry
create. The create release gate is unchanged; no live request/config/deploy occurs.
