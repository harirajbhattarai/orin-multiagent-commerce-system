# Phase 7 Prefect ownership commissioning

This is a one-shot, dry-run-only proof that Prefect can become the scheduler
request owner while the existing ORIN automatic worker remains the execution
owner. It is not a recurring schedule and it cannot create a Shopify article.

## Boundary

- `orin_prefect_shadow` remains read-only and unchanged.
- `orin_prefect_scheduler` starts `NOLOGIN`, has no table privileges, and can
  execute only
  `orin_private.enqueue_hoverboard_prefect_commissioning_job()`.
- The function accepts no client, date, mode, payload, command, or schedule
  input. It creates at most one deterministic commissioning request.
- It requires client status `active`, intake and automation enabled,
  concurrency one, `allowed_mode=dry-run`, Shopify writes disabled, and
  scheduler owner `prefect:orin-hbstore-prod`.
- A transaction advisory lock serializes retries. An existing exact request is
  replayed; a different active job blocks commissioning.
- The isolated owner worker receives only Prefect API authentication and the
  `orin_prefect_scheduler` URL. It receives no Shopify, writer, ORIN worker,
  OpenClaw, control API, shadow, evidence, or Docker credential.

## Deployment state

Bootstrap creates a second process pool, `orin-owner-process`, and a paused
deployment, `orin-hbstore-owner-commissioning`. Both have concurrency one,
`CANCEL_NEW`, and no schedules. The owner worker is disabled by default and
uses `restart: "no"`.

## Controlled proof order

1. Keep all ORIN and OpenClaw gates closed. Merge the reviewed migration and
   immutable Prefect image first.
2. Temporarily enable login for `orin_prefect_scheduler`, install its unique
   session-pooler URL as mode `0400`, and validate the expected database role.
3. Confirm no active jobs or incidents, all OpenClaw schedules disabled, both
   Prefect pools and deployments paused, and Shopify writes disabled.
4. Start only the owner worker, resume only `orin-owner-process`, and create one
   ad-hoc owner deployment run. Do not add a Prefect schedule.
5. Open only the commissioning gates and set scheduler owner to
   `prefect:orin-hbstore-prod`. Shopify writes stay disabled and mode stays
   `dry-run`.
6. Require one non-replayed commissioning request, then require the existing
   automatic ORIN worker to create one terminal job/run/attempt with zero
   Shopify creates, no publication, no queue mutation, and no reconciliation.
7. Immediately close all gates, pause the owner pool/deployment, stop and
   remove the owner worker, set the database role back to `NOLOGIN`, and remove
   its VPS secret.

Any failed invariant triggers step 7 before investigation. Passing this proof
does not enable a Prefect schedule or Shopify writes; recurring ownership is a
separate reviewed promotion.
