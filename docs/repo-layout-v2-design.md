# Per-directory layout contract v2 (#731)

Status: proposal only. This PR changes no checker, contract or runtime behavior.
Current v1 implements global required paths, root allow/deny and recursive
per-directory basename allow rules. Per-directory deny/required are absent.

## Placement and scope

This design: `docs/repo-layout-v2-design.md`. Future implementation edits
`tools/check_repo_layout.py`, `.repo-layout.yml`, `tests/test_repo_layout.py`
and `docs/repo-layout.md` in one reviewed PR. No new root code or dependency.

## Proposed schema

Version 2 retains the existing root and global required fields. Each existing
top-level directory entry contains `allow`, optional `deny` and optional
`required`. Missing optional lists mean empty. All lists contain strings;
unknown keys, duplicate JSON keys and unsupported versions fail closed.
Migration is explicit, never silently interpreted as version 1.

`allow` and `deny` are case-sensitive basename globs, applied recursively inside
that directory. A glob-free string is an exact filename, so `README.md` and
`LICENSE` need no separate type syntax. Deny always wins over allow.
`required` contains exact directory-relative file paths, not globs. No absolute
paths, empty components, dot/dot-dot segments or backslashes. Nested requirements
are explicit paths, never an implicit requirement in every subdirectory.
Required files must be tracked regular files and pass allow/deny. No exemption
from policy: a required-but-denied file is a contract error. Required directories
continue to use the existing global mechanism, not this file-only list.

## Enumeration and failure behavior

Read tracked paths with NUL-delimited Git output. Verify the requested root is
the Git top-level; isolate repository-location environment variables while
preserving safe Git configuration. Reject tracked links for required files;
check required path containment before reading. Untracked files do not satisfy
required policy. Existing public/private data boundaries do not change.

Report file paths and rule categories only, deterministically sorted. Do not
print file contents, secrets or auto-edit the contract. Missing Git metadata,
invalid schema or unreadable required files are failures, not an empty tree.

## Acceptance and mutation plan

Positive cases: exact names, extension globs, nested allowed files, valid tracked
required files, absent optional lists and explicit v1-to-v2 migration.
Negative cases: deny overriding allow, missing/untracked/linked required files,
required-denied conflict, invalid traversal, duplicate keys, unknown fields,
wrong root and unsupported version. Unicode and newline paths stay single paths;
only a filesystem-unsupported filename case may skip on that platform.

Mutants must remove each guard separately: deny precedence, required enforcement,
tracked-only requirement, containment, duplicate rejection and version dispatch.
Each must fail a relevant test. Re-run the real tracked repository checker, not
only temporary fixtures. Review exact head and require green CI before adoption.

## Rollout

Implement in geni-uploader first, keep reusable semantics documented, then use
separate issue/PR adoption per repository. Do not edit other owners' active
layout work or widen any release, credential or execution gate.
