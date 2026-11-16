# Installable src package foundation (#457)

First implementation slice of the staged source layout, not the full migration.
Adds `src/geni_uploader/__init__.py` with no import-time work, explicit pinned
build backend and an explicit two-package map. Existing `geni_offline` stays in
its original root package and the built wheel. No root runtime module, command,
workflow, Docker path, behavior, production gate or source hash pin moves here.
The new wheel does not claim to contain the uploader CLI yet.

The wheel test runs with pip index disabled, checks exact packaged module
inventory, installs without dependencies into a fresh virtual environment, and
imports both packages outside the checkout using isolated Python. A planted cwd
module must not win. An audit hook rejects network/subprocess activity during
imports. These are behavioral guards, not a security sandbox.

Development requirements include the exact build tools so wheel regression
runs without downloading build dependencies. No workflow dependency/permission
change is needed. Full CI still covers the old root imports until their separate
moves. Next slice moves one stdlib-only module intact with an identity-preserving
compatibility strategy and explicit caller/source-guard tests, not duplicated
implementations or a production sys.path hack. See src-layout-plan.md.
