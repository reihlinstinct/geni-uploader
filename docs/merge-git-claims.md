# Private Git remote claims

Issue #825. The GitHub claim backend implements the remote object/ref mechanics,
not a configured production ledger. No repository, branch, credential, HTTP client
or signer is installed by this change. No live calls are made by imports/tests.
The merge engine's public execute entry point remains unconditionally closed.

## Append contract

The configured repository must be private. The configured exact branch must
already exist and contain only hash-named claim blobs in its root tree. Snapshot
reads are bounded to one tree with at most 1000 entries, rejecting truncation,
subtrees, duplicate names, non-blob objects and unexpected paths. Existing record
filenames block replay without retrieving private bodies or per-record fan-out.

An append adds one hash-only record to the immutable snapshot tree, signs the exact
Git commit payload through an injected signer and requires verified signature,
matching signed payload, tree and parent in GitHub's response. It moves only the
configured ref with force=false. Object creation alone is not a claim. A failed or
ambiguous response stops; no retry, reset, deletion, branch creation or force
update is implemented. A new snapshot that sees the operation filename blocks
another claim, including after a lost accepted-ref response.

[GitHub's reference contract](https://docs.github.com/en/rest/git/refs) says
force=false requires a fast-forward update. Competing child commits of the same
head cannot both advance the ref. The backend tests this with fake responses;
actual remote contention/verification behavior still needs a reviewed staged
validation before release, without any Geni write.

## Remaining release checks

The injected HTTP client must pin the GitHub origin, reject redirects, bound
responses, keep credentials private and make no retries. The signer must use the
approved identity. These dependencies and effective branch protection (no force,
no deletion, restricted writers), repository/branch/identity pins, recovery and
single-store binding must be independently verified. A repository administrator
can otherwise reset history; the class does not turn caller-supplied configuration
into authenticated authority or an immutable service. Empty-ledger initialization
is a separate deliberate change, not an automatic fallback.

## Content-addressed append verification

The backend computes the new record's Git blob ID, the complete sorted root-tree
ID (existing records plus the new entry), and the signed commit ID locally.
Server tree and commit IDs must match those exact objects before the one non-force
ref update. The commit ID includes the indented multiline `gpgsig` header, exact
parent, author/committer stamps and message bytes. Frozen vectors independently
checked with Git's `hash-object` cover blob, tree and signed-commit serialization;
the runtime and tests require no Git subprocess.

Malformed nested responses produce fixed exceptions. Tests isolate snapshot,
append and ref-response guards, assert no ref update before verified objects,
and allow exactly one attempted update on a malformed update response. Consumed
snapshots cannot make another request, including after an uncertain result.
These offline checks do not replace staged remote contention and signature
verification evidence before release.
