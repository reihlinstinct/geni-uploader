# Protected update safety probes (#780)

Follow-up to post-merge reviews of #777 and #773. No live operation.

New alias additions must already be NFC, with ordinary single spaces only and
no invisible format characters, line/paragraph separators or C1 controls. The
combined existing/new list must be casefold-unique. Reject ambiguous input before
any effect; never normalize or rewrite approved spelling. Existing alias values
remain baseline-pinned and are not silently cleaned. This is a conservative input
rule, not verified evidence of Geni normalization. Other vendor changes may still
produce a post-write STOP; consumed intent forbids retry or automatic repair.

Synthetic probes pin owner ID/name, owner != target, distinct four-addition cap,
expiry immediately before send and after vendor spacing, and exact source/config
consistency. The batch entry path has a positive encryption-boundary control,
negative gates that cannot pass via invalid synthetic age data, fresh output-dir
checks, phase-to-exit checks, and exclusive/fsynced encrypted evidence checks.
These tests authorize no live run. Existing execution holds remain independent.

The existing-only collision case is also pinned (#782): an old list containing
casefold-equivalent values blocks a distinct new addition. The old list is not
silently deduplicated, normalized or rewritten, and the rejected plan is unmodified.
