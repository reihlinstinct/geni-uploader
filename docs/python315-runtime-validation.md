# Python 3.15 runtime validation (#598)

The dependency update moves the digest-pinned Docker base from Python3.12 to
Python3.15. Python3.15 is stable, but the existing3.11/3.12/3.13 test matrix did
not exercise it. CI now includes3.15 and builds the actual Dockerfile on code PRs.
The summary gate depends on that container job, so its failure cannot pass as green.
Docs-only skips retain the existing behavior.

The smoke runs every container with network disabled and supplies no credentials.
It compares all six copied runtime files against their reviewed source bytes,
checks Python3.15 and PyYAML import, runs three CLI help commands and imports the report helper, and verifies
that the real entrypoint refuses a missing runtime repository with exit1. Build
uses package/image network; the smoke itself has none. No registry login, image
push, production workflow pin change or vendor call is included. This is not a
live upload E2E test; the existing offline suites still cover upload behavior.

Sources: https://www.python.org/downloads/release/python-3150/ and
https://docs.python.org/3/whatsnew/3.15.html .
