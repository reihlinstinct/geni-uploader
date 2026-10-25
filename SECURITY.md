# Security Policy

## Reporting a vulnerability

Please open a private security advisory on this repository
(Security → Advisories) rather than a public issue:
https://github.com/reihlinstinct/geni-uploader/security/advisories/new

Languages: Hebrew or English. No personal email is published on purpose.

## Scope notes

- No credentials, tokens, manifests, assets or personal data belong in this
  repo; it is scanned with GitHub secret scanning + push protection.
- The loader handles secrets only as runtime-mounted files (mode 600) and
  never prints them; the GitHub Action captures all output and encrypts it
  to the caller's own private repository before anything is logged.
- The public Actions log is fixed-format by design (exit codes, byte
  counts, yes/no markers); report any run where identifying content
  appears there.
- The container image is pinned by digest in the workflow; the loader is
  pinned by git commit (`GENI_UPLOAD_EXPECT_SHA`) at runtime.
