# Database-owned content plan

Phase 6 moves ORIN's SEO article plan from Markdown transaction state into
Supabase. `public.content_plan_items` is authoritative for job identity,
status, due date, Shopify draft identity, and execution ownership.

The existing Markdown queue remains in Git as historical planning material. It
is not read directly by the automatic worker after Phase 6 deployment.

## Execution boundary

1. The existing worker atomically leases a gated `content_jobs` request.
2. `orin_private.get_content_plan_snapshot()` verifies the worker owns that
   unexpired lease.
3. Postgres binds the lowest-numbered due `planned` item to the execution job.
4. The worker receives a versioned, tenant-scoped JSON snapshot.
5. The runner preserves the snapshot and generates a private Markdown
   projection inside the run evidence directory.
6. The proven ORIN content pipeline reads that projection through
   `ORIN_CONTENT_QUEUE_PATH`.

The projection is compatibility input only. It cannot be used to commit state,
and durable runs continue to skip all Markdown queue mutation.

## Security properties

- `content_plan_items` has RLS enabled.
- Authenticated members have tenant-scoped, read-only access.
- `anon`, `orin_api`, and `orin_worker` have no direct table access.
- Only `orin_worker` can execute the private snapshot capability.
- The capability requires the exact active lease owner and uses an empty
  function `search_path`.
- A same-tenant composite foreign key binds execution jobs to plan items.
- A partial unique index prevents two active executions from owning the same
  plan item.
- Run finalization rejects a reported article number that conflicts with its
  database-owned item.
- A verified, reconciled hidden-draft result changes `planned` to
  `draft_created` in the same database transaction as run completion.

No scheduler, credential, network endpoint, public write API, or Shopify-write
permission is created by the Phase 6 migration.

## Initial reconciliation

The migration imports the 30-item Hoverboard Store plan from the checked-in
queue revision
`019511c51f6189b9d79e793d739cc70274b391e36c6566febf2e0d841c11abeb`.

Jobs 28, 29, and 30 are imported as `draft_created`, using their already
verified and reconciled Shopify article IDs from durable run evidence. This
prevents the stale Markdown statuses from making ORIN select or recreate an
article that already exists.

## Verification

Application coverage:

```bash
uvx --from uv==0.11.16 uv run pytest
```

Database coverage:

```bash
npx --yes supabase@2.109.1 test db --local
```

The database test is `supabase/tests/phase6_content_plan_test.sql`. It verifies
RLS, role grants, content ownership, due-item selection, the snapshot contract,
and the reconciled seed state.
