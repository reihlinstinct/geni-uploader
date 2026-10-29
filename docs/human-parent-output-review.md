# Local review of supplied human probe output

This is an offline output adapter, not a collector, live preflight or executor.
A human may decrypt the existing read-only probe export using their own approved
local process, then pass its protected plaintext file and protected connection
configuration to parent_output.py. Decryption and collection are not performed
by this command. No credential is accepted. No URL, endpoint, OAuth, dispatch,
network request or production path is added.

The adapter checks the exact expected envelope and supplied connection/owner
binding, mode, disabled/unproved flags and timestamp. The supplied collection
time must claim at most 15 minutes ago, not the future. That is input hygiene,
not source authentication or proof that current remote state matches the file.
The configured expected name remains a reviewed configuration field; this
adapter binds canonical ID only and does not authenticate a name or person.
Every summary includes the fixed name_checked:false flag; supplying a configured
name does not change it.
The existing collector and its strict merge checks remain unchanged.

Only bounded snapshot fields reach the conservative offline parser. Its summary
contains fixed states, a content hash and observed count, no names, node IDs,
connection ID or raw provider data. The hash can correlate the same private
snapshot, so keep even summaries private unless sharing is approved. A summary
is not proof of absence of hidden parents. Unknown merge stays unknown. Every
output states unauthenticated source, no reviewer live checks, creation false,
and unknown hidden-parent/slot/private/default-locale create behavior.

The command reads only regular owner-only files and writes no files. It prints
a sanitized summary on success or fixed failure text. It never prints supplied
errors, paths, names or credentials. It cannot enable the production gate.
No human should treat a matching timestamp, summary or merge as approval to
create parents. A signed live Plan, vendor proofs, actual executor release and
separate human write approval remain required.
