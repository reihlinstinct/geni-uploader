# Isolated Node test process regression

Issue #319. The Node test runner sets an internal `NODE_TEST_CONTEXT` environment
variable in its child process. Passing that inherited value to a grandchild
`node --test` can make it execute zero tests while returning success. The prior
isolated runtime suite checks therefore did not prove their assertions ran.

The shared `runIsolatedSuite` helper removes that variable from a copied child
environment. It leaves the parent environment unchanged, captures output and
propagates a nonzero exit. Its 60-second process timeout exceeds the local
workerd suite's 45-second test budget; the parent allows 65 seconds.

A regression builds a deliberately failing child suite and a parent Node test
that calls the same helper. The parent must fail with exit status one. It also
runs the helper with an explicitly inherited child-v8 marker and checks the
failing child's test name appears in output. A silent zero-test pass fails the
regression. No integration permissions, credentials or production paths change.
