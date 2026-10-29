# Exact-head review attribution choices (#425)

Design only. No account, App, signing key, secret, permission, deployment,
workflow or release-policy change. Independent exact-head engineering review,
green CI and normal signed merge remain required. This document does not choose
an issuer trust policy or install a new human ceremony.

## The actual gap

Current engineering reviews can be independently performed while sharing a
GitHub account for comments/merges. The issuer cannot establish that independence
from that account's comment, APPROVED state or a content hash. Source/CI capture
correctly returns independent_review_verified:false. Adding a second username or
key that the author/deployer can use does not create meaningful separation.

Distinguish owner consent to an exact operation/run from code review and from
cryptographically attributable evidence. The existing sole reviewer GitHub
account plus2FA supports account approval, not technical code inspection or
interactive-presence proof. No automation may hold/use its PAT/OAuth/session.

## Options to put to the owner when this becomes the blocker

### A. Existing owner exact-run approval is the release decision of record

Retain independently performed agent review as an engineering process and its
private evidence, exact-head green CI and signed normal merge. At release the
owner's existing approval accepts the named immutable package/plan/risk/run.
Issuer verifies that account approval and package/source/CI/install pins, but
does NOT claim to have independently authenticated the agent code reviewer.
No extra account/key or extra human click is needed for review attribution.

This is viable only if the owner explicitly chooses this lower assurance model:
release may rely on process-level agent review that a malicious shared-credential
author/deployer could falsely describe. The approval UI must show that limit and
the exact package/source/diff/review-evidence references. The owner is accepting
release risk, not automatically asserting they personally read the code. Do not
rename this as verified independent code review or set its false flag true.

This changes the earlier issuer requirement that all review provenance checks
pass. A reviewed versioned policy would explicitly accept owner release consent
plus process-level review, with a distinct assurance label, while keeping code
review gates for merges. The current v2 content format has code_review role and
principal-separation checks; do not insert the owner ID into that field or delete
those checks ad hoc. Separate consent/review assurance semantics through review
and compatibility tests. Until an explicit owner choice and policy revision,
the issuer's automated independent-review proof remains a blocker.

### B. A distinct GitHub reviewer principal

A reviewer account/App with exclusive authentication submits an exact-head review
or bounded receipt. Author/deployer must not control its credentials, ability to
impersonate it, or reviewer policy. Pin numeric identity, repository, exact commit
and current review state; account name/display text is not identity. Resolve
review-to-source and reviewed-source-to-merge binding separately. A dismissed or
wrong-head approval never carries forward automatically.

This can automate account-level attribution but cannot prove the quality or
independence of reasoning. Account administrators and compromised reviewer code
remain risks. A principal created in the author's credential domain supplies no
separation. Actual independent control/capability is unverified; account/App and
permission provisioning require exact approval. No extra human is necessarily
required if a supported independent automated reviewer owns that principal.

### C. A signed exact-head reviewer receipt with exclusive custody

Recommended if machine-verifiable independent review attribution is mandatory,
but only after actual exclusive reviewer custody is established. Use a dedicated
review key held outside author/deployer/release-signer control, not the commit GPG
or release key and not another file accessible to the author. Reviewer signs only
its own reviewed result; never accepts author-supplied PASS as fact. Pin verifier
public key and reviewer identity through separately approved installation/audit.
No supported separate custody mechanism has yet been established here.

Receipt has a domain prefix and version, policy ID, exact repository numeric ID,
reviewed commit/tree/bundle hashes, diff base, scoped test evidence hashes,
reviewer principal, explicit PASS decision, issued/expiry bounds and revocation
scope. No generic arbitrary-message signing endpoint. Verify signature/canonical
encoding, freshness, expected head/diff/artifact and reviewer distinctness. A
receipt for an old head, merge-conflict fix or another build is not transferable.
Maintain read-only durable evidence and disable new acceptance on revocation.

A signature proves that key signed those bytes, not good judgment, absence of
collusion or source/install provenance. A provider admin who controls reviewer
code/key remains trusted. Costs, supported custody/isolation and recovery must
be verified; never create resources, enable billing or promise free operation
merely because key signing is cheap. This is more implementation/custody work,
not a cryptographic replacement for the owner exact-run approval.

## Shared constraints whichever model is selected

- Preserve all permanent issuance/grant/intent barriers and no retry/reset.
- Keep exact immutable package/source/run/attempt/namespace/config/expiry pins.
- Reviewed source head, GitHub CI test-merge head and signed merge/deployed bundle
  are distinct objects. Prove the approved relation; do not equate SHA strings.
- GitHub signature verification is GitHub's attestation, not pinned GPG proof.
- No changes to OAuth service, no public signing key custody, no broad token.
- Exact provisioning and subsequent release/live action approvals remain separate.

## One clear question, deferred until needed

For the release, is the existing exact-run owner approval enough to accept the
package and the disclosed process-level agent review, or must the issuer verify
a separately attributable reviewer receipt as an additional technical gate?

If the former, choose A and review an honest lower-assurance policy revision.
If the latter, first establish whether B or C has real independent custody and
verified nonbillable capacity, then show the exact provisioning action. Do not
ask the owner to choose a fictional already-available capability. Neither choice
waives independent engineering review or owner approval for the actual operation.

## Current official source context

- https://docs.github.com/en/rest/pulls/reviews
- https://docs.github.com/en/rest/commits/commits
- https://docs.github.com/en/rest/checks/runs
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user
