# Policy and transport diagnostics regression (#584)

The protected parent runner imports the shared fixed-field setup classifier. Add a synthetic direct regression showing that a policy Blocked error differs from a TransportStop error at the same stage. Only the exact transport type can retain its fixed code, bounded status and boolean redirect flags. Arbitrary error text and extra evidence never appear. No runtime, workflow, credentials or live execution change.
