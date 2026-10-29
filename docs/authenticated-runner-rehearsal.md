# Real authenticated runner rehearsal (#346)

Synthetic integration now joins the protected Node runner, real private Git
writers, actual age encryption, signed workload JWT verification, real service
approval/live capture/owner preflight, real workerd SQLite owner object, the
single fixed synthetic vendor POST/readbacks and immutable completion admission.
The test bundle alone replaces the unconditional release gate. Production source
and release policy are unchanged. Every external HTTP response is synthetic.

The shared in-memory private Git fixture handles actual writer commits, preserved
trees, encrypted blobs and service immutable readback of those same bytes. The
service sees the real submitted descriptors, not fixture descriptors. Two cases
exercise consistent readback and lost profile response. Both permanently consume
once, retain the acknowledged ID, encrypt/persist returned private evidence and
account two immutable ciphertext objects without declaring VERIFIED. Reopening
the actual SQLite persistence retains ledger and receipt. A repeat execute does
not send another POST. Existing runner loss tests cover service response/upload/
completion failure; existing executor tests cover all vendor fault boundaries.

This closes the prior mock-service gap, not operational release. No workflow is
installed, no real JWT or credential is used, no actual namespace is provisioned,
and no Geni request is sent. The test cannot prove deployed configuration, actual
issuer claims, vendor behavior, persistent private journal backing or successful
reconciliation of an unknown live outcome. Those remain release obligations.
