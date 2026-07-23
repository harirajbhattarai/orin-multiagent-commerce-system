# ORIN worker

The Phase 3B worker is a one-shot, database-backed adapter around the existing
deterministic runner. It is not a scheduler. Each invocation claims at most one
due job, renews that lease while the runner is active, and stores every exact
`final_result.json` attempt in PostgreSQL. Terminal results also enter the
authoritative `runs` ledger.

## Safety boundary

- The `orin_worker` role has no direct table privileges.
- It can execute only `claim_next_job`, `renew_job_lease`, `defer_job`, and
  `complete_job` in the non-exposed `orin_private` schema.
- Claims require an active client, automation enabled, Shopify writes disabled,
  concurrency one, allowed mode `dry-run`, and an empty dry-run job.
- A unique partial index allows only one leased/running job per client.
- Dry-run run rows cannot record an article, Shopify creation, publication, or
  queue mutation.
- Completion verifies the lease owner and the immutable client, request, and
  mode fields. Repeating an already committed identical completion is safe;
  a different result for the same request is rejected.
- `retry` and `reconcile` results are written to `job_attempts`, have their
  lease cleared, and are requeued with delay. They cannot enter `runs` or the
  reconciled Shopify ownership ledger.
- `needs_review` and unknown Shopify outcomes are never terminal. Exhausting
  automatic reconciliation attempts creates a critical incident.
- Expired leases are reclaimable. An expired lease at maximum attempts is
  failed and creates a critical incident instead of running indefinitely.

The local runner request index provides the second idempotency layer. If a
worker dies after a terminal pipeline execution but before database completion,
a later lease can finalize the existing local result. Nonterminal indexes
re-execute the marker-first pipeline. Legacy v1 indexes are re-executed into the
v2 contract.

## One-shot command

```bash
python -m orin_worker once \
  --workspace-root /runtime \
  --artifact-root /evidence
```

The command requires either `ORIN_WORKER_DATABASE_URL` for isolated development
or a private file named by `ORIN_WORKER_DATABASE_URL_FILE`. The VPS contract
uses `/run/secrets/worker_database_url`. Configuring both is rejected. The
worker verifies `current_user` before every operation; never use a `postgres`
connection or Supabase service-role key.

The default lease is 1,200 seconds and the heartbeat interval is 60 seconds.
The worker exits successfully with `status: no_job_due` when no job is
eligible. It does not poll or schedule itself.

## Current deployment state

No worker credential exists, the image is not deployed, automation remains
disabled, and the legacy OpenClaw scheduler remains disabled. The
disabled-by-default VPS sequence is documented in `deploy/vps/README.md`.
