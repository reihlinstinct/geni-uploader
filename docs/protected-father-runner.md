# Dormant protected job composition (#343)

`runProtectedFatherJob` is a Node-only orchestration function, not a CLI, workflow,
dispatcher or deployment. It composes the existing real private approval writer,
prewrite age encryption/private writer, one authenticated service `/execute`,
postwrite age/private writer and authenticated immutable `/complete` receipt.
The returned status still requires reconciliation, not VERIFIED. The shipped
service's unconditional release gate still rejects before consuming or creating.

The fixed configuration supplies the service HTTPS origin, full execution binding,
pinned prewrite bytes, two evidence storage policies and run. The existing
approval storage configuration binds the captured v2 record by its static plan,
not a pre-dispatch digest of the not-yet-existing approval capture. All three
writes require the same private repository and branch with distinct root files.
Each next writer's parent is the exact verified previous commit, not an arbitrary
caller override. Postwrite accounting starts from the actual prewrite ciphertext
length for this operation. Neither write silently retries a ref conflict.

The caller must supply the existing collector's captured approval bytes and fixed
prewrite bytes in memory, a short-lived workload token from the protected job,
and the private receipt journal callback. No credential collection or logging is
added. Invalid config stops before writes. Response loss after the service execute
attempt has no create retry, including encrypted upload and completion failures.
The service origin is deployment policy, never an input URL from external data.
Responses are bounded, UTF8/JSON and duplicate-key checked with timeout and no
redirects. No raw private result is persisted in plaintext by this module.

The synthetic integration exercises all three real Git writers (33 mocked Git
requests), two mocked service calls and two real age encryptions, then decrypts
both remote ciphertext blobs. Failure tests at execute response, postwrite blob
and final completion prove the execute request occurs once. These are not live
service/vendor calls or proof that the uninstalled workflow can run. CI extends
the already pinned age test step, without permissions changes.

Remaining before release: install a separately reviewed protected workflow and
collector wrapper/OIDC acquisition, authenticate actual deployed configuration,
verify emitted claims, provide durable partial-receipt journaling and read-only
lost-response reconciliation. Full joined test using the actual authenticated
Worker and SQLite object rather than mocked service responses is still required.
Cumulative accounting is per operation; cross-operation budget reservation before
remote writes remains a release requirement. No operational release is claimed.
