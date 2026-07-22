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
There are no authenticated insert, update, or delete grants in Phase 2. The
future API and worker will use a server-only credential and must still enforce
the same tenant identifier in every operation.

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

## Next integration boundary

Phase 3 adds a narrow authenticated API and a single-concurrency worker. Until
that is implemented and tested, do not place a service-role key in OpenClaw,
the frontend, GitHub, or this repository, and do not enable any scheduler.
