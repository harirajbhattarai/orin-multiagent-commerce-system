begin;
create extension if not exists pgtap with schema extensions;
select plan(10);

select ok(
  (
    select
      not rolcanlogin
      and not rolsuper
      and not rolcreaterole
      and not rolcreatedb
      and not rolbypassrls
    from pg_roles
    where rolname = 'orin_scheduler'
  ),
  'orin_scheduler is a non-login, non-admin, RLS-bound role'
);

select ok(
  not has_table_privilege('orin_scheduler', 'public.content_jobs', 'SELECT')
  and not has_table_privilege('orin_scheduler', 'public.content_jobs', 'INSERT')
  and not has_table_privilege('orin_scheduler', 'public.content_jobs', 'UPDATE')
  and not has_table_privilege('orin_scheduler', 'public.content_jobs', 'DELETE'),
  'orin_scheduler has no direct content job privileges'
);

select ok(
  has_function_privilege(
    'orin_scheduler',
    'orin_private.enqueue_hoverboard_scheduled_job()',
    'EXECUTE'
  ),
  'orin_scheduler can execute only the narrow enqueue boundary'
);

select ok(
  not has_function_privilege(
    'orin_scheduler',
    'orin_private.claim_next_job(text, integer)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_scheduler',
    'orin_private.complete_job(uuid, text, jsonb)',
    'EXECUTE'
  ),
  'orin_scheduler cannot claim or complete worker jobs'
);

create temporary table scheduler_test_results (
  test_name text primary key,
  passed boolean not null
) on commit drop;
grant insert, select on scheduler_test_results to orin_scheduler;

set local role orin_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hoverboard_scheduled_job();
    insert into scheduler_test_results values ('maintenance', false);
  exception when insufficient_privilege or check_violation then
    insert into scheduler_test_results values ('maintenance', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from scheduler_test_results where test_name = 'maintenance'),
  'closed maintenance gates reject scheduled enqueue'
);

update public.clients
set status = 'active'
where client_id = 'hoverboard_store';

update public.client_runtime_settings
set
  request_intake_enabled = true,
  automation_enabled = true,
  shopify_writes_enabled = false,
  allowed_mode = 'hidden-draft'
where client_id = 'hoverboard_store';

update public.scheduler_health
set
  scheduler_owner = 'openclaw:orin-hbstore-prod',
  state = 'healthy',
  last_heartbeat_at = now()
where client_id = 'hoverboard_store';

set local role orin_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hoverboard_scheduled_job();
    insert into scheduler_test_results values ('hidden_write_gate', false);
  exception when insufficient_privilege or check_violation then
    insert into scheduler_test_results values ('hidden_write_gate', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from scheduler_test_results where test_name = 'hidden_write_gate'),
  'hidden-draft enqueue requires the Shopify write gate'
);

update public.client_runtime_settings
set allowed_mode = 'dry-run'
where client_id = 'hoverboard_store';

create temporary table scheduler_jobs_result (
  job_id uuid,
  client_id text,
  request_id uuid,
  requested_mode text,
  job_status text,
  scheduled_for timestamptz,
  created_at timestamptz,
  replayed boolean
) on commit drop;
grant insert, select on scheduler_jobs_result to orin_scheduler;

set local role orin_scheduler;
insert into scheduler_jobs_result
select * from orin_private.enqueue_hoverboard_scheduled_job();
insert into scheduler_jobs_result
select * from orin_private.enqueue_hoverboard_scheduled_job();
reset role;

select is(
  (select count(*) from scheduler_jobs_result),
  2::bigint,
  'two trigger calls return two acknowledgements'
);

select is(
  (
    select count(distinct job_id)
    from scheduler_jobs_result
  ),
  1::bigint,
  'daily trigger replay resolves to one durable job'
);

select results_eq(
  'select replayed from scheduler_jobs_result order by replayed',
  array[false, true],
  'first trigger inserts and second trigger replays'
);

select ok(
  (
    select
      requested_by is null
      and requested_mode = 'dry-run'
      and source_job_key like 'scheduler:orin-hbstore-prod:%'
      and payload ->> 'scheduler_owner' = 'openclaw:orin-hbstore-prod'
      and payload ->> 'schedule' = 'daily-1100-europe-london'
    from public.content_jobs
    where job_id = (select job_id from scheduler_jobs_result limit 1)
  ),
  'scheduled job is system-owned, dry-run, and provenance-bound'
);

select * from finish();
rollback;
