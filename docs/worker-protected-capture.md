# Worker protected-capture correlation (#421)

Dormant Worker port, not a deployed route or issuer authority. Validate complete
v2 content record before network, bind operation pins and static plan, verify
exact public run/attempt1, sole in-progress job, current sole reviewer User/id,
no-self-review/no-bypass rules, approval action content hash/decision source and
immutable workflow bytes. Re-read environment/branch rules at the end. Approval
must be fresh before and after capture. No signing, storage reservation or POST.

One transport closure owns eight GETs across six exact official GitHub routes,
under its16fetch/256KiB-response/1MiB-total/depth16/10s ceiling. No pagination,
redirects or retries. Workflow decoded bytes are capped64KiB. Fixed errors never
include credential, config, record or provider output. Credential/fetch/config
are deployment-owned dependencies, not caller-authenticated facts. No production
entrypoint accepts them from public JSON. The test-only endpoint does so solely
to feed synthetic fixtures into workerd without external network.

The returned flags remain historical_protection_verified:false,
independent_review_provenance_verified:false and shared_identity_limit:true.
Current account approval is not proof of an interactive human click or fresh2FA.
No automation may use the reviewer's PAT/OAuth/session. Current API correlation
is not independent code-review provenance or proof of historical protections.

Source signature/review/CI, actual installed namespace/config/Worker identity,
private evidence persistence, OIDC workload verification and exclusive signer
composition remain separate release blockers. Capture does not solve them.
Whole-issuer subrequest and CPU fit must still be measured/proven, with separately
approved provider measurement; fast synthetic local tests are not that proof.

Tests compare the existing Node capture output against workerd for valid and
hostile run/reviewer/rules/job/workflow evidence, then add Worker-only complete
v2 validation, expiry and exact operation-binding rejection. Bundle contains only
capture, pure v2 validator and bounded transport; no Node compatibility. No
resources, secrets, keys, account settings, deploy or live API calls.

## Capture regression integrity

The Worker test deep-copies every response body so late environment/branch
changes cannot mutate the early responses by alias. It changes jobs[0].run_id
independently of job ID/name and advances a test-only clock to exact expiry
while the eighth response is returned. No production clock injection is added.

Negative controls were run individually against the real-workerd suite: deleting
late rules reread, final fresh() or job-to-run comparison each passed the old
test (coverage gap); each now fails the updated test. Unmodified implementation
passes. Production capture bytes are unchanged by these regression repairs.
