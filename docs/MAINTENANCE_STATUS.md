# ORIN maintenance status

Last updated: 2026-07-26

## Current phase

Phase 3 manual verification is complete. Phase 4 commissioning has started, but
production scheduler ownership has not transferred. ORIN remains in
maintenance.

The isolated `orin-hbstore-prod` agent and its five boundary files are
versioned, deployed, and verified. Its dedicated schedule is wired only to one
fixed no-argument Python client over a private Unix socket. The job remains
disabled, has no delivery, and has no agent or tool execution path.

The reviewed code deployed on the VPS is:

`c569ab92e09f9ae2af86edb25d4baf62de1f546e`

## Verified results

- The dedicated API and worker images are immutable and tied to the reviewed
  Git commit.
- The control API and worker use separate file-backed database credentials.
- The Shopify credential is file-backed and isolated from OpenClaw.
- A normal Compose start has no unprofiled service.
- The worker has no port, polling loop, restart policy, or scheduler.
- Read-only identity, API health, no-job, deterministic dry-run, controlled
  hidden-draft, retry/idempotency, and partial-failure reconciliation checks
  passed.
- MiniMax M3 produced the Job 29 article under the fail-closed content-quality,
  topic-identity, HTML, publisher, live-draft, and post-create verification
  gates.
- The exact stored Job 29 article passes the content-quality contract with
  1,927 visible words, 8 H2s, 30 paragraphs, 3 FAQ items, 13 internal links, no
  quality blockers, and no Hoverkart contamination term.
- PRs 24-26 added the manual-only Job 29 pin, aligned it with the active planner
  contract, and aligned the writer plan with the topic-identity gate.
- PRs 28-29 added and stabilized the credential-free reconciliation drill.
  The exact reviewed drill image ran with `--network none`, a read-only root
  filesystem, no Shopify environment variables, and only the loopback network
  interface.
- PR 31 versioned the five `orin-hbstore-prod` boundary files and added tests
  for required safety statements and secret-value patterns.
- The isolated commissioning test ran on `minimax/MiniMax-M3`. It correctly
  identified Hoverboard Store, read-only commissioning mode, production
  execution disabled, scheduler ownership none, no channel bindings, and
  heartbeat disabled. Its runtime exposed only the `read` tool.
- PRs 33-34 added and corrected the narrow HBStore scheduler trigger. It uses
  a distinct `orin_scheduler` role, a private Unix socket, one fixed argv, and
  an immutable source-job key. The worker-compatible job payload is empty;
  no client, mode, schedule, or arbitrary payload comes from OpenClaw.
- Closed-gate trigger commissioning returned a blocked response with zero
  queued scheduler jobs.
- The supervised scheduler dry-run was accepted once, replayed idempotently,
  claimed by the worker, and durably finalized. Shopify creates, publishing,
  and queue changes were all zero. The pipeline stopped at the content-quality
  gate before any Shopify transaction.
- PR 36 added one bounded MiniMax quality-correction attempt. If an initial
  model response fails the deterministic contract, ORIN regenerates once using
  only the machine-readable failed requirements, stores private evidence for
  both attempts, and remains blocked unless the replacement passes. It does
  not send the prior article text back to the model and does not alter Shopify
  or queue behavior.
- PR 36 passed the application and database CI checks before merge. The VPS
  trigger and dormant worker images were rebuilt from this exact commit; only
  the trigger sidecar was restarted and it is healthy.

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

The partial-failure drill then simulated a remote create whose response was
lost. Attempt 1 timed out with `shopify_write_state=unknown`,
`reconciliation_status=needs_review`, and `replay_disposition=reconcile`.
Attempt 2 found the same marker-owned unpublished article and terminalized as
reconciled. Attempt 3 returned the cached attempt-2 result. The simulated remote
state recorded exactly one create. No Shopify network call or real article was
possible during the drill.

## Current safety state

- Client status: `maintenance`
- Automation enabled: `false`
- Shopify writes enabled: `false`
- Allowed mode: `dry-run`
- Database scheduler state: `disabled`
- Database scheduler owner: none
- Legacy OpenClaw job: disabled
- Dedicated `orin-hbstore-prod` commissioning job: disabled
- Dedicated job payload: fixed `python3` argv to the HBStore socket client
- Dedicated job agent/tools: none
- Dedicated job delivery: none
- Production trigger attached: yes, disabled
- OpenClaw next wake: none
- ORIN containers: scheduler trigger sidecar only; no API or worker container
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

Successful partial-failure drill evidence:

`/docker/orin/evidence/drills/partial_failure_reconciliation_dd5c21f_20260726T1909Z`

Local operator copy:

`/Users/harirajbhattarai/Documents/COMPUTER_USE/ORIN_EVIDENCE/drills/partial_failure_reconciliation_dd5c21f_20260726T1909Z`

The earlier fail-closed simulator timing result is intentionally preserved at:

`/docker/orin/evidence/drills/partial_failure_reconciliation_a1fc792c_20260726T1903Z`

The previous and deployed agent boundary files are preserved at:

`/docker/orin/evidence/config-deployments/orin-hbstore-prod_ff1ccf_20260726T1922Z`

Successful scheduler-boundary evidence (the content pipeline was correctly
blocked before Shopify):

`/docker/orin/evidence/hb_20260726T210343Z_2dcfa08c`

The Job 28 dry-run reached the actual writer and then failed closed because the
first model output had 565 visible words, several underdeveloped sections, and
13 uses of the target keyword. The result recorded zero Shopify creates, no
publish, and no queue change. PR 36 is deployed to provide exactly one bounded
correction attempt for this class of failure; it has not yet been exercised
against MiniMax on the VPS.

## Next approved path

Continue Phase 4 without enabling either schedule:

1. Run another supervised dry-run through the already-attached disabled fixed
   trigger. Confirm a terminal `final_result.json` with zero Shopify creates,
   publishing, and queue changes, and verify that the bounded writer retry
   either produces a clean content-quality receipt or still fails closed.
2. Run the separately approved controlled hidden-draft test only after the
   dry-run content-quality result is clean.
3. Transfer scheduler ownership only after that test. Keep exactly one
   production scheduler enabled.
4. Add the read-only watchdog after scheduler ownership is proven.

Do not enable the legacy main-agent scheduler, enable Shopify writes outside a
controlled transaction, or begin additional clients before HBStore scheduler
ownership is proven.
