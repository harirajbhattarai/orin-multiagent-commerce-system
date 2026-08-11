# Phase 7 recurring Prefect dry-run scheduler

This promotion gives Prefect the normal 11:00 Europe/London scheduler request
boundary for Hoverboard Store. It does not give Prefect Shopify credentials,
content-worker credentials, arbitrary SQL access, or hidden-draft permission.

## Fixed boundary

- `orin_prefect_scheduler` remains `NOLOGIN` outside an approved run window.
- It has no direct table privileges and can execute only
  `orin_private.enqueue_hoverboard_prefect_scheduled_job()`.
- The previous one-shot commissioning function is revoked from the role.
- The function accepts no client, date, mode, payload, command, or schedule
  input.
- It uses the same London business date, source key, and deterministic request
  identity as the retired OpenClaw scheduler boundary. A scheduler handoff
  therefore cannot create a second daily request.
- It requires client status `active`, intake and automation enabled,
  concurrency one, `allowed_mode=dry-run`, Shopify writes disabled, and
  scheduler owner `prefect:orin-hbstore-prod`.
- A transaction advisory lock serializes same-day calls. A valid existing
  request replays; a different active job blocks the enqueue.

## Disabled-by-default deployment

Bootstrap installs `orin-hbstore-prefect-scheduler` on
`orin-owner-process` with:

- cron `0 11 * * *`;
- timezone `Europe/London`;
- schedule slug `hbstore-daily-dry-run`;
- the recurring schedule inactive;
- the deployment paused;
- pool concurrency one;
- deployment collision strategy `CANCEL_NEW`;
- zero retries and no parameters.

The owner worker is disabled by its Compose profile, uses `restart: "no"`,
and receives only Prefect API authentication plus the isolated owner database
URL. It receives no Shopify, writer, shadow, OpenClaw, ORIN worker, control
API, evidence, or Docker credential.

## Automatic ownership proof

The proof must use a new London business date that has no existing normal
scheduler source key. It must not delete or rewrite a previous scheduler
receipt to manufacture a fresh test.

1. Merge the reviewed migration and immutable image with all gates closed.
2. Apply the migration, bootstrap the inactive recurring schedule, and verify
   the exact image, pool, deployment, cron, timezone, and inactive state.
3. Temporarily enable login for `orin_prefect_scheduler`, install its unique
   session-pooler URL as mode `0400`, and validate `current_user`.
4. Confirm zero active jobs and incidents, all OpenClaw schedules disabled,
   Shopify writes disabled, and no existing source key for the proof date.
5. Start only the owner worker and resume only `orin-owner-process`.
6. Add one active `COUNT=1` Prefect schedule for the near-term proof time,
   leaving the normal daily schedule inactive. Unpause only the scheduler
   deployment, then open only the dry-run commissioning gates.
7. Do not create a deployment run manually. Require Prefect to create one
   auto-scheduled flow run with no parameters and no retry.
8. Require `replayed=false`, the exact normal daily source key, and one
   automatic ORIN worker terminal job/run/attempt with zero Shopify creates,
   no publication, no queue change, and no reconciliation.
9. Immediately close all database gates, deactivate and remove the one-shot
   schedule, pause the recurring schedule/deployment/pool, stop and remove the
   owner worker, return the role to `NOLOGIN`, and delete its credential.
10. Reverify zero active jobs and incidents, all OpenClaw schedules disabled,
    the normal Prefect schedule inactive, and all temporary credentials absent.

Any failed invariant triggers step 9 before investigation. The normal
recurring schedule is enabled only in a later, explicit production activation
after this automatic proof passes. Shopify writes remain disabled.
