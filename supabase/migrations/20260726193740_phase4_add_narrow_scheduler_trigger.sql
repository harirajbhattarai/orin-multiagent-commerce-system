do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_scheduler') then
    create role orin_scheduler
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

alter role orin_scheduler
  nologin
  noinherit
  nocreaterole
  nocreatedb;

do $$
begin
  if exists (
    select 1
    from pg_roles
    where rolname = 'orin_scheduler'
      and (
        rolsuper
        or rolcreaterole
        or rolcreatedb
        or rolreplication
        or rolbypassrls
      )
  ) then
    raise exception 'orin_scheduler has prohibited privileged attributes'
      using errcode = '42501';
  end if;
end;
$$;

revoke all on schema public from orin_scheduler;
revoke all on schema orin_private from orin_scheduler;
revoke all on all tables in schema public from orin_scheduler;
revoke all on all sequences in schema public from orin_scheduler;
revoke all on all functions in schema public from orin_scheduler;
revoke all on all functions in schema orin_private from orin_scheduler;
grant usage on schema orin_private to orin_scheduler;

create or replace function orin_private.enqueue_hoverboard_scheduled_job()
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
as $$
declare
  v_client_id constant text := 'hoverboard_store';
  v_scheduler_owner constant text := 'openclaw:orin-hbstore-prod';
  v_schedule_date date := (clock_timestamp() at time zone 'Europe/London')::date;
  v_source_job_key text :=
    'scheduler:orin-hbstore-prod:' || v_schedule_date::text;
  v_digest text := md5(
    'orin-scheduler-v1:' || v_client_id || ':' || v_schedule_date::text
  );
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
begin
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
       or v_job.request_id <> v_request_id then
      raise exception 'scheduled request identity conflict'
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
    raise exception 'Hoverboard Store scheduler configuration is missing'
      using errcode = 'P0002';
  end if;
  if v_access.client_status <> 'active'
     or not v_access.request_intake_enabled
     or not v_access.automation_enabled then
    raise exception 'Hoverboard Store automation gates are closed'
      using errcode = '42501';
  end if;
  if v_access.scheduler_state <> 'healthy'
     or v_access.scheduler_owner <> v_scheduler_owner then
    raise exception 'Hoverboard Store scheduler ownership is not active'
      using errcode = '42501';
  end if;
  if v_access.max_concurrency <> 1 then
    raise exception 'Hoverboard Store concurrency policy is invalid'
      using errcode = '23514';
  end if;
  if v_access.allowed_mode not in ('dry-run', 'hidden-draft') then
    raise exception 'Hoverboard Store scheduler mode is invalid'
      using errcode = '23514';
  end if;
  if v_access.allowed_mode = 'hidden-draft'
     and not v_access.shopify_writes_enabled then
    raise exception 'Hoverboard Store Shopify write gate is closed'
      using errcode = '42501';
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
    v_access.allowed_mode,
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
       or v_job.requested_mode <> v_access.allowed_mode then
      raise exception 'scheduled request conflict'
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

revoke all on function orin_private.enqueue_hoverboard_scheduled_job()
from public, anon, authenticated, orin_api, orin_worker;
grant execute on function orin_private.enqueue_hoverboard_scheduled_job()
to orin_scheduler;

grant orin_scheduler to postgres with set true;

comment on function orin_private.enqueue_hoverboard_scheduled_job() is
'Hard-wired idempotent Hoverboard Store scheduler enqueue boundary. No client, mode, command, payload, or schedule input is accepted.';
