# Existing dependency finding evidence update

The dependency update changes the existing unhashed dev requirement from `ruff>=0.17.1`
to `ruff>=0.17.3`. Scorecard tracks the exact requirement text, so the prior evidence
becomes stale. This change updates that one evidence string only, retaining the
same unhashed-requirement finding, reason and #494 remediation issue. It does not
remove the finding, widen the exception set, enable hash-locked pip or change any
permission. Dependency tests and the security guard must pass before merge.
