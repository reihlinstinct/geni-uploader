# Python Docker update policy

Automatic Python Docker major-version tag updates are ignored. Minor, patch and digest updates remain enabled. The current Dockerfile stays on Python3.12.

Major runtime upgrades need a separate change with a full version-matrix run, actual Dockerfile build and offline container checks. The3.15attempt passed the container smoke but failed12normalized-AST hash contract tests; see #591, #598 and the separate portability follow-up #599. Do not blindly rebaseline those hashes or weaken the contracts.
