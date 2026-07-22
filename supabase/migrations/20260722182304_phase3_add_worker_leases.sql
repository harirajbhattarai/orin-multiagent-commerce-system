-- Phase 3B: narrow worker capability and atomic lease/finalization functions.
-- This migration creates no login, credential, scheduler, or Shopify write path.

create unique index content_jobs_one_active_per_client_idx
  on public.content_jobs(client_id)
  where status in ('leased', 'running');

alter table public.runs
  add constraint runs_dry_run_has_no_mutation
  check (
    requested_mode <> 'dry-run'
    or (
      shopify_article_id is null
      and shopify_create_count = 0
      and not shopify_published
      and not queue_changed
    )
  );

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_worker') then
    create role orin_worker nologin noinherit nobypassrls;
  end if;
end
$$;

revoke all on schema public from orin_worker;
revoke all on schema orin_private from orin_worker;
grant usage on schema orin_private to orin_worker;

create or replace function orin_private.claim_next_job(
  p_worker_id text,
  p_lease_seconds integer default 1200
)
returns table (
  job_id uuid,
  client_id text,
  request_id uuid,
  requested_mode text,
  attempt_count smallint,
  payload jsonb,
  lease_expires_at timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_client_id text;
  v_job_id uuid;
begin
  if p_worker_id is null
     or length(p_worker_id) < 8
     or length(p_worker_id) > 128
     or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]+$' then
    raise exception 'invalid worker identifier' using errcode = '22023';
  end if;

  if p_lease_seconds < 60 or p_lease_seconds > 3600 then
    raise exception 'lease must be between 60 and 3600 seconds' using errcode = '22023';
  end if;

  with exhausted as (
    update public.content_jobs job
    set status = 'failed',
        lock_owner = null,
        locked_at = null,
        lease_expires_at = null,
        last_error_code = 'ORIN_MAX_ATTEMPTS_EXCEEDED'
    where job.status in ('leased', 'running')
      and job.lease_expires_at <= statement_timestamp()
      and job.attempt_count >= job.max_attempts
    returning job.client_id, job.job_id
  )
  insert into public.incidents (client_id, severity, code, summary, details)
  select
    exhausted.client_id,
    'critical',
    'ORIN_MAX_ATTEMPTS_EXCEEDED',
    'Worker lease expired after the maximum number of claims',
    jsonb_build_object('job_id', exhausted.job_id)
  from exhausted;

  select client.client_id
  into v_client_id
  from public.clients client
  join public.client_runtime_settings settings
    on settings.client_id = client.client_id
  where client.status = 'active'
    and settings.automation_enabled
    and not settings.shopify_writes_enabled
    and settings.max_concurrency = 1
    and settings.allowed_mode = 'dry-run'
    and not exists (
      select 1
      from public.content_jobs active_job
      where active_job.client_id = client.client_id
        and active_job.status in ('leased', 'running')
        and active_job.lease_expires_at > statement_timestamp()
    )
    and exists (
      select 1
      from public.content_jobs candidate
      where candidate.client_id = client.client_id
        and candidate.requested_mode = 'dry-run'
        and candidate.payload = '{}'::jsonb
        and candidate.attempt_count < candidate.max_attempts
        and (
          (candidate.status = 'queued' and candidate.scheduled_for <= statement_timestamp())
          or (
            candidate.status in ('leased', 'running')
            and candidate.lease_expires_at <= statement_timestamp()
          )
        )
    )
  order by client.client_id
  for update of client skip locked
  limit 1;

  if v_client_id is null then
    return;
  end if;

  select candidate.job_id
  into v_job_id
  from public.content_jobs candidate
  where candidate.client_id = v_client_id
    and candidate.requested_mode = 'dry-run'
    and candidate.payload = '{}'::jsonb
    and candidate.attempt_count < candidate.max_attempts
    and (
      (candidate.status = 'queued' and candidate.scheduled_for <= statement_timestamp())
      or (
        candidate.status in ('leased', 'running')
        and candidate.lease_expires_at <= statement_timestamp()
      )
    )
  order by
    case when candidate.status in ('leased', 'running') then 0 else 1 end,
    candidate.scheduled_for,
    candidate.created_at,
    candidate.job_id
  for update skip locked
  limit 1;

  if v_job_id is null then
    return;
  end if;

  return query
  update public.content_jobs claimed
  set status = 'leased',
      attempt_count = claimed.attempt_count + 1,
      lock_owner = p_worker_id,
      locked_at = statement_timestamp(),
      lease_expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds),
      last_error_code = null
  where claimed.job_id = v_job_id
  returning
    claimed.job_id,
    claimed.client_id,
    claimed.request_id,
    claimed.requested_mode,
    claimed.attempt_count,
    claimed.payload,
    claimed.lease_expires_at;
end;
$$;

create or replace function orin_private.renew_job_lease(
  p_job_id uuid,
  p_worker_id text,
  p_lease_seconds integer default 1200
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_renewed boolean;
begin
  if p_lease_seconds < 60 or p_lease_seconds > 3600 then
    raise exception 'lease must be between 60 and 3600 seconds' using errcode = '22023';
  end if;

  update public.content_jobs job
  set lease_expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds)
  where job.job_id = p_job_id
    and job.status in ('leased', 'running')
    and job.lock_owner = p_worker_id
    and job.lease_expires_at > statement_timestamp()
  returning true into v_renewed;

  return coalesce(v_renewed, false);
end;
$$;

create or replace function orin_private.complete_job(
  p_job_id uuid,
  p_worker_id text,
  p_final_result jsonb
)
returns table (run_id text, status text, replayed boolean)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_job public.content_jobs%rowtype;
  v_existing public.runs%rowtype;
  v_status text;
  v_run_id text;
  v_request_id uuid;
  v_started_at timestamptz;
  v_finished_at timestamptz;
begin
  if jsonb_typeof(p_final_result) <> 'object' then
    raise exception 'final result must be a JSON object' using errcode = '22023';
  end if;

  select * into v_job
  from public.content_jobs job
  where job.job_id = p_job_id
  for update;

  if not found then
    raise exception 'job not found' using errcode = 'P0002';
  end if;

  select * into v_existing
  from public.runs existing_run
  where existing_run.client_id = v_job.client_id
    and existing_run.request_id = v_job.request_id;

  if found then
    if v_existing.final_result = p_final_result
       and v_existing.job_id = v_job.job_id
       and v_job.status in ('completed', 'blocked', 'failed') then
      return query select v_existing.run_id, v_existing.status, true;
      return;
    end if;
    raise exception 'request already has a different final result' using errcode = '23505';
  end if;

  if v_job.status not in ('leased', 'running') or v_job.lock_owner <> p_worker_id then
    raise exception 'worker does not own the job lease' using errcode = '42501';
  end if;

  v_status := p_final_result ->> 'status';
  v_run_id := p_final_result ->> 'run_id';
  v_request_id := (p_final_result ->> 'request_id')::uuid;
  v_started_at := (p_final_result ->> 'started_at')::timestamptz;
  v_finished_at := (p_final_result ->> 'finished_at')::timestamptz;

  if p_final_result ->> 'schema' <> 'orin.final-result/v1'
     or p_final_result ->> 'client_id' <> v_job.client_id
     or v_request_id <> v_job.request_id
     or p_final_result ->> 'requested_mode' <> v_job.requested_mode
     or v_job.requested_mode <> 'dry-run'
     or v_status not in ('completed', 'blocked', 'failed')
     or nullif(v_run_id, '') is null
     or nullif(p_final_result ->> 'decision', '') is null
     or nullif(p_final_result ->> 'code_version', '') is null
     or coalesce((p_final_result ->> 'shopify_published')::boolean, true)
     or coalesce((p_final_result ->> 'shopify_create_count')::smallint, 1) <> 0
     or coalesce((p_final_result ->> 'queue_changed')::boolean, true)
     or p_final_result ->> 'shopify_article_id' is not null
     or v_finished_at < v_started_at then
    raise exception 'final result violates the worker contract' using errcode = '23514';
  end if;

  insert into public.runs (
    run_id,
    client_id,
    request_id,
    job_id,
    attempt,
    requested_mode,
    effective_mode,
    status,
    decision,
    code_version,
    config_version,
    shopify_article_id,
    shopify_create_count,
    shopify_published,
    queue_changed,
    reconciliation_status,
    artifact_prefix,
    final_result,
    error_code,
    pipeline_exit_code,
    started_at,
    finished_at
  ) values (
    v_run_id,
    v_job.client_id,
    v_job.request_id,
    v_job.job_id,
    coalesce((p_final_result ->> 'attempt')::smallint, 1),
    v_job.requested_mode,
    p_final_result ->> 'effective_mode',
    v_status,
    p_final_result ->> 'decision',
    p_final_result ->> 'code_version',
    p_final_result ->> 'config_version',
    p_final_result ->> 'shopify_article_id',
    (p_final_result ->> 'shopify_create_count')::smallint,
    (p_final_result ->> 'shopify_published')::boolean,
    (p_final_result ->> 'queue_changed')::boolean,
    coalesce(p_final_result ->> 'reconciliation_status', 'not_started'),
    v_job.client_id || '/' || v_run_id || '/',
    p_final_result,
    p_final_result ->> 'error_code',
    (p_final_result ->> 'pipeline_exit_code')::integer,
    v_started_at,
    v_finished_at
  );

  update public.content_jobs job
  set status = v_status,
      lock_owner = null,
      locked_at = null,
      lease_expires_at = null,
      last_error_code = p_final_result ->> 'error_code'
  where job.job_id = v_job.job_id;

  return query select v_run_id, v_status, false;
end;
$$;

revoke all on function orin_private.claim_next_job(text, integer) from public, anon, authenticated;
revoke all on function orin_private.renew_job_lease(uuid, text, integer) from public, anon, authenticated;
revoke all on function orin_private.complete_job(uuid, text, jsonb) from public, anon, authenticated;

grant execute on function orin_private.claim_next_job(text, integer) to orin_worker;
grant execute on function orin_private.renew_job_lease(uuid, text, integer) to orin_worker;
grant execute on function orin_private.complete_job(uuid, text, jsonb) to orin_worker;

grant orin_worker to postgres with set true;
