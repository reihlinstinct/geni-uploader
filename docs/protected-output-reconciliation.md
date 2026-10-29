# Protected output workflow reconciliation

Related: #123 and PRs #125, #127, #129. Consolidates the useful
unmerged changes against the current workflow rather than adding competing
final steps or a second result file. No workflow permission, secret, trigger,
environment or execution-scope change. No dispatch or source operation.

The existing numeric `container-exit-code` remains the sole result file.
Encryption/retention runs with `always()` and initializes a missing raw log
without truncating partial output. Its failures still fail closed. The final
result check also runs with `always()` after retention; no retained log can turn
a failed source container into success. Selftest passes only for a present,
bounded, canonical nonzero result (1 through 255), not an absent result file or
MODE=selftest alone. Missing, malformed and zero selftest results fail.

Fixed-path temporary plaintext cleanup runs after result enforcement with
`always()`, preserving ciphertext. It removes raw output, temporary credentials,
private log checkout and report directory without printing their contents.
Cleanup is idempotent and best effort: abrupt runner loss/cancellation can still
prevent it. Encryption may retain an empty log after an earlier failure; that
is not evidence that an operation succeeded or that no request was sent.

Tests execute the actual named shell steps with synthetic files, pin relative
capture < encryption < enforcement < cleanup ordering, verify partial-log
preservation and missing initialization, and reject status leakage. They avoid
assuming enforcement is the last step, so appended cleanup does not break them.
No test performs encryption, a credential operation, Git push or a Geni call.
