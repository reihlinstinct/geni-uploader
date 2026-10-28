# Dedicated token response test

Preparation only until this PR passes reviews and the human approves merge.
Agents do not run this workflow, call Geni or install a secret under this change.

This does NOT create parents or profiles. No tree manifest is loaded. Nothing
is uploaded, tagged, merged or changed in Geni. It makes exactly one attempted
GET to https://www.geni.com/api/user, using only the distinct TOKEN_PROBE_CREDENTIAL
environment secret. It never falls back to the source-uploader credential.
No retries, redirects, proxy, response-body log, identity values or artifact.
The fixed verdict is stored in the PUBLIC GitHub Actions log. Normal GitHub
workflow metadata (actor, commit, timing) is also retained. A successful response
shape is not proof of the tree owner's identity or write permissions. A response
that differs from the limited known shape stops as inconclusive, not invalid.

The user endpoint documents `name` and `account_type`, not profile `id`/`guid`:
https://www.geni.com/platform/developer/help/api?path=user&version=1 . The probe
requires a nonblank string name plus account_type basic, plus or pro. These
values stay in memory and are never logged or compared with any person's name.
Unknown/new account types fail closed as inconclusive. This checks the documented
response shape only, never proof that the credential belongs to the intended
owner or permits a future write.

After review/merge and separate approval to configure the dedicated credential,
the human can run Actions > Token context test (read-only, manual) > Run workflow,
branch master, confirm TEST. Only the personal GitHub account reihl is allowed.
Do not paste the token in a dispatch field, terminal command, email or git file.
The secret is not installed by this PR. It must be saved in the public repo's
Actions environment secret TOKEN_PROBE_CREDENTIAL via a separately approved secure route.
The existing source-uploader workflow is not a substitute for this test.

Stop after one result. HTTP errors, throttling, redirects, missing secret,
unknown response shapes and oversized responses fail closed. No automatic retry;
a fresh run is a new deliberate human decision. Do not share raw output or a
screenshot containing a token. Even OK leaves OWNER_IDENTITY=NOT_VERIFIED.

Offline verification: `python3 -m unittest discover -s tests -p test_token_probe.py -v`. Tests use fake
responses and synthetic ZZ identifiers only, never Geni or a real credential.

This probe adds no create command and accepts no upload manifest.

## Mandatory credential-release protections

Do not create TOKEN_PROBE_CREDENTIAL as a repository or organization secret. It must
exist only in environment token-probe with a selected BRANCH master rule (not a tag),
required reviewer reihl, and administrator bypass disabled. Audit actual saved
rules before installation and before approving a run. A plain repo secret could
be used by a writer in another workflow or branch. Actor checks do not prove
human authorship: an app can act under the same account. Approval must be done
by the human after inspecting the exact run commit. If reihl dispatches and is
the only reviewer, self-review prevention must be off; that is one human taking
two steps, not independent approval. Otherwise a second human must review.

Protect master against direct/force pushes and deletion, require PR approval and
CODEOWNER review with no app bypass. CODEOWNERS must cover /.github/ and
/tools/token-probe/ (and itself through /.github/). Review security-relevant tests/docs too.
The owner must authorize settings changes separately. Do not claim this is configured: this PR changes code only, not repository rules.
A writer or compromised app that changes master, a reviewer that approves malicious
code, or an administrator that weakens the protection can still expose the token.

GitHub public-repository logs, run metadata and fixed verdicts are visible to
anyone. No family data, private repository references, token, identity value or
response body belongs in workflow inputs, code, test data, logs or artifacts.
Public Actions normally avoids private-minute billing limits; verify actual CI
status before promising availability. Existing source-upload secrets are not
modified or used by this workflow, and their presence is not a safety guarantee.

The Bearer header matches the existing client but provider compatibility has not
been live-tested here. An error can be a false negative; stop and inspect safely,
never automatically switch authentication routes or retry.
