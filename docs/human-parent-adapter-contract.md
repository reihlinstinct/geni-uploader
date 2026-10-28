# Pure future adapter contract

This module creates offline descriptors and classifies synthetic create-response
fixtures. It imports no HTTP transport, receives no credential, performs no
request, opens no URL and is not a production adapter. There is no entry point
to construct a live client or enable execution. Descriptor routes are strings,
not executable commands. Do not send them as an instruction to a live service.

GET descriptors allow only profile, canonical profile/union and immediate-family
paths. POST descriptors allow only the exact canonical owner's add-parent path,
with explicit private, life/gender and matching English main-name plus he/en
name fields. No caller URL, query, credential, redirect or retry is accepted.
Only this first scope's exact two locales are accepted. This is a proposed
encoding contract, not proof of actual API slot, privacy or locale behavior.

A separate existing human read-only collector is unchanged. This contract does
not invoke or relax it. The Geni vendor references in the release design remain
the source for documented paths/fields; undocumented return/status behavior is
not claimed as known. The synthetic success fixture deliberately accepts only
status 200 with a single canonical id object. Actual added-profile responses
may have more fields and will remain UNCERTAIN until a separately reviewed
response adapter is grounded. Never broaden the contract from a guessed result.

Response classification is pure and not a journal transition. sent:false means
no transmission began; invalid combinations are blocked. Once sent:true means
transmission may have begun, a timeout, non-200/unknown status, redirect, error,
throttle, duplicate JSON key, oversized/malformed/unexpected body or mismatched
identity is UNCERTAIN and requires human read-only reconciliation. No retry is
permitted by any result. Canonical acknowledgement is not verification: it
still requires exact parent link, privacy, full names and life readback. No
readback, source authentication, completeness, durable intent or current graph
proof is supplied by this module. Production gates remain closed.
