# Encrypted own-profile probe

One human-run GET to
`https://www.geni.com/api/profile?fields=id,guid,name,public,is_alive`.
The official SDK says /profile without an ID addresses the current user's
profile: https://www.geni.com/platform/developer/help/sdk_js . Field contracts:
https://www.geni.com/platform/developer/help/api?path=profile .
This is not a parent upload, write-permission test or proof of intended identity.

The token-probe environment requires the same human approval and master-only
policy described in token-probe.md. Existing TOKEN_PROBE_CREDENTIAL is reused;
there is no second token, data-repo credential or private key in this workflow.
A separately approved environment variable PROFILE_REPORT_RECIPIENT must hold
the existing age public recipient. Code pins its SHA256 and refuses any different
or missing recipient before the read. No environment settings are applied by
this PR. Do not enable/run until the recipient and decryption custody are audited.
An administrator able to change code/protection remains a risk.

No expected name or ID is needed. There are NO public match booleans. Public log
prints fixed report/encryption status plus GENI_WRITES=0 and
OWNER_IDENTITY=NOT_VERIFIED. No name, identifier, privacy/living value, body,
error text or response length is printed. Do not add debug output on failure.
No redirect, proxy, cookie jar, retry, fallback auth or extra profile read.

The encrypted report contains ONLY returned id/guid/name/public/is_alive,
requested fields/source endpoint, UTC observation time, reviewed run SHA, schema,
missing-field list and explicit unverified-identity/no-write markers. Missing
fields are null/unknown, not inferred. Extra returned fields are discarded. At
least one string profile identifier is required; invalid supplied field types
stop. No email, phone, dates, biography, relatives, links or whole response is
recorded. No comparison against a person's name is performed.

The allowlisted JSON exists only in memory, padded with spaces to exactly16384
bytes, then piped to checksum-pinned age v1.3.2 using only the public recipient.
No plaintext file is created. The ONLY artifact file is profile-report.age,
with a generic artifact name and1-day requested retention. Ciphertext and public
run metadata may be downloaded/copied before expiry; retention is not a recall.
Fixed-size padding hides exact JSON length, not that a run occurred. Encryption
failure publishes no report. The private key never enters CI. Decryption is
separate, private and requires authority for the key/report and eventual storage.
Do not commit decrypted content or feed it into an upload automatically.

After review/merge and separately approved recipient configuration: human opens
Actions > Encrypted own-profile probe (read-only, manual), new Run workflow on
master, confirmation TEST. Inspect exact reviewed run SHA, then Review deployments
and approve token-probe. Only the human executes. Any STOP means stop; a fresh
request is a new deliberate choice. Share the run link, never a token screenshot.
