# ORIN maintenance status

Last updated: 2026-07-28

## Current phase

Phase 3 manual verification is complete. The first Phase 4 automatic trigger
commissioning run is complete, but production scheduler ownership has not
transferred. ORIN remains in maintenance.

The isolated `orin-hbstore-prod` agent and its five boundary files are
versioned, deployed, and verified. Its dedicated schedule is wired only to one
fixed no-argument Python client over a private Unix socket. The job remains
disabled, has no delivery, and has no agent or tool execution path.

The reviewed code deployed on the VPS is:

`08e0c2435a120229291ad91aab83928c9ece4718`

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
- PR 46 brought topic identity into the writer's existing single bounded
  correction attempt. It does not increase the two-call ceiling, send previous
  article text to the model, or retry provider, network, or credential errors.
- The first controlled Job 30 transaction after PR 46 corrected the missing
  `Introduction` H2 but failed closed before Shopify because `Quick Answer`
  was represented both as a dedicated structural block and as an approved H2.
  Evidence records zero creates, `shopify_write_state=not_attempted`, no
  publication, and no queue change.
- PR 47 removed that deterministic plan conflict. `Quick Answer` remains a
  mandatory `div.hs-quick-answer` quality requirement, but it is no longer an
  H2 or broken TOC anchor.
- The fresh Job 30 transaction at PR 47's reviewed revision created exactly
  one hidden Shopify draft and passed post-create verification. The stored
  article independently passes the content-quality contract with 1,740 visible
  words, 10 H2s, 23 paragraphs, 4 FAQ items, 18 internal links, 7 substantive
  sections, 4 exact target-keyword occurrences, and no blockers.
- A live read-only Shopify verification found 45 total blog articles, exactly
  one matching Job 30 handle, exactly one matching idempotency marker, and
  `publishedAt = null`.
- An identical Job 30 replay ran from the immutable worker image with
  `--network none`, no Shopify or MiniMax credentials, and the gates closed.
  It returned the original terminal result and created no new run directory.
  Supabase still records one completed job, one run, one attempt receipt, and
  one reconciled ownership row for the request.
- The dedicated fixed-argv OpenClaw trigger ran automatically at 00:02
  Europe/London on 2026-07-28. Its diagnostic receipt returned `accepted`,
  `replayed=false`, `requested_mode=dry-run`, and an empty payload for the
  unique source key `scheduler:orin-hbstore-prod:2026-07-28`.
- The immutable worker claimed that automatic request without an as-of-date or
  job-number override. Supabase records exactly one terminal run and one
  attempt at code version
  `08e0c2435a120229291ad91aab83928c9ece4718`.
- The run failed closed in Publisher preflight with
  `ORIN_PIPELINE_BLOCKED`. It made zero Shopify creates, published nothing,
  left the queue unchanged, recorded `shopify_write_state=not_attempted`, and
  required no reconciliation.
- The failure exposed a dry-run integration defect: the runner correctly
  removes Shopify credentials, while Publisher preflight attempted to
  initialise the live Shopify client before its local-inventory fallback.
  The remediation catches that configuration boundary, uses the checked-in
  inventory snapshot for credential-free simulation, and blocks explicitly if
  neither inventory source is available.
- Both OpenClaw jobs were returned to disabled state after the attempt. The
  dedicated job was restored to `0 11 * * *` Europe/London with exact timing,
  the trigger sidecar remained healthy, and OpenClaw reports no next wake.
- This test proves automatic request creation, not automatic end-to-end worker
  execution. The worker was invoked manually after the trigger receipt.
  Production scheduler ownership therefore remains unproven.

The latest controlled Shopify test created exactly one article:

- Job: 30
- Title: `Hoverboard Bundle Buying Guide: Board, Kart and Safety Gear`
- Handle: `hoverboard-bundle-buying-guide-board-kart-and-safety-gear`
- Model: `MiniMax-M3`
- Shopify article ID: `1007206334812`
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
- Request intake enabled: `false`
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

The first controlled Job 30 transaction after bounded topic correction was
blocked at the remaining `Quick Answer` plan conflict. It reached no Shopify
transaction and is preserved at:

`/docker/orin/evidence/hb_20260727T151449Z_1ff3da79`

The successful Job 30 hidden-draft transaction and its complete private
evidence are preserved at:

`/docker/orin/evidence/hb_20260727T152443Z_61184304`

The generated article is:

`writer_output_job30_1785165886_b45bf89a.html`

The terminal result is `DRAFT_CREATED_VERIFICATION_PASSED` for Shopify article
`1007206334812`. The request ID is
`dd8428fb-22d5-47d3-b6f2-01e929dce004`; its exact terminal replay was proven
offline without creating a new run directory.

The first automatic Phase 4 trigger receipt and its terminal worker evidence
are preserved at:

`/docker/orin/evidence/hb_20260727T231643Z_3cca08a0`

The database request is
`44c6d452-9b98-58a6-86e5-2bf4f747d606`, and the terminal run is
`hb_20260727T231643Z_3cca08a0`. The evidence directory is private mode `0700`;
its key files are private mode `0600`.

SHA-256:

- `final_result.json`:
  `bc46cea7bfc96f8457a985fe158ec9f6045051948c5b9d813e45c3001ba2fec6`
- `pipeline_preview.json`:
  `ad35c9d51288e18f7ea56c9c754b3ed20af20b962ff7dceeb9455f1ac3b6dee1`
- `stdout.log`:
  `2104b5c6eb42b6abb34aecd034253fedbd7d05a5432afa75958be41899a45bac`

## Next approved path

Continue Phase 4 without enabling either schedule:

1. Merge, deploy, and verify the credential-free Publisher inventory fallback.
   Keep the existing Job 28 sample draft unchanged.
2. Add one narrow automatic worker-invocation boundary. It must run the
   immutable worker with fixed arguments, concurrency one, no arbitrary shell
   input, and no Shopify-write permission while the allowed mode is dry-run.
3. Repeat the automatic dry-run on a fresh London calendar date. Require one
   accepted trigger receipt, one automatically claimed job, one terminal
   completed run, the reviewed code version, zero Shopify creates, unchanged
   queue state, and durable evidence.
4. Keep the legacy schedule permanently disabled. Transfer production
   ownership only after the dedicated trigger and automatic worker path pass
   together; keep exactly one production scheduler enabled.
5. Observe several successful scheduled dry-run receipts before separately
   approving hidden-draft writes.
6. Add the read-only watchdog after scheduler ownership is proven.

Do not enable the legacy main-agent scheduler, enable Shopify writes outside a
controlled transaction, or begin additional clients before HBStore scheduler
ownership is proven.
