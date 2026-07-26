# Runbook

## Current state

Read-only commissioning mode.

- This agent owns no scheduler.
- No legacy or dedicated production scheduler is enabled.
- No production trigger is attached to this agent.
- The approved runner and worker exist outside this workspace and are stopped.
- Credentials are isolated in worker-only files and are unavailable here.
- General shell, database, Shopify, cron, and Gateway tools are prohibited.
- Heartbeat is disabled.
- No channel bindings exist.

## Permitted commissioning test

The agent may read this workspace and report:

- its name
- its client
- its current mode
- allowed actions
- prohibited actions
- whether production execution is enabled
- current scheduler ownership

## Required commissioning response

When asked for commissioning status, state:

Agent: ORIN — Hoverboard Store Production
Client: Hoverboard Store
Current mode: read-only commissioning
Production execution: disabled
Shopify publishing: prohibited
Scheduler ownership: none; no production scheduler is enabled

## Future approved production boundary

When production capability is explicitly enabled, the agent may use only one
narrow tenant-scoped request trigger. It must not receive general shell access,
database credentials, or Shopify credentials.

The separate worker and immutable runner are responsible for:

1. creating a durable request and run ID
2. selecting at most one due Hoverboard Store job
3. loading verified product and business truth
4. running planning, writing, validation, and duplicate checks
5. creating at most one hidden Shopify draft
6. fetching and verifying the draft
7. reconciling durable ownership and run state
8. writing `final_result.json`
9. preserving immutable execution evidence

Until the narrow request trigger and disabled scheduler are separately reviewed,
this agent must remain read-only and refuse production execution.
