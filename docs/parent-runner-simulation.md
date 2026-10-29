# Parent runner: synthetic integration slice

For #190, based on #144 and offline core #184/#185. `parent_runner.py` composes
schema/receipt binding, deterministic payload proposals and journal transitions
against an exact-type in-memory `SyntheticTransport`. No HTTP library, token,
production adapter, CLI entry point, image or workflow is added. The separate
`run_production()` always blocks. This is offline implementation progress, not
an executable human trial or an authenticated coordinator.

## What the simulation tests

Validate the entire batch before intent; require an English locale and preserve
all supplied locale names; propose English root-name fields and fixed private
payloads. These are proposal shapes, NOT proof of the vendor's default locale or
encoding. Bind canonical manifest hash/count/owner, receipt/run/attempt and initial
journal version, then recheck expiry before each intent and before its one POST.
A crash/expiry after intent leaves it blocked, even if no create was called.
Acknowledgment and GET verification proceed after expiry; another parent still
needs a valid receipt. Record acknowledged ID before GET, compare exact proposed
payload/anchor and only then mark verified. A failed read leaves GET-only state.

The resumable helper only inspects the known ID through the synthetic GET; it
never posts or upgrades journal state, and does not claim it revalidates a real
vendor payload. No operation reset, delete or automatic uncertain retry exists.

## Remaining production blockers

- Actual authenticated token-self identity and separately approved owner/anchor
  and operator connection (#189), exact data/storage/create authority.
- Complete hidden-parent visibility, union/slot behavior and explicit create-time
  privacy/life/default-locale readback evidence (#188). A supplied snapshot or
  test fixture cannot attest these properties.
- Reviewed authentication/receipt envelope, trusted allowlists, actual remote
  graph preconditions immediately before intent/POST, persistent shared lock,
  crash-safe encrypted storage and supported recovery. This prototype assumes
  an honest caller and the supplied disposable synthetic journal; it is not a
  security boundary against Python code or a database administrator.
- Human-run production transport with bounded endpoints/fields, no hidden retry,
  explicit rate/error stops, journal/readback integration and reviewed release.
  No model/MCP upload/approval/dispatch tool (#186/#187). Host compromise and a
  malicious runner with a vendor token remain explicit trust limits.

No new account, service deployment, hosting cost, live Geni call or production
permission is implied. Before enablement: independent exact-head review, green
CI, user chat approval and the separately authorized human-run release/trial.
