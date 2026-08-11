-- Phase 7: one disabled-by-default Prefect scheduler ownership proof.
--
-- The role has no direct table access. It can execute one zero-argument,
-- fixed-client, dry-run-only commissioning function. The function is
-- deliberately separate from the read-only Prefect shadow role.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_prefect_scheduler') then
    create role orin_prefect_scheduler
      nologin
      noinherit
      nosuperuser
      nocreaterole
      nocreatedb
      noreplication
      nobypassrls;
  end if;
end;
$$;

alter role orin_prefect_scheduler
  nologin
  noinherit
  nocreaterole
  nocreatedb;

do $$
begin
  if exists (
    select 1
    from pg_roles
    where rolname = 'orin_prefect_scheduler'
      and (
        rolsuper
        or rolcreaterole
        or rolcreatedb
        or rolreplication
        or rolbypassrls
      )
  ) then
    raise exception 'orin_prefect_scheduler has prohibited privileged attributes'
      using errcode = '42501';
  end if;
end;
$$;

revoke all on schema public from orin_prefect_scheduler;
revoke all on schema orin_private from orin_prefect_scheduler;
revoke all on all tables in schema public from orin_prefect_scheduler;
revoke all on all sequences in schema public from orin_prefect_scheduler;
revoke all on all functions in schema public from orin_prefect_scheduler;
revoke all on all functions in schema orin_private from orin_prefect_scheduler;
grant usage on schema orin_private to orin_prefect_scheduler;

create or replace function orin_private.enqueue_hoverboard_prefect_commissioning_job()
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
  v_client_id constant text := 'hoverboard_store';
  v_scheduler_owner constant text := 'prefect:orin-hbstore-prod';
  v_source_job_key constant text :=
    'scheduler:orin-hbstore-prod:prefect-commissioning-v1';
  v_digest text := md5('orin-prefect-commissioning-v1:' || v_client_id);
  v_request_id uuid := (
    substr(v_digest, 1, 8) || '-' ||
    substr(v_digest, 9, 4) || '-' ||
    '5' || substr(v_digest, 14, 3) || '-' ||
    '8' || substr(v_digest, 18, 3) || '-' ||
    substr(v_digest, 21, 12)
  )::uuid;
  v_access record;
  v_job public.content_jobs%rowtype;
  v_inserted boolean := false;
  v_active_jobs integer;
begin
  perform pg_advisory_xact_lock(hashtext(v_source_job_key));

  select
    client.status as client_status,
    settings.request_intake_enabled,
    settings.automation_enabled,
    settings.shopify_writes_enabled,
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
    raise exception 'Hoverboard Store Prefect scheduler configuration is missing'
      using errcode = 'P0002';
  end if;
  if v_access.client_status <> 'active'
     or not v_access.request_intake_enabled
     or not v_access.automation_enabled then
    raise exception 'Hoverboard Store Prefect commissioning gates are closed'
      using errcode = '42501';
  end if;
  if v_access.scheduler_state <> 'healthy'
     or v_access.scheduler_owner <> v_scheduler_owner then
    raise exception 'Prefect scheduler ownership is not active'
      using errcode = '42501';
  end if;
  if v_access.max_concurrency <> 1
     or v_access.allowed_mode <> 'dry-run'
     or v_access.shopify_writes_enabled then
    raise exception 'Prefect commissioning is dry-run-only'
      using errcode = '23514';
  end if;

  select existing.*
  into v_job
  from public.content_jobs existing
  where existing.client_id = v_client_id
    and (
      existing.source_job_key = v_source_job_key
      or existing.request_id = v_request_id
    )
  limit 1;

  if found then
    if v_job.source_job_key <> v_source_job_key
       or v_job.request_id <> v_request_id
       or v_job.requested_mode <> 'dry-run' then
      raise exception 'Prefect commissioning request identity conflict'
        using errcode = '23505';
    end if;
    return query
    select
      v_job.job_id,
      v_job.client_id,
      v_job.request_id,
      v_job.requested_mode,
      v_job.status,
      v_job.scheduled_for,
      v_job.created_at,
      true;
    return;
  end if;

  select count(*)::integer
  into v_active_jobs
  from public.content_jobs active_job
  where active_job.client_id = v_client_id
    and active_job.status in ('queued', 'leased', 'running');

  if v_active_jobs <> 0 then
    raise exception 'Prefect commissioning requires an empty active queue'
      using errcode = '55000';
  end if;

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
    v_client_id,
    v_source_job_key,
    v_request_id,
    null,
    'dry-run',
    'queued',
    clock_timestamp(),
    '{}'::jsonb
  )
  on conflict do nothing
  returning * into v_job;

  v_inserted := found;
  if not v_inserted then
    select raced.*
    into v_job
    from public.content_jobs raced
    where raced.client_id = v_client_id
      and (
        raced.source_job_key = v_source_job_key
        or raced.request_id = v_request_id
      )
    limit 1;

    if not found
       or v_job.source_job_key <> v_source_job_key
       or v_job.request_id <> v_request_id
       or v_job.requested_mode <> 'dry-run' then
      raise exception 'Prefect commissioning request conflict'
        using errcode = '23505';
    end if;
  end if;

  return query
  select
    v_job.job_id,
    v_job.client_id,
    v_job.request_id,
    v_job.requested_mode,
    v_job.status,
    v_job.scheduled_for,
    v_job.created_at,
    not v_inserted;
end;
$$;

revoke all on function orin_private.enqueue_hoverboard_prefect_commissioning_job()
from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
     orin_watchdog, orin_prefect_shadow;
grant execute on function orin_private.enqueue_hoverboard_prefect_commissioning_job()
to orin_prefect_scheduler;

grant orin_prefect_scheduler to postgres with set true;

comment on role orin_prefect_scheduler is
  'NOLOGIN fixed-client dry-run-only Prefect commissioning role; no direct table access';
comment on function orin_private.enqueue_hoverboard_prefect_commissioning_job() is
  'One idempotent HBStore dry-run enqueue for the controlled Prefect ownership proof.';
