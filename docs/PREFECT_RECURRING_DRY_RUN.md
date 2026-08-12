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

The owner worker is disabled by its Compose profile until production
activation. Once explicitly activated it uses `restart: unless-stopped` and a
container-local Prefect polling health check. It receives only Prefect API
authentication plus the isolated owner database URL. It receives no Shopify,
writer, shadow, OpenClaw, ORIN worker, control API, evidence, or Docker
credential.

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
   no publication, no queue change, and no reconciliation. Verify revisions
   at their component boundaries: the Prefect deployment must match the
   reviewed scheduler revision, while `runs.code_version` must match the
   separately pinned ORIN worker image revision. Do not require a scheduler
   commit SHA to appear as the worker's `code_version`.
9. Immediately close all database gates, deactivate and remove the one-shot
   schedule, pause the recurring schedule/deployment/pool, stop and remove the
   owner worker, return the role to `NOLOGIN`, and delete its credential.
10. Reverify zero active jobs and incidents, all OpenClaw schedules disabled,
    the normal Prefect schedule inactive, and all temporary credentials absent.

Any failed invariant triggers step 9 before investigation. The normal
recurring schedule is enabled only in a later, explicit production activation
after this automatic proof passes. Shopify writes remain disabled.

## Explicit production activation

Activation is allowed only after the fresh-date automatic proof and its
component-scoped revision review have passed. During an approved production
ownership period, `orin_prefect_scheduler` is a `LOGIN` role and its unique
session-pooler URL remains installed as UID/GID `10004:10004`, mode `0400`.
This is the minimum persistent credential required for an unattended daily
worker. The role still has no table privileges and may execute only the
fixed-client, zero-argument, dry-run enqueue function.

Activate in this order:

1. deploy one exact reviewed Prefect image and verify the clean release,
   image label, server health, and zero restarts;
2. verify zero active jobs and incidents, no same-date source key, all
   OpenClaw production schedulers disabled, and Shopify writes disabled;
3. enable login for only `orin_prefect_scheduler`, install and validate its
   unique session-pooler credential without printing it;
4. start the owner worker while its pool, deployment, and schedule are still
   paused, then require the container health check and current-user probe;
5. resume the owner pool, unpause the deployment, and activate only
   `hbstore-daily-dry-run` at `0 11 * * *` Europe/London;
6. set the client active, intake and automation enabled, concurrency one,
   `allowed_mode=dry-run`, Shopify writes disabled, and scheduler owner
   `prefect:orin-hbstore-prod`;
7. enable the read-only 11:15 watchdog after its expected-owner policy is
   deployed at the same reviewed revision; keep legacy and dedicated
   OpenClaw production schedules disabled;
8. verify the owner worker is healthy with restart count zero, the normal
   Prefect schedule is the only active production schedule, and no run was
   created by the activation itself.

Rollback closes intake and automation, disables scheduler ownership, keeps
Shopify writes disabled, deactivates the Prefect schedule, pauses the
deployment and pool, stops the owner worker, returns the role to `NOLOGIN`,
and removes the owner credential. The read-only watchdog is disabled after
the production schedule is closed.
