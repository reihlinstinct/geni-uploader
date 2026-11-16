# Offline evidence content-contract layout (#463)

Moves approval, ciphertext, GitHub review, workflow content, parent evidence,
profile result and single-human approval content validators into
src/geni_uploader/evidence. Canonical runtime imports replace root imports;
temporary root modules alias the same module object. These validators check
content consistency only. Their output still does not authenticate a sender,
authorize a request or open a production gate.

All old validation tests remain unchanged. Add exact normalized-AST hashes
allowing only mapped import paths and top-level import ordering, fresh-process
both import orders, same-object monkeypatch identity, canonical import scan,
explicit package/wheel inventory and installed isolated import checks. Runtime
parity/private issuer/private writer subprocess suites continue to exercise
the installed Python package. Existing archive inventory includes src code.
No CLI/resource/workflow/Docker/settings/permission/secret/live/deploy changes.
