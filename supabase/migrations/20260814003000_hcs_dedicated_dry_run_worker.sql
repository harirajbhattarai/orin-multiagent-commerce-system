-- Bind the HCS worker to one client and one non-mutating execution mode.
-- Exact topic and body identities are also globally unique so one tenant's
-- content cannot be copied into another tenant accidentally.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_hcs_worker') then
    create role orin_hcs_worker nologin nosuperuser nocreatedb nocreaterole
      noinherit noreplication nobypassrls;
  end if;
end
$$;

create unique index content_plan_items_global_topic_identity_idx
on public.content_plan_items (
  btrim(lower(regexp_replace(topic, '[^[:alnum:]]+', ' ', 'g')))
)
where topic is not null and btrim(topic) <> '';

create unique index content_drafts_global_body_identity_idx
on public.content_drafts (body_sha256)
where body_sha256 is not null and body_sha256 <> '';

create or replace function orin_private.materialize_next_dry_run_decision_for_client(
  p_client_id text
)
returns table (decision_id uuid, job_id uuid, processing_status text)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_decision public.content_decisions%rowtype;
  v_item public.content_plan_items%rowtype;
  v_settings public.client_runtime_settings%rowtype;
  v_client public.clients%rowtype;
  v_job_id uuid;
begin
  if p_client_id is distinct from 'hcs_gadgets' then
    raise exception 'dedicated worker client is not allowed' using errcode = '42501';
  end if;

  select decision.*
  into v_decision
  from public.content_decisions decision
  join public.content_plan_items item
    on item.client_id = decision.client_id
   and item.content_item_id = decision.content_item_id
  join public.clients client on client.client_id = decision.client_id
  join public.client_runtime_settings settings on settings.client_id = decision.client_id
  where decision.client_id = p_client_id
    and decision.processing_status = 'recorded'
    and decision.decision in ('request_changes', 'approve_concept')
    and (
      decision.decision = 'request_changes'
      or decision.content_item_version <> item.version
      or item.status <> 'planned'
      or (
        client.status = 'active'
        and settings.request_intake_enabled
        and settings.automation_enabled
        and not settings.shopify_writes_enabled
        and not settings.approved_draft_writes_enabled
        and settings.allowed_mode = 'dry-run'
      )
    )
  order by decision.created_at, decision.decision_id
  for update of decision skip locked
  limit 1;

  if not found then return; end if;

  select * into v_item
  from public.content_plan_items item
  where item.client_id = v_decision.client_id
    and item.content_item_id = v_decision.content_item_id
  for update;
  select * into v_client from public.clients client
  where client.client_id = v_decision.client_id;
  select * into v_settings from public.client_runtime_settings settings
  where settings.client_id = v_decision.client_id;

  if v_decision.content_item_version <> v_item.version
     or (v_decision.decision = 'approve_concept' and v_item.status <> 'planned') then
    update public.content_decisions decision
    set processing_status = 'superseded',
        outcome = 'Content version or stage changed before processing.'
    where decision.decision_id = v_decision.decision_id;
    return query select v_decision.decision_id, null::uuid, 'superseded'::text;
    return;
  end if;

  if v_decision.decision = 'request_changes' then
    update public.content_plan_items item
    set status = 'needs_human_review', version = item.version + 1
    where item.client_id = v_item.client_id
      and item.content_item_id = v_item.content_item_id;
    update public.content_decisions decision
    set processing_status = 'consumed',
        consumed_at = statement_timestamp(),
        outcome = 'Change request recorded for human revision.'
    where decision.decision_id = v_decision.decision_id;
    return query select v_decision.decision_id, null::uuid, 'consumed'::text;
    return;
  end if;

  if v_client.status <> 'active'
     or not v_settings.request_intake_enabled
     or not v_settings.automation_enabled
     or v_settings.shopify_writes_enabled
     or v_settings.approved_draft_writes_enabled
     or v_settings.allowed_mode <> 'dry-run' then
    return;
  end if;

  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_by, requested_mode,
    status, scheduled_for, payload, content_plan_item_id
  ) values (
    v_decision.client_id,
    'decision:' || v_decision.decision_id::text,
    v_decision.request_id,
    v_decision.requested_by,
    'dry-run',
    'queued',
    statement_timestamp(),
    '{}'::jsonb,
    v_decision.content_item_id
  ) returning content_jobs.job_id into v_job_id;

  update public.content_plan_items item
  set status = 'in_progress'
  where item.client_id = v_item.client_id
    and item.content_item_id = v_item.content_item_id;

  update public.content_decisions decision
  set processing_status = 'consumed',
      consumed_at = statement_timestamp(),
      content_job_id = v_job_id,
      outcome = 'Dedicated HCS dry-run draft-generation job queued.'
  where decision.decision_id = v_decision.decision_id;

  return query select v_decision.decision_id, v_job_id, 'consumed'::text;
end;
$$;

create or replace function orin_private.claim_next_dry_run_job_for_client(
  p_worker_id text,
  p_client_id text,
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
  v_job_id uuid;
begin
  if p_client_id is distinct from 'hcs_gadgets' then
    raise exception 'dedicated worker client is not allowed' using errcode = '42501';
  end if;
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
    set status = 'failed', lock_owner = null, locked_at = null,
        lease_expires_at = null,
        last_error_code = 'ORIN_MAX_ATTEMPTS_EXCEEDED'
    where job.client_id = p_client_id
      and job.status in ('leased', 'running')
      and job.lease_expires_at <= statement_timestamp()
      and job.attempt_count >= job.max_attempts
    returning job.client_id, job.job_id
  )
  insert into public.incidents (client_id, severity, code, summary, details)
  select exhausted.client_id, 'critical', 'ORIN_MAX_ATTEMPTS_EXCEEDED',
         'Dedicated worker lease expired after the maximum number of claims',
         jsonb_build_object('job_id', exhausted.job_id)
  from exhausted;

  if not exists (
    select 1
    from public.clients client
    join public.client_runtime_settings settings using (client_id)
    where client.client_id = p_client_id
      and client.status = 'active'
      and settings.request_intake_enabled
      and settings.automation_enabled
      and settings.max_concurrency = 1
      and settings.allowed_mode = 'dry-run'
      and not settings.shopify_writes_enabled
      and not settings.approved_draft_writes_enabled
  ) then
    return;
  end if;

  if exists (
    select 1 from public.content_jobs active_job
    where active_job.client_id = p_client_id
      and active_job.status in ('leased', 'running')
      and active_job.lease_expires_at > statement_timestamp()
  ) then
    return;
  end if;

  select candidate.job_id
  into v_job_id
  from public.content_jobs candidate
  where candidate.client_id = p_client_id
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
    candidate.scheduled_for, candidate.created_at, candidate.job_id
  for update of candidate skip locked
  limit 1;

  if v_job_id is null then return; end if;

  return query
  update public.content_jobs claimed
  set status = 'leased',
      attempt_count = claimed.attempt_count + 1,
      lock_owner = p_worker_id,
      locked_at = statement_timestamp(),
      lease_expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds),
      last_error_code = null
  where claimed.job_id = v_job_id
    and claimed.client_id = p_client_id
    and claimed.requested_mode = 'dry-run'
  returning claimed.job_id, claimed.client_id, claimed.request_id,
            claimed.requested_mode, claimed.attempt_count, claimed.payload,
            claimed.lease_expires_at;
end;
$$;

revoke all on function orin_private.materialize_next_dry_run_decision_for_client(text)
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
       orin_watchdog, orin_prefect_shadow, orin_prefect_scheduler;
revoke all on function orin_private.claim_next_dry_run_job_for_client(text, text, integer)
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
       orin_watchdog, orin_prefect_shadow, orin_prefect_scheduler;

grant usage on schema orin_private to orin_hcs_worker;
grant execute on function orin_private.materialize_next_dry_run_decision_for_client(text)
  to orin_hcs_worker;
grant execute on function orin_private.claim_next_dry_run_job_for_client(text, text, integer)
  to orin_hcs_worker;
grant execute on function orin_private.renew_job_lease(uuid, text, integer)
  to orin_hcs_worker;
grant execute on function orin_private.get_content_plan_snapshot(uuid, text)
  to orin_hcs_worker;
grant execute on function orin_private.complete_job_with_review_draft(uuid, text, jsonb, jsonb)
  to orin_hcs_worker;
grant execute on function orin_private.defer_job(uuid, text, jsonb)
  to orin_hcs_worker;

comment on function orin_private.claim_next_dry_run_job_for_client(text, text, integer) is
  'Claims only dry-run hcs_gadgets jobs for the dedicated least-privilege HCS worker.';
