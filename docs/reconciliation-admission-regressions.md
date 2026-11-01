# Reconciliation admission regressions (#587)

The GET-only reconciliation runner now has explicit negative coverage for its
entry environment, expiry before credentials, created-profile distinctness from
all approved profiles, every derived read route, non-GET methods, repeated reads,
finite request budget and expiry after pacing. Graph tests reject unknown profile
boundary keys, internal-union boundary injection, invalid roles, extra nodes,
adopted-child metadata and inconsistent focus edges. The positive source/ref
replay remains, ensuring negative tests do not pass merely because admission is
always blocked. The workflow step now describes read-only reconciliation.

No production runner logic, approval gates or live configuration changed. No
secret installation or dispatch is included.

## Credential follow-up still open

The existing workflow still maps the evidence-writer credential to the GET-only
reader. The live protected environment has no separately named read-scoped
private-source credential. Secret metadata cannot prove the scopes of a stored
credential. Provisioning a genuinely read-scoped credential is a separate owner
security decision; renaming or copying the writer would not reduce authority.
A future change must verify the new credential's scope and private-source access,
then switch the workflow and pin that selection with a regression. This PR does
not claim that credential reduction is complete and does not close #587.
