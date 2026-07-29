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
      and not rolreplication
      and not rolbypassrls
    from pg_roles
    where rolname = 'orin_watchdog'
  ),
  'orin_watchdog is a non-login, non-admin, RLS-bound role'
);

select ok(
  has_column_privilege('orin_watchdog', 'public.clients', 'client_id', 'SELECT')
  and has_column_privilege('orin_watchdog', 'public.clients', 'status', 'SELECT')
  and has_column_privilege(
    'orin_watchdog',
    'public.scheduler_health',
    'last_observed_run_id',
    'SELECT'
  ),
  'orin_watchdog can read only the required client and scheduler columns'
);

select ok(
  has_column_privilege(
    'orin_watchdog',
    'public.content_jobs',
    'source_job_key',
    'SELECT'
  )
  and has_column_privilege('orin_watchdog', 'public.runs', 'run_id', 'SELECT')
  and has_column_privilege(
    'orin_watchdog',
    'public.runs',
    'reconciliation_status',
    'SELECT'
  ),
  'orin_watchdog can read the required job and run receipt columns'
);

select ok(
  not has_table_privilege('orin_watchdog', 'public.content_jobs', 'INSERT')
  and not has_table_privilege('orin_watchdog', 'public.content_jobs', 'UPDATE')
  and not has_table_privilege('orin_watchdog', 'public.content_jobs', 'DELETE')
  and not has_table_privilege('orin_watchdog', 'public.runs', 'INSERT')
  and not has_table_privilege('orin_watchdog', 'public.runs', 'UPDATE')
  and not has_table_privilege('orin_watchdog', 'public.runs', 'DELETE'),
  'orin_watchdog cannot mutate jobs or runs'
);

select ok(
  not has_table_privilege('orin_watchdog', 'public.incidents', 'SELECT')
  and not has_table_privilege('orin_watchdog', 'public.run_artifacts', 'SELECT')
  and not has_table_privilege('orin_watchdog', 'public.client_members', 'SELECT'),
  'orin_watchdog cannot read users, incidents, or artifact metadata'
);

select ok(
  not has_function_privilege(
    'orin_watchdog',
    'orin_private.enqueue_hoverboard_scheduled_job()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_watchdog',
    'orin_private.claim_next_job(text, integer)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_watchdog',
    'orin_private.complete_job(uuid, text, jsonb)',
    'EXECUTE'
  ),
  'orin_watchdog cannot trigger, claim, or complete work'
);

insert into public.clients (client_id, display_name, status)
values ('watchdog_isolation', 'Watchdog Isolation', 'active');

insert into public.client_runtime_settings (
  client_id,
  request_intake_enabled,
  automation_enabled,
  shopify_writes_enabled,
  max_concurrency,
  allowed_mode
)
values ('watchdog_isolation', true, true, false, 1, 'dry-run');

insert into public.scheduler_health (client_id, state, scheduler_owner)
values ('watchdog_isolation', 'healthy', 'unapproved-owner');

set local role orin_watchdog;

select count(*) as visible_client_count
from public.clients
\gset watchdog_

select count(*) as isolated_client_count
from public.clients
where client_id = 'watchdog_isolation'
\gset watchdog_

select count(*) as hbstore_scheduler_count
from public.scheduler_health
where client_id = 'hoverboard_store'
\gset watchdog_

reset role;

select is(
  :'watchdog_visible_client_count'::bigint,
  1::bigint,
  'RLS exposes only Hoverboard Store to orin_watchdog'
);

select is(
  :'watchdog_isolated_client_count'::bigint,
  0::bigint,
  'RLS hides all other clients from orin_watchdog'
);

select is(
  :'watchdog_hbstore_scheduler_count'::bigint,
  1::bigint,
  'orin_watchdog can observe the fixed HBStore scheduler row'
);

select * from finish();
rollback;
