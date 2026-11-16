# Local synthetic Plan consumption ledger

This is an offline prototype, never a production lock, remote service, signature
verifier or executor. It accepts an unsigned supplied envelope only after the
offline structural/binding review. A match grants nothing. It performs no API
calls, creates no profiles and accepts no credential.

The caller must supply an existing absolute owner-only directory with no
symlink components. The fixed SQLite file is owner-only and refuses symlinks,
hardlinks and nonregular files. Keep the directory private. SQLite sidecar files
live there too. FULL synchronous commits persist local consumption before a
successful return. Competing processes sharing this exact ledger serialize via
an immediate transaction and unique Plan/owner constraints. A committed row
survives a crash; duplicate or new same-owner Plan/connection attempts stop.
This first model accepts an owner's empty journal version zero only, then
records version one and consumed_no_execution. It never marks real operations
successful or silently resets/releases an unfinished record. Recovery exposes
inspection-only counts, not a retry or a write.

This ledger is intentionally stricter than an eventual reusable journal: no
owner can start again through this instance. No completion transition is modeled.
A fresh path, copied/deleted/replaced database, noncooperating process, remote
runner or credential refresh consumer bypasses this local prototype. There is
no global exclusion or tamper-resistant storage claim. Filesystem checks assume
a trusted local process/user, not a hostile same-user actor racing path changes.
A future production release needs a separately approved shared authority and
full crash/reconciliation contract. Never use this to justify a live write.

Offline content hashes now reject dictionaries with non-string keys and input
deeper than 32 levels, cyclic structures and unsupported JSON values with a
fixed Blocked error. Canonical bytes for valid string-key JSON inputs remain
unchanged. Proposal CLI catches malformed overdeep JSON. Regression guards deny
socket, HTTP, urllib, subprocess and os process helpers during proposal, render
and envelope review, including fork and POSIX spawn helpers where present.
These are regression test guards, not complete operating-system isolation.
