# Privacy Policy - geni-uploader

Last updated: 27 October 2026

This policy describes the public geni-uploader project. It does not grant access
to anyone's accounts or say that a person has agreed to token custody or a
particular operating mode. Choose the mode and approve access separately.

## Operating modes and services

- **Local mode:** the user runs the container on their own machine. The project
  has no application server or built-in analytics. The running tool contacts
  Geni for the requested genealogy work and GitHub for the repository the user
  selects. The project author does not automatically receive local data.
- **Hosted GitHub Actions mode:** a user-triggered workflow runs the container
  on a GitHub-hosted runner. GitHub processes the workflow inputs, secrets,
  temporary files and logs under its own policies. Account and repository
  administrators may have access according to their permissions. Do not use
  this mode without permission from the account and data owners.
- **Separately agreed assistance or token custody:** if a person explicitly
  chooses to share private records or store a token with an assistant or other
  operator, that operator and the agreed storage provider can process the
  information within that permission. This is not implied by app registration,
  use of this project, or this policy. Agree who receives access, its purpose,
  storage, revocation and deletion before sharing a token.

Geni and GitHub also apply their own privacy policies and service terms.
The project does not add advertising or tracking services. Services separately
chosen for assistance or credential storage are outside the container's own
network calls and must be disclosed when that option is offered.

## Data handled

The tool reads the selected manifest, source documents or photos, expected
profile identities, and relevant Geni records. Requested uploads can include
names, titles, descriptions, dates, source references and profile tags. Existing
source metadata can be read or changed only through the selected supported mode.

Content sent to Geni follows Geni's visibility rules. Do not assume an uploaded
source is private merely because its input repository is private. The operator
must have permission to use the records, especially records about living people.

The selected Git repository may hold manifests, assets, profile identifiers,
item titles, timestamps, upload-status files, repair journals and encrypted logs.
Its access settings control who can read these files. Use a private repository
for personal data. The public project repository is for code and generic docs,
not family records, credentials or private logs.

## Tokens and diagnostics

Tokens are sensitive credentials. Do not paste them, application secrets, or
OAuth result URLs containing tokens into chat, email, public issues or commits.
In local mode, tokens are supplied through local files or the documented runtime
configuration. In hosted mode, configured Actions secrets are supplied to the
runner at runtime. The Geni token is intended only for Geni API requests; the
GitHub token is used for authorized repository operations.

The hosted source workflow captures raw container output in a temporary private
file, encrypts it with age for the configured recipient, and attempts to commit
only ciphertext to the selected private repository. Raw output can include
personal data, identifiers, source URLs and error context. It is not anonymous.
Anyone with the decryption key and ciphertext can read it. Public workflow logs
are intended to contain fixed operational status, not raw payloads or tokens.
Encryption, a private repository and redaction reduce exposure but are not a
promise that mistakes or service failures cannot happen.

Temporary plaintext and credentials exist during execution. Runner loss or hard
cancellation can prevent normal preservation or cleanup. Local logs and state
files remain on the user's machine unless the user deletes them. Optional
value-free plan summaries, when released and enabled, contain counts and check
results rather than source values; they are not completed writes or permission
to write.

## Retention, access and removal

The project does not impose a separate retention period on user-controlled
repositories, logs or local files. Their owners manage access and deletion.
Git history, backups and service retention can preserve earlier copies after a
file is removed. Removing an Actions secret does not remove old ciphertext,
revoke a token, erase repository history or delete content already sent to Geni.

Users can revoke Geni authorization through Geni's account controls and revoke
GitHub credentials through GitHub. Manage uploaded content under Geni's controls
and policies. If separate custody was agreed, also ask the agreed custodian to
remove its stored copy. No remote deletion of that copy is promised by the CLI.

## Contact

For a general project question, open a public issue at
https://github.com/reihlinstinct/geni-uploader/issues.
Do not include personal records or credentials. A private access or deletion
request should go to the operator or custodian through the private channel
already agreed with them, not a public issue.

## Client-side token helper page

The static callback page reads only access_token values from the URL fragment or
query locally in that browser, displays the token in a read-only field and offers
an explicit Copy button using the system clipboard. It clears the visible response
URL immediately after parsing. Conflicting or repeated token fields are refused.
Other response fields are checked only for fixed-name presence, not read by value.

A fragment is not sent in the HTTP page request. A query token IS sent to the
hosting service before the page code runs, and can be retained in hosting or
infrastructure logs and browser history. This helper cannot prevent or erase that
initial disclosure. The page script makes no further network requests, uses no
analytics or external resources, and saves nothing in cookies or browser storage.
It is not accurate to say that a query token never leaves the browser.

Use only with informed acceptance of this hosting exposure, or choose a separately
reviewed local authorization route instead. Do not manually move a token into a
query URL. Revoke any exposed authorization using Geni's controls before requesting
a replacement; issuing a new token is not proof the old one is revoked.

The code is public; it does not publish the token itself or grant custody. Paste
only into a separately agreed secure vault form, never chat, email or a public
issue. Close the tab and clear the clipboard after use. Clipboard history, sync,
extensions, other apps or screen captures can expose it. Clearing the page cannot
erase prior copies, browser history, hosting retention or previously sent requests.
