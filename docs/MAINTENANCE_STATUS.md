# ORIN maintenance status

Last updated: 2026-07-26

## Current phase

Phase 3.5 model writing and the controlled Job 29 hidden-draft transaction are
deployed and verified. ORIN is intentionally back in maintenance; scheduler
transfer has not started.

The manual verification sequence has passed through the controlled
hidden-draft and terminal replay/idempotency tests. The next reliability task is
the partial-failure reconciliation drill. It must use a controlled fault or
simulation and must not create another Shopify article.

The reviewed code deployed on the VPS is:

`cee122f0853f2aa35f69adcf187e610b957a5b67`

## Verified results

- The dedicated API and worker images are immutable and tied to the reviewed
  Git commit.
- The control API and worker use separate file-backed database credentials.
- The Shopify credential is file-backed and isolated from OpenClaw.
- A normal Compose start has no unprofiled service.
- The worker has no port, polling loop, restart policy, or scheduler.
- Read-only identity, API health, no-job, deterministic dry-run, controlled
  hidden-draft, idempotency, and reconciliation checks passed.
- MiniMax M3 produced the Job 29 article under the fail-closed content-quality,
  topic-identity, HTML, publisher, live-draft, and post-create verification
  gates.
- The exact stored Job 29 article passes the content-quality contract with
  1,927 visible words, 8 H2s, 30 paragraphs, 3 FAQ items, 13 internal links, no
  quality blockers, and no Hoverkart contamination term.
- PRs 24-26 added the manual-only Job 29 pin, aligned it with the active planner
  contract, and aligned the writer plan with the topic-identity gate.

The latest controlled Shopify test created exactly one article:

- Job: 29
- Title: `Birthday Hoverboard Gift Guide for Kids UK`
- Handle: `birthday-hoverboard-gift-guide-for-kids-uk`
- Model: `MiniMax-M3`
- Shopify article ID: `1007195390300`
- Published state: hidden draft (`publishedAt = null`)
- Queue file changed: no
- Durable database reconciliation: complete
- Observed article count for the request: one

The first Job 29 controlled attempt was safely blocked before Shopify. The
topic-identity gate detected a contradictory CTA H2 and a Hoverkart link
supplied to a non-Hoverkart plan. That run recorded
`shopify_write_state=not_attempted`, zero creates, unpublished state, and no
queue change. The writer contract was corrected and the fresh request passed.

An identical request replay was then run with networking disabled and without
Shopify or MiniMax credentials. It returned the original terminal result,
created no new run directory, and left exactly one database run, one
reconciliation row, and one observed Shopify create.

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

`/docker/orin/evidence/hb_20260726T184559Z_a0ed5cae`

Preserved pre-write Job 29 topic-identity block:

`/docker/orin/evidence/hb_20260726T183807Z_53a3d819`

Do not delete either directory. They contain the final result, pipeline preview,
logs, model request/response evidence, the generated article, verification
decision, and transaction result.

Local operator copies of the successful final result, pipeline preview, and
article are stored under:

`/Users/harirajbhattarai/Documents/COMPUTER_USE/ORIN_EVIDENCE/hb_20260726T184559Z_a0ed5cae`

## Next approved path

Keep the system in maintenance for a short observation window. During that
window, use read-only checks only:

1. Confirm the client and Shopify write gates remain disabled.
2. Confirm no scheduler has a next wake.
3. Confirm no ORIN container or loopback API listener remains active.
4. Confirm the controlled Shopify article remains unpublished.

After the observation window:

1. Run the partial-failure reconciliation drill without creating another
   Shopify article.
2. Confirm the drill cannot terminalize unknown Shopify state and that replay
   converges to one reconciled article.
3. Create the dedicated `orin-hbstore-prod` scheduler in a disabled state.
4. Run one supervised near-term test and verify the exact model and
   `final_result.json`.
5. Keep only one production scheduler owner.
6. Add the read-only watchdog after scheduler ownership is proven.

Do not enable the legacy main-agent scheduler, enable Shopify writes outside a
controlled transaction, or begin additional clients during the maintenance
window.
