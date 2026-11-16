# Existing dependency finding evidence update

The dependency update changes the existing unhashed dev requirement from `pytest>=9.1.1`
to `pytest>=9.2.0`. Scorecard tracks the exact requirement text, so the prior evidence
becomes stale. This change updates that one evidence string only, retaining the
same unhashed-requirement finding, reason and #494 remediation issue. It does not
remove the finding, widen the exception set, enable hash-locked pip or change any
permission. Dependency tests and the security guard must pass before merge.
