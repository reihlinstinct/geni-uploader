# Python Docker update policy

Automatic Python Docker SemVer major and minor tag updates are ignored. Patch and digest updates remain enabled. The current Dockerfile stays on Python 3.12. This is not a blanket dependency ignore.

Dependabot reads x.y.z as major.minor.patch: 3.12 to 3.15 is semver-minor, not semver-major. Ignoring only semver-major would not block that update. Both types are scoped to the Docker python dependency only. Source: https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference#update-types-ignore

Manual runtime upgrades need a separate change with a full version-matrix run, actual Dockerfile build and offline container checks. The 3.15 attempt passed the container smoke but failed 12 normalized-AST hash contract tests; see #591, #598 and the separate portability follow-up #599. Do not blindly rebaseline those hashes or weaken the contracts.
