# GitHub reviewer account assurance (#415)

The selected ceremony remains one exact-run GitHub deployment approval by the
sole fixed reviewer account, with account 2FA, agent dispatch and independent
exact-head code review. No extra human-presence challenge is added. This is an
account-approval assurance, not cryptographic evidence of an interactive human
click. 2FA is an account-security condition; the approval payload does not prove
that a fresh second factor or human-presence check occurred for that approval.

Preserve all existing runtime pins: exact sole reviewer numeric ID with User
type, exact environment/run/attempt/job/source/plan/risk, prevent-self-review,
no admin bypass, fixed branch and distinct dispatcher. A Bot/App identity with
a different ID cannot match the reviewer. These checks do not distinguish a
human using that account from supported automation using its credentials or
browser session. No automation may hold or use the reviewer's PAT, OAuth
credential or logged-in session for this ceremony. Do not ask for or collect
such credentials to automate the approval. Agent dispatch uses a separate
principal and is not review consent.

## Current documented token boundary, checked 2026-10-29

GitHub's pending-deployment review endpoint documents OAuth app tokens and
classic PATs with repo scope, used by an eligible required reviewer. Current
official OpenAPI marks that POST enabledForGitHubApps:false; it does not list
GitHub App user/installation tokens or fine-grained PAT support for that action.
Do not infer endpoint support merely from a token's permission names.

GitHub App installation requests are attributed to the App, not its installer.
For endpoints that support App user access tokens, requests are attributed to
the user; GitHub says corresponding audit/security entries may include
programmatic_access_type. Ordinary deployment review history exposes
environments/state/user/comment, not an interactive-user/token-type field.
A supported account credential can therefore produce a User/id-matching review
without proving a click. An installed App's actual token path/scopes must be
checked separately; subscription/compute billing says nothing about GitHub
reviewer identity. No approval call was made to test token behavior.

No technical human-presence guarantee is claimed. If one is requested later,
review a new exact-run independent confirmation or hardware-backed challenge
and its effect on the one-approval ceremony before implementation. Do not add
an invented interactive_user pin, silently require a second review, change
permissions, or delegate the reviewer account to an agent. No setting, resource,
secret, key, workflow approval or deployment is changed by this documentation.

## Official sources

- https://docs.github.com/en/rest/actions/workflow-runs
- https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user
- https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments
