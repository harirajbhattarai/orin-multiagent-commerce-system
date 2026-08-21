begin;
create extension if not exists pgtap with schema extensions;
select plan(17);

select ok(
  (
    select not rolcanlogin and not rolsuper and not rolcreaterole
      and not rolcreatedb and not rolreplication and not rolbypassrls
    from pg_roles where rolname = 'orin_hcs_prefect_scheduler'
  ),
  'HCS Prefect scheduler is a disabled non-admin role'
);

select ok(
  not has_table_privilege('orin_hcs_prefect_scheduler', 'public.content_jobs', 'SELECT')
  and not has_table_privilege('orin_hcs_prefect_scheduler', 'public.content_jobs', 'INSERT')
  and not has_table_privilege('orin_hcs_prefect_scheduler', 'public.content_jobs', 'UPDATE')
  and not has_table_privilege('orin_hcs_prefect_scheduler', 'public.content_jobs', 'DELETE'),
  'HCS Prefect scheduler has no direct job privileges'
);

select ok(
  has_function_privilege(
    'orin_hcs_prefect_scheduler',
    'orin_private.enqueue_hcs_prefect_scheduled_job()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_hcs_prefect_scheduler',
    'orin_private.enqueue_hoverboard_prefect_scheduled_job()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_hcs_prefect_scheduler',
    'orin_private.claim_next_dry_run_job_for_client(text,text,integer)',
    'EXECUTE'
  ),
  'HCS Prefect scheduler can execute only its fixed enqueue boundary'
);

create temporary table hcs_scheduler_test_results (
  test_name text primary key,
  passed boolean not null
) on commit drop;
grant insert, select on hcs_scheduler_test_results to orin_hcs_prefect_scheduler;

-- CI starts from the canonical seed, which intentionally contains only the
-- production HBStore tenant. Create an isolated, fully closed HCS fixture so
-- the scheduler assertions exercise gate behavior rather than missing setup.
insert into public.clients (client_id, display_name, status)
values ('hcs_gadgets', 'HCS Gadgets', 'maintenance');

insert into public.client_runtime_settings (
  client_id,
  request_intake_enabled,
  automation_enabled,
  shopify_writes_enabled,
  approved_draft_writes_enabled,
  max_concurrency,
  allowed_mode
)
values ('hcs_gadgets', false, false, false, false, 1, 'dry-run');

insert into public.scheduler_health (client_id, state, scheduler_owner)
values ('hcs_gadgets', 'disabled', null);

set local role orin_hcs_prefect_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hcs_prefect_scheduled_job();
    insert into hcs_scheduler_test_results values ('maintenance', false);
  exception when insufficient_privilege or check_violation then
    insert into hcs_scheduler_test_results values ('maintenance', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from hcs_scheduler_test_results where test_name = 'maintenance'),
  'maintenance gates reject HCS scheduling'
);

update public.clients set status = 'active' where client_id = 'hcs_gadgets';
update public.client_runtime_settings
set request_intake_enabled = true,
    automation_enabled = true,
    shopify_writes_enabled = false,
    approved_draft_writes_enabled = false,
    max_concurrency = 1,
    allowed_mode = 'dry-run'
where client_id = 'hcs_gadgets';
update public.scheduler_health
set scheduler_owner = 'prefect:orin-hbstore-prod', state = 'healthy'
where client_id = 'hcs_gadgets';

set local role orin_hcs_prefect_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hcs_prefect_scheduled_job();
    insert into hcs_scheduler_test_results values ('wrong_owner', false);
  exception when insufficient_privilege then
    insert into hcs_scheduler_test_results values ('wrong_owner', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from hcs_scheduler_test_results where test_name = 'wrong_owner'),
  'HBStore ownership cannot authorize the HCS scheduler'
);

update public.scheduler_health
set scheduler_owner = 'prefect:orin-hcs-prod'
where client_id = 'hcs_gadgets';
update public.client_runtime_settings
set approved_draft_writes_enabled = true
where client_id = 'hcs_gadgets';

set local role orin_hcs_prefect_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hcs_prefect_scheduled_job();
    insert into hcs_scheduler_test_results values ('approval_gate', false);
  exception when check_violation then
    insert into hcs_scheduler_test_results values ('approval_gate', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from hcs_scheduler_test_results where test_name = 'approval_gate'),
  'approval-draft access cannot coexist with credential-free HCS scheduling'
);

update public.client_runtime_settings
set approved_draft_writes_enabled = false
where client_id = 'hcs_gadgets';
delete from public.content_jobs
where client_id = 'hcs_gadgets' and status in ('queued', 'leased', 'running');
insert into public.content_jobs (
  client_id, source_job_key, request_id, requested_by, requested_mode,
  status, scheduled_for, payload
) values (
  'hcs_gadgets', 'test:hcs-prefect-active-job',
  '77777777-7777-5777-8777-777777777777', null, 'dry-run',
  'queued', now(), '{}'::jsonb
);

set local role orin_hcs_prefect_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hcs_prefect_scheduled_job();
    insert into hcs_scheduler_test_results values ('active_queue', false);
  exception when object_not_in_prerequisite_state then
    insert into hcs_scheduler_test_results values ('active_queue', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from hcs_scheduler_test_results where test_name = 'active_queue'),
  'HCS scheduling rejects a non-empty active queue'
);

delete from public.content_jobs where source_job_key = 'test:hcs-prefect-active-job';
create temporary table hcs_scheduler_jobs_result (
  job_id uuid, client_id text, request_id uuid, requested_mode text,
  job_status text, scheduled_for timestamptz, created_at timestamptz,
  replayed boolean
) on commit drop;
grant insert, select on hcs_scheduler_jobs_result to orin_hcs_prefect_scheduler;

set local role orin_hcs_prefect_scheduler;
insert into hcs_scheduler_jobs_result
select * from orin_private.enqueue_hcs_prefect_scheduled_job();
insert into hcs_scheduler_jobs_result
select * from orin_private.enqueue_hcs_prefect_scheduled_job();
reset role;

select is(
  (select count(*) from hcs_scheduler_jobs_result), 2::bigint,
  'two HCS scheduler calls return two acknowledgements'
);
select is(
  (select count(distinct job_id) from hcs_scheduler_jobs_result), 1::bigint,
  'HCS scheduler replay resolves to one durable job'
);
select results_eq(
  'select replayed from hcs_scheduler_jobs_result order by replayed',
  array[false, true],
  'first HCS scheduler call inserts and second replays'
);
select ok(
  (
    select requested_by is null and requested_mode = 'dry-run'
      and source_job_key ~ '^scheduler:orin-hcs-prod:[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      and payload = '{}'::jsonb
    from public.content_jobs
    where job_id = (select job_id from hcs_scheduler_jobs_result limit 1)
  ),
  'HCS daily job is fixed, dry-run, system-owned, and payload-free'
);

select ok(
  (
    select not rolcanlogin and not rolsuper and not rolcreaterole
      and not rolcreatedb and not rolreplication and not rolbypassrls
    from pg_roles where rolname = 'orin_hcs_watchdog'
  ),
  'HCS watchdog is a disabled non-admin RLS role'
);
select ok(
  has_column_privilege(
    'orin_hcs_watchdog', 'public.client_runtime_settings',
    'approved_draft_writes_enabled', 'SELECT'
  )
  and has_column_privilege(
    'orin_hcs_watchdog', 'public.content_jobs', 'source_job_key', 'SELECT'
  )
  and has_column_privilege(
    'orin_hcs_watchdog', 'public.runs', 'reconciliation_status', 'SELECT'
  ),
  'HCS watchdog can read only required safety and receipt columns'
);
select ok(
  not has_table_privilege('orin_hcs_watchdog', 'public.content_jobs', 'INSERT')
  and not has_table_privilege('orin_hcs_watchdog', 'public.content_jobs', 'UPDATE')
  and not has_table_privilege('orin_hcs_watchdog', 'public.runs', 'INSERT')
  and not has_table_privilege('orin_hcs_watchdog', 'public.incidents', 'SELECT')
  and not has_function_privilege(
    'orin_hcs_watchdog', 'orin_private.enqueue_hcs_prefect_scheduled_job()', 'EXECUTE'
  ),
  'HCS watchdog cannot mutate, enqueue, or inspect incidents'
);

set local role orin_hcs_watchdog;
select count(*) as visible_client_count from public.clients \gset hcs_watchdog_
select count(*) as hbstore_count from public.clients
where client_id = 'hoverboard_store' \gset hcs_watchdog_
select count(*) as hcs_count from public.clients
where client_id = 'hcs_gadgets' \gset hcs_watchdog_
reset role;

select is(
  :'hcs_watchdog_visible_client_count'::bigint, 1::bigint,
  'RLS exposes exactly one tenant to the HCS watchdog'
);
select is(
  :'hcs_watchdog_hbstore_count'::bigint, 0::bigint,
  'RLS hides Hoverboard Store from the HCS watchdog'
);
select is(
  :'hcs_watchdog_hcs_count'::bigint, 1::bigint,
  'RLS exposes HCS Gadgets to its watchdog'
);

select * from finish();
rollback;
