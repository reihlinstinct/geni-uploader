# Pure proposal closure (#465)

Extracts the complete payloads, proposal, verify_proposal and BLOCKERS closure
into core/proposal_review and PROOFS names into core/proof_requirements. Existing
root modules reexport the same objects for compatibility. No render, protected
file access, simulation transport, release gate or production entrypoint moves.
The envelope now imports only pure core components, not a CLI or workflow gate.

Exact extracted-definition byte hashes cover all six definitions. Existing
proposal/envelope/gate behavior tests remain unchanged. Add recursive local
import-direction guard, reexport identity, wheel inventory and isolated package
imports. Existing people core includes SQLite journal definitions, but no
journal is constructed by imports. The pure closure does no I/O on its own.
No live operation, release permission, workflow/settings/Docker or deploy change.
