# Explicit Linux runner image (#300)

Every workflow job uses ubuntu-24.04, not the migrating ubuntu-latest alias.
The supported image table lists that explicit x64 label:
https://github.com/actions/runner-images/blob/main/README.md

This avoids the Ubuntu26 migration annotation and holds the OS major/minor
stable. The hosted image's installed package versions still change over time;
this label is not an immutable image digest. Re-evaluate support before Ubuntu24
retires and independently test any OS-major change. Job permissions, credentials,
environments, triggers and deployment authority are unchanged.

Exact-head CI annotation inspection is required before merging, in addition to
all existing checks. Manual-only workflows are statically inspected for labels;
they are not dispatched merely to test this label change.
