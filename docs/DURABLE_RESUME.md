# Durable source resume

A source create intent is committed and pushed before POST. The acknowledged object ID is committed and pushed before any tag or readback. Each tag has an intent, acknowledged, and verified phase. Every checkpoint is atomic and fsynced locally; normal container execution requires a successful remote push before continuing. Failure stops. `--no-repo-sync` is for offline or deliberately persistent local operation only, never the disposable production container.

A pending journal binds the full upload payload (including file bytes), primary target, extra targets and served identities. Changed inputs fail closed. A new run uses the known object ID, checks already attempted tags through GET, and sends only tags with no prior intent. It never repeats add or an attempted tag. Readback waits up to twelve 30-second intervals, with the shared rate limiter still active; 429 stops immediately, including photo listings.

A create intent without an acknowledged ID is not safe to replay, even if a title appears in a listing. It needs explicit reviewed manual reconciliation. Interrupted target identity or tag requests block continuation. Acknowledged readback lag remains pending and can resume through reads after a fresh user decision to run. Legacy uncertain/resolved records are not silently migrated. Changing only status to not_found does not erase a journal intent. Do not delete a journal as a retry mechanism.

No new endpoints, credential sources, profile edits, automated dispatch, or production calls are added. A new reviewed image must be published and pinned before this implementation is used by the upload workflow. Publishing code alone does not change the currently pinned runtime image.
