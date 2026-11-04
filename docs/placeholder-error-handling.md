# Placeholder baseline errors (#737)

Unreadable or syntactically invalid current JSON and wrong-type current/base JSON objects stop the scanner with exit 1 and a fixed diagnostic, without a traceback. No baseline values are printed on these paths. Existing finding/growth checks remain unchanged. This is error-path cleanup, not a scanner bypass or baseline expansion.

Offline tests cover corrupt current JSON, wrong-type current JSON and wrong-type base JSON. No workflow, credential or live API changes. Master merge remains held pending independent exact-head review and green CI.
