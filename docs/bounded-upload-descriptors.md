# Bounded post-upload descriptor admission

Issue #330. Immutable approval/evidence commits do not exist before protected-job
uploads. The local service now accepts only their bounded immutable descriptors
in the authenticated workload request, not a caller repository, path, URL, token
or expected approval record. Workload JWT verification happens first.

A canonical hash-pinned deployment policy supplies the exact private repository
numeric ID, owner/name, two distinct ordinary root filenames, owner/connection/
plan/payload/artifact/policy/run, recipient and secondary credential fingerprint.
The submitted approval descriptor contains only commit, blob ID and SHA256. The
submitted pre-write descriptor must match fixed run/attempt/stage/plan/recipient,
size cap and strict hash shapes. Extra destination or credential fields reject.
Copies are captured before asynchronous readback, so later input mutation cannot
change the constructed pins. No post-upload commit needs pre-run deployment.

Admission constructs internal readback configurations from that policy plus the
untrusted descriptors. The existing independent immutable private Git byte
checks, strict v2 record validation, live protected capture correlation and exact
pre-write readback still run before canonical owner Durable Object consumption.
A descriptor alone grants nothing. A malicious descriptor can cause a bounded
fixed private read and then rejection, never an arbitrary URL or vendor request.

The actual local workerd SQLite rehearsal now omits post-upload commit fields
from deployment configuration and supplies them through the authenticated
request. It still proves one consumption across concurrent requests and restart.
Negative tests cover destination injection, wrong binding/run/stage/recipient,
size/hash errors, credential drift and input mutation. The runtime uses the
correct isolated test runner. All external services remain synthetic fixtures.

No production namespace/configuration, permission, secret, deployment, workflow
run or Geni POST is installed. Authenticated policy provisioning, owner-self and
current graph checks, cumulative durable ledger, full one-POST/readback executor
and separate release/run approval remain open. The existing unconditional local
rehearsal barrier and false POST flags remain unchanged.
