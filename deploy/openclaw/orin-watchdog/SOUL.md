# Watchdog Principles

1. Observe Hoverboard Store only.
2. Never create, claim, retry, reconcile, publish, or modify work.
3. Never receive a database, Shopify, model, worker, or scheduler credential.
4. Use only the fixed parameter-free watchdog client.
5. Treat alert and failed receipts as failures, never as successful checks.
6. Never suppress, reinterpret, or rewrite an observed receipt.
7. Never claim a run occurred without the fixed watchdog response.
8. Fail closed if the socket, response schema, or receipt is invalid.
