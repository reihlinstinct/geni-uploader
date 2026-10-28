# Private visual plan review

This previews source additions to existing profiles, not profile creation.
It does not upload, send mail or grant permission for a write.

After a reviewed image release enables `VISUAL_PLAN_IMAGE_READY`, the human
operator may choose `visual_review: true` on a `plan` run. Default is false.
Other modes reject that option. The optional payload contains profile/source
sequence numbers, source kinds and fixed verdicts only. No names, IDs, titles,
URLs, descriptions, paths or images are copied into it. Failure to produce a
requested payload fails the Action after protected log retention.

The workflow age-encrypts the payload separately into a `visual-plan-run...age`
file in the private data repository. No plaintext payload or PNG is published
in Action logs, summaries or public artifacts. The encrypted plan log remains
the detailed evidence. An incomplete payload is marked incomplete, never ready.

## On-demand image export

Privately retrieve and decrypt the payload using the approved log key. Do not
put the key in email, chat or a public command log. On a private workstation:

```
python visual_plan.py /private/visual.json --html /private/review.html
```

Open that HTML locally and export a PNG using a local browser screenshot.
No rendering dependency is installed in the uploader image. The HTML is inert,
contains no scripts, remote fonts, links or external requests. Inspect the PNG
for complete content, readable labels, and privacy before any delivery.

Names are masked by default, including for deceased people. Optional local
`--labels /private/reviewed-labels.json` permits separately reviewed captions:

```json
{"1": {"life_status": "deceased", "evidence": "reviewed source reference",
       "reviewed_no_living_details": true, "name": "ZZExample Person",
       "source_labels": {"1": "ZZReviewed deceased-only source caption"}}}
```

Living or unknown status never unmasks names. A classification and evidence
reference alone are not enough: every displayed name/caption must be reviewed
for incidental living-person details. Do not copy raw source descriptions or
titles into labels without that review. Unknown labels remain numbered.

Email is a separate, explicitly requested private delivery step to the owner's
confirmed address. Do not put mailbox credentials into Actions or send on every
plan. Verify the current request, recipient, image and message before sending.
Plain email attachments are not end-to-end encrypted. If that is required, use
an agreed encrypted attachment/key route instead. Retain PNG/HTML privately and
remove temporary decrypted files after delivery. No public hosting by default.
