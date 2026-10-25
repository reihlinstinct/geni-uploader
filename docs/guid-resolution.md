# Finding the API id for a Geni profile URL number

Geni profiles carry **two different identifiers**, and the one in the
profile's website URL is usually **not** the one most API calls expect:

- **Node id** - the API's primary identifier. Singular reads use the
  form `api/profile-<node id>`, and writes that reference a profile
  (tagging, for example) embed this id. Node ids are typically short
  (the public API documentation's examples use values like
  `122248213`).
- **Guid** - a "globally unique identifier", typically a much longer
  number. The profile's canonical website URL is keyed by the guid
  (`/people/id/<guid>` redirects to the profile page), so the long
  number you copy out of a profile's web address is the guid, not the
  node id.

## Why a URL number can fail every naive API call

If you take the long number from a profile's URL and try the obvious
forms, each one fails *silently*:

| Call form with a guid | Observed result |
| --- | --- |
| `api/<guid>` (bare) | HTTP 500 |
| `api/profile-<guid>` | HTTP 200 with an empty result set |
| `api/profile?guids=<guid>` | HTTP 400 |
| `api/profile?ids=<guid>` (bulk, any guid form) | HTTP 200, empty results |

The working form is the immutable **`profile-g<guid>`** prefix:

    GET https://www.geni.com/api/profile-g<guid>

which returns the full profile, including its **node id** - the value
later API calls need. The served profile's `guid` field equals the
input number, which is what confirms the mapping.

## Evidence and confidence

- The `profile-g<guid>` form and the failure table above come from a
  third-party open-source client
  ([dmalch/go-geni#71](https://github.com/dmalch/go-geni/issues/71)),
  which reports live probing against the production API. That is
  medium-confidence external evidence: real, reproducible claims, not
  Geni's own documentation.
- This repository then **independently confirmed** the behavior live
  against its own manifest targets (the `pguid` diagnostic, followed by
  wiring into `verify_profile`): every target's URL number resolved
  through `profile-g<guid>` to a served profile whose guid equaled the
  input and whose node id differed from it.

## How this tool resolves a URL number

`verify_profile` (used by `plan` and `run` before anything else
touches a target) resolves fail-closed, never conflating the two
spaces:

1. **Node-id form first** (`api/profile-<N>`). If it serves a profile
   whose recorded names match the manifest's `expect_name`, the number
   IS a node id and is used as-is. A served profile whose names do
   **not** match raises immediately - a name mismatch never falls
   through to the second identity space.
2. **Guid form second** (`api/profile-g<N>`), only after the node-id
   form returns empty or an HTTP error. It resolves **only** when all
   of these hold: the served `guid` equals the input number, the
   served `id` (node id) is nonempty, and the same strict name guard
   passes. The *served* node id - not the URL number - is what later
   calls (listings, tags, readbacks) use.
3. Anything else raises, and the target is skipped. An unresolved
   target is never guessed.

Two operational guarantees around this:

- **Stop on throttle:** an HTTP 429 aborts the run immediately and is
  never followed by another request (including the fallback above).
- **No values in logs:** diagnostics print shapes and booleans only
  (`guid_equals_input`, name-match), never identifiers or names.

The `pguid` container mode runs this resolution as a standalone
read-only check (one paced GET per manifest target) when you want to
confirm the mapping without running a full plan.
