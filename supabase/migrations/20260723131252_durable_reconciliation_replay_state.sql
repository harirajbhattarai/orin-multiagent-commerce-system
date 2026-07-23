-- Phase 3F: durable replay and reconciliation state.
--
-- `public.runs` remains the terminal request ledger. Every worker execution,
-- including a retryable or reconciliation-required result, is first recorded
-- in `public.job_attempts`. Only a v2 result with replay_disposition=terminal
-- may finalize a job and enter `public.runs`.

alter table public.runs
  add column replay_disposition text,
  add column shopify_write_state text;

update public.runs
set replay_disposition = 'terminal',
    shopify_write_state = case
      when shopify_article_id is not null then 'article_observed'
      else 'not_attempted'
    end;

alter table public.runs
  alter column replay_disposition set default 'terminal',
  alter column replay_disposition set not null,
  alter column shopify_write_state set default 'not_attempted',
  alter column shopify_write_state set not null,
  add constraint runs_replay_disposition_terminal
    check (replay_disposition = 'terminal'),
  add constraint runs_shopify_write_state_valid
    check (shopify_write_state in ('not_attempted', 'article_observed')),
  add constraint runs_shopify_evidence_coherent
    check (
      (
        shopify_write_state = 'not_attempted'
        and shopify_article_id is null
        and shopify_create_count = 0
      )
      or (
        shopify_write_state = 'article_observed'
        and shopify_article_id is not null
        and shopify_create_count = 1
        and reconciliation_status = 'reconciled'
      )
    );

update public.shopify_draft_reconciliations
set observed_create_count = 1
where observed_create_count = 0;

alter table public.shopify_draft_reconciliations
  add constraint shopify_reconciliation_observes_one_article
  check (observed_create_count = 1);

create table public.job_attempts (
  job_id uuid not null,
  client_id text not null,
  request_id uuid not null,
  attempt smallint not null check (attempt >= 1),
  run_id text not null,
  status text not null check (status in ('completed', 'blocked', 'failed')),
  replay_disposition text not null
    check (replay_disposition in ('terminal', 'retry', 'reconcile')),
  shopify_write_state text not null
    check (shopify_write_state in ('not_attempted', 'unknown', 'article_observed')),
  reconciliation_status text not null
    check (
      reconciliation_status in (
        'not_started',
        'not_required',
        'pending',
        'reconciled',
        'needs_review',
        'failed'
      )
    ),
  final_result jsonb not null check (jsonb_typeof(final_result) = 'object'),
  created_at timestamptz not null default now(),
  primary key (job_id, attempt),
  unique (client_id, request_id, attempt),
  unique (client_id, run_id),
  foreign key (client_id, job_id)
    references public.content_jobs(client_id, job_id) on delete restrict
);

alter table public.job_attempts enable row level security;
revoke all on table public.job_attempts from public, anon, authenticated, orin_worker;

create or replace function orin_private.defer_job(
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
  v_existing_attempt public.job_attempts%rowtype;
  v_status text;
  v_next_status text;
  v_run_id text;
  v_request_id uuid;
  v_attempt smallint;
  v_started_at timestamptz;
  v_finished_at timestamptz;
  v_article_id text;
  v_marker text;
  v_expected_key text;
  v_expected_marker text;
  v_create_count smallint;
  v_reconciliation_status text;
  v_replay_disposition text;
  v_write_state text;
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

  v_attempt := (p_final_result ->> 'attempt')::smallint;

  select * into v_existing_attempt
  from public.job_attempts attempt_record
  where attempt_record.job_id = v_job.job_id
    and attempt_record.attempt = v_attempt;

  if found then
    if v_existing_attempt.final_result = p_final_result then
      return query
      select v_existing_attempt.run_id, v_job.status, true;
      return;
    end if;
    raise exception 'job attempt already has a different result' using errcode = '23505';
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
  v_replay_disposition := p_final_result ->> 'replay_disposition';
  v_write_state := p_final_result ->> 'shopify_write_state';
  v_expected_key := v_job.client_id || ':' || v_job.request_id::text;
  v_expected_marker := 'orin-v1:' || v_expected_key;

  if p_final_result ->> 'schema' is distinct from 'orin.final-result/v2'
     or p_final_result ->> 'client_id' is distinct from v_job.client_id
     or v_request_id is distinct from v_job.request_id
     or p_final_result ->> 'requested_mode' is distinct from v_job.requested_mode
     or p_final_result ->> 'idempotency_key' is distinct from v_expected_key
     or v_attempt is distinct from v_job.attempt_count
     or coalesce(v_status, '') not in ('blocked', 'failed')
     or coalesce(v_replay_disposition, '') not in ('retry', 'reconcile')
     or coalesce(v_write_state, '') not in ('not_attempted', 'unknown', 'article_observed')
     or nullif(v_run_id, '') is null
     or nullif(p_final_result ->> 'decision', '') is null
     or nullif(p_final_result ->> 'code_version', '') is null
     or v_create_count is null
     or coalesce((p_final_result ->> 'shopify_published')::boolean, true)
     or coalesce((p_final_result ->> 'queue_changed')::boolean, true)
     or v_started_at is null
     or v_finished_at is null
     or v_finished_at < v_started_at then
    raise exception 'deferred result violates the common worker contract'
      using errcode = '23514';
  end if;

  if v_job.requested_mode = 'dry-run' then
    if v_replay_disposition <> 'retry'
       or v_write_state <> 'not_attempted'
       or v_article_id is not null
       or v_marker is not null
       or v_create_count <> 0 then
      raise exception 'dry-run deferral claims a Shopify mutation'
        using errcode = '23514';
    end if;
  elsif v_job.requested_mode = 'hidden-draft' then
    if v_marker is distinct from v_expected_marker
       or (
         coalesce(p_final_result ->> 'effective_mode', '') not in ('hidden-draft', 'none')
       )
       or (
         v_replay_disposition = 'retry'
         and (
           v_write_state <> 'not_attempted'
           or v_article_id is not null
           or v_create_count <> 0
           or coalesce(v_reconciliation_status, '') not in ('not_started', 'not_required', 'failed')
         )
       )
       or (
         v_replay_disposition = 'reconcile'
         and not (
           (
             v_write_state = 'unknown'
             and v_article_id is null
             and v_create_count = 0
             and coalesce(v_reconciliation_status, '') in ('needs_review', 'failed')
           )
           or (
             v_write_state = 'article_observed'
             and v_article_id is not null
             and v_create_count = 1
             and coalesce(v_reconciliation_status, '') in ('reconciled', 'needs_review')
           )
         )
       ) then
      raise exception 'hidden-draft deferral violates reconciliation policy'
        using errcode = '23514';
    end if;
  else
    raise exception 'unsupported job mode' using errcode = '23514';
  end if;

  insert into public.job_attempts (
    job_id,
    client_id,
    request_id,
    attempt,
    run_id,
    status,
    replay_disposition,
    shopify_write_state,
    reconciliation_status,
    final_result
  ) values (
    v_job.job_id,
    v_job.client_id,
    v_job.request_id,
    v_attempt,
    v_run_id,
    v_status,
    v_replay_disposition,
    v_write_state,
    v_reconciliation_status,
    p_final_result
  );

  v_next_status := case
    when v_job.attempt_count >= v_job.max_attempts then 'failed'
    else 'queued'
  end;

  update public.content_jobs job
  set status = v_next_status,
      scheduled_for = case
        when v_next_status = 'queued'
          then statement_timestamp() + interval '1 minute'
        else job.scheduled_for
      end,
      lock_owner = null,
      locked_at = null,
      lease_expires_at = null,
      last_error_code = p_final_result ->> 'error_code'
  where job.job_id = v_job.job_id;

  if v_next_status = 'failed' then
    insert into public.incidents (client_id, severity, code, summary, details)
    values (
      v_job.client_id,
      'critical',
      'ORIN_RECONCILIATION_ATTEMPTS_EXHAUSTED',
      'Automatic replay ended with unresolved Shopify state',
      jsonb_build_object(
        'job_id', v_job.job_id,
        'request_id', v_job.request_id,
        'attempt', v_attempt,
        'run_id', v_run_id,
        'replay_disposition', v_replay_disposition,
        'shopify_write_state', v_write_state
      )
    );
  end if;

  return query select v_run_id, v_next_status, false;
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
  v_attempt smallint;
  v_started_at timestamptz;
  v_finished_at timestamptz;
  v_article_id text;
  v_marker text;
  v_expected_key text;
  v_expected_marker text;
  v_create_count smallint;
  v_reconciliation_status text;
  v_write_state text;
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
  v_attempt := (p_final_result ->> 'attempt')::smallint;
  v_started_at := (p_final_result ->> 'started_at')::timestamptz;
  v_finished_at := (p_final_result ->> 'finished_at')::timestamptz;
  v_article_id := p_final_result ->> 'shopify_article_id';
  v_marker := p_final_result ->> 'shopify_idempotency_marker';
  v_create_count := (p_final_result ->> 'shopify_create_count')::smallint;
  v_reconciliation_status := p_final_result ->> 'reconciliation_status';
  v_write_state := p_final_result ->> 'shopify_write_state';
  v_expected_key := v_job.client_id || ':' || v_job.request_id::text;
  v_expected_marker := 'orin-v1:' || v_expected_key;

  if p_final_result ->> 'schema' is distinct from 'orin.final-result/v2'
     or p_final_result ->> 'client_id' is distinct from v_job.client_id
     or v_request_id is distinct from v_job.request_id
     or p_final_result ->> 'requested_mode' is distinct from v_job.requested_mode
     or p_final_result ->> 'idempotency_key' is distinct from v_expected_key
     or p_final_result ->> 'replay_disposition' is distinct from 'terminal'
     -- A terminal artifact may originate from an earlier lease when the
     -- pipeline finished but its worker crashed before database completion.
     -- The current lease owner may finalize it only while no later attempt has
     -- already produced durable evidence.
     or v_attempt is null
     or v_attempt < 1
     or v_attempt > v_job.attempt_count
     or exists (
       select 1
       from public.job_attempts later_attempt
       where later_attempt.job_id = v_job.job_id
         and later_attempt.attempt > v_attempt
     )
     or coalesce(v_status, '') not in ('completed', 'blocked', 'failed')
     or coalesce(v_write_state, '') not in ('not_attempted', 'article_observed')
     or nullif(v_run_id, '') is null
     or nullif(p_final_result ->> 'decision', '') is null
     or nullif(p_final_result ->> 'code_version', '') is null
     or v_create_count is null
     or coalesce((p_final_result ->> 'shopify_published')::boolean, true)
     or coalesce((p_final_result ->> 'queue_changed')::boolean, true)
     or v_started_at is null
     or v_finished_at is null
     or v_finished_at < v_started_at then
    raise exception 'final result violates the common worker contract'
      using errcode = '23514';
  end if;

  if v_job.requested_mode = 'dry-run' then
    if v_write_state <> 'not_attempted'
       or v_article_id is not null
       or v_marker is not null
       or v_create_count <> 0 then
      raise exception 'dry-run result claims a Shopify mutation'
        using errcode = '23514';
    end if;
  elsif v_job.requested_mode = 'hidden-draft' then
    if v_marker is distinct from v_expected_marker
       or (
         p_final_result ->> 'effective_mode' is distinct from 'hidden-draft'
         and not (
           v_status = 'failed'
           and v_article_id is null
           and p_final_result ->> 'effective_mode' is not distinct from 'none'
         )
       )
       or not (
         (
           v_write_state = 'not_attempted'
           and v_article_id is null
           and v_create_count = 0
           and coalesce(v_reconciliation_status, '') in ('not_started', 'not_required', 'failed')
         )
         or (
           v_write_state = 'article_observed'
           and v_article_id is not null
           and v_create_count = 1
           and v_reconciliation_status = 'reconciled'
         )
       ) then
      raise exception 'hidden-draft result violates terminal reconciliation policy'
        using errcode = '23514';
    end if;
  else
    raise exception 'unsupported job mode' using errcode = '23514';
  end if;

  insert into public.job_attempts (
    job_id,
    client_id,
    request_id,
    attempt,
    run_id,
    status,
    replay_disposition,
    shopify_write_state,
    reconciliation_status,
    final_result
  ) values (
    v_job.job_id,
    v_job.client_id,
    v_job.request_id,
    v_attempt,
    v_run_id,
    v_status,
    'terminal',
    v_write_state,
    v_reconciliation_status,
    p_final_result
  );

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
    replay_disposition,
    shopify_write_state,
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
    v_attempt,
    v_job.requested_mode,
    p_final_result ->> 'effective_mode',
    v_status,
    p_final_result ->> 'decision',
    p_final_result ->> 'code_version',
    p_final_result ->> 'config_version',
    'terminal',
    v_write_state,
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
      'reconciled',
      1,
      false
    )
    on conflict (client_id, request_id) do nothing;

    select * into v_reconciliation
    from public.shopify_draft_reconciliations reconciliation
    where reconciliation.client_id = v_job.client_id
      and reconciliation.request_id = v_job.request_id;

    if v_reconciliation.job_id <> v_job.job_id
       or v_reconciliation.idempotency_marker <> v_expected_marker
       or v_reconciliation.shopify_article_id <> v_article_id
       or v_reconciliation.status <> 'reconciled'
       or v_reconciliation.observed_create_count <> 1 then
      raise exception 'Shopify reconciliation conflicts with durable ownership'
        using errcode = '23505';
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

revoke all on function orin_private.defer_job(uuid, text, jsonb)
  from public, anon, authenticated;
revoke all on function orin_private.complete_job(uuid, text, jsonb)
  from public, anon, authenticated;
grant execute on function orin_private.defer_job(uuid, text, jsonb) to orin_worker;
grant execute on function orin_private.complete_job(uuid, text, jsonb) to orin_worker;
