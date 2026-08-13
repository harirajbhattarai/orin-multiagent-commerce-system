# ORIN maintenance status

Last updated: 2026-08-14

## Current phase

HCS Gadgets onboarding has passed its first server-side commissioning gate.
The durable read-only identity audit verified the exact
`hcsgadgets-com.myshopify.com` store, `Gadget Blog`, and 86 readable products
without attempting a Shopify write. HCS remains in maintenance with request
intake, automation, both Shopify write gates, and scheduler ownership closed;
there are zero active HCS jobs and zero open HCS incidents.

The dedicated HCS dry-run worker foundation is now database-scoped rather
than relying on a worker name. The new `orin_hcs_worker` role starts `NOLOGIN`,
cannot call the global claim function, and can claim only `hcs_gadgets`
`dry-run` jobs through its dedicated function while both Shopify gates remain
closed. Exact normalized topic identities and exact generated body hashes are
globally unique across tenants, blocking accidental cross-client content
reuse. The worker has not been started and HCS has not been activated; a
separate credential installation, immutable deployment, and controlled
dry-run proof are still required.

HBStore completed its controlled reactivation proof on 2026-08-13. The client
is active with request intake and dry-run automation enabled, concurrency one,
and Prefect retaining scheduler ownership. Broad Shopify writes remain off.
The approval-only draft gate is also closed except for the brief,
version-bound transaction window after a human reviews an exact local draft.
The legacy and dedicated OpenClaw content schedules remain disabled; only the
read-only 11:15 watchdog is enabled. There are zero active jobs, zero open
incidents, and zero recorded decisions.

The proof exposed and corrected three content-quality defects before any
Shopify transaction. PR #127 made model-generated meta descriptions complete
sentences. PR #128 hardened accessory plans with grammatical headings,
topic-specific FAQs, closed-footwear guidance, and fail-closed footpad/sensor
instructions. PR #129 fixed a compliance-checker sentence-boundary false
positive that joined a correct `not on UK public roads or pavements` sentence
to unrelated permission wording in the following sentence. Every change
passed focused tests, the full Python suite, and GitHub dashboard, database,
and test CI before immutable deployment.

Job 42 remains in human review because its generated motor-power explanation
was not acceptable; no Shopify article was created. Job 43 was regenerated and
reviewed at exact worker revision
`db11da4eb9414ec6d0a02493194e4c60cf5c8acf`. Its 1,994-word draft passed the
quality and compliance gates. The approval-only run
`hb_20260813T163034Z_0637596b` created exactly one hidden Shopify article,
`1007438561628`, with handle `hoverboard-footpads-grip-buying-checks`.
Shopify independently reports `published_at=null` and exactly one article with
that handle. The run published nothing, left the queue unchanged, reconciled
the exact reviewed body, and the narrow draft gate was immediately closed.
Durable public evidence is in
`docs/evidence/2026-08-13-hbstore-controlled-reactivation.json`; canonical
private run evidence remains under
`/docker/orin/evidence/hb_20260813T163034Z_0637596b`.

The fixed read-only watchdog command now returns
`ORIN_SCHEDULED_RUN_OBSERVED` for the 2026-08-13 Prefect run. The OpenClaw UI
still retains the earlier scheduled error as historical state; the corrected
UID-1000 command and direct post-fix receipt prove the current monitoring path.

The private HBStore dashboard now projects that maintenance boundary directly
from Supabase instead of displaying a generic live state. It labels the
workspace `Maintenance paused`, shows the scheduler, worker, watchdog, and
Shopify draft path as paused or idle, and disables concept and hidden-draft
approval buttons while their matching gates are closed. PR #124 added the
state projection and a database trigger that rejects approvals behind closed
gates. The first production render then exposed an intentionally narrow column
grant: the client queried the ungranted `scheduler_health.details` column. PR
#125 removed that column from the browser query and added a regression test for
the approved scheduler-health projection. The corrected private Sites release
was visually verified on the overview and Job 42 review pages, including a
disabled concept approval with its maintenance reason. No content, scheduler,
or Shopify gate was opened. Durable details are in
`docs/evidence/2026-08-13-dashboard-maintenance-boundary.json`.

The checkpoint found one genuine monitoring regression. The 11:15 read-only
watchdog could not select the Phase 6 `approved_draft_writes_enabled` column,
so it returned `ORIN_WATCHDOG_CHECK_FAILED` even though its container was
healthy. PR #122 added only that missing column-level `SELECT` grant and
executable pgTAP coverage. All 269 Python tests, 169 database tests, database
lint, and GitHub CI passed before the migration was applied. A post-fix
read-only check executed the complete projection and returned the expected
`ORIN_SCHEDULER_NOT_ACTIVE` alert because maintenance mode was deliberate.

Jobs 28-31 also predated durable Shopify-handle persistence. Read-only Shopify
queries verified their stored article IDs, exact handles, Journal Insights
blog ownership, and `publishedAt=null`; those four handles were backfilled.
Jobs 28-41 now contain 14 unique article IDs and 14 handles, all at
`draft_created`, with no duplicate article ID. Items 3, 21, and 22 remain an
inactive human-review backlog rather than active execution work.

The controlled hidden-draft architecture has therefore passed this
maintenance checkpoint, but it is not currently active. Resuming content is a
separate explicit operation: restore Prefect ownership and the daily schedule,
open only the approved dry-run gates, re-enable the read-only watchdog, and
require a healthy receipt before approving another content item. Durable
details are in
`docs/evidence/2026-08-13-hbstore-reliability-checkpoint.json`.

Job 38, “Electric Scooter for Older Children and Teens: Buying Factors That
Matter,” now has a completed 1,993-word local review draft. The first run
exposed a contradictory contract: it required the H1 to remain the approved
title while also requiring the exact target keyword in that H1. PR #117 made
an exact approved H1 satisfy the heading requirement while preserving exact
keyword checks in the opening and article body. A fresh run then exposed
model-variable SEO metadata at 180 characters. PR #118 moved all structured
SEO metadata to deterministic approved-plan normalization before quality
validation.

Both fixes passed focused, full, dashboard, container, and database CI before
deployment. Run `hb_20260813T093034Z_b24e7473` completed on exact worker
revision `8b9ef58525aca55f38428829281e3f095302074c` with decision
`READY_TO_CREATE_SELECTED_JOB_DRAFT`. It persisted version 4 draft
`6c9b943f-9f45-4949-80fe-b24ba62f29dc`, performed zero Shopify creates,
published nothing, left the queue unchanged, and required no reconciliation.
There are zero active jobs and zero open incidents. Durable details are in
`docs/evidence/2026-08-13-job38-content-quality-recovery-proof.json`.

Phase 6 exact-reviewed hidden-draft proof is complete for Hoverboard Store.
Supabase owns the 60-item plan, execution jobs bind to plan items through a
lease-checked worker capability, and the legacy Markdown format is generated
only as private run input. Jobs 28-37 are reconciled to their verified hidden
Shopify drafts. Job 33 completed through the version-bound dashboard approval,
automatic worker, marker-first Shopify reconciliation, narrow body
canonicalization, and durable article-handle persistence path.

Job 37 completed through the approval-only dashboard path on 2026-08-12. Its
first reconciliation attempts found the one marker-owned, unpublished Shopify
article but failed closed because Shopify inserted render-equivalent newlines
before leading anchors in the Related Guides list. PR 115 extended the narrow
body canonicalizer to that observed serialization only. The exact failed job
was reopened for one recovery attempt at merged worker revision
`20142585fd2319a38fab5fb4994fa05a30613d70`; run
`hb_20260812T173606Z_dec5473e` reconciled article `1007424700764` without a
second create, persisted the canonical handle, published nothing, left the
queue unchanged, and resolved the recovery incident. Durable evidence is in
`docs/evidence/2026-08-12-job37-anchor-reconciliation-proof.json`.

Job 41, “All-Terrain Hoverboards: Tyres, Surfaces and Buyer Checks,” completed
the same approval-only path on 2026-08-13. Shopify preserved the exact content
and marker but inserted render-equivalent newlines between nested FAQ `div`
blocks. The worker failed closed, kept the item in review, and opened a
reconciliation incident instead of claiming an unverified success. PR #120
added only that observed block-boundary serialization to the narrow
canonicalizer. After correcting the immutable release root and verifying the
patched image against the live article, guarded attempt 5 found the existing
unpublished article before any create call. Run
`hb_20260813T114312Z_5201b5dc` completed at revision
`6ae6561b5e01a6250b1cfd10ad7392f06c4ba25a`, persisted article
`1007434367324`, created no duplicate, and moved the dashboard projection to
`Approved` / `Shopify draft`. Both recovery incidents are resolved. Durable
evidence is in
`docs/evidence/2026-08-13-job41-faq-reconciliation-proof.json`.

Phase 7 Prefect dry-run production ownership was commissioned for Hoverboard
Store and is intentionally paused by the current maintenance checkpoint.
The reviewed Prefect server, scheduler deployment, owner worker, and watchdog
policy run at revision `4b96b85e1e5f64a564ba4554a9471c436dc3a4af`.
When active, Prefect owns the fixed daily `0 11 * * *` Europe/London request
boundary; the legacy and dedicated OpenClaw production schedulers remain
disabled. The OpenClaw read-only watchdog normally runs at `15 11 * * *`
Europe/London with no delivery and is also disabled during this pause.

The current safe state supersedes the older chronological operating-state
notes below: the client is in maintenance, request intake and automation are
disabled, maximum concurrency is one, allowed mode is `dry-run`, Shopify
writes are disabled, and scheduler ownership is disabled. Prefect and
OpenClaw schedules are paused/disabled. The Prefect services, automatic ORIN
worker, scheduler-trigger, and watchdog remain healthy with zero restarts;
there are zero active jobs and zero open incidents. Live publishing was never
enabled.

Phase 3 manual verification is complete. Phase 4 automatic
trigger-plus-worker commissioning passed on the fresh London-date source key
`scheduler:orin-hbstore-prod:2026-07-31`. The dedicated fixed command was
accepted once with `replayed=false`, automatically claimed by the continuously
running immutable worker without overrides, and durably terminalized as
`completed` with `READY_TO_CREATE_SELECTED_JOB_DRAFT`. It made zero Shopify
creates, published nothing, left the queue unchanged, and required no
reconciliation.

An immediate one-shot automatic dry-run was also executed on 2026-08-01 after
the normal 11:00 schedule was found disabled. The fixed trigger was accepted
once with `replayed=false`, and the automatic worker claimed the request
without overrides. At the previous runtime revision, the run safely
terminalized as blocked because MiniMax added a contract-external H1 anchor.
It created zero Shopify articles, published nothing, left the queue unchanged,
and required no reconciliation.

PRs 61-63 then generalized safe model-anchor canonicalization and corrected
the worker deployment boundary. The worker still sees the overall runtime as
read-only, with a nested writable mount limited to Hoverboard Store's
`content_engine`; credentials, other clients, Docker, and the rest of the
workspace remain unavailable for writes. A post-deployment direct controlled
dry-run completed with `READY_TO_CREATE_SELECTED_JOB_DRAFT` at the new
revision, with zero Shopify creates, no publishing, no queue change, and no
reconciliation requirement.

Production scheduler ownership transferred on 2026-08-01 to
`openclaw:orin-hbstore-prod` in dry-run mode only. The client is active,
request intake and automation are enabled, maximum concurrency is one, and
Shopify writes remain disabled. The dedicated fixed-command schedule is the
only enabled production schedule at `0 11 * * *` Europe/London; the legacy
main-agent schedule remains disabled.

The isolated `orin-hbstore-prod` agent and its five boundary files are
versioned, deployed, and verified. Its dedicated schedule is wired only to one
fixed no-argument Python client over a private Unix socket. The dedicated
schedule is enabled at `0 11 * * *` Europe/London with exact timing, no
delivery, and no agent or tool execution path. Its next wake follows the normal
daily 11:00 Europe/London schedule.

Phase 5 watchdog commissioning is complete. The read-only database role,
unique credential, private socket service, fixed OpenClaw client, and automatic
command path have all been tested. The permanent watchdog schedule is enabled
at `15 11 * * *` Europe/London with alert delivery disabled. It observes only
the scheduler receipt and has no capability to trigger or modify work.

The first normal post-migration production dry-run completed automatically on
2026-08-02. Source key `scheduler:orin-hbstore-prod:2026-08-02` exists exactly
once and owns one completed job, run, and attempt. Run
`hb_20260802T100007Z_6bb867ff` returned `no_job_due` because Job 31 is not due
until 2026-08-03. It used the exact deployed revision, made zero Shopify
creates, published nothing, did not change the content plan, and required no
reconciliation. The automatic 11:15 watchdog run and an explicit execution of
the same fixed read-only client both returned `ORIN_SCHEDULED_RUN_OBSERVED`.

A supervised Job 31 proof completed on 2026-08-02 before any Shopify write was
authorized. The automatic worker was stopped to prevent a claim race, one
uniquely keyed dry-run request was queued, and the reviewed one-shot worker was
run with `--as-of-date 2026-08-03 --job-number 31`. Run
`hb_20260802T161901Z_f20b53c6` selected Job 31, passed topic identity,
post-write review, duplicate, publisher-preflight, and HTML validation, and
returned `READY_TO_CREATE_SELECTED_JOB_DRAFT`. It made zero Shopify creates,
published nothing, did not change the queue, and required no reconciliation.
Job 31 remains `planned` at version 1. The automatic worker was then restored
and returned `no_job_due` with zero restarts.

The separately approved controlled Job 31 Shopify transaction then completed
on 2026-08-02. Automatic scheduling and the daemon were stopped first, request
intake was closed, and one unique hidden-draft request was bound to the
authoritative Job 31 content item. Run `hb_20260802T164938Z_27643c00` passed
topic identity, post-write review, duplicate checking, publisher preflight,
and HTML validation before creating exactly one Shopify article. Independent
read-only verification found exactly one idempotency-marker match for article
`1007283863900`, handle
`kids-electric-scooter-buying-checklist-for-parents`, with
`publishedAt = null`. Supabase records one completed job, run, attempt, and
reconciliation row; Job 31 is `draft_created` at version 2. The write gate was
closed immediately, then normal dry-run scheduling and the automatic worker
were restored.

Job 32 then proved the automatic hidden-draft path using the continuously
running immutable worker, with no manual worker invocation and no date or job
override. The first automatic request failed closed before Shopify because the
generated article contained an unsupported superlative and the planned H1 did
not contain the exact target keyword. It created zero Shopify articles. With
all gates closed, the content-plan wording was corrected without weakening any
runtime check, and one fresh request with `max_attempts=1` was queued. The
daemon selected and bound Job 32 itself, then run
`hb_20260802T200042Z_532d13f6` created and reconciled exactly one unpublished
draft. Independent Shopify verification found one marker match for article
`1007284420956`, handle
`electric-scooter-handlebar-height-for-children-fit-guide`, with
`publishedAt = null`. Normal dry-run scheduling was restored immediately.

The reviewed worker and scheduler-trigger code deployed on the VPS is:

`d257e94271a916c13f736f74e8831c9d0cc1cde6`

## Phase 6 Job 33 exact reviewed hidden-draft proof — 2026-08-04

- Dashboard decision `17f732ba-de75-439d-999c-b7a4961f5cbd` approved only
  the immutable version-5 review draft for Job 33. The dashboard exposes no
  live-publish action.
- The first worker attempt failed closed with
  `ORIN_SHOPIFY_RECONCILIATION_FAILED` after Shopify inserted newline text
  nodes between opening `li` tags and leading `strong` tags. The stored and
  sent raw SHA-256 remained `cded6db118f6967bdbc1d02a066265368e69c586ea1b5be1e708e5a220f880ea`;
  Shopify's fetched raw SHA-256 was
  `afad7da732ecf77689c6bb293e74be20519c462b594785e9812ec69fa08ca1da`.
- PR 86 added one narrow normalization rule for that observed Shopify
  serializer behavior. No other whitespace, text, element, or attribute
  difference is ignored. The approved and fetched canonical hashes are both
  `cded6db118f6967bdbc1d02a066265368e69c586ea1b5be1e708e5a220f880ea`.
- Attempt two reconciled the existing request marker and terminalized run
  `hb_20260804T142717Z_9d305d7d` as
  `APPROVED_REVIEW_DRAFT_CREATED_VERIFICATION_PASSED` at revision
  `e2c5ef62135c7938d45c15dd15a2fbf38c39e264`. Independent read-only Shopify
  verification found exactly one marker match: article `1007318892892`, handle
  `foldable-vs-fixed-kids-electric-scooters`, with `publishedAt = null`.
- Job 33 is `draft_created` at version 6. The one request-owned article is
  reconciled, unpublished, and queue-unchanged. The retry created no duplicate.
- PR 87 requires future exact-reviewed terminal results to include a canonical
  Shopify handle and persists it atomically. Remote migration
  `20260804144407_phase6_persist_verified_shopify_handle` constrained the
  historical Job 33 backfill to its exact client, item number, terminal state,
  article ID, and null handle. Supabase now stores the verified handle.
- The VPS checkout, worker image, and scheduler-trigger image are exact revision
  `d257e94271a916c13f736f74e8831c9d0cc1cde6`, with zero restarts. The trigger
  and independently pinned watchdog are healthy; the worker reports
  `no_job_due` with all gates closed.
- Canonical private evidence is mode `0700`/`0600` under
  `/docker/orin/evidence/hb_20260804T142717Z_9d305d7d`. The non-secret proof is
  `docs/evidence/2026-08-04-job33-exact-reviewed-hidden-draft-proof.json`.

## Verified results

- Automatic hidden-draft source key
  `commissioning:job32-auto-hidden-draft-corrected:2026-08-02` exists exactly
  once and owns one completed job, one completed run with attempt value one,
  and one reconciled Shopify ownership row.
- The fixed automatic daemon selected and bound Job 32 without `--as-of-date`
  or `--job-number`. Run `hb_20260802T200042Z_532d13f6` used deployed revision
  `5c755295604648161af83fdebf92b2c176b6f8e6` and returned
  `DRAFT_CREATED_VERIFICATION_PASSED`.
- Independent Shopify verification found exactly one request-marker match.
  Article `1007284420956` has handle
  `electric-scooter-handlebar-height-for-children-fit-guide` and
  `publishedAt = null`. Supabase records create count one, unpublished state,
  no queue change, and reconciled ownership.
- Job 32 is `draft_created` at version 3. Its original target date is restored,
  there are zero active jobs and zero open incidents, and every private run
  evidence file is mode `0600`.
- Production is restored to active dry-run operation: request intake and
  automation enabled, maximum concurrency one, Shopify writes disabled,
  scheduler healthy with owner `openclaw:orin-hbstore-prod`, automatic worker
  running with zero restarts and reporting `no_job_due`, 11:00 scheduler and
  11:15 watchdog enabled, and the legacy scheduler disabled.
- The non-secret verification manifest is preserved at
  `docs/evidence/2026-08-02-job32-automatic-hidden-draft-verification.json`;
  canonical private evidence remains at
  `/docker/orin/evidence/hb_20260802T200042Z_532d13f6`.

- Controlled hidden-draft source key
  `commissioning:job31-hidden-draft:2026-08-02` exists exactly once and owns
  one completed job, one completed run, one terminal attempt, and one
  reconciled Shopify ownership row.
- Run `hb_20260802T164938Z_27643c00` used deployed code version
  `5c755295604648161af83fdebf92b2c176b6f8e6` and returned
  `DRAFT_CREATED_VERIFICATION_PASSED`. Shopify write state is
  `article_observed`, create count is one, `shopify_published=false`, queue
  changed is false, and reconciliation is `reconciled`.
- Independent Shopify verification found exactly one article with the request
  marker. Article `1007283863900` has handle
  `kids-electric-scooter-buying-checklist-for-parents` and
  `publishedAt = null`. The generated article has approximately 1,944 visible
  words and passed the complete content-quality path.
- Supabase moved Job 31 from `planned` version 1 to `draft_created` version 2,
  stores Shopify article ID `1007283863900`, and links the item to the exact
  terminal run. There are zero active jobs and zero open incidents.
- Production is restored to active dry-run operation: request intake and
  automation enabled, maximum concurrency one, Shopify writes disabled,
  scheduler healthy with owner `openclaw:orin-hbstore-prod`, automatic worker
  running with zero restarts, 11:00 scheduler and 11:15 watchdog enabled, and
  the legacy scheduler disabled.
- The non-secret controlled-write manifest is preserved at
  `docs/evidence/2026-08-02-job31-hidden-draft-verification.json`; canonical
  private evidence remains on the VPS at
  `/docker/orin/evidence/hb_20260802T164938Z_27643c00` with every file mode
  `0600`.

- Supervised proof source key
  `commissioning:job31-dry-run-proof:2026-08-02` exists exactly once and owns
  one completed job, one completed run, and one terminal attempt. Requested and
  effective modes are `dry-run`; Shopify write state is `not_attempted`,
  creates are zero, `shopify_published=false`, `queue_changed=false`, and
  reconciliation is `not_required`.
- The proof used deployed code version
  `5c755295604648161af83fdebf92b2c176b6f8e6`. Its final result names Job 31 and
  decision `READY_TO_CREATE_SELECTED_JOB_DRAFT`; the generated HTML is private
  run evidence and was not sent to Shopify.
- Job 31 remains authoritative database state `planned`, version 1, with no
  Shopify article ID or handle. There are zero active jobs and zero open
  incidents after the proof.
- The automatic worker was restored at the same immutable image, has zero
  restarts, and is producing `no_job_due`. Scheduler-trigger and watchdog
  services remain healthy; the 11:00 and 11:15 schedules remain enabled and
  unchanged, while the legacy schedule remains disabled.
- The non-secret proof manifest is preserved at
  `docs/evidence/2026-08-02-job31-dry-run-proof.json`; canonical private
  evidence remains on the VPS at
  `/docker/orin/evidence/hb_20260802T161901Z_f20b53c6` with every file mode
  `0600`.

- The 2026-08-02 11:00 Europe/London dedicated schedule was accepted with
  `replayed=false`; the legacy main-agent schedule remained disabled.
- Supabase records exactly one completed job, one completed run, and one
  terminal attempt for source key
  `scheduler:orin-hbstore-prod:2026-08-02`. Requested and effective modes are
  `dry-run`; Shopify creates are zero, `shopify_published=false`,
  `queue_changed=false`, and reconciliation is `not_required`.
- The client remains active with intake and automation enabled, concurrency
  one, Shopify writes disabled, and scheduler owner
  `openclaw:orin-hbstore-prod`. There are no active jobs or open incidents.
- Worker and scheduler-trigger images remain at exact revision
  `5c755295604648161af83fdebf92b2c176b6f8e6`, with zero restarts; the trigger
  and read-only watchdog are healthy.
- The 11:15 watchdog schedule remains enabled with delivery disabled. Its
  automatic run and the explicit fixed-client verification both returned
  `ORIN_SCHEDULED_RUN_OBSERVED`.
- The non-secret verification manifest is preserved at
  `docs/evidence/2026-08-02-normal-run-verification.json`; the canonical private
  evidence remains on the VPS at
  `/docker/orin/evidence/hb_20260802T100007Z_6bb867ff`.

- PR 69 added and reviewed the Phase 6 database-owned content plan. Application
  CI passed 175 tests and database CI passed the complete migration plus 14 new
  pgTAP assertions.
- Remote migration `20260801145042_phase6_add_authoritative_content_plan` is
  applied. Supabase security advisors report no findings. The only new
  performance notices are informational unused-index notices expected before a
  new due item and run history use those indexes.
- `content_plan_items` contains exactly 60 Hoverboard Store rows with RLS
  enabled. Jobs 28-32 are `draft_created`; future approved items remain
  `planned` until their due dates or an explicitly approved commissioning run.
- The Phase 6 commissioning request
  `commissioning:phase6-content-plan:2026-08-01` was automatically claimed by
  the continuously running worker. Run `hb_20260801T145434Z_fe901cf2`
  completed with `no_job_due` at code version
  `5c755295604648161af83fdebf92b2c176b6f8e6`, with zero Shopify creates, no
  publishing, no queue mutation, no reconciliation requirement, and zero
  active jobs afterward.
- Its private evidence directory contains `content_plan_snapshot.json` and
  `content_queue_projection.md` alongside the normal final result and logs.
  Every file is mode `0600`; the snapshot is tenant-scoped, has 30 items, and
  has no selected item.
- The VPS checkout is clean. The automatic worker and scheduler-trigger images
  both identify revision `5c755295604648161af83fdebf92b2c176b6f8e6`, have
  zero restarts, and the trigger is healthy. The read-only watchdog remains
  healthy at its independently pinned revision.
- Production returned to its safe operating state: client active, request
  intake and automation enabled, concurrency one, dry-run only, Shopify writes
  disabled, scheduler owner `openclaw:orin-hbstore-prod`, dedicated 11:00
  schedule enabled, 11:15 watchdog enabled, and the legacy schedule disabled.

- The 2026-08-01 automatic request used source key
  `scheduler:orin-hbstore-prod:2026-08-01`, was accepted with
  `replayed=false`, and was automatically claimed. Its fail-closed result is
  preserved at `/docker/orin/evidence/hb_20260801T105011Z_a6368142`.
- The corrected post-deployment dry-run is
  `hb_20260801T112513Z_9940038c` at code version
  `45533132b85a247827e29a6320f955ad295e336b`. It completed with decision
  `READY_TO_CREATE_SELECTED_JOB_DRAFT`, selected Job 28, made zero Shopify
  creates, did not publish, did not change the queue, and required no
  reconciliation. Evidence is preserved on the VPS and in the local
  `ORIN_EVIDENCE` directory.
- The deployed automatic worker and scheduler-trigger images both identify
  revision `45533132b85a247827e29a6320f955ad295e336b`; both have zero
  restarts, and the trigger is healthy.
- The dedicated production schedule
  `e09fc195-17e4-44f0-8697-bf6ae4b3dec8` is enabled in exact dry-run mode for
  11:00 Europe/London. Supabase records the client as active, intake and
  automation enabled, Shopify writes disabled, concurrency one, scheduler
  state healthy, and owner `openclaw:orin-hbstore-prod`. The legacy schedule
  `c5c7e16b-5ee1-4855-ae7a-97fd25bfd67d` remains disabled.
- The Phase 4 automatic proof is sealed root-owned mode `0400` at
  `/docker/orin/evidence/phase4/latest_automatic_proof.json`.
- Migration `phase5_add_readonly_watchdog_role` is applied. `orin_watchdog`
  has no admin or RLS-bypass attributes, cannot read incidents, cannot execute
  the scheduler trigger, and cannot insert or update content jobs. RLS exposes
  only `hoverboard_store`.
- PRs 65-66 isolated the watchdog socket from the scheduler-trigger directory
  and allowed the bounded Supabase session-pooler health handshake. The
  watchdog runs healthy with zero restarts, a read-only root filesystem, UID
  10003, and immutable image revision
  `38aa69c01e87d487148503f51e73a0a631a0169a`.
- Commissioning rejected an unauthorized root peer and an authorized malformed
  request with stable redacted codes. A synthetic missed-run snapshot returned
  `ORIN_SCHEDULED_RUN_MISSED`; the real completed July 31 receipt returned
  `ORIN_SCHEDULED_RUN_OBSERVED`.
- A near-term automatic OpenClaw command check executed the fixed watchdog
  client with no delivery. It correctly returned
  `ORIN_SCHEDULED_RUN_FAILED` for the known blocked August 1 scheduler receipt
  and exit code 4. The temporary one-shot was removed. The permanent watchdog
  schedule `f030dfc8-b493-4250-ad94-bd4afe91e607` is enabled at 11:15
  Europe/London with no alert delivery; its next execution is post-deployment
  observation rather than a Phase 5 activation blocker.

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
- A filesystem-durable direct controlled dry-run at the corrected revision
  terminalized as `completed` with
  `READY_TO_CREATE_SELECTED_JOB_DRAFT`. MiniMax used its bounded retry:
  attempt 1 was rejected and attempt 2 passed the full content, topic, HTML,
  publisher, and compliance gates. This direct harness run is not represented
  in the Supabase jobs, runs, attempts, or artifact ledgers.
- The corrected controlled run selected Job 28, made zero Shopify creates,
  published nothing, left the queue unchanged, and required no
  reconciliation. All database gates remain closed, both OpenClaw jobs remain
  disabled at `0 11 * * *` Europe/London exact, and `nextWakeAtMs` is null.
- The fresh 2026-07-31 automatic proof passed at the exact deployed revision.
  OpenClaw executed only the fixed no-argument command at `00:02`
  Europe/London. Its receipt was `accepted` with `replayed=false`,
  `requested_mode=dry-run`, and `payload={}`.
- The continuously running worker automatically claimed that request and
  terminalized exactly one database job, one run, and one attempt as
  `completed` with `READY_TO_CREATE_SELECTED_JOB_DRAFT`. The run used code
  version `59a34ac5c881424826a2a90e97ba9e1e66fedd81`, made zero Shopify
  creates, published nothing, left the queue unchanged, and required no
  reconciliation.
- All gates were closed immediately after terminalization. The client is in
  maintenance, request intake and automation are disabled, Shopify writes are
  disabled, allowed mode remains `dry-run`, scheduler state is disabled with
  no owner, and there are zero active jobs or open incidents. Both OpenClaw
  schedules are disabled at `0 11 * * *` Europe/London exact and
  `nextWakeAtMs` is null.

The latest automatic Shopify test created exactly one article:

- Job: 32
- Title: `Electric Scooter Handlebar Height for Children: Fit Guide`
- Handle: `electric-scooter-handlebar-height-for-children-fit-guide`
- Model: `MiniMax-M3`
- Shopify article ID: `1007284420956`
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

- Client status: `active`
- Request intake enabled: `true`
- Automation enabled: `true`
- Shopify writes enabled: `false`
- Allowed mode: `dry-run`
- Database scheduler state: `healthy`
- Database scheduler owner: `openclaw:orin-hbstore-prod`
- Legacy OpenClaw job: disabled
- Dedicated `orin-hbstore-prod` job: enabled at `0 11 * * *` Europe/London
- Read-only watchdog job: enabled at `15 11 * * *` Europe/London
- Dedicated job payload: fixed `python3` argv to the HBStore socket client
- Dedicated job agent/tools: none
- Dedicated job delivery: none
- Production trigger attached: yes, dry-run only
- ORIN containers: healthy scheduler-trigger and watchdog sidecars; automatic
  worker running with zero restarts and reporting `no_job_due`
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

The post-fix filesystem-durable direct controlled dry-run evidence is
preserved at:

`/docker/orin/evidence/hb_20260730T000603Z_c31b49a1`

The local operator copy is:

`/Users/harirajbhattarai/Documents/COMPUTER_USE/ORIN_EVIDENCE/hb_20260730T000603Z_c31b49a1`

The direct runner request ID is
`41840073-f0e4-48a7-af96-e069f0d671b5`; the terminal run is
`hb_20260730T000603Z_c31b49a1`. It completed at code version
`59a34ac5c881424826a2a90e97ba9e1e66fedd81` with
`READY_TO_CREATE_SELECTED_JOB_DRAFT`, zero Shopify creates,
`shopify_published=false`, an unchanged queue, and
`reconciliation_status=not_required`. This direct run has no corresponding
Supabase `content_jobs`, `runs`, `job_attempts`, or `run_artifacts` row.

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

The successful fresh-date automatic trigger-plus-worker proof is preserved at:

`/docker/orin/evidence/hb_20260730T230209Z_8658cadf`

The local operator copy is:

`/Users/harirajbhattarai/Documents/COMPUTER_USE/ORIN_EVIDENCE/hb_20260730T230209Z_8658cadf`

At `00:02` Europe/London on 2026-07-31, the dedicated fixed command created
exactly one request for
`scheduler:orin-hbstore-prod:2026-07-31`. The trigger receipt was `accepted`
with `replayed=false`, `requested_mode=dry-run`, and `payload={}`. The request
ID is `33d0c67b-6922-5f31-817c-262678413a65`; the database job is
`97825339-f9f1-4cb6-9962-10dbcf79fc3d`; and the terminal run is
`hb_20260730T230209Z_8658cadf`.

Supabase records exactly one job, one run, and one attempt. The run completed
at code version `59a34ac5c881424826a2a90e97ba9e1e66fedd81` with
`READY_TO_CREATE_SELECTED_JOB_DRAFT`, zero Shopify creates,
`shopify_published=false`, an unchanged queue,
`shopify_write_state=not_attempted`, and
`reconciliation_status=not_required`.

SHA-256:

- `final_result.json`:
  `78be17bf831736ab0e326e8ce9347066c1e6a0fd3cd9eb0afa233ce9437ee0bb`
- `pipeline_preview.json`:
  `980bfbb74ce0bd4b99fbe648521418235f599194d1f40ff68211064076999c25`
- `stdout.log`:
  `07aa1d979f3425b60fcb5cabe6aa41c8c3b52bafc8021bc96c6e080c6b8d8059`
- `stderr.log`:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `writer_output_job28_1785452532_31b3d19f.html`:
  `b6f42df2cb9f9ae063105a9a4697300cba1b4cbfd39c66913fd919ba33729cdb`

## Phase 6 client-product implementation — 2026-08-02

Migration `phase6_client_product_boundary` is applied to Supabase. It adds the
redacted authenticated dashboard projection, immutable version-bound client
decisions, narrow customer column grants, and transactional scheduler-health
freshness. The production scheduler health ledger now points to the normal
2026-08-02 run `hb_20260802T100007Z_6bb867ff` rather than stale commissioning
evidence.

Verification:

- Supabase security advisor: zero findings;
- pgTAP client-product boundary: 19 checks pass;
- full Python suite: 181 tests pass;
- dashboard production build and four hosting tests pass;
- browser QA: authenticated configuration correctly fails closed to the
  magic-link sign-in screen with no console warnings;
- active database jobs: zero;
- Shopify writes: disabled.

The isolated `evidence-sync` one-shot profile is implemented and tested. It is
not commissioned because its server-side Supabase key must be installed
interactively on the VPS and must never be pasted into chat or Git. Supabase
Auth also still has no real user/member, so the first HBStore owner identity
must be selected before the live dashboard can be commissioned.

See `docs/PHASE6_CLIENT_PRODUCT.md` for the exact two handoffs and verification
sequence.

## Next approved path

Proceed from transferred dry-run ownership without enabling Shopify writes:

1. Create/sign in the first HBStore Supabase Auth user and add exactly one
   `owner` membership.
2. Prove the live dashboard reads only HBStore and records one harmless,
   idempotent `request_changes` decision without creating a job.
3. Install the evidence-sync server key directly on the VPS, run the isolated
   one-shot profile, and verify one authenticated download plus SHA-256.
4. Keep the legacy main-agent scheduler permanently disabled and keep Shopify
   writes disabled while normal dry-run and watchdog receipts continue.
5. Only after the private HBStore client pilot, design a separate
   approval-to-worker bridge. It must not let a browser enable runtime gates or
   invoke Shopify directly.
6. Start additional clients only after HBStore completes this observation and
   client-access window. Reuse tested code but separate credentials, policies,
   database membership, queues, scheduler ownership, and evidence.

Do not enable the legacy main-agent scheduler, enable Shopify writes outside a
controlled transaction, or describe the system as public-ready while the
customer access layer and HBStore observation window remain incomplete.

## Phase 6 private-pilot commissioning — 2026-08-03

The two production handoffs are now installed without exposing credentials.
The selected Bitleaf Supabase Auth identity has exactly one
`hoverboard_store` owner membership. An authenticated database-boundary check
returned exactly one redacted HBStore dashboard workspace for that owner and
zero workspaces for a nonmember.

One harmless `request_changes` decision was recorded with request ID
`d4f6462a-6f03-4d5c-9e3f-431fd1b2f6a0`. The trigger bound the actor to
`auth.uid()`. An exact retry hit the expected unique constraint and durable
verification found one decision row, zero active jobs, zero open incidents,
`allowed_mode=dry-run`, and `shopify_writes_enabled=false`.

Portable evidence sync completed for the normal automatic dry-run
`hb_20260802T100007Z_6bb867ff`:

- first sync: seven uploads and seven `run_artifacts` registrations;
- exact replay: zero uploads, zero registrations, seven verified replays;
- bucket visibility: private;
- service-side verification: all seven byte counts and SHA-256 digests match.

The production checkout and running worker, scheduler-trigger, and watchdog
remain at `6d4b108b0471ffe314a370ad555793ef2f12c6aa`. The dedicated dry-run
scheduler and read-only watchdog are healthy and enabled at their normal
11:00/11:15 Europe/London schedules. The legacy main-agent schedule remains
disabled. There are zero active jobs and zero open incidents.

Phase 6 is not yet declared complete. The selected owner must sign in through
the hosted dashboard after the Supabase email rate limit clears, prove the live
snapshot, and download one Storage object as that authenticated owner. The
latest Supabase security advisor also reports leaked-password protection as
disabled; enable it before public access. Unused-index notices are informational
and are retained until representative production traffic exists.

Durable details are in
`docs/evidence/2026-08-03-phase6-private-pilot-commissioning.json`.

## Normal dry-run and watchdog verification — 2026-08-04

The normal 11:00 Europe/London dedicated schedule ran automatically with its
fixed command. OpenClaw recorded `status=accepted`, `replayed=false`, and
source key `scheduler:orin-hbstore-prod:2026-08-04`. The continuously running
immutable worker claimed the request without overrides and completed run
`hb_20260804T100003Z_24be9981` with decision `no_job_due`.

Durable database verification found exactly one job, one run, and one attempt
for the source key. Requested and effective modes are `dry-run`; Shopify create
count is zero, `shopify_published=false`, `queue_changed=false`, Shopify write
state is `not_attempted`, and reconciliation is `not_required`. The previously
required source key `scheduler:orin-hbstore-prod:2026-08-02` also remains
unique with exactly one completed job, run, and attempt.

The worker and scheduler-trigger are running at exact deployed revision
`6d4b108b0471ffe314a370ad555793ef2f12c6aa`, both with zero restarts, and the
trigger sidecar is healthy. The VPS checkout is clean. Production remains
dry-run only: the client is active, intake and automation are enabled,
concurrency is one, Shopify writes are disabled, and scheduler ownership is
`openclaw:orin-hbstore-prod`. There are zero active jobs and zero open
incidents.

The read-only watchdog ran automatically at 11:15 Europe/London and returned
`ORIN_SCHEDULED_RUN_OBSERVED` for the same completed run. Its delivery remains
disabled. The dedicated schedule remains enabled at `0 11 * * *`, the
watchdog remains enabled at `15 11 * * *`, and the legacy main-agent schedule
has no active entry.

Canonical private evidence is contained beneath mode-`0700` directories at
`/docker/orin/evidence/hb_20260804T100003Z_24be9981`. The four canonical
receipt files are mode `0600` and their hashes are recorded in the non-secret
manifest. One moved pre-existing pipeline preview retains mode `0644`, but is
not externally readable because both parent directories are mode `0700`; its
mode should be normalized in a subsequent hardening change.

Durable details are in
`docs/evidence/2026-08-04-normal-run-verification.json`.

## Phase 6 durable review workflow implementation — 2026-08-04

The dashboard review boundary is now implemented as a two-stage workflow in
the development branch. Concept approval and unpublished-Shopify-draft
approval are distinct decisions. Generated HTML is captured from the exact
private run directory, hashed, stored as an immutable tenant/version-bound
`content_drafts` row, and exposed through a `security_invoker` review view.
The dashboard renders that full HTML inside a sandboxed, script-disabled
frame; it no longer substitutes another queue item's article.

The existing automatic worker now asks the database to materialize at most one
eligible decision before claiming normal jobs. The database can create only a
dry-run job from `approve_concept`. `approve_hidden_draft` additionally
requires the matching stored draft plus active intake, automation,
hidden-draft mode, and Shopify-write gates. The browser cannot open those
gates or create jobs directly. Stale decisions are superseded and closed gates
leave approvals recorded without work.

Local verification completed with 182 Python tests, 131 pgTAP database tests,
five dashboard routing tests, four Sites worker tests, a production dashboard
build, schema lint, and whitespace validation. No production migration,
worker deployment, dashboard deployment, Shopify request, or live publish was
performed by this implementation step. Production rollout must be ordered:
database migration, immutable worker deployment with gates closed, dashboard
deployment, then one concept-only pilot. Shopify writes remain disabled until
that pilot is reviewed.

## Phase 6 Job 33 durable-draft pilot — 2026-08-04

The concept-only production pilot is complete. PR #83 corrected the natural-H1
false negative without weakening the fail-closed keyword rule: every meaningful
target term is still required, while hyphenation, natural word order, and simple
singular/plural differences are accepted. It also preserves genuine pipeline
blockers instead of replacing them with a selected-item mismatch. All three CI
jobs passed, and the worker plus scheduler-trigger were deployed at exact merged
revision `008c4ebe3fb82eb403bdc2596faff96dd054bd0e` with zero restarts.

The owner approved Job 33 version 4 through the private dashboard. The existing
automatic worker materialized, claimed, and completed exactly one dry-run job,
one run, and one attempt without a date or item override. Run
`hb_20260804T123458Z_729bc75f` returned
`READY_TO_CREATE_SELECTED_JOB_DRAFT`, selected Job 33, and recorded zero Shopify
creates, no publish, no queue mutation, `shopify_write_state=not_attempted`, and
`reconciliation_status=not_required`.

Completion atomically advanced Job 33 to `local_draft_created` version 5 and
stored the exact 2,122-word HTML as an immutable `content_drafts` row. The
database body digest and private evidence-file digest both equal
`cded6db118f6967bdbc1d02a066265368e69c586ea1b5be1e708e5a220f880ea`.
The owner dashboard renders the full stored draft in its sandboxed frame and
shows the separate unpublished-Shopify-draft approval action. That action was
not selected.

Commissioning gates were closed immediately after completion: the client is in
maintenance, request intake and automation are disabled, Shopify writes are
disabled, allowed mode remains `dry-run`, scheduler state is disabled with no
owner, and there are zero active jobs or open incidents. Legacy, dedicated, and
watchdog OpenClaw schedules are all disabled. Phase 6 durable concept-to-review
is proven. Before any hidden-draft approval, the next implementation must prove
that the exact stored reviewed HTML—not regenerated content—is the idempotent
input to the Shopify hidden-draft transaction and reconciliation path.

Durable details are in
`docs/evidence/2026-08-04-job33-durable-draft-proof.json`.

## Phase 7 Prefect shadow foundation validation — 2026-08-04

The isolated Prefect foundation is reviewed, merged, and deployed at exact
revision `5bdc759ddedb22105a8c8b00a77774d9aac0431e`. Prefect 3.8.1 and
PostgreSQL 16.10 are pinned by immutable image digests. The separate Compose
project has no default service, exposes the authenticated API and UI only on
VPS loopback `127.0.0.1:54200`, and gives its process worker neither the Docker
socket nor any Shopify, model-writer, ORIN worker, scheduler, control API,
evidence, or OpenClaw credential.

The local integration proof started the authenticated Prefect server and its
dedicated PostgreSQL database, applied a deployment with no schedules, and
confirmed both the deployment and process pool were paused. Pool and
deployment concurrency were one with `CANCEL_NEW` collision behavior. One
supervised flow run then used the dedicated `orin_prefect_shadow` login to call
only the fixed-client sanitized snapshot function. It observed maintenance,
closed intake and automation, disabled scheduler ownership, disabled Shopify
writes, zero active jobs, and zero open incidents; it emitted a shadow
prediction artifact and completed successfully. The pool was immediately
paused again and the test stack and temporary login were removed.

Validation passed with 239 Python tests, 149 pgTAP database assertions, schema
lint, shell and Compose contract checks, an immutable image build, authenticated
server health, paused bootstrap inspection, and the real process-worker flow.
The production deployment additionally proves authenticated API and UI HTTP
200 responses, a read-only root filesystem, bounded non-executable UI tmpfs,
zero UI runtime errors, a paused pool with concurrency one, a paused deployment
with no schedules and `CANCEL_NEW`, and no shadow worker container or shadow
database secret. PRs #89 and #90 passed all CI jobs.

At this foundation checkpoint the production shadow role remained `NOLOGIN`
and its VPS secret was absent. All ORIN gates were closed, all three OpenClaw
schedules were disabled with `nextWakeAtMs=null`, and the latest production
dry-run recorded zero Shopify creates. No Prefect schedule or Shopify
permission was enabled.

Durable details are in
`docs/evidence/2026-08-04-phase7-prefect-foundation.json`.

## Phase 7 first production shadow comparison — 2026-08-04

The first supervised production shadow comparison passed at deployed revision
`5bdc759ddedb22105a8c8b00a77774d9aac0431e`. Prefect flow run
`4f712cfc-30fb-41f7-9551-3d80d4277a37` completed once with no retries and
emitted the fixed-client prediction artifact. For London business date
2026-08-04 it predicted `no_job_due`, matching OpenClaw production dry-run
`hb_20260804T100003Z_24be9981` exactly. The next planned item is Job 34, due
2026-08-12.

The dedicated database login has no direct `content_jobs` read or insert
privilege, cannot execute the scheduler enqueue function, and can execute only
the sanitized snapshot function. The initial malformed URL credential was
removed and rotated before this run. No credential value is stored in evidence
or repository history.

The comparison observed maintenance mode, closed intake and automation,
disabled scheduler ownership, disabled Shopify writes, zero active jobs, and
zero open incidents. After completion the worker container was removed, the
pool was paused with concurrency one and zero active slots, the deployment was
paused with no schedules, all OpenClaw schedules remained disabled, and
`nextWakeAtMs` remained null. Production state still records zero Shopify
creates, no publication, no queue mutation, and reconciliation not required.

Phase 7 now has one valid production shadow match. Promotion is not authorized:
several additional same-date matches are required before proposing any Prefect
schedule or scheduler-ownership transfer, and Shopify writes remain disabled.

Durable details are in
`docs/evidence/2026-08-04-phase7-first-production-shadow-proof.json`.

## Phase 7 second production shadow comparison — 2026-08-09

The second independent same-date production comparison passed. With Shopify
writes explicitly disabled, a controlled invocation of the existing fixed
OpenClaw schedule created source key
`scheduler:orin-hbstore-prod:2026-08-09` exactly once. The automatic ORIN
worker completed one job, one run, and one terminal attempt as
`no_job_due`. Run `hb_20260809T122528Z_eccb4fdb` recorded zero Shopify
creates, no publication, no queue change, `shopify_write_state=not_attempted`,
and `reconciliation_status=not_required`.

Prefect flow run `af0ea3da-bf10-47c5-a5aa-3ce380b581f0` then completed once
with no retry at deployed revision
`5bdc759ddedb22105a8c8b00a77774d9aac0431e`. For London business date
2026-08-09 it independently predicted `no_job_due` and matched the OpenClaw
run exactly. The next due plan item remains Job 34 on 2026-08-12.

Cleanup is complete. The client is in maintenance, request intake and
automation are disabled, Shopify writes are disabled, allowed mode is
`dry-run`, scheduler ownership is disabled with no owner, and there are zero
active jobs or open incidents. The Prefect worker was removed, its process
pool is paused at concurrency one, the deployment is paused with no schedules,
concurrency one, zero active slots, and `CANCEL_NEW`. All three OpenClaw
schedules are disabled and `nextWakeAtMs` is null.

Phase 7 now has two valid production shadow matches. Promotion remains
unauthorized: record at least one more independent same-date match before any
Prefect schedule or scheduler-ownership proposal. Shopify writes remain
disabled.

Durable details are in
`docs/evidence/2026-08-09-phase7-second-production-shadow-proof.json`.

## Phase 7 third production shadow comparison — 2026-08-11

The third independent same-date comparison passed for London business date
2026-08-11. The first OpenClaw cron-wrapper attempt reached the scheduler
sidecar but returned `ORIN_SCHEDULER_TRIGGER_BLOCKED`; the sidecar recorded only
the exception class `ProgrammingError`. It created no database job. All gates
were closed immediately, a rollback-only scheduler-role preflight passed, and
the exact fixed schedule command was then invoked as the OpenClaw runtime UID
without changing credentials or configuration.

That controlled retry created source key
`scheduler:orin-hbstore-prod:2026-08-11` exactly once. The automatic worker
completed one job, one run, and one terminal attempt as `no_job_due`. Run
`hb_20260810T233526Z_5d645f81` recorded zero Shopify creates, no publication,
no queue change, `shopify_write_state=not_attempted`, and
`reconciliation_status=not_required`.

Prefect flow run `7e3599f8-e2b8-42fa-a545-5eb2d5c2572e` completed once with
no retry at deployed revision
`5bdc759ddedb22105a8c8b00a77774d9aac0431e`. It independently predicted
`no_job_due` for 2026-08-11 and matched the OpenClaw result exactly. The next
due item remains Job 34 on 2026-08-12.

Cleanup is complete: the client is in maintenance, intake and automation are
disabled, Shopify writes are disabled, scheduler ownership is disabled with no
owner, and there are zero active jobs or incidents. The Prefect worker is
removed, its pool and deployment are paused at concurrency one with zero
active slots, the deployment has no schedules, all OpenClaw schedules are
disabled, and `nextWakeAtMs` is null.

Phase 7 has now accumulated three valid production shadow matches, so the
shadow-observation threshold is met. Scheduler ownership is not transferred
yet. Before a controlled ownership test, harden the scheduler-trigger database
health/retry boundary so a transient blocked call is observable and safely
recoverable without exposing database details. Prefect scheduling and Shopify
writes remain disabled.

Durable details are in
`docs/evidence/2026-08-11-phase7-third-production-shadow-proof.json`.

## Scheduler-trigger reliability deployment — 2026-08-11

The scheduler-trigger reliability hardening from PR #95 is merged and deployed
at exact revision `96cc33c34a8288090846060e430c69bf01eb76b7`. The boundary now
classifies database failures into stable non-sensitive categories, retries an
idempotent trigger exactly once only for transient database failures, never
retries policy failures, and reports database unavailability without exposing
SQL or credential details. Its container health check now verifies both the
real `orin_scheduler` database role and the fixed Unix socket.

Validation passed 21 focused tests, the 244-test Python suite, compileall, diff
checks, and all GitHub CI jobs, including database and immutable image checks.
The scheduler-only image was built from a local Git archive of the exact merge
revision and deployed with `--no-deps`; the pinned Prefect checkout was not
moved. The replacement sidecar is healthy with restart count zero and emits
`ORIN_SCHEDULER_TRIGGER_HEALTHY`. The previous scheduler image remains on the
VPS for rollback.

The existing fixed OpenClaw command was exercised as runtime UID 1000. Because
the 2026-08-11 source key already existed from the third shadow proof, the safe
probe returned the existing completed dry-run with `replayed=true`. The source
key remains exactly one job and one run with zero Shopify creates; no new job
was inserted. Policy classification and its no-retry behavior are covered by
automated tests; no database fault was injected into production.

Post-deployment state remains closed: maintenance mode, intake and automation
off, Shopify writes off, dry-run only, scheduler disabled with no owner, and
zero active jobs or incidents. The worker, watchdog, and Prefect server images
and restart counts are unchanged. Legacy, dedicated, and watchdog OpenClaw
schedules are all disabled, the dedicated cron remains `0 11 * * *`
Europe/London, and `nextWakeAtMs` is null.

The scheduler reliability prerequisite is complete. The next Phase 7 action is
a separately reviewed, controlled Prefect ownership-transfer test with Shopify
writes and Prefect scheduling still disabled until that test is explicitly
commissioned.

Durable details are in
`docs/evidence/2026-08-11-scheduler-trigger-reliability-deployment.json`.

## Phase 7 controlled Prefect ownership proof — 2026-08-11

The controlled Prefect ownership proof passed at reviewed revision
`2ce3859b4f6775f3e5f37173b45d734185cb473e`. PR #97 passed dashboard,
database, and test CI, including 12 new pgTAP assertions, schema lint, the full
Python suite, Compose contracts, and an immutable Prefect image build. The
production migration created a separate `NOLOGIN` role with no direct table
access and one zero-argument, fixed-client, dry-run-only commissioning
function. The existing read-only shadow role was not widened.

The private Prefect server and both paused deployments were upgraded to the
exact merged revision. The new owner pool and deployment had concurrency one,
zero active slots, `CANCEL_NEW`, no parameters, and no schedules. A real
closed-gate call using the temporary owner credential was rejected with
SQLSTATE `42501` and created no job. Only after that proof passed were the
short commissioning gates opened with Shopify writes still disabled.

Ad-hoc Prefect flow run `44559044-dab9-4bb3-8563-eba7ba55ce88` completed once
with no retries or parameters. Its durable receipt was accepted with
`replayed=false` and created source key
`scheduler:orin-hbstore-prod:prefect-commissioning-v1` exactly once. The
existing automatic ORIN worker then completed one job, one run, and one attempt
as run `hb_20260811T005721Z_47de955c`, decision `no_job_due`, at worker
revision `d257e94271a916c13f736f74e8831c9d0cc1cde6`. It recorded zero Shopify
creates, no publication, no queue change, reconciliation not required, and no
error.

Cleanup is complete. Maintenance mode is restored; intake and automation are
off; Shopify writes are off; allowed mode remains `dry-run`; scheduler state is
disabled with no owner; and there are zero active jobs or incidents. The owner
pool and deployment are paused with no schedules, the owner worker is removed,
the database role is back to `NOLOGIN`, and both owner credential files were
deleted. All three OpenClaw schedules remain disabled with `nextWakeAtMs=null`.

Several setup commands had recoverable shell/TTY issues before or after the
actual proof. They did not create extra work or expose credentials and are
recorded in the evidence. The proof itself produced one clean Prefect receipt
and one clean ORIN terminal execution.

Phase 7 has now passed three shadow comparisons and one controlled Prefect
ownership proof. Recurring scheduler ownership is not active yet. The next
step is a separate reviewed recurring Prefect dry-run schedule, followed by
one fresh-date automatic Prefect trigger plus automatic ORIN worker proof.
Shopify writes remain disabled.

Durable details are in
`docs/evidence/2026-08-11-phase7-prefect-ownership-commissioning-proof.json`.

## Phase 7 automatic recurring Prefect proof — 2026-08-12

The fresh-date automatic Prefect path completed successfully using the
disabled-by-default scheduler implementation from PR #99 at exact revision
`8b0223d8621cfd7ec8cecf09b8250769b878c4e0`. The proof used a temporary
one-shot schedule for 00:02 Europe/London. The normal `0 11 * * *` schedule
remained inactive, all three OpenClaw schedules remained disabled, and no flow
run was created manually.

Prefect created exactly one auto-scheduled flow run,
`019ff30d-433b-7148-82f6-1e020b1ef197`, with no parameters, one run, and zero
retries. It completed and returned an accepted, non-replayed receipt for
`scheduler:orin-hbstore-prod:2026-08-12`. The existing automatic ORIN worker
then claimed and terminalized exactly one database job, run, and attempt as
`hb_20260811T230211Z_41663ea2`. The dry run selected content-plan item 34 and
recorded `READY_TO_CREATE_SELECTED_JOB_DRAFT`, zero Shopify creates, no
publication, no queue change, `shopify_write_state=not_attempted`, no
reconciliation, and no error.

The commissioning checklist initially compared `runs.code_version` with the
Prefect scheduler revision. That conflated two independently deployed
components. The Prefect control plane correctly ran revision
`8b0223d8621cfd7ec8cecf09b8250769b878c4e0`; the ORIN data-plane run correctly
recorded its separately pinned worker image revision
`d257e94271a916c13f736f74e8831c9d0cc1cde6`. This change clarifies the runbook
so future proofs verify each revision at its own boundary. Formal acceptance
of the automatic proof remains pending review and CI for this clarification;
the live evidence itself does not require a rerun.

Cleanup completed immediately after terminalization. The client is in
maintenance; intake and automation are off; Shopify writes are off; dry-run is
the only allowed mode; scheduler state is disabled with no owner; and there
are zero active jobs or incidents. The owner role is `NOLOGIN`, the owner pool
and deployment are paused, the temporary schedule and owner worker were
removed, and the temporary owner credential was securely deleted. The normal
Prefect schedule remains inactive. All OpenClaw schedules remain disabled and
`nextWakeAtMs` is null.

Durable details are in
`docs/evidence/2026-08-12-phase7-prefect-recurring-automatic-proof.json`.

## Phase 7 Prefect production ownership activation — 2026-08-12

Recurring Prefect dry-run ownership is active at reviewed revision
`4b96b85e1e5f64a564ba4554a9471c436dc3a4af`. The Prefect server, scheduler
deployment, owner worker, and read-only watchdog policy use that exact clean
release. The owner worker and server are healthy with zero restarts. The owner
pool is active at concurrency one, the scheduler deployment is unpaused, and
its only active schedule is `hbstore-daily-dry-run` at `0 11 * * *`
Europe/London.

The first normal production flow run,
`019ff533-2b7a-7930-9dc4-431f99a61aa4`, was created automatically by schedule
`d08b9809-e5cb-4ad4-b9bb-0716193f1393`. It completed once with no parameters
and zero retries. Because the successful midnight proof already owned source
key `scheduler:orin-hbstore-prod:2026-08-12`, the fixed daily boundary returned
`accepted` with `replayed=true`. The database still contains exactly one job,
one run, and one attempt for the source key. No duplicate execution occurred.

The retained terminal run records zero Shopify creates, no publication, no
queue mutation, `shopify_write_state=not_attempted`, reconciliation not
required, and no error. The client is active with intake and automation on,
maximum concurrency one, dry-run as the only allowed mode, Shopify writes off,
and scheduler owner `prefect:orin-hbstore-prod`. There are zero active jobs and
zero open incidents.

The narrowly scoped `orin_prefect_scheduler` role is login-enabled for the
unattended worker but remains non-superuser and cannot bypass RLS. It has no
direct content-job table access and can execute only the fixed zero-argument
daily enqueue function. Its credential is a regular non-empty file owned by
`10004:10004` with mode `0400`; no credential value was printed or recorded.

The legacy and dedicated OpenClaw production schedulers remain disabled. The
only enabled OpenClaw job is the read-only watchdog at `15 11 * * *`
Europe/London with delivery disabled. Its 11:15 automatic run exited zero and
returned `ORIN_SCHEDULED_RUN_OBSERVED` with healthy status.

Phase 7 production ownership is therefore complete in dry-run mode. Shopify
writes remain disabled. Additional clients remain a separate Phase 8 rollout
and must receive independent credentials, policies, queues, evidence, and an
equivalent proof before activation.

Durable details are in
`docs/evidence/2026-08-12-phase7-prefect-production-activation.json`.

## Job 34 exact-reviewed hidden-draft proof — 2026-08-12

The first controlled content promotion after Prefect dry-run ownership
activation passed without changing the recurring Prefect scheduler. The
dashboard owner approved version 2 of Job 34, “Solid vs Air-Filled Electric
Scooter Tyres: A Parent's Guide.” The approval was bound to immutable draft
`b9dd2a02-bbd2-499f-a5f9-69edfa16a430`, its 1,945-word body, and SHA-256
`5dded6849d7f7d3720f51e167115df04b84c1e635a6ebadb9d58ffc4def5d0b6`.

The duplicate preflight found no existing Shopify article with the exact
title. Only the hidden-draft mode and Shopify-write gate were opened; maximum
concurrency remained one. The existing automatic ORIN worker consumed one
approval, created one job, and completed one run and one attempt as
`hb_20260812T112653Z_471a4bab` at worker revision
`d257e94271a916c13f736f74e8831c9d0cc1cde6`. The terminal decision was
`APPROVED_REVIEW_DRAFT_CREATED_VERIFICATION_PASSED` with one Shopify create,
no publication, no queue mutation, and reconciliation complete.

An independent Shopify GraphQL query found exactly one matching article,
`1007420408156`, handle `solid-vs-air-filled-electric-scooter-tyres`, in the
Journal Insights blog. It remains unpublished with `publishedAt=null`.
The fetched body matched the approved body after the narrowly defined
Shopify list-whitespace canonicalization, and the database contains exactly
one durable ownership record for the article.

The write gate was closed immediately after terminalization. The client is
again active in dry-run-only mode with Shopify writes disabled, Prefect remains
the healthy scheduler owner, and there are zero active jobs or incidents. The
normal recurring Prefect schedule and read-only OpenClaw watchdog are
unchanged; both legacy OpenClaw production schedulers remain disabled. All
worker, Prefect, trigger, and watchdog containers are healthy with zero
restarts.

Durable details are in
`docs/evidence/2026-08-12-job34-exact-reviewed-hidden-draft-proof.json`.

## Job 35 approval-only reconciliation proof — 2026-08-12

The dashboard owner approved version 4 of Job 35, “How to Store a Kids
Electric Scooter Between Rides.” The approval was bound to immutable draft
`c0f0b2c0-6ae4-4e5d-939c-cc515aed4d3e`, its 2,093-word body, and SHA-256
`60c689f1c6c373a475596fab51ec94792b9b0f0a1c2a9cfe7530eef1cb9bf2d1`.
Shopify created exactly one unpublished article, `1007422767452`, but decoded
seven numeric apostrophe entities to literal apostrophes. The original
fail-closed verifier did not recognize that render-equivalent serialization,
so three automatic attempts correctly stopped with unknown write state and
opened one critical reconciliation incident. No retry created a duplicate.

PR #106 added only the observed Shopify-safe apostrophe serialization to the
existing narrow body canonicalizer. It remains fail-closed for all other
entity, whitespace, element, attribute, and text differences. Dashboard,
database, focused reconciliation, and full Python CI passed before merge at
`25d4159f528dd6a1faa422e0b272b70bcbe26bce`. The automatic worker was then
rebuilt from that exact clean release and replaced with zero restarts while
the approval-only gate remained closed.

A fresh read-only marker scan found exactly one matching article, with
`publishedAt=null`. One guarded fourth attempt was allowed for the exact
failed job. Run `hb_20260812T144745Z_5ab834da` found the existing article
before any create call and completed with decision
`APPROVED_REVIEW_DRAFT_CREATED_VERIFICATION_PASSED`, reconciliation status
`reconciled`, article-observed state, one request-owned Shopify article, no
publication, and no queue mutation. The fetched and approved canonical body
hashes both equal
`9ed03c16e697b322497a75575ec8de4b18213b02b833c4d1ce31b651a834fab2`.

The incident was resolved against the successful run. Job 35 is
`draft_created`, its source key exists exactly once, there are zero active jobs
and zero open incidents, and the approval-only draft gate is enabled. Broad
Shopify writes remain disabled, dry-run remains the only scheduler mode, and
the dashboard still has no live-publish capability. Prefect remains the
healthy recurring scheduler owner; both OpenClaw production schedulers remain
disabled and the read-only watchdog remains healthy.

Durable details are in
`docs/evidence/2026-08-12-job35-approval-only-reconciliation-proof.json`.

## Job 36 quality-gated hidden-draft proof — 2026-08-12

Job 36, “Kids Electric Scooter Brake Checks Before Every Ride,” completed the
full dashboard concept-review, controlled drafting, quality-review, and
approval-only Shopify workflow. Human review rejected three earlier drafts for
topic drift, unsupported safety wording, incomplete metadata, an invented
internal link, and an unsuitable public-car-park example. Those failures were
converted into reusable model and post-write gates in PRs #108, #109, and
#110; all application, dashboard, and database CI passed before the final
worker deployment.

The final 1,925-word review draft was generated and checked at exact worker
revision `c2ed28902327d08bfefcc5906a1725670a4b7877`. It contains finished SEO
metadata, scooter-specific FAQs, private-land guidance, and only the five
approved Hoverboard Store URLs. It contains no invented URL, public-car-park
example, or unsupported weather-performance prediction. The dashboard owner
approved immutable draft `b544d288-55fc-4f23-b559-f4becdf3d65d`, version 13,
with body SHA-256
`407500b4b05189eaed27e308e4f5a95b4bda5f429ec9651263714b51e61215ca`.

The automatic worker consumed exactly one approval, job, run, and attempt.
Run `hb_20260812T155801Z_38b0169c` completed with decision
`APPROVED_REVIEW_DRAFT_CREATED_VERIFICATION_PASSED`, one request-owned Shopify
create, no publication, no queue mutation, and successful reconciliation.
An independent read-only Shopify GraphQL query verified article
`1007424012636`, handle
`kids-electric-scooter-brake-checks-before-every-ride`, with
`publishedAt=null`, the expected idempotency marker, and a body hash exactly
matching the approved dashboard draft.

Broad Shopify writes remain disabled. The narrow approval-only draft gate is
enabled, the recurring scheduler remains dry-run-only under Prefect ownership,
both OpenClaw production schedulers remain disabled, and the read-only
watchdog remains healthy. There are zero active jobs and zero open incidents.

Durable details are in
`docs/evidence/2026-08-12-job36-quality-gated-hidden-draft-proof.json`.
