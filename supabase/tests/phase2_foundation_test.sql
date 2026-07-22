begin;
create extension if not exists pgtap with schema extensions;
select plan(16);

select has_table('public', 'clients', 'clients table exists');
select has_table('public', 'client_members', 'client_members table exists');
select has_table('public', 'client_runtime_settings', 'runtime settings table exists');
select has_table('public', 'content_jobs', 'durable jobs table exists');
select has_table('public', 'runs', 'runs table exists');
select has_table('public', 'run_artifacts', 'artifact metadata table exists');
select has_table('public', 'incidents', 'incidents table exists');
select has_table('public', 'scheduler_health', 'scheduler health table exists');

select is(
  (
    select count(*)
    from pg_class relation
    join pg_namespace namespace on namespace.oid = relation.relnamespace
    where namespace.nspname = 'public'
      and relation.relname in (
        'clients',
        'client_members',
        'client_runtime_settings',
        'content_jobs',
        'runs',
        'run_artifacts',
        'incidents',
        'scheduler_health'
      )
      and relation.relrowsecurity
  ),
  8::bigint,
  'RLS is enabled on every exposed ORIN table'
);

select ok(
  not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename in (
        'clients',
        'client_members',
        'client_runtime_settings',
        'content_jobs',
        'runs',
        'run_artifacts',
        'incidents',
        'scheduler_health'
      )
      and cmd <> 'SELECT'
      and roles && array['anon', 'authenticated', 'public']::name[]
  ),
  'customer-facing policies remain read-only'
);

select ok(
  (
    select
      not request_intake_enabled
      and not automation_enabled
      and not shopify_writes_enabled
      and max_concurrency = 1
      and allowed_mode = 'dry-run'
    from public.client_runtime_settings
    where client_id = 'hoverboard_store'
  )
  and (
    select state = 'disabled' and scheduler_owner is null
    from public.scheduler_health
    where client_id = 'hoverboard_store'
  ),
  'request intake, automation, Shopify writes, and scheduler ownership start disabled'
);

select ok(
  (select not public from storage.buckets where id = 'orin-evidence'),
  'evidence bucket is private'
);

insert into auth.users (id)
values
  ('11111111-1111-4111-8111-111111111111'),
  ('22222222-2222-4222-8222-222222222222');

insert into public.clients (client_id, display_name, status)
values ('isolation_test_client', 'Isolation Test Client', 'maintenance');

insert into public.client_members (client_id, user_id, role)
values
  ('hoverboard_store', '11111111-1111-4111-8111-111111111111', 'viewer'),
  ('isolation_test_client', '22222222-2222-4222-8222-222222222222', 'viewer');

insert into public.content_jobs (
  client_id,
  source_job_key,
  request_id,
  requested_mode,
  scheduled_for
)
values
  (
    'hoverboard_store',
    'rls-test-hb',
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'dry-run',
    now()
  ),
  (
    'isolation_test_client',
    'rls-test-other',
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    'dry-run',
    now()
  );

select set_config('request.jwt.claim.sub', '11111111-1111-4111-8111-111111111111', true);
set local role authenticated;

select results_eq(
  'select client_id from public.clients order by client_id',
  array['hoverboard_store']::text[],
  'a member sees only their own client'
);

select results_eq(
  'select client_id from public.content_jobs order by client_id',
  array['hoverboard_store']::text[],
  'a member sees only jobs for their own client'
);

select ok(
  not has_table_privilege('authenticated', 'public.content_jobs', 'INSERT'),
  'authenticated users cannot insert jobs directly'
);

select ok(
  not has_table_privilege('authenticated', 'public.runs', 'UPDATE'),
  'authenticated users cannot mutate run evidence'
);

reset role;
select * from finish();
rollback;
