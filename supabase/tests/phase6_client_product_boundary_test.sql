begin;
create extension if not exists pgtap with schema extensions;
select plan(20);

select has_table('public', 'content_decisions', 'decision ledger exists');

select ok(
  (select relrowsecurity from pg_class where oid = 'public.content_decisions'::regclass),
  'decision ledger has RLS enabled'
);

select ok(
  has_table_privilege('authenticated', 'public.content_decisions', 'SELECT')
  and has_table_privilege('authenticated', 'public.content_decisions', 'INSERT')
  and not has_table_privilege('authenticated', 'public.content_decisions', 'UPDATE')
  and not has_table_privilege('authenticated', 'public.content_decisions', 'DELETE'),
  'authenticated clients can only read and append decisions'
);

select has_view(
  'public',
  'client_dashboard_snapshot',
  'redacted dashboard view exists'
);

select ok(
  coalesce(
    (select reloptions @> array['security_invoker=true']
     from pg_class
     where oid = 'public.client_dashboard_snapshot'::regclass),
    false
  ),
  'dashboard view is security invoker'
);

select ok(
  has_table_privilege('authenticated', 'public.client_dashboard_snapshot', 'SELECT')
  and not has_table_privilege('anon', 'public.client_dashboard_snapshot', 'SELECT'),
  'dashboard is authenticated-only'
);

select ok(
  not has_column_privilege('authenticated', 'public.runs', 'final_result', 'SELECT')
  and not has_column_privilege('authenticated', 'public.runs', 'artifact_prefix', 'SELECT')
  and has_column_privilege('authenticated', 'public.runs', 'run_id', 'SELECT'),
  'raw runner payload and local path are not customer-readable'
);

select ok(
  not has_table_privilege('authenticated', 'public.content_jobs', 'SELECT'),
  'raw execution queue is not customer-readable'
);

select ok(
  has_column_privilege(
    'authenticated',
    'public.client_runtime_settings',
    'approved_draft_writes_enabled',
    'SELECT'
  )
  and not has_table_privilege(
    'authenticated',
    'public.client_runtime_settings',
    'UPDATE'
  ),
  'dashboard members can observe but never change the approval-only capability'
);

insert into auth.users (id)
values
  ('44444444-4444-4444-8444-444444444444'),
  ('55555555-5555-4555-8555-555555555555'),
  ('66666666-6666-4666-8666-666666666666');

insert into public.client_members (client_id, user_id, role)
values
  ('hoverboard_store', '44444444-4444-4444-8444-444444444444', 'operator'),
  ('hoverboard_store', '55555555-5555-4555-8555-555555555555', 'viewer');

create temporary table phase6_job_count_before as
select count(*)::bigint as value from public.content_jobs;

insert into public.content_plan_items (
  content_item_id, client_id, item_number, target_date, cluster, decision,
  status, topic, target_keyword, draft_path, source_document, source_revision
) values (
  'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', 'hoverboard_store', 999,
  '2026-12-31', 'Test', 'create_new', 'planned', 'Phase 6 test concept',
  'phase 6 test concept',
  'clients/hoverboard_store/content_engine/drafts/phase-6-test-concept.html',
  'supabase-test', repeat('e', 64)
);

select set_config('request.jwt.claim.sub', '44444444-4444-4444-8444-444444444444', true);
set local role authenticated;

select is(
  (select count(*) from public.client_dashboard_snapshot),
  1::bigint,
  'member receives only their dashboard tenant'
);

select is(
  (select snapshot ->> 'schema' from public.client_dashboard_snapshot),
  'orin.client-dashboard/v1',
  'dashboard contract is versioned'
);

select is(
  (select snapshot #>> '{client,id}' from public.client_dashboard_snapshot),
  'hoverboard_store',
  'dashboard payload is bound to the member tenant'
);

reset role;
update public.clients
set status = 'active'
where client_id = 'hoverboard_store';
update public.client_runtime_settings
set request_intake_enabled = true,
    automation_enabled = true,
    shopify_writes_enabled = false,
    approved_draft_writes_enabled = false,
    allowed_mode = 'dry-run'
where client_id = 'hoverboard_store';
set local role authenticated;

insert into public.content_decisions (
  client_id,
  content_item_id,
  content_item_version,
  decision,
  note,
  requested_by,
  request_id
)
select
  item.client_id,
  item.content_item_id,
  item.version,
  'approve_concept',
  '',
  '66666666-6666-4666-8666-666666666666',
  '77777777-7777-4777-8777-777777777777'
from public.content_plan_items item
where item.client_id = 'hoverboard_store'
  and item.status = 'planned'
order by item.item_number
limit 1;

select is(
  (select requested_by from public.content_decisions where request_id = '77777777-7777-4777-8777-777777777777'),
  '44444444-4444-4444-8444-444444444444'::uuid,
  'trigger binds the decision actor to auth.uid instead of client input'
);

reset role;
select is(
  (select count(*)::bigint from public.content_jobs),
  (select value from phase6_job_count_before),
  'recording a decision does not enqueue execution work'
);
select set_config('request.jwt.claim.sub', '44444444-4444-4444-8444-444444444444', true);
set local role authenticated;

select throws_ok(
  $$
    insert into public.content_decisions (
      client_id, content_item_id, content_item_version, decision,
      requested_by, request_id
    )
    select client_id, content_item_id, version + 1, 'approve_concept',
           '44444444-4444-4444-8444-444444444444',
           '88888888-8888-4888-8888-888888888888'
    from public.content_plan_items
    where client_id = 'hoverboard_store'
      and status = 'planned'
    order by item_number
    limit 1
  $$,
  '40001',
  'content item version changed; refresh before deciding',
  'stale content decisions fail closed'
);

select throws_ok(
  $$
    insert into public.content_decisions (
      client_id, content_item_id, content_item_version, decision,
      requested_by, request_id
    )
    select client_id, content_item_id, version, 'approve_concept',
           '44444444-4444-4444-8444-444444444444',
           '77777777-7777-4777-8777-777777777777'
    from public.content_plan_items
    where client_id = 'hoverboard_store'
      and status = 'planned'
    order by item_number
    limit 1
  $$,
  '23505',
  null,
  'request IDs are idempotency keys'
);

reset role;
select set_config('request.jwt.claim.sub', '55555555-5555-4555-8555-555555555555', true);
set local role authenticated;

select throws_ok(
  $$
    insert into public.content_decisions (
      client_id, content_item_id, content_item_version, decision,
      note, requested_by, request_id
    )
    select client_id, content_item_id, version, 'request_changes',
           'viewer attempt', '55555555-5555-4555-8555-555555555555',
           '99999999-9999-4999-8999-999999999999'
    from public.content_plan_items
    where client_id = 'hoverboard_store'
    order by item_number
    limit 1
  $$,
  '42501',
  'client operator membership required',
  'viewers cannot append decisions'
);

reset role;
select set_config('request.jwt.claim.sub', '66666666-6666-4666-8666-666666666666', true);
set local role authenticated;

select is(
  (select count(*) from public.client_dashboard_snapshot),
  0::bigint,
  'a nonmember cannot read another client dashboard'
);

reset role;

select ok(
  exists (
    select 1
    from pg_trigger
    where tgrelid = 'public.runs'::regclass
      and tgname = 'runs_refresh_scheduler_health'
      and not tgisinternal
  ),
  'scheduler health refresh is bound to durable run insertion'
);

select ok(
  not has_function_privilege(
    'authenticated',
    'orin_private.refresh_scheduler_health_from_run()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_watchdog',
    'orin_private.refresh_scheduler_health_from_run()',
    'EXECUTE'
  ),
  'dashboard users and watchdog cannot invoke scheduler health writes'
);

select * from finish();
rollback;
