# Independent setup: supported path and remaining gaps

Status checked 5 November 2026. Documentation reconciliation for #784, not a
new release, an installation audit or permission to access any account. An
existing deployment's successful operation does not prove that another operator's
registration, credentials, settings or selected workflow are ready.

## Choose the path before registering anything

| Path | What exists | What is not established |
|---|---|---|
| Owner-local document/photo upload to existing profiles | Container upload CLI, private data manifest, plan/run, local credential files | This guide is not a completed independent installation test |
| Hosted source upload | Manual workflow with fixed repository and personal actor/triggering-actor checks | Not a general hosted service another operator can invoke unchanged |
| Separate assistant operation or token custody | Privacy disclosure and separately reviewed bootstrap components | Consent alone is not a released independent assistant onboarding route or proof of compliance |
| People/relationship creation | Public bounded protected runner code and deployment-specific pilot paths | No general released independent-user creation CLI in the upload image |

Start with [container usage](usage.md) and the [README private data layout](../README.md#expected-private-repository-structure)
for local uploads. Do not mix the desktop token flow with hosted server-side
OAuth. For custody/hosted design, read [connection boundaries](../oauth-bootstrap/CONNECTIONS.md)
and [custody status](click-only-oauth-custody.md), not just the privacy policy.

## Local GitHub credential scope

The local loader clones the selected private data repository and normally pushes
upload status back to it. A least-privilege candidate for an owner-controlled
repository is a **fine-grained personal access token** with:

- Resource owner: the account or organization that owns that data repository.
- Repository access: **Only select repositories**, selecting that exact repository.
- Repository permissions: **Contents: read and write**; Metadata read is included.
- No Actions, Administration or Workflows permission for this clone/status-push
  path. Those are different tasks, not upload prerequisites.

Save it in the local file described in usage, not chat, shell history or git.
This is repository-scoped, not branch-scoped. Rules and organization approval/SSO
policies may still deny a push; token permissions do not bypass them. This scope
has not been tested for every independent account configuration. Fine-grained
PAT limitations may matter for outside-collaborator or cross-owner setups; do not
silently substitute a broad classic token.

A strictly read-only plan needs only repository read access. A run that omits
status sync has different repeat/duplicate bookkeeping consequences; do not
remove write access from the normal status-push path and call it equivalent.
See [GitHub PAT guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
and [permission reference](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens).

## Image pin discovery is not full provenance

Usage examples contain `@sha256:<pinned-digest>` placeholders. The concrete image
used by the project's source workflow is its `IMAGE` value in
[geni-upload.yml](../.github/workflows/geni-upload.yml). Do not use a floating tag
as a replacement. Read the current value rather than copying a digest from an
old conversation or assuming current source is already baked into that image.

The publishing workflow can emit an `image-release-descriptor` artifact and step
summary that bind image files to a source revision. The tools and limits are in
[image release provenance](image-release.md). At this status check there is no
committed descriptor for the current workflow pin, and no latest GitHub Release
was returned. Thus there is **not yet a stable, verified release-catalog link**
connecting the current pin to all reviewed source bytes.

`podman inspect` checks the pulled image's reported digest/architecture; it does
not by itself prove the intended reviewed code is inside. Do not describe the
workflow literal as a fresh registry-byte or full source-provenance verification.
A tested release pointer plus its descriptor remains an onboarding gap.

## Geni app registration and parameter mapping

The [token guide](geni-token.md) describes local desktop authorization. It is not
a field-by-field verified guide to today's registration form. The [open registration
guide issue](https://github.com/reihlinstinct/geni-uploader/issues/136) records a
[project-observed correction](https://github.com/reihlinstinct/geni-uploader/issues/136#issuecomment-6435014003):
HTTPS on URL fields and a bare hostname, without a scheme, for Site Domain.
That observation is not proof of which fields a personal Native/Desktop app must
fill today. No sanitized registration screenshot/table has been released.

| Field or parameter | Desktop flow, vendor documented | Hosted server-side flow, vendor documented | Current registration UI evidence |
|---|---|---|---|
| `client_id` | Required; Geni calls it the application key | Required; same wording | Numeric App ID versus Key label mapping is unresolved; do not guess |
| `response_type` | Required `token` | Defaults to `code` | Request parameter, not proof of a registration-field label |
| `display` | Required `desktop` | Defaults to `web` | Same distinction |
| `scope` | Optional; documented default full data access | Optional; documented default full data access | Default is not least-privilege assurance |
| `redirect_uri` / callback | Not listed as a required desktop request parameter | Required, within Site Domain; exchange must match authorization URL | Desktop registration blank/optional behavior unverified |
| Site URL / Site Domain | No desktop registration requirement established here | Callback must be within configured Site Domain | Project observed HTTPS URLs / bare hostname; personal-app requiredness unresolved |
| Privacy/terms/deauthorize URLs | Not settled by desktop authorization parameter docs | Not settled by server-side authorization parameter docs | Which are required/optional/default for each current app type remains unverified |
| App secret | Not used by shipped desktop auth-url command | `client_secret` required for code exchange/refresh | Do not equate a UI field named Key with a secret without verified mapping |

The CLI passes `--client-id` verbatim as OAuth `client_id`. Do not paste a secret
there or assume numeric App ID and the form's Key are interchangeable. Until the
current labels are independently verified, this is an explicit setup stop, not
a request to share settings or credentials.

Official sources: [Desktop authorization](https://www.geni.com/platform/developer/help/oauth_desktop)
and [server-side authorization](https://www.geni.com/platform/developer/help/oauth_server_side).
These document authorization parameters, not every current registration-form rule.
Do not copy the project's privacy/terms URLs as another application's policy
without checking that they accurately describe that application's own operation.

## Creation and assistance: reconcile the older design labels

[profile-creation-design.md](profile-creation-design.md) describes the earlier,
general design and its unreleased gates. Later [one-time pilot](one-time-parent-pilot.md)
and [bounded batch](bounded-parent-pair-sibling-batch-design.md) work is a separate,
narrow protected path. Successful deployment-specific creation does not release
a generic `people-run` command in the upload container. The image's actual
[Dockerfile](../Dockerfile), [entrypoint](../entrypoint.sh) and
`src/geni_uploader/client/cli_spec.py` shipped command definitions identify
its command surface; public runner source alone is not a portable installation.

The [batch workflow](../.github/workflows/parent-pair-batch-create.yml) requires
fixed repository/actors, reviewed code/config hashes, private source admission,
correct owner, protected credentials and separately approved human review.
Changing those conditions is a new reviewed integration, not ordinary setup.
There is no invitation to reuse an existing person's credentials or dataset.

The privacy policy's separate-consent paragraph describes data handling only.
It neither releases independent assistant operation nor settles Geni's service
or API requirements. App registration, a token, an endpoint and owner approval
are not by themselves proof of vendor-policy compliance.

## GitHub Free: separate uploads from creation-design rules

GitHub Free supports private repositories. Owner-local source/photo upload uses
local compute and ordinary authorized clone/push, so this path has no inherent
paid GitHub plan requirement. The earlier creation design's private ruleset/audit
requirements do **not** become upload prerequisites.

Hosted execution is separate: standard GitHub-hosted runners in public repos are
free; private Actions has included quotas and storage limits, with possible usage
blocks or charges beyond allowances. Deployment-review protection availability
also depends on repository visibility and plan. Do not move private family data
into a public repo to obtain free runtime, and do not promise a hosted installation
works on Free without checking its required protections and current usage.

Sources: [GitHub plans](https://docs.github.com/en/get-started/learning-about-github/githubs-plans),
[Actions billing](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions)
and [rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets).

No account settings, registrations, OAuth exchanges, deployments or live vendor
operations were performed for this documentation. Independent setup remains
incomplete until the selected route, registration mapping, release provenance,
credential scope and owner/target identity can be verified for that installation.
