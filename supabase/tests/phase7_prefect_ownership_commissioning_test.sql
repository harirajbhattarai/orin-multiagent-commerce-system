begin;
create extension if not exists pgtap with schema extensions;
select plan(13);

select ok(
  (
    select
      not rolcanlogin
      and not rolsuper
      and not rolcreaterole
      and not rolcreatedb
      and not rolreplication
      and not rolbypassrls
    from pg_roles
    where rolname = 'orin_prefect_scheduler'
  ),
  'Prefect scheduler is a disabled, non-admin role'
);

select ok(
  not has_table_privilege('orin_prefect_scheduler', 'public.content_jobs', 'SELECT')
  and not has_table_privilege('orin_prefect_scheduler', 'public.content_jobs', 'INSERT')
  and not has_table_privilege('orin_prefect_scheduler', 'public.content_jobs', 'UPDATE')
  and not has_table_privilege('orin_prefect_scheduler', 'public.content_jobs', 'DELETE'),
  'Prefect scheduler has no direct content job privileges'
);

select ok(
  has_function_privilege(
    'orin_prefect_scheduler',
    'orin_private.enqueue_hoverboard_prefect_scheduled_job()',
    'EXECUTE'
  ),
  'Prefect scheduler can execute the fixed daily scheduler function'
);

select ok(
  not has_function_privilege(
    'orin_prefect_scheduler',
    'orin_private.get_prefect_shadow_snapshot(text)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_prefect_scheduler',
    'orin_private.enqueue_hoverboard_scheduled_job()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_prefect_scheduler',
    'orin_private.enqueue_hoverboard_prefect_commissioning_job()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_prefect_scheduler',
    'orin_private.claim_next_job(text, integer)',
    'EXECUTE'
  ),
  'Prefect scheduler cannot observe broadly or use production worker capabilities'
);

create temporary table prefect_owner_test_results (
  test_name text primary key,
  passed boolean not null
) on commit drop;
grant insert, select on prefect_owner_test_results to orin_prefect_scheduler;

set local role orin_prefect_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hoverboard_prefect_scheduled_job();
    insert into prefect_owner_test_results values ('maintenance', false);
  exception when insufficient_privilege or check_violation then
    insert into prefect_owner_test_results values ('maintenance', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from prefect_owner_test_results where test_name = 'maintenance'),
  'maintenance gates reject Prefect scheduling'
);

update public.clients
set status = 'active'
where client_id = 'hoverboard_store';

update public.client_runtime_settings
set
  request_intake_enabled = true,
  automation_enabled = true,
  shopify_writes_enabled = false,
  allowed_mode = 'dry-run'
where client_id = 'hoverboard_store';

update public.scheduler_health
set
  scheduler_owner = 'openclaw:orin-hbstore-prod',
  state = 'healthy'
where client_id = 'hoverboard_store';

set local role orin_prefect_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hoverboard_prefect_scheduled_job();
    insert into prefect_owner_test_results values ('wrong_owner', false);
  exception when insufficient_privilege then
    insert into prefect_owner_test_results values ('wrong_owner', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from prefect_owner_test_results where test_name = 'wrong_owner'),
  'OpenClaw ownership cannot authorize the Prefect function'
);

update public.client_runtime_settings
set
  allowed_mode = 'hidden-draft',
  shopify_writes_enabled = true
where client_id = 'hoverboard_store';

update public.scheduler_health
set scheduler_owner = 'prefect:orin-hbstore-prod'
where client_id = 'hoverboard_store';

set local role orin_prefect_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hoverboard_prefect_scheduled_job();
    insert into prefect_owner_test_results values ('not_dry_run', false);
  exception when check_violation then
    insert into prefect_owner_test_results values ('not_dry_run', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from prefect_owner_test_results where test_name = 'not_dry_run'),
  'Prefect scheduling rejects Shopify writes and hidden-draft mode'
);

update public.client_runtime_settings
set
  allowed_mode = 'dry-run',
  shopify_writes_enabled = false
where client_id = 'hoverboard_store';

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
  'test:prefect-owner-active-job',
  '77777777-7777-5777-8777-777777777777',
  null,
  'dry-run',
  'queued',
  now(),
  '{}'::jsonb
);

set local role orin_prefect_scheduler;
do $$
begin
  begin
    perform * from orin_private.enqueue_hoverboard_prefect_scheduled_job();
    insert into prefect_owner_test_results values ('active_queue', false);
  exception when object_not_in_prerequisite_state then
    insert into prefect_owner_test_results values ('active_queue', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from prefect_owner_test_results where test_name = 'active_queue'),
  'Prefect scheduling rejects a non-empty active queue'
);

delete from public.content_jobs
where source_job_key = 'test:prefect-owner-active-job';

create temporary table prefect_owner_jobs_result (
  job_id uuid,
  client_id text,
  request_id uuid,
  requested_mode text,
  job_status text,
  scheduled_for timestamptz,
  created_at timestamptz,
  replayed boolean
) on commit drop;
grant insert, select on prefect_owner_jobs_result to orin_prefect_scheduler;

set local role orin_prefect_scheduler;
insert into prefect_owner_jobs_result
select * from orin_private.enqueue_hoverboard_prefect_scheduled_job();
insert into prefect_owner_jobs_result
select * from orin_private.enqueue_hoverboard_prefect_scheduled_job();
reset role;

select is(
  (select count(*) from prefect_owner_jobs_result),
  2::bigint,
  'two scheduler calls return two acknowledgements'
);

select is(
  (select count(distinct job_id) from prefect_owner_jobs_result),
  1::bigint,
  'scheduler replay resolves to one durable job'
);

select results_eq(
  'select replayed from prefect_owner_jobs_result order by replayed',
  array[false, true],
  'first scheduler call inserts and second replays'
);

select ok(
  (
    select
      requested_by is null
      and requested_mode = 'dry-run'
      and source_job_key ~
        '^scheduler:orin-hbstore-prod:[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      and right(source_job_key, 10)::date =
        (scheduled_for at time zone 'Europe/London')::date
      and payload = '{}'::jsonb
    from public.content_jobs
    where job_id = (select job_id from prefect_owner_jobs_result limit 1)
  ),
  'daily job is fixed, dry-run, system-owned, and payload-free'
);

select ok(
  (
    select request_id = (
      substr(expected_digest, 1, 8) || '-' ||
      substr(expected_digest, 9, 4) || '-' ||
      '5' || substr(expected_digest, 14, 3) || '-' ||
      '8' || substr(expected_digest, 18, 3) || '-' ||
      substr(expected_digest, 21, 12)
    )::uuid
    from public.content_jobs,
    lateral (
      select md5(
        'orin-scheduler-v1:hoverboard_store:' ||
        right(source_job_key, 10)
      ) as expected_digest
    ) digest
    where job_id = (select job_id from prefect_owner_jobs_result limit 1)
  ),
  'Prefect preserves the existing cross-owner daily request identity'
);

select * from finish();
rollback;
