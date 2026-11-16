# OIDC guard-isolated regressions

Issue #326. Remove null/object `x5t` cases from the header-guard tests because
the flat scalar parser rejects them first. Remaining invalid scalar values
reach the dedicated header guard. Deleting only that guard makes all four
focused cases fail with missing expected rejection.

For each reusable-workflow half, the new test removes that field from both the
pins and the signed token. Thus no extra unpinned claim masks the paired-pin
check. Deleting only the both-or-none check makes the focused pair test fail.
The normal 52-test JWT suite passes after both mutations are restored. No
production code, setting, permission or execution changes.
