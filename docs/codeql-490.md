# CodeQL regression fix (#490)

Privacy tests now extract exactly one plain inline script through HTMLParser, not regex. Exact script text remains the input to the existing CSP hash and offline DOM checks. Regressions cover mixed-case tags, duplicate/missing/unclosed/self-closing/attributed scripts. This is test parsing, not an HTML sanitizer. No callback page behavior or publication change.
