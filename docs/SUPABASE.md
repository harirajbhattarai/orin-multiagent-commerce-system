# Supabase foundation

ORIN uses one dedicated development project:

- Project: `orinclaw-dev`
- Project reference: `hgbpfkrenxfezaztwlkp`
- Region: `eu-central-1`
- PostgreSQL: 17

The project reference is not a credential. Never commit database passwords,
secret/service-role keys, access tokens, or Shopify credentials.

## Schema ownership

`supabase/migrations` is the only database schema history. Do not introduce a
second Alembic migration history. Create new migrations with the pinned CLI
pattern used during Phase 2:

```bash
npx --yes supabase@2.109.1 migration new descriptive_name
```

Review and test migrations against development before any future production
project exists. Do not edit an already-applied migration; add a new one.

## Phase 2 data model

- `clients`: tenant identity and maintenance state.
- `client_members`: Supabase Auth user-to-client membership.
- `client_runtime_settings`: automation, write, and concurrency gates.
- `content_jobs`: durable jobs, request uniqueness, and lease fields.
- `runs`: authoritative idempotent final-result records.
- `run_artifacts`: checksummed pointers to private evidence objects.
- `incidents`: operational failures and reconciliation issues.
- `scheduler_health`: the single scheduler owner and heartbeat state.

The `orin-evidence` Storage bucket is private. Object keys must use:

```text
<client_id>/<run_id>/<artifact_name>
```

Authenticated customer access is read-only and limited by `client_members`.
There are no authenticated insert, update, or delete grants. The API and worker
use separate backend-only roles and must still enforce the same tenant
identifier in every operation.

## Initial safety state

`hoverboard_store` starts with:

- client status `maintenance`
- automation disabled
- Shopify writes disabled
- allowed mode `dry-run`
- maximum concurrency `1`
- scheduler state `disabled`
- no scheduler owner

The database has no Cron extension, webhook, queue consumer, or job. Creating
tables does not authorize execution.

## Verification

The versioned pgTAP suite is:

```text
supabase/tests/phase2_foundation_test.sql
```

With a local Supabase stack running:

```bash
npx --yes supabase@2.109.1 start
npx --yes supabase@2.109.1 test db --local
```

After every remote DDL change, run both Supabase security and performance
advisors. New empty indexes can appear as unused; missing RLS policies, mutable
function search paths, public security-definer functions, and unindexed foreign
keys are release blockers.

## Current integration boundary

Phase 3A adds the narrow authenticated request API and the `orin_api` database
role. The role intentionally remains `NOLOGIN`, and request intake remains
disabled, until credential provisioning and a controlled API integration test
are approved. See `docs/CONTROL_API.md`.

Phase 3B adds the `orin_worker` role and stored functions for atomic claim,
renewal, and idempotent completion. The role has no table privileges and
remains `NOLOGIN`. Claims are possible only when the client and automation gate
are active, Shopify writes are disabled, and the job is an empty `dry-run`.
The unique active-job index is the database-level concurrency-one backstop.

Do not place a database password or service-role key in OpenClaw, the frontend,
GitHub, or this repository, and do not enable any scheduler. See
`docs/WORKER.md`.

## Phase 6 authoritative content plan

`content_plan_items` replaces the Markdown SEO queue as operational truth. The
automatic worker obtains a tenant-scoped snapshot only after proving ownership
of an active database lease. The runner stores that snapshot as private evidence
and renders a read-only Markdown compatibility projection for the existing
content pipeline.

Authenticated members may read only their tenant's plan. They cannot mutate it.
The API and worker roles have no direct table privileges, and Shopify writes are
not enabled by this migration. See `docs/CONTENT_PLAN.md`.

## Phase 6 client-product boundary

`client_dashboard_snapshot` is a redacted `security_invoker` projection over
RLS-protected tenant data. Broad customer table grants are removed; authenticated
users receive only the columns required by the projection. Raw runner JSON,
local artifact paths, and the execution queue are not customer-readable.

`content_decisions` is an immutable owner/operator ledger. Inserts are bound to
`auth.uid()`, the current content item version, tenant membership, and a unique
request ID. A decision cannot enqueue a job or invoke Shopify.

Scheduler health is refreshed in the same database transaction that inserts a
scheduler-owned run. The watchdog remains read-only. Portable evidence is
uploaded separately by the isolated one-shot sync described in
`docs/PHASE6_CLIENT_PRODUCT.md`.
