# Contributing

- Work on a branch or fork and open a PR. One focused change per PR, tests included; `ruff check .` and `pytest` must pass.
- Never push to `master` and never merge your own PR.
- `geni_upload.py` is byte-synced with a reviewed private copy: changes to it are synced to both repos identically and pinned in a new reviewed image.
- No personal data, real names, profile IDs, tokens or GEDCOM content in any file, issue or PR. Use invented examples.

## Issues: labels, milestones and order

The same scheme is used in every public repo, defined in
[collaboration-docs CONTRIBUTING](https://github.com/reihlinstinct/collaboration-docs/blob/main/CONTRIBUTING.md).
Do not add parallel label schemes.

**Labels** (every open issue has one type, one area and one priority)
- `type: feature | fix | task | docs | security` - the kind of work.
- `area: ...` - the part of the project. In this repo: `area: uploader`, `area: ci`, `area: containers`, `area: docs`, `area: security`, `area: quality`.
- `priority: high | medium | low` - high is done first.
- `status: blocked | held | in-progress | needs-review` - only when it applies. `status: in-progress` means someone claimed it.
- `needs-triage` - not sorted yet. Remove it when the three labels above are set.
- `good first issue` - small and clear, a good place to start.

The older GitHub default labels (`bug`, `enhancement`, `documentation`, ...) stay for history; new issues use the scheme above.

**Milestones:** `Now` (in progress or due this week), `Next` (planned after Now), `Later` (backlog). High priority goes to Now, medium to Next, low to Later, unless the maintainer decides otherwise.

**Picking an issue:** filter by milestone `Now`, then `Next`. Take high priority first. Skip blocked, held and in-progress items. Comment "taking this" on the issue, then open a PR that references it (`fixes #N` / `refs #N`).
