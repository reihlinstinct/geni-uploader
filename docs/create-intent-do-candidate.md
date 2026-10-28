# Durable Object create-intent candidate, offline only

Part of #233. This storage-only class is not a DurableObject export, Worker
route, production adapter, authentication policy or execution permit. No binding,
migration, configuration, credential or deployment is changed. Default production
gates stay closed. Backend selection/deployment requires a separate decision.

## Candidate source contract

Official source inspected 28 October 2026:
https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/

Cloudflare documents storage.transaction callback operations through txn.get and
txn.put, and synchronous transactionSync for synchronous SQL/KV operations. This
candidate uses the ASYNC transaction interface only, not async get/put inside a
transactionSync callback. SQLite-backed storage transactions also include direct
storage operations, but this candidate uses the transaction argument explicitly.
It does not configure a namespace or assert runtime durability from fake tests.

The eventual trusted wrapper must route ONE canonical owner to ONE permanent
Durable Object namespace, independently of plan/payload/connection. A caller-
selected/new namespace evades exclusion. No user-provided namespace, connection
label, environment or Plan ID may create an alternate consumption ledger.
Authentication, issuer/reviewer policy, owner authority, approved release pins,
code/data hashes and protected human approval are not implemented by this class.

## Transaction contract

consume checks empty permanent intent at version 0, then atomically writes both
current consumed version 1 and its event:1 snapshot. No reset, TTL, delete or
release method exists. Changing plan, connection or payload never clears owner
consumption. Output always says production_enabled:false and is not permission
to send a POST. A failed/unknown response after commit requires inspection, not
replay. A storage rollback before commit cannot prove a request was never sent;
no Geni transport is present here to make that judgment.

advance checks exact immutable binding and expected version in the same
transaction. It writes current state and a new immutable event snapshot together,
refusing pre-existing event version. Only consumed->acknowledged/uncertain,
acknowledged->verified/uncertain, uncertain->verified via reconcile_verified are
allowed. Known created ID cannot change. Verified is terminal. No ordinary
verify from uncertain, no retry event or automatic repair.

Evidence descriptors are opaque ciphertext SHA256 values. Syntax is not proof
of ciphertext existence, encryption, correct recipient, source authenticity or
retention. Actual encrypted durable object storage, authorized evidence upload
and GET-only reconciliation still need implementation and review. Do not expose
owner IDs/bindings/evidence descriptors publicly. Returned profile links and
source/fact provenance integration remain separate #244 work.

## Tests and unproved properties

The fake backend serializes transactions and rolls back staged writes on throw.
Tests cover concurrent connection/plan variants, first/second-write failure,
lost acknowledgment and fresh class instances on shared fake storage, stale
versions, wrong IDs/bindings, repeated evidence and an independent phase/event
matrix. They prove local semantics under that fake contract, not production
Cloudflare concurrency, disk durability, authentication or encryption.

No deployed backend is provided. Real runtime tests, cross-run exclusion,
storage rollback/restore and administrative trust limits, route authentication,
namespace versioning and encrypted retention are release blockers. Admin restore,
namespace deletion or changed binding can erase history outside this class;
never claim append-only methods protect against an administrator. Any ambiguous
storage outcome blocks the future executor until separately approved read-only
inspection. The candidate cannot be wired into #232 as a trusted permit yet.
