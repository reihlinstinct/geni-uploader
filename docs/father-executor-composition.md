# Fixture-only father composition (#297)

`execute_fixture(plan, boundaries, now)` accepts an EXACT FixtureBoundaries type,
not subclasses, URLs or tokens. The fixture holder can monkeypatch attributes
(including methods); this is a test seam, NOT a security sandbox for hostile Python. It has no HTTP, process, credential or
private-writer access. `execute_production()` always calls the unchanged closed
gate. The artifact is an ordering/failure rehearsal, NOT a runnable create tool.

Only existing approved name-payload fields, direct-source names/relationship and
reviewed control facts pass. No dates, places, biography, sources or research
fields. male/private controls required; supplied provenance is fixture content,
not actual authenticated owner/source proof. Sources remain pending.

Order: exact plan/payload/time/preflight/result-shape checks; canonical-owner
fixture CAS; pre-write evidence store; at most one fixture POST; acknowledgment
store; exact name/privacy/life/child/single-parent readback; readback store; result
store with vendor-supplied distinct profile ID/URL. UNKNOWN stays UNKNOWN and
needs an explicit supplied risk flag; adverse status blocks. That flag is NOT
an authenticated real risk approval. Fault after consume never resets it and
has only GET-only human reconciliation next action. Changed run hash cannot
bypass consumed owner. Pre-write evidence must store before fixture POST.

The in-memory set is NOT durable/shared production CAS and not sufficient for
multiple processes. Stores are digest-event simulations, NOT encryption/private
Git persistence. Actual vendor response/privacy/union shape remains unproved;
synthetic expected fields are never a vendor API claim. Real identity/workload,
approval ceremony, reviewed deployment config (#304), service authentication,
permanent owner-global DO, encryption/writer and final private status integration
still need composition. These deliberate gaps must not be hidden by a successful
fixture. No Geni operation, environment, dispatch, release or deployment occurs.

40tests cover14boundary faults (including lost consume/POST/store outcome),
readback identity/payload/parent mismatch, source provenance, fresh graph/time,
owner replay and gate closure. Full Python2842tests plus7subtests pass. Sixteen
individual guard-removal mutants executed/killed (eight original plus eight review): male, freshness, origin,
owner, parent set, payload readback, child and replay; production flag, direct post
consumption, now exact type, pre-consumption result validation, ack identity,
readback exact keys, final result validation and copied observed nested data. The expected result
profile URL comes from fixture/vendor input, never built from API profile ID.
