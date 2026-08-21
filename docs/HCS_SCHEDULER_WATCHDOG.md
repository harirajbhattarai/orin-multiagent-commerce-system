# HCS recurring dry-run scheduler and watchdog

## Safety boundary

HCS scheduling is credential-free and dry-run-only. The recurring scheduler
cannot read tables directly and can execute only the zero-argument
`orin_private.enqueue_hcs_prefect_scheduled_job()` function. That function is
fixed to `hcs_gadgets`, source keys under `scheduler:orin-hcs-prod:`, and an
empty payload. It refuses to enqueue unless both Shopify write gates are off,
the mode is `dry-run`, concurrency is one, the active owner is
`prefect:orin-hcs-prod`, and the active queue is empty.

The persistent HCS content worker remains a separate process and principal. It
has the model-writer credential but no Shopify credential. The temporary
approval worker remains the only process that can receive the HCS Shopify
credential, and it is never part of the schedule.

## Fixed schedule

- Prefect pool: `orin-hcs-owner-process`
- deployment: `orin-hcs-prefect-scheduler`
- schedule slug: `hcs-daily-dry-run`
- cron: `30 11 * * *`
- timezone: `Europe/London`
- maximum concurrency: 1
- default state: pool paused, deployment paused, schedule inactive

The 11:30 time avoids overlapping the existing Hoverboard Store 11:00 run on
the current single-concurrency VPS.

## Read-only watchdog

The separate `orin_hcs_watchdog` role can read only the HCS client, runtime
gates, scheduler health, daily job, and terminal run receipt through RLS. It
cannot read Hoverboard Store, incidents, members, or artifact metadata; it
cannot execute an enqueue or worker function; and it has no mutation grant.

The `hcs-watchdog` service expects the 11:30 run and evaluates it after a
15-minute grace period. Its fixed Unix-socket request is:

```text
CHECK ORIN-HCS WATCHDOG V1
```

The OpenClaw-side client
`deploy/openclaw/orin-hcs-watchdog/bin/orin_hcs_watchdog_check.py` accepts no
arguments and receives no database credential. Its eventual OpenClaw schedule
is `45 11 * * *` in `Europe/London`, with delivery disabled until alert routing
is separately approved.

## Commissioning order

1. Merge reviewed code and database CI.
2. Apply the migration while both new roles remain `NOLOGIN`.
3. Deploy the exact immutable Prefect/watchdog image with the HCS pool,
   deployment, daily schedule, watchdog service, and OpenClaw job all disabled.
   Use only the isolated `prefect-hcs-bootstrap` service. The general bootstrap
   also manages HBStore and is prohibited for HCS commissioning.

   ```bash
   docker compose --env-file /docker/orin-prefect-shadow/hcs-deployment.env \
     -f deploy/prefect-shadow/compose.yml --profile hcs-bootstrap \
     run --rm --no-deps prefect-hcs-bootstrap
   ```

   The required receipt is `ORIN_HCS_PREFECT_BOOTSTRAP_OK`. The command creates
   or updates only `orin-hcs-owner-process` and
   `orin-hcs-prefect-scheduler`; both remain paused and its schedule inactive.
4. Set unique passwords, temporarily enable login, and install the two distinct
   session-pooler URLs using the interactive installers. Never paste either
   credential into chat, Git, shell history, or OpenClaw.

   ```bash
   deploy/prefect-shadow/install_hcs_owner_db_secret.sh
   deploy/prefect-shadow/preflight.sh --require-hcs-owner-secret \
     --allow-running-server
   deploy/vps/install_hcs_watchdog_db_secret.sh
   deploy/vps/hcs_watchdog_preflight.sh
   ```
5. Verify role identity, exact image revisions, zero restarts, no active jobs or
   incidents, closed Shopify gates, and an empty HCS source key for the proof
   date.
6. Run a near-term automatic one-shot Prefect proof. Do not invoke the flow or
   data-plane worker manually.
7. Require one automatic flow receipt, one database job/run/attempt, dry-run
   mode, payload `{}`, zero Shopify creates, no publication, no queue change,
   and no reconciliation requirement.
8. Close all gates immediately after proof. If every invariant passes, activate
   only the normal 11:30 dry-run schedule and the 11:45 read-only watchdog.

Any failed invariant returns HCS to maintenance, pauses the pool/deployment,
deactivates schedules, stops the HCS Prefect owner worker and watchdog, and
keeps both Shopify write gates off.
