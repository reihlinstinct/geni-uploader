# Comparison-only alias collision keys (#796)

Existing aliases can contain decomposed Unicode, NBSP or repeated spaces even
though proposed additions must already meet the stricter syntax rules. Raw
casefold alone failed to detect equivalent existing/new or existing-only names.

Collision keys normalize to NFC, split and join whitespace, casefold, and apply
NFC again. The keys are used only for collision detection. Stored aliases,
approved additions, order, payload bytes and intent markers are not rewritten.
The accepted syntax for new aliases is unchanged. A normalized collision stops
before any effect; it is not an identity match, merge or permission override.

Test-first: six collision cases failed and five control cases passed before the
source change. Controls verify exact stored alias payload bytes. No credentials,
network, live Geni calls or dispatch are involved.
