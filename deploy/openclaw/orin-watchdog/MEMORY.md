# Durable Commissioning Memory

- Agent ID: `orin-watchdog`
- Client ID: `hoverboard_store`
- Scope: read-only scheduler observation
- Database access: none
- Shopify access: none
- Model access: none
- Worker access: none
- Scheduler ownership: none
- Approved future command: `python3 bin/orin_watchdog_check.py`
- Command arguments: prohibited
- Normal check time: after `11:15 Europe/London`
- Current state: disabled
- Alert delivery: disabled

Operational truth comes from the validated fixed-socket response and durable
database receipts, not conversational memory.
