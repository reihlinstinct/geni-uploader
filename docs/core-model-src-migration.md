# Offline core model layout (#461)

Moves parent_intent_model, parent_adapter_contract, parent_snapshot and
profile_outcome_model into core/intent, core/parent_contract, core/snapshot and
core/outcome under src/geni_uploader. Runtime imports use canonical locations.
Temporary old module names alias the same module object, preserving monkeypatch
and exception identity for existing callers/tests. No behavior extraction or
CLI/resource/workflow/Docker change. The outcome model's intent import changes
location; source hashes normalized only for these mapped import paths verify
that no other model code changed. Pure models remain offline and grant nothing.

Existing behavior tests remain unchanged. Added identity/monkeypatch and both
fresh-process import orders for each module, canonical runtime-import scan,
exact wheel inventory and isolated installed imports for all new paths. The
existing release inventory includes every tracked Python src file and rejects
dirty or symlink implementations. Python matrices, coverage and all runtime
parity suites remain required. No deployment, live action or settings change.
