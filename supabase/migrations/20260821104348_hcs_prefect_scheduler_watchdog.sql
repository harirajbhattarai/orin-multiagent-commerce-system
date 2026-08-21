-- HCS recurring dry-run scheduling and read-only observation boundaries.
-- Both roles remain NOLOGIN after migration. Credentials, workers, and
-- schedules are commissioned separately and no Shopify write gate is opened.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_hcs_prefect_scheduler') then
    create role orin_hcs_prefect_scheduler nologin noinherit nosuperuser
      nocreaterole nocreatedb noreplication nobypassrls;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'orin_hcs_watchdog') then
    create role orin_hcs_watchdog nologin noinherit nosuperuser
      nocreaterole nocreatedb noreplication nobypassrls;
  end if;
end;
$$;

alter role orin_hcs_prefect_scheduler nologin noinherit nocreaterole nocreatedb;
alter role orin_hcs_watchdog nologin noinherit nocreaterole nocreatedb;

do $$
declare
  v_role text;
begin
  foreach v_role in array array['orin_hcs_prefect_scheduler', 'orin_hcs_watchdog'] loop
    if exists (
      select 1 from pg_roles where rolname = v_role
        and (rolsuper or rolcreaterole or rolcreatedb or rolreplication or rolbypassrls)
    ) then
      raise exception '% has prohibited privileged attributes', v_role
        using errcode = '42501';
    end if;
  end loop;
end;
$$;

revoke all on schema public from orin_hcs_prefect_scheduler, orin_hcs_watchdog;
revoke all on schema orin_private from orin_hcs_prefect_scheduler, orin_hcs_watchdog;
revoke all on all tables in schema public from orin_hcs_prefect_scheduler, orin_hcs_watchdog;
revoke all on all sequences in schema public from orin_hcs_prefect_scheduler, orin_hcs_watchdog;
revoke all on all functions in schema public from orin_hcs_prefect_scheduler, orin_hcs_watchdog;
revoke all on all functions in schema orin_private from orin_hcs_prefect_scheduler, orin_hcs_watchdog;

grant usage on schema orin_private to orin_hcs_prefect_scheduler;

create or replace function orin_private.enqueue_hcs_prefect_scheduled_job()
returns table (
  job_id uuid,
  client_id text,
  request_id uuid,
  requested_mode text,
  job_status text,
  scheduled_for timestamptz,
  created_at timestamptz,
  replayed boolean
)
language plpgsql
security definer
set search_path = ''
set statement_timeout = '5s'
as $$
declare
  v_client_id constant text := 'hcs_gadgets';
  v_scheduler_owner constant text := 'prefect:orin-hcs-prod';
  v_schedule_date date := (clock_timestamp() at time zone 'Europe/London')::date;
  v_source_job_key text := 'scheduler:orin-hcs-prod:' || v_schedule_date::text;
  v_digest text := md5('orin-hcs-scheduler-v1:' || v_client_id || ':' || v_schedule_date::text);
  v_request_id uuid := (
    substr(v_digest, 1, 8) || '-' || substr(v_digest, 9, 4) || '-' ||
    '5' || substr(v_digest, 14, 3) || '-' ||
    '8' || substr(v_digest, 18, 3) || '-' || substr(v_digest, 21, 12)
  )::uuid;
  v_access record;
  v_job public.content_jobs%rowtype;
  v_inserted boolean := false;
  v_active_jobs integer;
begin
  perform pg_advisory_xact_lock(hashtext(v_source_job_key));

  select client.status as client_status,
         settings.request_intake_enabled,
         settings.automation_enabled,
         settings.shopify_writes_enabled,
         settings.approved_draft_writes_enabled,
         settings.max_concurrency,
         settings.allowed_mode,
         health.state as scheduler_state,
         health.scheduler_owner
  into v_access
  from public.clients client
  join public.client_runtime_settings settings using (client_id)
  join public.scheduler_health health using (client_id)
  where client.client_id = v_client_id;

  if not found then
    raise exception 'HCS Prefect scheduler configuration is missing' using errcode = 'P0002';
  end if;
  if v_access.client_status <> 'active'
     or not v_access.request_intake_enabled
     or not v_access.automation_enabled then
    raise exception 'HCS Prefect scheduler gates are closed' using errcode = '42501';
  end if;
  if v_access.scheduler_state <> 'healthy'
     or v_access.scheduler_owner <> v_scheduler_owner then
    raise exception 'HCS Prefect scheduler ownership is not active' using errcode = '42501';
  end if;
  if v_access.max_concurrency <> 1
     or v_access.allowed_mode <> 'dry-run'
     or v_access.shopify_writes_enabled
     or v_access.approved_draft_writes_enabled then
    raise exception 'HCS Prefect scheduling is credential-free dry-run-only'
      using errcode = '23514';
  end if;

  select existing.* into v_job
  from public.content_jobs existing
  where existing.client_id = v_client_id
    and (existing.source_job_key = v_source_job_key or existing.request_id = v_request_id)
  limit 1;

  if found then
    if v_job.source_job_key <> v_source_job_key
       or v_job.request_id <> v_request_id
       or v_job.requested_mode <> 'dry-run'
       or v_job.payload <> '{}'::jsonb then
      raise exception 'HCS Prefect scheduled request identity conflict' using errcode = '23505';
    end if;
    return query select v_job.job_id, v_job.client_id, v_job.request_id,
      v_job.requested_mode, v_job.status, v_job.scheduled_for, v_job.created_at, true;
    return;
  end if;

  select count(*)::integer into v_active_jobs
  from public.content_jobs active_job
  where active_job.client_id = v_client_id
    and active_job.status in ('queued', 'leased', 'running');
  if v_active_jobs <> 0 then
    raise exception 'HCS Prefect scheduler requires an empty active queue' using errcode = '55000';
  end if;

  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_by, requested_mode,
    status, scheduled_for, payload
  ) values (
    v_client_id, v_source_job_key, v_request_id, null, 'dry-run',
    'queued', clock_timestamp(), '{}'::jsonb
  )
  on conflict do nothing
  returning * into v_job;

  v_inserted := found;
  if not v_inserted then
    select raced.* into v_job
    from public.content_jobs raced
    where raced.client_id = v_client_id
      and (raced.source_job_key = v_source_job_key or raced.request_id = v_request_id)
    limit 1;
    if not found
       or v_job.source_job_key <> v_source_job_key
       or v_job.request_id <> v_request_id
       or v_job.requested_mode <> 'dry-run'
       or v_job.payload <> '{}'::jsonb then
      raise exception 'HCS Prefect scheduled request conflict' using errcode = '23505';
    end if;
  end if;

  return query select v_job.job_id, v_job.client_id, v_job.request_id,
    v_job.requested_mode, v_job.status, v_job.scheduled_for, v_job.created_at,
    not v_inserted;
end;
$$;

revoke all on function orin_private.enqueue_hcs_prefect_scheduled_job()
from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
     orin_watchdog, orin_prefect_shadow, orin_prefect_scheduler,
     orin_hcs_worker, orin_hcs_shopify_worker, orin_hcs_prefect_scheduler,
     orin_hcs_watchdog;
grant execute on function orin_private.enqueue_hcs_prefect_scheduled_job()
to orin_hcs_prefect_scheduler;

grant usage on schema public to orin_hcs_watchdog;
grant select (client_id, status) on table public.clients to orin_hcs_watchdog;
grant select (
  client_id, request_intake_enabled, automation_enabled,
  shopify_writes_enabled, approved_draft_writes_enabled,
  max_concurrency, allowed_mode
) on table public.client_runtime_settings to orin_hcs_watchdog;
grant select (
  client_id, scheduler_owner, state, last_heartbeat_at,
  last_expected_run_at, last_observed_run_id
) on table public.scheduler_health to orin_hcs_watchdog;
grant select (
  job_id, client_id, source_job_key, request_id, requested_mode, status,
  scheduled_for, attempt_count, last_error_code, created_at, updated_at
) on table public.content_jobs to orin_hcs_watchdog;
grant select (
  run_id, client_id, request_id, job_id, requested_mode, effective_mode,
  status, decision, code_version, shopify_create_count, shopify_published,
  queue_changed, reconciliation_status, error_code, started_at, finished_at
) on table public.runs to orin_hcs_watchdog;

create policy clients_hcs_watchdog_select
on public.clients for select to orin_hcs_watchdog using (client_id = 'hcs_gadgets');
create policy client_runtime_settings_hcs_watchdog_select
on public.client_runtime_settings for select to orin_hcs_watchdog using (client_id = 'hcs_gadgets');
create policy scheduler_health_hcs_watchdog_select
on public.scheduler_health for select to orin_hcs_watchdog using (client_id = 'hcs_gadgets');
create policy content_jobs_hcs_watchdog_select
on public.content_jobs for select to orin_hcs_watchdog using (client_id = 'hcs_gadgets');
create policy runs_hcs_watchdog_select
on public.runs for select to orin_hcs_watchdog using (client_id = 'hcs_gadgets');

grant orin_hcs_prefect_scheduler, orin_hcs_watchdog to postgres with set true;

comment on role orin_hcs_prefect_scheduler is
  'NOLOGIN fixed-HCS credential-free dry-run Prefect scheduler; no direct table access';
comment on role orin_hcs_watchdog is
  'NOLOGIN read-only HCS scheduler observation role; no write capability';
comment on function orin_private.enqueue_hcs_prefect_scheduled_job() is
  'Idempotent HCS daily dry-run enqueue for isolated Prefect scheduler ownership.';
