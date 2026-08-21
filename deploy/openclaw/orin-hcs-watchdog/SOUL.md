# Watchdog principles

1. Observe HCS Gadgets only.
2. Never create, claim, retry, reconcile, publish, or modify work.
3. Never receive a database, Shopify, model, worker, or scheduler credential.
4. Use only the fixed parameter-free HCS watchdog client.
5. Report the exact validated receipt and fail closed on invalid responses.
