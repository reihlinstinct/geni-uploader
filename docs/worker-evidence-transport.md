# Worker evidence transport (#413)

Dormant infrastructure only. No source authenticity, complete approval capture,
installation audit, issuer composition or grant is implemented by this module.
Only deployment-owned callers may supply routes, credential and fetch adapter.
Those inputs do not authenticate themselves. No public caller is installed.

One closure fixes exact GET routes under https://api.github.com/repos/, rejects
normalization/host-override tricks, and never follows redirects. It rejects any
Link pagination header rather than treating partial evidence as complete. A
fixed API route is not permission to read or disclose its contents. Production
integration must independently resolve credential scopes and exact API graph.

Limits per closure: 16 attempted fetches, 256KiB per streamed response, 1MiB
aggregate decoded response bytes, JSON depth16, one absolute10s deadline. These
are fixed ceilings, not a caller budget. Failed/parallel calls share the same
counters. No retry. Abort closes all tracked readers and future reads. UTF-8 is
fatal, duplicate object keys reject, malformed JSON rejects. Fixed errors omit
credential, route, provider diagnostics and body. Successful JSON is private data,
not a sanitized receipt: a future capture must reduce it before any handoff/log.

Sixteen fetches is below the Free50-subrequest ceiling for this transport alone.
It is NOT proof the whole future issuer stays below50: OIDC JWKS, installation
audit, DO reserve, evidence persistence and handoff each need accounting. The
production reviewed orchestration must use one shared budget or prove an exact
whole-request upper bound. No helper may reset its budget mid-request. No
pagination/truncation or weakened verification may make oversized evidence fit.

Tests run the import-closed module in workerd without Node compatibility, using
synthetic local responses only. They cover request/aggregate/concurrent budgets,
redirects, pagination, declared and chunked oversized bodies, duplicate keys,
depth, malformed JSON/UTF-8, raw fetch failure, explicit close, blocked later
reads, stalled-fetch and stalled-stream deadlines. These are functional checks,
not provider CPU measurement. No Cloudflare resource, key, deploy or live API
call is made. The full CPU profiling/release blockers remain in #407/#411.

## Repository segment boundary (#429)

Transport itself rejects leading-dot repository segments and dot/double-dot
segments before any fetch, independently of source/CI config. Safe internal-dot
names remain accepted. Direct workerd tests exercise both outcomes. No caller
can bypass this boundary by skipping upstream config validation.
