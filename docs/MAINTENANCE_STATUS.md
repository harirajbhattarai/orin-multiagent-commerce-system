# ORIN maintenance status

Last updated: 2026-07-23

## Current phase

Phase 3 manual production verification is complete. ORIN is intentionally in
maintenance observation; scheduler transfer has not started.

The reviewed code deployed on the VPS is:

`4580604983974838168c4caaab6293db88aec830`

## Verified results

- The dedicated API and worker images are immutable and tied to the reviewed
  Git commit.
- The control API and worker use separate file-backed database credentials.
- The Shopify credential is file-backed and isolated from OpenClaw.
- A normal Compose start has no unprofiled service.
- The worker has no port, polling loop, restart policy, or scheduler.
- Read-only identity, API health, no-job, deterministic dry-run, controlled
  hidden-draft, idempotency, and reconciliation checks passed.

The controlled Shopify test created exactly one article:

- Job: 28
- Title: `Hoverboard Charger Not Working: Checks Before Buying a New One`
- Handle: `hoverboard-charger-not-working-checks-before-buying-a-new-one`
- Shopify article ID: `1007164260700`
- Published state: hidden draft (`publishedAt = null`)
- Queue file changed: no
- Durable database reconciliation: complete
- Observed article count for the request: one

The first controlled attempt was safely blocked before Shopify because H11
checked a legacy read-only evidence path. That run remains preserved. The H11
path was corrected to the private per-run evidence directory and the replacement
controlled run passed.

An identical request replay returned the original terminal result without
executing the pipeline again. A separate reconciliation probe found the existing
idempotency marker with one GraphQL read and zero mutation calls.

## Current safety state

- Client status: `maintenance`
- Automation enabled: `false`
- Shopify writes enabled: `false`
- Allowed mode: `dry-run`
- Database scheduler state: `disabled`
- Database scheduler owner: none
- Legacy OpenClaw job: disabled
- OpenClaw next wake: none
- ORIN containers: none
- ORIN loopback API port: closed

## Durable evidence

Successful run:

`/docker/orin/evidence/hb_20260723T190341Z_0c8b91a5`

Preserved pre-write H11 block:

`/docker/orin/evidence/hb_20260723T185628Z_81d75fd7`

Do not delete either directory. They contain the final result, pipeline preview,
logs, sent and fetched bodies, body hashes, verification decision, and
transaction result.

## Next approved path

Keep the system in maintenance for a short observation window. During that
window, use read-only checks only:

1. Confirm the client and Shopify write gates remain disabled.
2. Confirm no scheduler has a next wake.
3. Confirm no ORIN container or loopback API listener remains active.
4. Confirm the controlled Shopify article remains unpublished.

After the observation window:

1. Create the dedicated `orin-hbstore-prod` scheduler in a disabled state.
2. Run one supervised near-term test and verify the exact model and
   `final_result.json`.
3. Keep only one production scheduler owner.
4. Add the read-only watchdog after scheduler ownership is proven.

Do not enable the legacy main-agent scheduler, enable Shopify writes outside a
controlled transaction, or begin additional clients during the maintenance
window.
