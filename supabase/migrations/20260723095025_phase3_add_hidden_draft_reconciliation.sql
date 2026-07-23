-- Phase 3E: durable hidden-draft reconciliation.
-- No runtime gate is enabled by this migration. Hidden-draft jobs can only be
-- claimed when the existing per-client automation and Shopify-write gates are
-- both explicitly enabled.

create table public.shopify_draft_reconciliations (
  client_id text not null references public.clients(client_id) on delete restrict,
  request_id uuid not null,
  job_id uuid not null,
  idempotency_key text generated always as (client_id || ':' || request_id::text) stored,
  idempotency_marker text generated always as (
    'orin-v1:' || client_id || ':' || request_id::text
  ) stored,
  shopify_article_id text not null,
  status text not null check (status in ('reconciled', 'needs_review')),
  observed_create_count smallint not null check (observed_create_count between 0 and 1),
  shopify_published boolean not null default false check (not shopify_published),
  first_observed_at timestamptz not null default now(),
  last_verified_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (client_id, request_id),
  unique (client_id, idempotency_marker),
  unique (client_id, shopify_article_id),
  foreign key (client_id, job_id)
    references public.content_jobs(client_id, job_id) on delete restrict,
  unique (client_id, job_id)
);

create trigger shopify_draft_reconciliations_set_updated_at
before update on public.shopify_draft_reconciliations
for each row execute function orin_private.set_updated_at();

alter table public.shopify_draft_reconciliations enable row level security;
revoke all on table public.shopify_draft_reconciliations from anon, authenticated;
grant select on table public.shopify_draft_reconciliations to authenticated;

create policy shopify_draft_reconciliations_select_for_members
on public.shopify_draft_reconciliations for select to authenticated
using (
  exists (
    select 1
    from public.client_members membership
    where membership.client_id = shopify_draft_reconciliations.client_id
      and membership.user_id = (select auth.uid())
  )
);

alter table public.runs
  add constraint runs_hidden_draft_never_published
  check (
    requested_mode <> 'hidden-draft'
    or (
      not shopify_published
      and not queue_changed
      and shopify_create_count between 0 and 1
    )
  );

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
  v_requested_mode text;
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

  select client.client_id, settings.allowed_mode
  into v_client_id, v_requested_mode
  from public.clients client
  join public.client_runtime_settings settings
    on settings.client_id = client.client_id
  where client.status = 'active'
    and settings.automation_enabled
    and settings.max_concurrency = 1
    and (
      (settings.allowed_mode = 'dry-run' and not settings.shopify_writes_enabled)
      or
      (settings.allowed_mode = 'hidden-draft' and settings.shopify_writes_enabled)
    )
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
        and candidate.requested_mode = settings.allowed_mode
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
    and candidate.requested_mode = v_requested_mode
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
  v_reconciliation public.shopify_draft_reconciliations%rowtype;
  v_status text;
  v_run_id text;
  v_request_id uuid;
  v_started_at timestamptz;
  v_finished_at timestamptz;
  v_article_id text;
  v_marker text;
  v_expected_key text;
  v_expected_marker text;
  v_create_count smallint;
  v_reconciliation_status text;
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
  v_article_id := p_final_result ->> 'shopify_article_id';
  v_marker := p_final_result ->> 'shopify_idempotency_marker';
  v_create_count := (p_final_result ->> 'shopify_create_count')::smallint;
  v_reconciliation_status := p_final_result ->> 'reconciliation_status';
  v_expected_key := v_job.client_id || ':' || v_job.request_id::text;
  v_expected_marker := 'orin-v1:' || v_expected_key;

  if p_final_result ->> 'schema' is distinct from 'orin.final-result/v1'
     or p_final_result ->> 'client_id' is distinct from v_job.client_id
     or v_request_id <> v_job.request_id
     or p_final_result ->> 'requested_mode' is distinct from v_job.requested_mode
     or p_final_result ->> 'idempotency_key' is distinct from v_expected_key
     or v_status not in ('completed', 'blocked', 'failed')
     or nullif(v_run_id, '') is null
     or nullif(p_final_result ->> 'decision', '') is null
     or nullif(p_final_result ->> 'code_version', '') is null
     or v_create_count is null
     or coalesce((p_final_result ->> 'shopify_published')::boolean, true)
     or coalesce((p_final_result ->> 'queue_changed')::boolean, true)
     or v_finished_at < v_started_at then
    raise exception 'final result violates the common worker contract' using errcode = '23514';
  end if;

  if v_job.requested_mode = 'dry-run' then
    if v_article_id is not null
       or v_marker is not null
       or v_create_count <> 0 then
      raise exception 'dry-run result claims a Shopify mutation' using errcode = '23514';
    end if;
  elsif v_job.requested_mode = 'hidden-draft' then
    if v_marker is distinct from v_expected_marker
       or v_create_count not between 0 and 1
       or (
         p_final_result ->> 'effective_mode' is distinct from 'hidden-draft'
         and not (
           v_status = 'failed'
           and v_article_id is null
           and p_final_result ->> 'effective_mode' is not distinct from 'none'
         )
       )
       or (
         v_article_id is null
         and (
           v_create_count <> 0
           or v_reconciliation_status is null
           or v_reconciliation_status not in ('not_started', 'failed', 'needs_review')
         )
       )
       or (
         v_article_id is not null
         and (
           v_reconciliation_status is null
           or v_reconciliation_status not in ('reconciled', 'needs_review')
         )
       ) then
      raise exception 'hidden-draft result violates reconciliation policy' using errcode = '23514';
    end if;
  else
    raise exception 'unsupported job mode' using errcode = '23514';
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
    v_article_id,
    v_create_count,
    false,
    false,
    coalesce(v_reconciliation_status, 'not_started'),
    v_job.client_id || '/' || v_run_id || '/',
    p_final_result,
    p_final_result ->> 'error_code',
    (p_final_result ->> 'pipeline_exit_code')::integer,
    v_started_at,
    v_finished_at
  );

  if v_job.requested_mode = 'hidden-draft' and v_article_id is not null then
    insert into public.shopify_draft_reconciliations (
      client_id,
      request_id,
      job_id,
      shopify_article_id,
      status,
      observed_create_count,
      shopify_published
    ) values (
      v_job.client_id,
      v_job.request_id,
      v_job.job_id,
      v_article_id,
      v_reconciliation_status,
      v_create_count,
      false
    )
    on conflict (client_id, request_id) do nothing;

    select * into v_reconciliation
    from public.shopify_draft_reconciliations reconciliation
    where reconciliation.client_id = v_job.client_id
      and reconciliation.request_id = v_job.request_id;

    if v_reconciliation.job_id <> v_job.job_id
       or v_reconciliation.idempotency_marker <> v_expected_marker
       or v_reconciliation.shopify_article_id <> v_article_id then
      raise exception 'Shopify reconciliation conflicts with durable ownership' using errcode = '23505';
    end if;
  end if;

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

revoke all on table public.shopify_draft_reconciliations from orin_worker;
