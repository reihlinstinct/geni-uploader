# CodeQL regression fix (#489)

Temporary state paths now live inside managed private TemporaryDirectory instances, cleaned at process exit. Regression checks unique directories, mode0700 and cleanup. The alert6 value was an invented profile ID passed to a manifest, not a credential. It is renamed synthetic_profile_id with explicit synthetic data; the stderr redaction regression remains. No alert dismissal or production storage change.
