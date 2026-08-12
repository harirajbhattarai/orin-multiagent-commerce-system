# ORIN worker

The ORIN worker is a database-backed adapter around the existing deterministic
runner. The Phase 3B `once` command remains available for supervised work.
Phase 4 adds a fixed-argument `serve` command that repeats the same atomic claim
path for automatic execution. It is a queue consumer, not a scheduler: it
cannot create requests or choose their client, mode, date, or queue job.

Each claim renews its lease while the runner is active and stores every exact
`final_result.json` attempt in PostgreSQL. Terminal results also enter the
authoritative `runs` ledger.

## Safety boundary

- The `orin_worker` role has no direct table privileges.
- It can execute only `claim_next_job`, `renew_job_lease`, `defer_job`, and
  `complete_job` in the non-exposed `orin_private` schema.
- Claims require an active client, open request intake, automation enabled,
  concurrency one, and an empty job payload. Daily jobs additionally require
  broad Shopify writes disabled and allowed mode `dry-run`.
- A hidden-draft claim is a separate approval-only capability. It requires the
  broad Shopify switch to remain off, allowed mode to remain `dry-run`, the
  narrow `approved_draft_writes_enabled` gate, and a consumed human decision
  bound to the exact item, version, stored draft, and SHA-256. A direct or
  scheduler-created hidden-draft job is never claimable.
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
- The automatic command accepts no `--as-of-date` or `--job-number` override.
  It receives no payload from OpenClaw and exposes no port or Docker socket.

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
eligible.

For a supervised controlled-write test, `once` accepts an explicit
`--as-of-date YYYY-MM-DD`. The normal Compose command and all schedulers omit
this flag. Database-backed runs keep the operational workspace read-only and
write generated HTML into the private per-run evidence directory.

## Automatic command

```bash
python -m orin_worker serve \
  --workspace-root /runtime \
  --artifact-root /evidence \
  --worker-id orin-hbstore-prod \
  --poll-seconds 15 \
  --error-backoff-seconds 60
```

`serve` waits between atomic claims and backs off after database or runner
errors. SIGTERM and SIGINT stop new claims; an active lease-bound execution is
allowed to finish before the process exits. The VPS uses a 300-second stop
grace period.

The Compose service is behind the explicit `automatic-worker` profile and is
disabled until Phase 4 commissioning. Its restart policy is
`unless-stopped`, but database maintenance, request-intake, automation, mode,
approval, and concurrency gates remain authoritative. Starting the container
cannot create a job or bypass a closed gate.

The disabled-by-default VPS sequence and private Shopify token handoff are
documented in `deploy/vps/README.md`.
