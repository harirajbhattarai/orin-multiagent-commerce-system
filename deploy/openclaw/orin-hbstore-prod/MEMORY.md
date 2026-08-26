# Durable Commissioning Memory

- Agent ID: `orin-hbstore-prod`
- Client ID: `hoverboard_store`
- Client: Hoverboard Store
- Model: `minimax/MiniMax-M3`
- Workspace: isolated from the default agent and every other client
- Current mode: read-only commissioning
- Production execution: disabled
- Scheduler ownership: none
- Channel bindings: none
- Heartbeat: disabled
- Direct shell access: prohibited
- Direct database access: prohibited
- Direct Shopify access and credentials: prohibited
- Shopify live publishing: always prohibited
- Allowed production outcome after future approval: at most one verified
  hidden draft for one tenant-scoped request
- Operational truth: durable database records and immutable run evidence, not
  conversational memory

Phase 3 manual reliability tests passed, including no-job, controlled
hidden-draft, retry/idempotency, and network-isolated partial-failure
reconciliation. This fact does not enable scheduling or production execution.

Never infer that a run occurred from a prompt, plan, or scheduler message.
Report success only from an observed terminal `final_result.json`.
