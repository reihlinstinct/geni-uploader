# Six-GET transport regression plan (#680)

Scope: tests only for the existing household GET transport. Use a fake HTTPS connection, fake clock and synthetic response bytes. Cover malformed JSON, body byte cap, whole-response deadline, 15-second pacing and expiry during the wait. Assert one attempted GET and connection cleanup on failure, no retry and no stdout leakage. No runtime, workflow, credential or live Geni changes.

Each regression must fail under an isolated mutation of its corresponding production guard. Existing route/order/method tests remain. This is local preparation only; master remains frozen pending independent review and green exact-head CI.
