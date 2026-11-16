# Immutable workflow-content candidate (#260)

Offline synthetic evidence only. No HTTP, credentials, execution, workflow
integration, settings, permissions, deployment or Geni call. Fixed GET descriptor
sequence: pinned commit, root tree, .github tree, workflows tree, exact filename
blob. Inputs accept immutable lowercase SHA identifiers, never branch refs or
caller URLs. Metadata URLs and download links are ignored. Redirects, pagination,
truncated trees, duplicate paths/JSON keys, non-200 and overlarge responses block.
The selected path must be two directory trees and one ordinary 100644 file, not
a symlink, executable or submodule. Other valid sibling object modes are allowed.

The exact content must match canonical base64 (GitHub LF wrapping allowed),
reported size, Git blob SHA1 including its header and independently pinned SHA256.
256KiB content and 1MiB per-response caps are offline candidate limits. No YAML
parsing or execution occurs. The caller must obtain the SHA256 from independently
reviewed exact bytes, including intended human job, environment and permissions.
The digest cannot certify those semantics or supply approval. A malicious caller
can forge envelopes, including commit/tree associations; commit and tree hashes
are asserted by the synthetic snapshots, NOT recomputed/authenticated here.

A production release needs a trusted bounded HTTPS reader, current verified
repository/run identity, immutable workflow SHA256 approval, job-review/attempt
correlation, freshness/rule-change handling and separate exact owner/payload
approval. The candidate returns provenance/semantics/approval/correlation false
and never enables execution. A same-content file elsewhere does not independently
prove provenance. Byte equality is the only cryptographic content claim here.
No production entry imports this module.

Sources read 2026-10-28:
- https://docs.github.com/en/rest/git/commits#get-a-commit-object
- https://docs.github.com/en/rest/git/trees#get-a-tree
- https://docs.github.com/en/rest/git/blobs#get-a-blob
