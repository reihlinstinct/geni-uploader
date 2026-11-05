# English-name updater guard regressions (#793)

Test-only follow-up to the #779 post-merge review. Synthetic ZZ fixtures exercise
account binding, expiry at each clock boundary, route order, body pinning,
mode-specific exact confirmation, claimed status, duplicate unions, self-target
rejection, readback identity, plan/config consistency, fresh output directories
and encryption preflight. No production, workflow or permission changes.

Expiry after consumption must not send; expiry after a send leaves the operation
consumed and never writes a final receipt. Wrong confirmation values fail before
encryption. Request order and exact body checks are exercised before transport.

No credentials, live Geni calls, dispatch, plan run or age binary are used by
these tests. The display_name recomputation question is tracked separately in
#794. Current fail-closed readback remains unchanged. Offline guard coverage is
not approval for a live update, nor proof of vendor display-name behavior.

The added file has 36 passing cases. A broad isolated scan removed 53 require/now
statements across both runners: 37 are killed by the original plus new tests.
This is not a claim that every statement is independently pinned. The remaining
16 include guards outside the review scope and checks masked by other layers;
post-count/read-only checks are redundant under the fixed request sequence.
