# ORIN maintenance status

Last updated: 2026-07-27

## Current phase

Phase 3 manual verification is complete. Phase 4 commissioning has started, but
production scheduler ownership has not transferred. ORIN remains in
maintenance.

The isolated `orin-hbstore-prod` agent and its five boundary files are
versioned, deployed, and verified. Its dedicated schedule is wired only to one
fixed no-argument Python client over a private Unix socket. The job remains
disabled, has no delivery, and has no agent or tool execution path.

The reviewed code deployed on the VPS is:

`31c0357276e5cb815d83eb73264100e460fb43b6`

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
- PR 38 hardened the private trigger boundary with Linux peer-credential
  authorization. The sidecar runs as UID/GID `10002:1000`; its private socket
  is owned by `10002:1000` with mode `0620`, and only the OpenClaw UID is
  accepted as a caller.
- PRs 39-42 aligned the MiniMax prompt with deterministic review policy, added
  non-secret model failure diagnostics, and applied exactly one bounded retry
  to correctable structural and content-policy failures. Provider, network,
  and credential failures remain non-retryable.
- The bounded retry was exercised on the VPS. Attempt 1 failed the model-output
  policy and attempt 2 produced a corrected article of approximately 2,369
  words. Topic identity and the full post-write content review passed. No
  Shopify write or queue change occurred.
- PR 43 made publisher evidence fail-safe by persisting canonical JSON before
  optional Markdown projection. A standalone Phase 2E verification against
  the accepted article returned `BLOCKED_DUPLICATE_SHOPIFY_HANDLE`, preserved
  both evidence formats, and recorded `shopify_touched=false` and
  `queue_touched=false`.
- PRs 38-43 passed application and database CI before merge. The VPS trigger
  sidecar is healthy at the reviewed deployed revision shown above.
- Job 30 was selected as a fresh manual-only commissioning topic while the
  existing Job 28 sample draft was preserved. A live read-only Shopify
  inventory refresh returned 44 articles with no exact or near title/handle
  conflict for Job 30.
- MiniMax M3 generated the Job 30 article under the bounded writer policy.
  Topic identity and the full post-write review passed. A separate Phase 2E
  run against the exact preserved article refreshed live Shopify inventory,
  passed compliance and publisher checks, and returned
  `READY_TO_CREATE_SELECTED_JOB_DRAFT`.
- The Job 30 commissioning run and publisher preflight made zero Shopify
  creates, published nothing, and left the queue byte-for-byte unchanged.

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

The first 2026-07-27 scheduler-bound dry-run reached the pipeline but used the
deterministic template because model writing had not yet been enabled in the
deployment environment. It failed closed at content quality with 565 words,
underdeveloped sections, and 13 uses of the target keyword:

`/docker/orin/evidence/hb_20260727T111055Z_03d424fb`

After enabling the existing file-backed MiniMax credential path, the corrected
model dry-run exercised the single bounded retry. Attempt 2 passed topic
identity and the full content review:

`/docker/orin/evidence/hb_20260727T114526Z_dcf4b8ad`

The accepted article did not reach Shopify because publisher preflight found
an existing hidden draft with the same handle:

`hoverboard-charger-not-working-checks-before-buying-a-new-one`

This is a safe, expected duplicate block. No Shopify create, publication, or
queue mutation occurred. Do not delete or modify the existing draft, or
reconcile its queue ownership, without an explicit operator decision.

The fresh Job 30 supervised dry-run and live read-only publisher preflight are
preserved at:

`/docker/orin/evidence/hb_20260727T124044Z_eee612b6`

The generated article is:

`writer_output_job30_1785156047_0dbb9ed1.html`

The publisher decision is recorded in both
`orin_phase2e_publisher_preview.json` and `orin_status_phase2e.md`. Live
inventory contained 44 articles and returned no exact handle, exact title,
near-handle, or near-title conflict. The resulting proposed hidden draft has:

- Title: `Hoverboard Bundle Buying Guide`
- Handle: `hoverboard-bundle-buying-guide`
- Published state: `false`
- Decision: `READY_TO_CREATE_SELECTED_JOB_DRAFT`
- Shopify touched: `false`
- Queue touched: `false`

## Next approved path

Continue Phase 4 without enabling either schedule:

1. Keep the existing Job 28 sample draft unchanged. Its ownership can be
   reconciled separately after the Job 30 commissioning path is complete.
2. Run one separately approved controlled Job 30 hidden-draft transaction.
   Open Shopify writes only for that transaction, retain both schedules
   disabled, and require exactly one unpublished article plus durable
   reconciliation evidence.
3. Close Shopify writes immediately after the transaction and prove an
   identical request replay creates no second article.
4. Transfer scheduler ownership only after the controlled transaction and
   replay pass. Keep exactly one production scheduler enabled.
5. Add the read-only watchdog after scheduler ownership is proven.

Do not enable the legacy main-agent scheduler, enable Shopify writes outside a
controlled transaction, or begin additional clients before HBStore scheduler
ownership is proven.
