# Offline composition layout (#471)

Moves the
intact one-attempt simulation to core/father_once; parent runner, fixture-only
father composition, protected job composition and offline release packager to
workflow. Temporary root aliases preserve module identity, canonical runtime
imports replace old names. No live entrypoint, gate or transport is added.

Exact normalized model structure guards permit only mapped import locations
and top-level import ordering. Existing behavior/mutation/ledger/archive tests
stay unchanged. Installed-wheel inventory and isolated imports include each
implementation. The source packager keeps collecting tracked src files and
explicit gate resource. Existing root compatibility import paths still work
for Node subprocess validators. No workflow YAML, permissions, Docker, settings,
secret, Geni request, archive upload or deployment changes in this slice.
