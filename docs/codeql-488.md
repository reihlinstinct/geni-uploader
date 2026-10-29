# CodeQL regression fix (#488)

The synthetic service transport now parses URLs and compares an exact origin with explicit route, query, fragment and userinfo checks. Regression tests reject suffix hosts, userinfo, wrong ports/protocol and unsupported paths. No production transport change.
