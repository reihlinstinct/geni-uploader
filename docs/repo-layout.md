# Repository layout contract (#721, v2 #731)

`.repo-layout.yml` at the repository root is the enforced layout contract:
required community-standards files, allowed top-level directories, the file
types permitted and denied in each, the files each directory must carry, and
the rule that no code lives at the repository root. The file uses JSON syntax
(valid YAML as well) so the checker needs only the Python standard library and
can be reused in every reihlinstinct repo. Version 2 implements
`docs/repo-layout-v2-design.md`.

## Schema (version 2)

```json
{
  "version": 2,
  "comment": "optional free text",
  "required": ["README.md", ".github/ISSUE_TEMPLATE/"],
  "root": {"allow": ["*.md"], "deny": ["*.py"]},
  "directories": {
    "docs": {"allow": ["*.md"], "deny": [], "required": []}
  }
}
```

- `version` must be the integer `2` (or `1`, see Migration). Anything else,
  including a missing version, is a contract error.
- `required` (global): repository-relative paths that must exist; a trailing
  `/` means a directory. A file must be tracked. Absolute paths, empty
  components, `.`/`..` segments and backslashes are rejected.
- `root`: `allow` (required) and `deny` (optional) for files at the root.
- `directories`: every tracked top-level directory must be listed. Each entry
  has `allow` and optional `deny` and `required`; a missing optional list
  means empty.
- `allow` and `deny` are case-sensitive basename globs (`fnmatch` syntax),
  applied recursively to every file under the directory. A glob-free string
  is an exact filename (`CODEOWNERS`, `README.md`). Deny always wins over
  allow.
- A directory's `required` lists exact directory-relative file paths
  (`README.md`, `sub/INDEX.md`): no globs, absolute paths, empty components,
  `.`/`..` segments or backslashes. Each must be a tracked regular file (not a
  link, not a submodule; an untracked file does not count), must resolve
  inside the repository (checked before it is opened) and must be readable.
  A required file must pass the directory's own allow/deny: a required file
  that is denied or not allowed is a contract error. Required directories use
  the global `required` list.
- Unknown keys, duplicate JSON keys and wrong types are contract errors.

## Checker

```sh
python tools/check_repo_layout.py [--root DIR]
```

No network. The checker verifies that the root is the git top-level, removes
repository-location variables (`GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`
and similar) from git's environment while keeping git configuration, and reads
tracked paths with NUL-delimited `git ls-files -s -z`, so unusual names
(Unicode, embedded newlines) stay single paths. Exit codes:

- `0`: `layout OK`;
- `1`: one `layout violation:` line per problem, sorted, naming only paths
  and rule categories (backslashes and control characters are escaped so
  each violation stays on one line);
- `2`: `layout error:` on stderr for an invalid or missing contract, an
  unsupported version, missing git metadata or a root that is not the git
  top-level. These are failures, never an empty tree.

Violation categories:

- `required file missing` / `required directory missing` (global list);
- `unlisted top-level directory`;
- `denied at repository root` / `not allowed at repository root`;
- `denied in DIR/` / `type not allowed in DIR/`;
- `required file missing|untracked|is a tracked link|is a link|is not a
  tracked regular file|is not a regular file|escapes repository|unreadable
  in DIR/`.

The checker never prints file contents and never edits the contract.

CI runs it directly (layout job) and via `tests/test_repo_layout.py`, which
also pins the empty root `.py` rule and the v2 semantics on temporary
fixture repositories.

## Migration from version 1

A version 1 contract has directory entries with `allow` only. The checker
reads it only through the explicit `migrate_v1_to_v2()` step in
`tools/check_repo_layout.py`, which keeps every rule and adds empty `deny`
and `required` lists; a version 1 file carrying `deny` or `required` is
rejected, and a version 2 file is never read as version 1. The migration is
in memory only: to adopt v2 in a repository, change `version` to `2` in the
same PR that adds any new per-directory rules.

## Changing the layout

A new kind of file, a new top-level directory, or a new required file means
updating `.repo-layout.yml` in the same PR. Placement is decided before a
file is created, per CONTRIBUTING.md; the human-readable map is the
"Repository layout map" section of `ARCHITECTURE.md`.

## Rollout

geni-uploader carries the reference implementation. Other reihlinstinct repos
adopt the same checker with their own contract file; each adoption is its own
issue + PR with green CI and independent review.
