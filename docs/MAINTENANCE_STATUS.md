# ORIN maintenance status

Last updated: 2026-07-30

## Current phase

Phase 3 manual verification is complete. Phase 4 has proven the automatic
fixed trigger and automatic worker handoff together on a fresh London-date
source key. The 2026-07-30 automatic run was accepted once, automatically
claimed, and terminalized without a manual cron or worker invocation. It
failed closed at the post-write compliance review because the checker treated
safe-negative public-road guidance as an unconditional blocked phrase.
PR 58 corrected that false positive, and its exact merge revision is deployed.
A database-backed controlled dry-run at that revision completed with
`READY_TO_CREATE_SELECTED_JOB_DRAFT`, zero Shopify creates, no publication,
and no queue change. Production scheduler ownership has not transferred.
ORIN remains in maintenance pending one fresh-date automatic
trigger-plus-worker proof at the corrected revision.

The isolated `orin-hbstore-prod` agent and its five boundary files are
versioned, deployed, and verified. Its dedicated schedule is wired only to one
fixed no-argument Python client over a private Unix socket. Both the dedicated
and legacy schedules are disabled. The dedicated schedule has been restored
to `0 11 * * *` Europe/London with exact timing, no delivery, and no agent or
tool execution path.

The reviewed code deployed on the VPS is:

`59a34ac5c881424826a2a90e97ba9e1e66fedd81`

## Verified results

- The dedicated API and worker images are immutable and tied to the reviewed
  Git commit.
- The control API and worker use separate file-backed database credentials.
- The Shopify credential is file-backed and isolated from OpenClaw.
- A normal Compose start has no unprofiled service.
- The manual worker remains one-shot. The automatic worker is the same
  immutable image running only the fixed atomic claim loop; it has no port,
  scheduler, Docker socket, OpenClaw payload, date override, or job override.
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
- PR 49 fixed credential-free Publisher preflight. A network-disabled
  standalone verification used the local 35-article inventory snapshot,
  returned `READY_TO_CREATE_SELECTED_JOB_DRAFT`, and recorded
  `shopify_touched=false` and `queue_touched=false`.
- PR 50 added the narrow automatic worker invocation boundary using the
  existing worker image and PostgreSQL claim contract. Application and
  database CI passed before merge.
- The automatic worker is deployed with a read-only root filesystem, non-root
  UID/GID `1000:1000`, no public port, and `unless-stopped` recovery. With all
  database gates closed it repeatedly returns `no_job_due`; its observed
  restart count is zero.
- The scheduler-trigger sidecar and automatic worker images, deployment
  configuration, VPS checkout, and fixed OpenClaw client are aligned to the
  reviewed revision above.
- The 2026-07-29 near-term commissioning retry passed the complete scheduler
  boundary: OpenClaw automatically returned `accepted`, `replayed=false`,
  `requested_mode=dry-run`, and an empty payload for the unique source key
  `scheduler:orin-hbstore-prod:2026-07-29`.
- The continuously running immutable worker automatically claimed that request
  without an as-of-date or job-number override and terminalized exactly one
  database job, run, and attempt at code version
  `35d3d2ae3a02eabd01cb5580a196bbe7b9b531da`.
- The pipeline failed closed after MiniMax M3 used an `id` attribute on a
  non-H2 element in both the initial response and the one bounded correction
  attempt. The terminal result recorded zero Shopify creates,
  `shopify_published=false`, `queue_changed=false`,
  `shopify_write_state=not_attempted`, and
  `reconciliation_status=not_required`.
- All database gates were closed immediately after terminalization. The
  dedicated job and legacy job are disabled, the dedicated job is restored to
  `0 11 * * *` Europe/London exact, and OpenClaw reports no next wake.
- PR 52 added targeted HTML-policy correction guidance and preserves each
  invalid model response as private failure evidence before the bounded retry.
  Focused tests and the complete 135-test application suite passed before
  merge.
- The reviewed PR 52 merge commit was deployed on 2026-07-29 after repairing
  mixed ownership left by earlier root Git operations in the canonical VPS
  checkout. The checkout is clean and the non-secret deployment configuration,
  automatic-worker image, and scheduler-trigger image all identify the exact
  reviewed revision shown above.
- Post-deployment verification found the automatic worker and trigger sidecar
  running read-only as their expected non-root users with zero restarts. The
  trigger sidecar is healthy and the worker repeatedly reports `no_job_due`.
  The database has zero active jobs; maintenance, intake, automation, Shopify
  writes, and scheduler ownership remain closed. Both OpenClaw jobs are
  disabled and `nextWakeAtMs` is null.
- A fresh controlled dry-run at the deployed PR 52 revision was inserted with
  a unique commissioning request while the future OpenClaw trigger was
  temporarily disabled. The continuously running worker claimed it
  automatically and completed attempt 1 in 58 seconds with
  `READY_TO_CREATE_SELECTED_JOB_DRAFT`.
- The controlled result used code version
  `013c12f95e1ec355b24288b39a76cddd70ce8cc6`, made zero Shopify creates,
  published nothing, left the queue unchanged, required no reconciliation,
  and recorded `shopify_write_state=not_attempted`. MiniMax produced a valid
  article on its first response, so the bounded correction branch was not
  needed during this run.
- All database gates were closed immediately after terminalization. The July
  30 fixed-trigger one-shot was restored for `00:02` Europe/London, the legacy
  job remains disabled, and Shopify writes remain disabled.
- PR 58 corrected the safe-negative public-road compliance false positive
  without weakening the blocked-claim policy. Application and database CI
  passed before squash merge at
  `59a34ac5c881424826a2a90e97ba9e1e66fedd81`.
- The VPS checkout, automatic worker image, scheduler-trigger image, and
  non-secret deployment revision are aligned to that exact merge commit. The
  worker and trigger sidecar run as their expected non-root users with zero
  restarts; the sidecar is healthy and the worker reports `no_job_due` while
  all gates are closed.
- A database-backed controlled dry-run at the corrected revision terminalized
  as `completed` with `READY_TO_CREATE_SELECTED_JOB_DRAFT`. MiniMax used its
  bounded retry: attempt 1 was rejected and attempt 2 passed the full content,
  topic, HTML, publisher, and compliance gates.
- The corrected controlled run selected Job 28, made zero Shopify creates,
  published nothing, left the queue unchanged, and required no
  reconciliation. All database gates remain closed, both OpenClaw jobs remain
  disabled at `0 11 * * *` Europe/London exact, and `nextWakeAtMs` is null.

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
- Dedicated `orin-hbstore-prod` commissioning job: enabled one-shot for
  `00:02` Europe/London on 2026-07-30
- Dedicated job payload: fixed `python3` argv to the HBStore socket client
- Dedicated job agent/tools: none
- Dedicated job delivery: none
- Production trigger attached: no
- OpenClaw next wake: the dedicated commissioning one-shot only
- ORIN containers: healthy scheduler-trigger sidecar and automatic worker;
  control API is stopped
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

The first complete automatic trigger-plus-worker commissioning evidence is
preserved at:

`/docker/orin/evidence/hb_20260729T074012Z_9a2687db`

The database request is
`5c1062f3-d7ae-54c8-8f50-260f06cf8e78`; the terminal run is
`hb_20260729T074012Z_9a2687db`. The scheduler request was accepted once with
`replayed=false`, then automatically claimed and terminalized as blocked after
the model output contract exhausted its single correction attempt. The
evidence directory is private mode `0700`; its canonical JSON and logs are
private mode `0600`.

SHA-256:

- `final_result.json`:
  `13da81f9ab1d4ff275cf67b315afa7f293b439b3937a51b037dadeae792d6e3b`
- `pipeline_preview.json`:
  `c2f28845788252baeab48f8bb6f561391683574e488c65de937b9fd7952056a0`
- `stdout.log`:
  `3412054f708c81faeb65b80db3693fb4b1a1ea9a4e8a118d99a9e02ac04fdd2e`

The post-deployment controlled model dry-run evidence is preserved at:

`/docker/orin/evidence/hb_20260729T103110Z_30e1dbf6`

The database request is
`22b43c67-2531-45b8-89f7-0236c9420fc7`; the terminal run is
`hb_20260729T103110Z_30e1dbf6`. The evidence directory is private mode `0700`.
Canonical JSON, logs, and model request/response evidence are private mode
`0600`.

SHA-256:

- `final_result.json`:
  `db1d027653762c1de1b6b0fe1c1475605d45c4ef6d6ffc4b7566c7e28edc6ef0`
- `pipeline_preview.json`:
  `f40c8f96758a0952f50367d0f33f2eb34490b1136bba5237156384041f29b35d`
- `stdout.log`:
  `8094a5a026c895d12aa3ab552b112bc45494de34653064400107ddf3c6d65045`
- `stderr.log`:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

The local operator copy is:

`/Users/harirajbhattarai/Documents/COMPUTER_USE/ORIN_EVIDENCE/hb_20260729T103110Z_30e1dbf6`

The fresh-date automatic trigger-plus-worker commissioning evidence is
preserved at:

`/docker/orin/evidence/hb_20260729T234013Z_8711e396`

The local operator copy is:

`/Users/harirajbhattarai/Documents/COMPUTER_USE/ORIN_EVIDENCE/hb_20260729T234013Z_8711e396`

At `00:40` Europe/London on 2026-07-30, the dedicated fixed trigger created
exactly one request for
`scheduler:orin-hbstore-prod:2026-07-30`. The receipt was `accepted` with
`replayed=false`, `requested_mode=dry-run`, and `payload={}`. The automatic
worker claimed it without date or job overrides and recorded exactly one job,
one run, and one attempt at code version
`013c12f95e1ec355b24288b39a76cddd70ce8cc6`.

The generated 2,094-visible-word Job 28 article passed topic identity, HTML,
and the deterministic content-quality contract. It was then terminalized as
`blocked` with `ORIN_PIPELINE_BLOCKED` because the compliance checker treated
the safe-negative sentence `not approved for use on public roads` as an
unconditional failure. Shopify creates were zero, `shopify_published=false`,
the queue was unchanged, reconciliation was not required, and the Shopify
transaction was never entered. All commissioning gates were closed
immediately afterwards. Both schedules are disabled and OpenClaw reports
`nextWakeAtMs=null`.

SHA-256:

- `final_result.json`:
  `eb32595898aae7f70490dd7f62c33e7ed11678f493b33d5d7d58463be7b79b4d`
- `pipeline_preview.json`:
  `45a5963245de8976d95acb3637be64e9f9e4a60db2e14f6390d92523557f3123`
- `stdout.log`:
  `e50b2bf9ac26077f274e2c266df22c05348d77eafc53c892210d39006175e232`
- `stderr.log`:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `writer_output_job28_1785368415_45488aa6.html`:
  `d763c7928ce5b6e01a7980510417b9b3f3da1911a66f5d93da3de3f94198c71e`

The post-fix database-backed controlled dry-run evidence is preserved at:

`/docker/orin/evidence/hb_20260730T000603Z_c31b49a1`

The local operator copy is:

`/Users/harirajbhattarai/Documents/COMPUTER_USE/ORIN_EVIDENCE/hb_20260730T000603Z_c31b49a1`

The database request is
`41840073-f0e4-48a7-af96-e069f0d671b5`; the terminal run is
`hb_20260730T000603Z_c31b49a1`. It completed at code version
`59a34ac5c881424826a2a90e97ba9e1e66fedd81` with
`READY_TO_CREATE_SELECTED_JOB_DRAFT`, zero Shopify creates,
`shopify_published=false`, an unchanged queue, and
`reconciliation_status=not_required`.

SHA-256:

- `final_result.json`:
  `295a36bd346ed9baf2c62a10a1d427daabb08258a6dbd5df4422fcefd2c11dbe`
- `pipeline_preview.json`:
  `b032ac34feac5aed4f6b198813d2e7deca20d9566feaf215f3dc5d9ee797a2b8`
- `stdout.log`:
  `64fe096e0e908a05c73cc1d302377d340b8f3f22d7cd4c9b85812e9d822d1181`
- `stderr.log`:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `writer_output_job28_1785369965_500ac89b.html`:
  `43f5ae8990001e77d74d088404274fd8fe65abc063e6558f2c31292c23e85da1`

## Next approved path

Continue Phase 4 without enabling Shopify writes:

1. Keep all database gates closed and both OpenClaw jobs disabled until the
   fresh-date automatic proof begins.
2. Run one supervised automatic dry-run at the deployed revision with source
   key `scheduler:orin-hbstore-prod:2026-07-31`; do not invoke the cron or
   worker manually.
3. Require one accepted, non-replayed trigger receipt, one automatically
   claimed job, one terminal completed run, zero Shopify creates, unchanged
   queue state, and durable evidence before transferring production scheduler
   ownership.
4. Keep the legacy schedule permanently disabled. When ownership transfers,
   keep exactly one production scheduler enabled.
5. Observe several successful scheduled dry-run receipts before separately
   approving hidden-draft writes.
6. Add the read-only watchdog after scheduler ownership is proven.

Do not enable the legacy main-agent scheduler, enable Shopify writes outside a
controlled transaction, or begin additional clients before HBStore scheduler
ownership is proven.
