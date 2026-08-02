# Phase 6 gap audit — 2026-08-02

## Outcome

Phase 6A, the database-owned backend migration for Hoverboard Store, is
complete. Supabase is authoritative for the content plan, execution ownership,
jobs, leases, runs, attempts, reconciliation, incidents, runtime gates, and
scheduler ownership.

The unfinished work belongs to the client-product extension of Phase 6: client
identity, a redacted dashboard read model, durable client decisions, and
portable evidence storage. The local dashboard prototype does not change the
production execution path and cannot write to Shopify.

## Evidence reviewed

- Remote Supabase migrations include
  `20260801145042_phase6_add_authoritative_content_plan`.
- The security advisor reports zero findings.
- All public operational tables have RLS enabled.
- Authenticated access is read-only and tenant-scoped through
  `client_members`.
- Private worker functions are not executable by `anon`, `authenticated`, or
  `public`.
- The targeted content-plan, worker, and runner test suites pass.
- The production worker, scheduler trigger, and watchdog containers are
  running with zero restarts; the trigger and watchdog report healthy.
- The 2026-08-02 automatic schedule and watchdog receipts are healthy.
- There are zero active database jobs and zero open incidents.
- Shopify writes remain disabled in runtime settings.

## Current authoritative state

| Area | Database state | Status |
| --- | --- | --- |
| Content plan | 60 `content_plan_items` rows | Authoritative |
| Plan distribution | 28 planned, 28 draft created, 3 human review, 1 live | Consistent |
| Execution ledger | 21 jobs, 21 runs, 21 attempts | Authoritative |
| Reconciliation | 5 durable reconciliation rows | Authoritative |
| Runtime gates | active, intake on, automation on, dry-run only, writes off | Authoritative |
| Scheduler | OpenClaw owner; daily 11:00 Europe/London | Active |
| Watchdog | daily 11:15 Europe/London | Active |
| Incidents | 0 open | Healthy |

## File-backed compatibility boundary

The production worker obtains a tenant-scoped database snapshot after claiming
an active lease. The runner writes that snapshot into the private run evidence
directory and renders a Markdown projection for the legacy content pipeline.

In durable database mode, `cron_entrypoint.py` uses
`DATABASE_AUTHORITATIVE_NO_QUEUE_COMMIT`. The worker contract also rejects any
result with `queue_changed=true`. Therefore the checked-in Markdown queue and
its historical backups are not production transaction state.

Legacy queue parsing and mutation modules remain in the repository for older
manual paths. They are not called by the deployed database-owned worker path,
but they should eventually be isolated behind an explicit legacy-only boundary
to reduce operator confusion.

## Remaining Phase 6 product gaps

### 6B — Client identity and read model

- Supabase currently has zero Auth users and zero `client_members` rows.
- There is no tenant-safe `client_dashboard_snapshot` view or equivalent
  redacted read model.
- The dashboard therefore uses safe preview data.

New dashboard objects must use explicit Data API grants because Supabase is
moving to non-exposure by default. Every exposed object must retain RLS or use a
Postgres 15+ `security_invoker` view over RLS-protected tables.

### 6C — Durable client decisions

- There is no approval or change-request table.
- Dashboard approval is deliberately local UI state and cannot enqueue a job.
- A production decision must be version-bound, tenant-bound, authenticated,
  idempotent, and consumed by a narrow backend capability. It must never call
  Shopify directly from the browser.

### 6D — Portable evidence

- The private `orin-evidence` bucket exists, but contains zero objects.
- `run_artifacts` contains zero index rows.
- Detailed evidence is currently durable on the VPS, while the terminal result
  itself is also stored in `runs.final_result`.

Before public rollout, upload checksummed evidence objects and record their
tenant/run-scoped pointers so a VPS loss does not remove the detailed audit
trail.

### 6E — Operational read-model freshness

The scheduler and watchdog receipts for 2026-08-02 are healthy, but
`scheduler_health.last_observed_run_id` and heartbeat fields lag the latest
automatic run. The watchdog or scheduler completion path should refresh this
ledger so the client dashboard does not display stale health information.

## Recommended implementation order

1. Add redacted `security_invoker` dashboard views with explicit
   `authenticated` grants and tenant membership tests.
2. Invite the first HBStore user and create one owner membership through a
   controlled admin path.
3. Connect the dashboard in read-only mode and prove cross-tenant denial.
4. Add a durable, version-bound `content_decisions` table and RLS policies.
5. Keep decisions non-executable until idempotency and authorization tests pass.
6. Upload new run evidence to the private bucket and populate `run_artifacts`.
7. Refresh scheduler health from automatic run/watchdog completion.
8. Run a private HBStore pilot before enabling any approval-to-worker bridge.

## Exit condition

The extended Phase 6 is complete when an authenticated HBStore owner can see
only HBStore's redacted operational data, record an idempotent approval or
change request, retrieve durable evidence after a VPS-independent lookup, and
the dashboard reports current scheduler health. Shopify writes remain a
separate controlled gate.
