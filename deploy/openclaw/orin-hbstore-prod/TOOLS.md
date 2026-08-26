# Approved Tools

## Current mode: read-only commissioning

Allowed:

- read files inside this isolated agent workspace
- report identity, client scope, safety boundaries, and commissioning state

Denied:

- general shell or process execution
- write, edit, or patch access
- browser automation
- direct database access
- direct Shopify access or credentials
- cron or Gateway modification
- elevated execution
- spawning sessions or agents
- cross-client file, queue, credential, or evidence access

There is currently no approved production trigger attached to this agent.

Future production execution must use a narrow tenant-scoped request boundary.
The separate worker—not this conversational agent—must invoke the immutable
runner, access credentials, reconcile Shopify state, and write evidence.

If asked to run, modify, publish, schedule, or transact before that trigger is
installed and approved, report that production execution is disabled.
