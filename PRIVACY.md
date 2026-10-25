# Privacy Policy — geni-uploader

geni-uploader is a personal, user-run command-line tool, distributed as a
container image, that uploads source documents and photos to Geni profiles
the user chooses, and records upload status in a Git repository the user
chooses. It is operated by the user, on the user's own machine, for the
user's own genealogy research.

## What the tool communicates with

The running tool contacts exactly two services:

1. **Geni** (`https://www.geni.com/api`) — to read profile, document and
   photo listings, and to upload and tag documents and photos, using the
   Geni access token the user supplies.
2. **GitHub** (`https://github.com`) — to clone the status repository the
   user designates and to push upload-status updates back to it, using the
   GitHub token the user supplies.

There is no application server, no analytics, no tracking, and no
communication with any other third party.

## What data goes where

- **To Geni:** the documents and photos the user places in the upload
  manifest, with their titles, source references and tags. Content uploaded
  to Geni becomes part of Geni's shared world family tree and is governed
  by Geni's own Terms of Service and Privacy Policy, including Geni's
  visibility rules for the profiles involved.
- **To GitHub:** an upload-status file (what was uploaded, when, and its
  verification state), pushed to the Git repository the user designates.
  That repository and its access settings belong to the user.
- **On the user's machine:** the Geni access token and GitHub token are
  stored only in files on the user's own machine and are mounted into the
  container at run time. The Geni token is sent only to Geni's API as an
  Authorization header. The GitHub token is used only for Git operations
  against github.com. Tokens are never written to logs or output.

## Data the tool's author receives

None. The tool runs entirely on the user's machine and reports to no one.
The author collects no data.

## Retention and deletion

- Content uploaded to Geni is managed through Geni, under Geni's policies.
- The upload-status file lives in the user's own Git repository and can be
  deleted by the user at any time.
- Tokens can be revoked by the user at any time in their Geni and GitHub
  account settings.

## Contact

Questions about this policy: open an issue at
https://github.com/reihlinstinct/geni-uploader/issues.
