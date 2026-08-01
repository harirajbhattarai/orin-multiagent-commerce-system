begin;
create extension if not exists pgtap with schema extensions;
select plan(14);

select has_table(
  'public',
  'content_plan_items',
  'authoritative content-plan table exists'
);

select ok(
  (
    select relrowsecurity
    from pg_class
    where oid = 'public.content_plan_items'::regclass
  ),
  'content-plan RLS is enabled'
);

select ok(
  has_table_privilege('authenticated', 'public.content_plan_items', 'SELECT')
  and not has_table_privilege('authenticated', 'public.content_plan_items', 'INSERT')
  and not has_table_privilege('authenticated', 'public.content_plan_items', 'UPDATE')
  and not has_table_privilege('authenticated', 'public.content_plan_items', 'DELETE'),
  'customers have read-only content-plan access'
);

select ok(
  not has_table_privilege('orin_worker', 'public.content_plan_items', 'SELECT')
  and not has_table_privilege('orin_worker', 'public.content_plan_items', 'INSERT')
  and not has_table_privilege('orin_worker', 'public.content_plan_items', 'UPDATE')
  and not has_table_privilege('orin_worker', 'public.content_plan_items', 'DELETE'),
  'worker has no direct content-plan table privileges'
);

select ok(
  has_function_privilege(
    'orin_worker',
    'orin_private.get_content_plan_snapshot(uuid,text)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated',
    'orin_private.get_content_plan_snapshot(uuid,text)',
    'EXECUTE'
  ),
  'only the worker capability can request a bound plan snapshot'
);

select ok(
  exists (
    select 1
    from pg_constraint
    where conrelid = 'public.content_jobs'::regclass
      and conname = 'content_jobs_content_plan_item_fkey'
  ),
  'execution jobs bind to a same-tenant content item'
);

select ok(
  exists (
    select 1
    from pg_indexes
    where schemaname = 'public'
      and tablename = 'content_jobs'
      and indexname = 'content_jobs_one_active_plan_item_idx'
  ),
  'one active execution owns a content item at a time'
);

select is(
  (
    select count(*)
    from public.content_plan_items
    where client_id = 'hoverboard_store'
  ),
  30::bigint,
  'the legacy plan is imported once'
);

select ok(
  (
    select
      status = 'draft_created'
      and shopify_article_id = '1007164260700'
    from public.content_plan_items
    where client_id = 'hoverboard_store' and item_number = 28
  )
  and (
    select
      status = 'draft_created'
      and shopify_article_id = '1007195390300'
    from public.content_plan_items
    where client_id = 'hoverboard_store' and item_number = 29
  )
  and (
    select
      status = 'draft_created'
      and shopify_article_id = '1007206334812'
    from public.content_plan_items
    where client_id = 'hoverboard_store' and item_number = 30
  ),
  'known Shopify drafts override stale Markdown statuses during import'
);

insert into public.content_plan_items (
  client_id,
  item_number,
  target_date,
  cluster,
  decision,
  status,
  topic,
  target_keyword,
  draft_path,
  source_document,
  source_revision
) values (
  'hoverboard_store',
  31,
  current_date,
  'Test',
  'create_new',
  'planned',
  'Phase 6 test article',
  'phase 6 test article',
  'clients/hoverboard_store/content_engine/drafts/phase-6-test.html',
  'supabase/tests/phase6_content_plan_test.sql',
  repeat('a', 64)
);

insert into public.content_jobs (
  client_id,
  source_job_key,
  request_id,
  requested_mode,
  scheduled_for,
  payload
) values (
  'hoverboard_store',
  'phase6-content-plan-test',
  '66666666-6666-4666-8666-666666666666',
  'dry-run',
  now(),
  '{}'::jsonb
);

update public.clients
set status = 'active'
where client_id = 'hoverboard_store';

update public.client_runtime_settings
set automation_enabled = true,
    shopify_writes_enabled = false,
    allowed_mode = 'dry-run'
where client_id = 'hoverboard_store';

create temporary table phase6_claim (
  job_id uuid,
  client_id text,
  request_id uuid,
  requested_mode text,
  attempt_count smallint,
  payload jsonb,
  lease_expires_at timestamptz
) on commit drop;
create temporary table phase6_snapshot (snapshot jsonb) on commit drop;
grant insert, select on phase6_claim, phase6_snapshot to orin_worker;

set local role orin_worker;
insert into phase6_claim
select * from orin_private.claim_next_job('worker:phase6:test', 1200);
insert into phase6_snapshot
select orin_private.get_content_plan_snapshot(
  (select job_id from phase6_claim limit 1),
  'worker:phase6:test'
);
reset role;

select is(
  (select snapshot ->> 'schema' from phase6_snapshot),
  'orin.content-plan-snapshot/v1',
  'worker receives the versioned snapshot contract'
);

select is(
  (select (snapshot ->> 'selected_item_number')::integer from phase6_snapshot),
  31,
  'database selects the lowest-numbered due planned item'
);

select is(
  (select jsonb_array_length(snapshot -> 'items') from phase6_snapshot),
  31,
  'snapshot contains the complete client plan'
);

select ok(
  (
    select content_plan_item_id is not null
    from public.content_jobs
    where request_id = '66666666-6666-4666-8666-666666666666'
  ),
  'snapshot binding durably records content ownership on the execution job'
);

insert into auth.users (id)
values ('33333333-3333-4333-8333-333333333333');
insert into public.client_members (client_id, user_id, role)
values (
  'hoverboard_store',
  '33333333-3333-4333-8333-333333333333',
  'viewer'
);

select set_config(
  'request.jwt.claim.sub',
  '33333333-3333-4333-8333-333333333333',
  true
);
set local role authenticated;
select is(
  (select count(*) from public.content_plan_items),
  31::bigint,
  'member can read only their tenant content plan'
);
reset role;

select * from finish();
rollback;
