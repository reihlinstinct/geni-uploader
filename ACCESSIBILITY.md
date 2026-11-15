# Accessibility statement

We want geni-uploader to be usable by everyone. Our target is WCAG 2.2 level AA for
user-facing content and interfaces.

## What we do

- Semantic markup and keyboard-navigable interfaces.
- Readable contrast and scalable text.
- This project ships no end-user web UI today; this statement covers its documentation and any interfaces it grows.

## Known limitations

Accessibility work is ongoing. If something blocks you, we want to know.

## Feedback

Report an accessibility problem by opening an issue:
https://github.com/reihlinstinct/geni-uploader/issues/new/choose
If the report is sensitive, use a private security advisory instead:
https://github.com/reihlinstinct/geni-uploader/security/advisories/new

## Documentation link check

The shared Pages theme override in `docs/_includes/head-custom.html` underlines
content and footer links so they do not depend on color alone (issue #835).
A source regression test guards both selectors. A local Chromium/axe check of
the home and privacy pages at desktop and mobile widths reproduces the original
barrier and checks the override. Automated checks are not a conformance audit;
manual assistive-technology and other-browser review remain necessary.
