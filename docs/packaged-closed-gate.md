# Packaged closed release gate (#469)

Moves human_parent_gate to workflow/release_gate. The temporary root module
aliases the same object, including the existing mutable CONTRACT test seam.
The gate function itself is byte-identical. Only resource resolution changes:
importlib.resources loads the explicit packaged JSON, not a path relative to
the root script. The docs copy stays as a readable fixture, checked byte-equal.

The JSON is included explicitly in the wheel and offline source archive.
Installed-wheel tests outside the checkout verify the valid resource still
blocks creation, then remove or corrupt the installed resource and require the
unavailable/changed blocker. Existing drift/missing/toggle tests are unchanged.
No valid fixture, caller proof or credential can open the gate. No workflow
YAML, permissions, settings, secret, Docker, live operation or deploy change.
