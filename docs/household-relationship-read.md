# Bounded household reconciliation read

Separate protected GET-only workflow. Exactly two profile identities and their immediate families, two explicit unions, and two owner identity reads. Eight ordered GETs maximum, 15-second pacing, no discovery, retry, profile writes or marker reset. Config is private and exact-hashed; executor pins current master and attempt1. Existing secondary-readonly-evidence human approval applies, no bypass. Raw JSON responses are encrypted before schema validation. Missing union fields remain UNKNOWN, never an empty list. No claim of complete visibility or repaired relationships. No creation workflow change.

Tests use ZZ synthetic names only. Offline exact config replay and independent exact-head review plus green CI precede any run. User GitHub approval required. Closes #673.
