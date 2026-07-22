# ORIN worker

The Phase 3B worker is a one-shot, database-backed adapter around the existing
deterministic runner. It is not a scheduler. Each invocation claims at most one
due job, renews that lease while the runner is active, and stores the exact
terminal `final_result.json` in PostgreSQL.

## Safety boundary

- The `orin_worker` role has no direct table privileges.
- It can execute only `claim_next_job`, `renew_job_lease`, and `complete_job` in
  the non-exposed `orin_private` schema.
- Claims require an active client, automation enabled, Shopify writes disabled,
  concurrency one, allowed mode `dry-run`, and an empty dry-run job.
- A unique partial index allows only one leased/running job per client.
- Dry-run run rows cannot record an article, Shopify creation, publication, or
  queue mutation.
- Completion verifies the lease owner and the immutable client, request, and
  mode fields. Repeating an already committed identical completion is safe;
  a different result for the same request is rejected.
- Expired leases are reclaimable. An expired lease at maximum attempts is
  failed and creates a critical incident instead of running indefinitely.

The local runner request index provides the second idempotency layer. If a
worker dies after pipeline execution but before database completion, a later
lease claim with the same request ID reads the existing local result instead of
executing the pipeline again.

## One-shot command

```bash
python -m orin_worker once \
  --workspace-root /runtime \
  --artifact-root /evidence
```

The command requires `ORIN_WORKER_DATABASE_URL` for the dedicated
`orin_worker` login and verifies `current_user` before every operation. Never
use a `postgres` connection or Supabase service-role key.

The default lease is 1,200 seconds and the heartbeat interval is 60 seconds.
The worker exits successfully with `status: no_job_due` when no job is
eligible. It does not poll or schedule itself.

## Current deployment state

No worker credential exists, the image is not deployed, automation remains
disabled, and the legacy OpenClaw scheduler remains disabled. Phase 3B tests
must pass before provisioning the role password directly into the VPS secret
store.
