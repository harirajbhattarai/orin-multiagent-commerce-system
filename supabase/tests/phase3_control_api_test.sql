begin;
create extension if not exists pgtap with schema extensions;
select plan(9);

select ok(
  (
    select
      not rolcanlogin
      and not rolsuper
      and not rolcreaterole
      and not rolcreatedb
      and not rolbypassrls
    from pg_roles
    where rolname = 'orin_api'
  ),
  'orin_api is a non-login, non-admin, RLS-bound role'
);

select ok(
  (
    select not request_intake_enabled
    from public.client_runtime_settings
    where client_id = 'hoverboard_store'
  ),
  'request intake starts disabled'
);

select ok(
  not has_table_privilege('orin_api', 'public.content_jobs', 'UPDATE')
  and not has_table_privilege('orin_api', 'public.content_jobs', 'DELETE'),
  'orin_api cannot update or delete jobs'
);

select ok(
  not has_table_privilege('orin_api', 'public.runs', 'SELECT'),
  'orin_api cannot read run evidence'
);

select ok(
  has_column_privilege('orin_api', 'public.content_jobs', 'client_id', 'INSERT')
  and has_column_privilege('orin_api', 'public.content_jobs', 'requested_by', 'INSERT')
  and not has_column_privilege('orin_api', 'public.content_jobs', 'job_id', 'INSERT')
  and not has_column_privilege('orin_api', 'public.content_jobs', 'lock_owner', 'INSERT'),
  'orin_api has only the intended job insert columns'
);

create temporary table api_role_test_results (
  test_name text primary key,
  passed boolean not null
) on commit drop;
grant insert, select on api_role_test_results to orin_api;

insert into auth.users (id)
values ('33333333-3333-4333-8333-333333333333');

insert into public.client_members (client_id, user_id, role)
values (
  'hoverboard_store',
  '33333333-3333-4333-8333-333333333333',
  'operator'
);

set local role orin_api;

do $$
begin
  begin
    insert into public.content_jobs (
      client_id,
      source_job_key,
      request_id,
      requested_by,
      requested_mode,
      status,
      scheduled_for,
      payload
    )
    values (
      'hoverboard_store',
      'api:11111111-1111-4111-8111-111111111111',
      '11111111-1111-4111-8111-111111111111',
      '33333333-3333-4333-8333-333333333333',
      'dry-run',
      'queued',
      now(),
      '{}'::jsonb
    );
    insert into api_role_test_results values ('disabled_intake', false);
  exception when insufficient_privilege or check_violation then
    insert into api_role_test_results values ('disabled_intake', true);
  end;
end;
$$;

reset role;

select ok(
  (select passed from api_role_test_results where test_name = 'disabled_intake'),
  'database policy blocks API insertion during maintenance'
);

update public.clients
set status = 'active'
where client_id = 'hoverboard_store';

update public.client_runtime_settings
set request_intake_enabled = true
where client_id = 'hoverboard_store';

set local role orin_api;

insert into public.content_jobs (
  client_id,
  source_job_key,
  request_id,
  requested_by,
  requested_mode,
  status,
  scheduled_for,
  payload
)
values (
  'hoverboard_store',
  'api:22222222-2222-4222-8222-222222222222',
  '22222222-2222-4222-8222-222222222222',
  '33333333-3333-4333-8333-333333333333',
  'dry-run',
  'queued',
  now(),
  '{}'::jsonb
);

do $$
begin
  begin
    insert into public.content_jobs (
      client_id,
      source_job_key,
      request_id,
      requested_by,
      requested_mode,
      status,
      scheduled_for,
      payload
    )
    values (
      'hoverboard_store',
      'api:44444444-4444-4444-8444-444444444444',
      '44444444-4444-4444-8444-444444444444',
      '33333333-3333-4333-8333-333333333333',
      'hidden-draft',
      'queued',
      now(),
      '{}'::jsonb
    );
    insert into api_role_test_results values ('hidden_draft', false);
  exception when insufficient_privilege or check_violation then
    insert into api_role_test_results values ('hidden_draft', true);
  end;
end;
$$;

reset role;

select is(
  (
    select count(*)
    from public.content_jobs
    where request_id = '22222222-2222-4222-8222-222222222222'
  ),
  1::bigint,
  'operator dry-run request is inserted exactly once when intake is enabled'
);

select is(
  (
    select requested_by
    from public.content_jobs
    where request_id = '22222222-2222-4222-8222-222222222222'
  ),
  '33333333-3333-4333-8333-333333333333'::uuid,
  'job records the authenticated requester'
);

select ok(
  (select passed from api_role_test_results where test_name = 'hidden_draft'),
  'database policy rejects hidden-draft API insertion'
);

select * from finish();
rollback;
