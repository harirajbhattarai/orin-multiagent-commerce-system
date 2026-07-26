# ORIN maintenance status

Last updated: 2026-07-26

## Current phase

Phase 3 manual verification is complete. Phase 4 commissioning has started, but
production scheduler ownership has not transferred. ORIN remains in
maintenance.

The isolated `orin-hbstore-prod` agent and its five boundary files are
versioned, deployed, and verified. A dedicated schedule exists only in disabled
commissioning form. It has no production trigger, no delivery, and only the
`read` tool.

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
- Dedicated job tools: `read` only
- Dedicated job delivery: none
- Production trigger attached: no
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

Successful partial-failure drill evidence:

`/docker/orin/evidence/drills/partial_failure_reconciliation_dd5c21f_20260726T1909Z`

Local operator copy:

`/Users/harirajbhattarai/Documents/COMPUTER_USE/ORIN_EVIDENCE/drills/partial_failure_reconciliation_dd5c21f_20260726T1909Z`

The earlier fail-closed simulator timing result is intentionally preserved at:

`/docker/orin/evidence/drills/partial_failure_reconciliation_a1fc792c_20260726T1903Z`

The previous and deployed agent boundary files are preserved at:

`/docker/orin/evidence/config-deployments/orin-hbstore-prod_ff1ccf_20260726T1922Z`

## Next approved path

Continue Phase 4 without enabling either schedule:

1. Implement and review one narrow tenant-scoped request trigger. It may create
   only Hoverboard Store requests through the control boundary and must not
   expose general shell access, database credentials, or Shopify credentials to
   OpenClaw.
2. Attach that trigger to the dedicated job while the job remains disabled.
3. Run one supervised manual or near-term automatic test and verify the exact
   model and terminal `final_result.json`.
4. Transfer scheduler ownership only after that test. Keep exactly one
   production scheduler enabled.
5. Add the read-only watchdog after scheduler ownership is proven.

Do not enable the legacy main-agent scheduler, enable Shopify writes outside a
controlled transaction, or begin additional clients before HBStore scheduler
ownership is proven.
