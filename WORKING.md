# Source workflow operation

Agents never post the exact source-run command comments, never invoke this source workflow and never use its token. This applies even when an agent shares the owner's account identity.

The dedicated control issue is selected in `.github/geni-command-policy.json`. Only new, unedited comments by the configured owner on that issue accept the two exact read-only commands listed there. No additional text, arguments, code fences or whitespace are accepted. Pull-request comments, other issues, other actors and write commands are refused. Do not paste private source data into the issue.

Commands use the currently selected private Actions secrets. They do not choose or disclose a private repository, ref, expected SHA or manifest path. Those selections must be reviewed and pinned before a human posts a command. A mismatched expected SHA stops the container. A plan's protected-log commit changes the private branch head; re-pin to its current exact head before the next fresh run. A rejected command performs no source work.

All upload or metadata-repair writes remain manual workflow dispatch with explicit confirmation after review. A plan is not authorization to write.
