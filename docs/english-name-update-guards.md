# English-name updater guard regressions (#793)

Test-only follow-up to the #779 post-merge review. Synthetic ZZ fixtures exercise
account binding, expiry at each clock boundary, route order, body pinning,
mode-specific exact confirmation, claimed status, duplicate unions, self-target
rejection, readback identity, plan/config consistency, fresh output directories
and encryption preflight. No production, workflow or permission changes.

Expiry after consumption must not send; expiry after a send leaves the operation
consumed and never writes a final receipt. Wrong confirmation values fail before
encryption. Request order and exact body checks are exercised before transport.

No credentials, live Geni calls, dispatch, plan run or age binary are used by
these tests. The display_name recomputation question is tracked separately in
#794. Current fail-closed readback remains unchanged. Offline guard coverage is
not approval for a live update, nor proof of vendor display-name behavior.

The added file has 36 passing cases.

## Mutation accounting

This is a broad statement-removal scan, not a claim that every statement is
independently pinned.

Counting method (AST): parse `src/geni_uploader/runners/bounded_english_name_update.py`
and `src/geni_uploader/runners/protected_english_name_update.py` with Python's `ast`
module and take every expression statement (`ast.Expr`) whose value is a direct call
to `require(...)` or `now()`, including statements that span several lines. That gives
53 statements: 36 in the bounded runner (30 `require`, 6 `now()`) and 17 in the
protected runner (all `require`). Each one was replaced in turn by `pass` (other lines
unchanged) in a scratch copy, and `tests/test_english_name_update.py` plus
`tests/test_english_name_update_guards.py` were run. A mutant is killed when that run
fails. Result: 37 of 53 killed, 16 survive.

The #795 review's 45 mutants are a narrower, selected count: only single-line
`require`/`now` statements. The 8 multi-line statements of the AST scan (bounded lines
15-16, 18-19, 22-23, 42-43, 51-52 and 128-129; protected lines 94-96 and 131-132) are
not in it, and all 8 are killed. So 45 single-line mutants, 29 killed, and the same 16
survivors. The two totals differ by method, not by result.

Surviving removals (line numbers at the time of the scan). These are listed for
audit only; they are not claimed to be covered by any other test or layer.

Bounded runner, snapshot/schema shape checks:

- L14 `require(type(actual) is dict and 'error' not in actual)`
- L20 `require(actual.get('gender') in ('male', 'female', 'unknown'))`
- L26 `require('first_name' in fields)`
- L29 `require(type(actual[key]) is str and len(actual[key]) <= 200)`
- L32 `require(type(actual.get('unions')) is list and len(actual['unions']) <= 8)`
- L50 `require(type(value['schema']) is int and value['schema'] == 1)`
- L56 `require(type(value['expect_name']) is str and 2 <= len(value['expect_name'].split()) <= 8)`
- L57 `require(type(value['expires_at']) is int and 0 < value['expires_at'] < 2**40)`
- L58 `require(type(value['expected']) is dict and set(value['expected']) <= set(SNAPSHOT_KEYS))`
- L65 `require(type(english) is dict)`
- L67 `require(key in english)`
- L91 `require(type(read_only) is bool)`

Protected runner:

- L44 `require(not self.read_only and self.post_count == 0)`
- L58 `require(target == self.client.plan['target'])`
- L76 `require(type(value['plan_sha256']) is str and re.fullmatch(r'[a-f0-9]{64}', value['plan_sha256']))`
- L84 `require(mode in ('plan', 'update'))`

Some of these are outside the #793 review scope and some may be masked by other
layers (for example L44 and L58 under the fixed request sequence); that reading is
not verified statement by statement here. The full suite was not run per mutant.
