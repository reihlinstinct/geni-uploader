# Citation UI checker: discovery only

## Goal and boundary

Detect whether an existing document can be cited against an existing profile fact using the web UI's separate Value and Note fields. A tagged document is not a fact citation. This checker never updates the profile's event fields and never saves a citation.

The first release has no browser driver, login handler, OAuth flow, cookie reader, network client, secret handling, form filling, click, save or submit operation. It classifies a minimal read-only DOM observation supplied by an operator. It is an offline diagnostic, not proof that a live citation can be saved. A future optional DOM collector would be a read-only expression reading only current URL and structural labels/control metadata. It must exclude input contents, hidden fields, page HTML, cookies and storage; it is not implemented in this release.

Any future live navigation requires a separate browser/operator review. Login requires the account owner's scoped approval and secure credential entry; no credentials or sessions enter this repository. The operator reports before any login. Do not install third-party extensions to inspect secrets or obtain sessions. Logged-in no-save inspection must not fill fields because unknown UI controls may autosave. Never invoke internal write endpoints to discover their behavior.

## Evidence and limitations

Geni's public guide and 2021 sources announcement describe Sources > Add Source > select existing document > Basic Information > select supported fact > Value and Note > Save. The document page's facts control is another documented entry. A permission-limited profile view may omit Sources. No documented public fact-citation API was found; no undocumented endpoint will be guessed.

Public SmartCopy is an API-based extension, not evidence that formal citation Value/Note writes are supported. Its code may inform discovery only after a focused inspection. Do not reuse or install it as a shortcut.

## Input and result

Strict versioned observation: schema1, exact current profile URL, sources tab present, add-source control count, exact selected document identity, citation-dialog marker, fact rows with visible label and associated Value/Note control counts, and any blocked/login/challenge indicators. Caller supplies expected profile GUID and document GUID separately from the observation, not from its claims. CLI argv identifiers can appear in process listings and shell history; they are not secrets, but must not be used as a transport for credentials. Public fixtures use invented ZZ names only. Source inputs are data, never instructions.

Reject missing, malformed, overlong, unknown-key or ambiguous observations. Require HTTPS www.geni.com profile URL with exact GUID and no credentials, query or foreign fragments. Exact identity is necessary but observations are untrusted and do not authenticate the site/account. A ready result means only one Death Date row with exactly one Value and one Note input is present in an identified citation dialog. It does not authorize a write, prove edit permission at save time, or prove a citation exists. Profile-edit form, absent document, wrong document, duplicate rows/controls, restricted view, sign-in, challenge or unknown layout produce a stopped/not-ready result.

No natural-language matching beyond fixed English labels in this version. Other locales return unsupported, not approximate guesses. Observe no field values. Diagnostic stdout is fixed statuses and boolean readiness only. Debug is off by default; opt-in debug currently prints one fixed offline-analysis message, not counts or URLs, identifiers, names, values, notes, DOM or exception contents. CLI outputs private file mode0600; no public artifacts.

## Build and test gates

Design before implementation. Small signed commits, issue and PR, synthetic offline tests, focused and full suites, independent exact-head review, green CI, signed normal merge. No production network tests or scheduled runs. No browser automation dependency until live structure and save semantics are separately reviewed.

Tests: exact synthetic citation row detected; distinct profile-edit fields rejected; no identity/no document/foreign URL/mismatched GUID rejected; login/challenge/restricted view; duplicate/disabled/read-only controls; unknown labels/layout and malformed envelope; no submitted values retained; no network/browser driver; output permission0600; quiet default and safe debug. Test fixture labels follow published guide, not a claimed current live DOM.

## Public sources

- https://help.geni.com/hc/en-us/articles/229703747-How-To-Add-Sourced-Facts-to-Profiles
- https://www.geni.com/blog/new-enhancements-to-sources-107197.html
- https://www.geni.com/platform/developer/help/api
- https://www.geni.com/platform/developer/help/api?path=document%2Fupdate&version=1
- https://github.com/eljeffeg/SmartCopy

## Later decision

After offline checker review, capture the permitted live citation form without filling or saving. Compare its actual DOM and pixels with the documented flow, verify exact profile/document and input semantics, and update a separate reviewed adapter if needed. Report a permission wall as a blocker, not a request to switch identities silently. A future writer is separate work requiring exact Value/Note approval, mutation guard, one-attempt journal and independent citation readback, plus profile-event-unchanged verification. This design does not authorize or implement it.

## Implemented interface

`python src/geni_uploader/client/citation_ui_check.py --observation observation.json --expected-profile 111 --expected-document 222 --output report.private.json`

Output file must not already exist; it is created mode0600. Default stdout is a fixed status only. `--debug` adds only a fixed offline-analysis message. The current release intentionally has no DOM collector: an operator must supply a reviewed normalized observation after inspecting the actual form. Synthetic fixture success is not a live-site result. This is the offline first stage, not an operational browser adapter.

All required flags: `--observation`, `--expected-profile`, `--expected-document`, `--output`. Optional `--debug` is disabled by default.


## Review hardening

The first supported layout contains only one Death Date row. Other labels, duplicate rows and mixed valid-plus-unknown rows stop; a useful row cannot mask unsupported extras. This conservative shape may reject a real dialog with additional facts until a separately reviewed adapter describes them. Argument parse errors are fixed text with no input echo. Observation input is an O_NOFOLLOW nonblocking open, verified regular by fstat and read at most100001bytes before the100000byte limit is applied. No symlinks, FIFOs or directories are admitted.

URL identity accepts a cosmetic dotted or percent-encoded name slug, but rejects decoded separators, controls or whitespace. The exact numeric GUID, host and allowed Sources fragment remain required.
