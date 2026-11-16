# Deterministic persona-rendered documents (#733, template slice)

Status: design only. No renderer, generated output or CI edit in this PR.
The current canonical input is `synthetic/personas.json`; public placeholders
remain governed by `docs/synthetic-personas.md` and the existing scanner.

## Placement

This document: `docs/persona-template-design.md`. Proposed later Python module stems (use the Python suffix in implementation):
`tools/render_persona_docs`, `tests/test_persona_templates`,
`docs/templates/` with `.md.in` inputs, and
`synthetic/persona-template-manifest.json` mapping inputs to Markdown outputs.
The future PR must allow `.md.in` under docs in the layout contract. Outputs
remain at their existing reader-facing paths. No new root files or dependency.

## Contract

Use literal `{persona.KEY.FIELD}` tokens. KEY and FIELD must exist in the
canonical JSON; fields must be strings. Unknown/unclosed tokens fail. No Python
format evaluation, expression language, attribute traversal, includes, shell,
network or secret access. A literal brace escape is specified and tested before
implementation. Replacement is one pass, so inserted values are never re-parsed.

The manifest is a strict versioned object with unique relative source/output
paths. Reject traversal, symlinks, duplicate outputs and source/output overlap.
Only explicitly listed documents render. Bootstrap with one small synthetic-only
example after review; never convert the whole corpus implicitly.

Render tokens inside prose and code fences identically. Code examples need
canonical data too; do not treat fences as a privacy exemption. Manifest entries
can declare a field forbidden in an output when the example does not need it.
Do not invent a new person or copy a value from private runtime data.

## Drift checks

Default command checks only: render in memory as UTF-8 with normalized LF and a
single final newline, compare exact committed bytes, fail on any drift. A local
explicit write flag updates outputs; writing is refused in CI. Generated output
carries a short source-template notice. Readers edit templates, not outputs.
Never regenerate the placeholder baseline to silence a new violation.

CI checks the manifest, generated drift and existing placeholder scanner. Neither
renderer nor scanner proves that prose contains no real names; review remains
required. Check mode must not modify tracked files or fetch external content.

## Acceptance

Tests cover canonical substitution, code fences, escaped braces, unknown keys,
malformed tokens, duplicate/escaping paths, symlinks, output collisions,
Unicode/newlines and byte determinism. Direct output edits and stale persona
values fail drift checks. Mutants disabling drift, unknown-token rejection,
containment or no-CI-write must be killed. A real-tree check verifies the first
adopted template/output pair. This design does not authorize a private-term
scanner, key installation or any live service operation.
