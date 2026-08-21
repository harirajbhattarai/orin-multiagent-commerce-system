-- Split HCS drafting and Shopify replay into separate database principals.
-- The persistent dry-run worker never receives a Shopify credential and can
-- claim only dry-run jobs. The temporary Shopify worker can claim only exact,
-- version-bound human-approved hidden-draft jobs.

do $$
begin
  if not exists (
    select 1 from pg_roles where rolname = 'orin_hcs_shopify_worker'
  ) then
    create role orin_hcs_shopify_worker nologin nosuperuser nocreatedb
      nocreaterole noinherit noreplication nobypassrls;
  end if;
end
$$;

-- Replace the dry-run claim function so even lease-expiry handling is scoped
-- to dry-run work. This removes the final cross-mode mutation path from the
-- persistent HCS worker role.
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
    raise exception 'dedicated HCS dry-run worker client is not allowed'
      using errcode = '42501';
  end if;
  if p_worker_id is null
     or length(p_worker_id) < 8
     or length(p_worker_id) > 128
     or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]+$' then
    raise exception 'invalid worker identifier' using errcode = '22023';
  end if;
  if p_lease_seconds < 60 or p_lease_seconds > 3600 then
    raise exception 'lease must be between 60 and 3600 seconds'
      using errcode = '22023';
  end if;

  with exhausted as (
    update public.content_jobs job
    set status = 'failed', lock_owner = null, locked_at = null,
        lease_expires_at = null,
        last_error_code = 'ORIN_MAX_ATTEMPTS_EXCEEDED'
    where job.client_id = p_client_id
      and job.requested_mode = 'dry-run'
      and job.status in ('leased', 'running')
      and job.lease_expires_at <= statement_timestamp()
      and job.attempt_count >= job.max_attempts
    returning job.client_id, job.job_id
  )
  insert into public.incidents (client_id, severity, code, summary, details)
  select exhausted.client_id, 'critical', 'ORIN_MAX_ATTEMPTS_EXCEEDED',
         'Dedicated HCS dry-run lease expired after the maximum number of claims',
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
      (candidate.status = 'queued'
       and candidate.scheduled_for <= statement_timestamp())
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
      lease_expires_at = statement_timestamp()
        + make_interval(secs => p_lease_seconds),
      last_error_code = null
  where claimed.job_id = v_job_id
    and claimed.client_id = p_client_id
    and claimed.requested_mode = 'dry-run'
  returning claimed.job_id, claimed.client_id, claimed.request_id,
            claimed.requested_mode, claimed.attempt_count, claimed.payload,
            claimed.lease_expires_at;
end;
$$;

create or replace function orin_private.materialize_next_hcs_approved_draft_decision_for_client(
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
  v_draft public.content_drafts%rowtype;
  v_settings public.client_runtime_settings%rowtype;
  v_client public.clients%rowtype;
  v_job_id uuid;
begin
  if p_client_id is distinct from 'hcs_gadgets' then
    raise exception 'dedicated HCS Shopify worker client is not allowed'
      using errcode = '42501';
  end if;

  select decision.*
  into v_decision
  from public.content_decisions decision
  where decision.client_id = p_client_id
    and decision.processing_status = 'recorded'
    and decision.decision = 'approve_hidden_draft'
  order by decision.created_at, decision.decision_id
  for update of decision skip locked
  limit 1;

  if not found then return; end if;

  select * into v_item
  from public.content_plan_items item
  where item.client_id = v_decision.client_id
    and item.content_item_id = v_decision.content_item_id
  for update;
  if not found then
    update public.content_decisions decision
    set processing_status = 'superseded',
        outcome = 'Content item no longer exists before Shopify replay.'
    where decision.decision_id = v_decision.decision_id;
    return query select v_decision.decision_id, null::uuid, 'superseded'::text;
    return;
  end if;
  select * into v_client
  from public.clients client
  where client.client_id = v_decision.client_id;
  if not found then return; end if;
  select * into v_settings
  from public.client_runtime_settings settings
  where settings.client_id = v_decision.client_id;
  if not found then return; end if;

  if v_decision.content_item_version <> v_item.version
     or v_item.status <> 'local_draft_created' then
    update public.content_decisions decision
    set processing_status = 'superseded',
        outcome = 'Content version or stage changed before Shopify replay.'
    where decision.decision_id = v_decision.decision_id;
    return query select v_decision.decision_id, null::uuid, 'superseded'::text;
    return;
  end if;

  if v_client.status <> 'active'
     or not v_settings.request_intake_enabled
     or not v_settings.automation_enabled
     or not v_settings.approved_draft_writes_enabled
     or v_settings.shopify_writes_enabled
     or v_settings.allowed_mode <> 'dry-run'
     or v_settings.max_concurrency <> 1 then
    return;
  end if;

  select draft.* into v_draft
  from public.content_drafts draft
  where draft.client_id = v_item.client_id
    and draft.content_item_id = v_item.content_item_id
    and draft.content_item_version = v_item.version
  for update;
  if not found then return; end if;

  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_by, requested_mode,
    status, scheduled_for, payload, content_plan_item_id,
    approved_draft_id, approved_content_item_version, approved_body_sha256
  ) values (
    v_decision.client_id,
    'decision:' || v_decision.decision_id::text,
    v_decision.request_id,
    v_decision.requested_by,
    'hidden-draft',
    'queued',
    statement_timestamp(),
    '{}'::jsonb,
    v_decision.content_item_id,
    v_draft.draft_id,
    v_draft.content_item_version,
    v_draft.body_sha256
  ) returning content_jobs.job_id into v_job_id;

  update public.content_decisions decision
  set processing_status = 'consumed',
      consumed_at = statement_timestamp(),
      content_job_id = v_job_id,
      outcome = 'Exact HCS reviewed HTML frozen for approval-only unpublished Shopify-draft replay.'
  where decision.decision_id = v_decision.decision_id;

  return query select v_decision.decision_id, v_job_id, 'consumed'::text;
end;
$$;

create or replace function orin_private.claim_next_hcs_approved_draft_job_for_client(
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
    raise exception 'dedicated HCS Shopify worker client is not allowed'
      using errcode = '42501';
  end if;
  if p_worker_id is null
     or length(p_worker_id) < 8
     or length(p_worker_id) > 128
     or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]+$' then
    raise exception 'invalid worker identifier' using errcode = '22023';
  end if;
  if p_lease_seconds < 60 or p_lease_seconds > 3600 then
    raise exception 'lease must be between 60 and 3600 seconds'
      using errcode = '22023';
  end if;

  with exhausted as (
    update public.content_jobs job
    set status = 'failed', lock_owner = null, locked_at = null,
        lease_expires_at = null,
        last_error_code = 'ORIN_MAX_ATTEMPTS_EXCEEDED'
    where job.client_id = p_client_id
      and job.requested_mode = 'hidden-draft'
      and job.status in ('leased', 'running')
      and job.lease_expires_at <= statement_timestamp()
      and job.attempt_count >= job.max_attempts
    returning job.client_id, job.job_id
  )
  insert into public.incidents (client_id, severity, code, summary, details)
  select exhausted.client_id, 'critical', 'ORIN_MAX_ATTEMPTS_EXCEEDED',
         'HCS approval-only lease expired after the maximum number of claims',
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
      and settings.approved_draft_writes_enabled
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
    and candidate.requested_mode = 'hidden-draft'
    and candidate.payload = '{}'::jsonb
    and candidate.attempt_count < candidate.max_attempts
    and candidate.content_plan_item_id is not null
    and candidate.approved_draft_id is not null
    and candidate.approved_content_item_version is not null
    and candidate.approved_body_sha256 is not null
    and (
      (candidate.status = 'queued'
       and candidate.scheduled_for <= statement_timestamp())
      or (
        candidate.status in ('leased', 'running')
        and candidate.lease_expires_at <= statement_timestamp()
      )
    )
    and exists (
      select 1
      from public.content_decisions decision
      join public.content_drafts draft
        on draft.client_id = candidate.client_id
       and draft.draft_id = candidate.approved_draft_id
       and draft.content_item_id = candidate.content_plan_item_id
       and draft.content_item_version = candidate.approved_content_item_version
       and draft.body_sha256 = candidate.approved_body_sha256
      where decision.client_id = candidate.client_id
        and decision.content_job_id = candidate.job_id
        and decision.request_id = candidate.request_id
        and decision.content_item_id = candidate.content_plan_item_id
        and decision.content_item_version = candidate.approved_content_item_version
        and decision.decision = 'approve_hidden_draft'
        and decision.processing_status = 'consumed'
        and candidate.source_job_key = 'decision:' || decision.decision_id::text
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
      lease_expires_at = statement_timestamp()
        + make_interval(secs => p_lease_seconds),
      last_error_code = null
  where claimed.job_id = v_job_id
    and claimed.client_id = p_client_id
    and claimed.requested_mode = 'hidden-draft'
  returning claimed.job_id, claimed.client_id, claimed.request_id,
            claimed.requested_mode, claimed.attempt_count, claimed.payload,
            claimed.lease_expires_at;
end;
$$;

-- Remove the mixed-mode boundary from every HCS principal.
revoke all on function orin_private.materialize_next_hcs_content_decision_for_client(text)
  from orin_hcs_worker, orin_hcs_shopify_worker;
revoke all on function orin_private.claim_next_hcs_job_for_client(text, text, integer)
  from orin_hcs_worker, orin_hcs_shopify_worker;

-- The persistent role receives only the strict dry-run pair.
revoke all on function orin_private.materialize_next_dry_run_decision_for_client(text)
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
       orin_watchdog, orin_prefect_shadow, orin_prefect_scheduler,
       orin_hcs_shopify_worker;
revoke all on function orin_private.claim_next_dry_run_job_for_client(text, text, integer)
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
       orin_watchdog, orin_prefect_shadow, orin_prefect_scheduler,
       orin_hcs_shopify_worker;
grant usage on schema orin_private to orin_hcs_worker;
grant execute on function orin_private.materialize_next_dry_run_decision_for_client(text)
  to orin_hcs_worker;
grant execute on function orin_private.claim_next_dry_run_job_for_client(text, text, integer)
  to orin_hcs_worker;

-- The temporary role receives only exact approved hidden-draft materialization
-- and claim, plus lease-bound completion RPCs required by a claimed job.
revoke all on function orin_private.materialize_next_hcs_approved_draft_decision_for_client(text)
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
       orin_watchdog, orin_prefect_shadow, orin_prefect_scheduler,
       orin_hcs_worker;
revoke all on function orin_private.claim_next_hcs_approved_draft_job_for_client(text, text, integer)
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
       orin_watchdog, orin_prefect_shadow, orin_prefect_scheduler,
       orin_hcs_worker;
grant usage on schema orin_private to orin_hcs_shopify_worker;
grant execute on function orin_private.materialize_next_hcs_approved_draft_decision_for_client(text)
  to orin_hcs_shopify_worker;
grant execute on function orin_private.claim_next_hcs_approved_draft_job_for_client(text, text, integer)
  to orin_hcs_shopify_worker;
grant execute on function orin_private.renew_job_lease(uuid, text, integer)
  to orin_hcs_shopify_worker;
grant execute on function orin_private.get_content_plan_snapshot(uuid, text)
  to orin_hcs_shopify_worker;
grant execute on function orin_private.complete_job_with_review_draft(uuid, text, jsonb, jsonb)
  to orin_hcs_shopify_worker;
grant execute on function orin_private.defer_job(uuid, text, jsonb)
  to orin_hcs_shopify_worker;

comment on function orin_private.claim_next_dry_run_job_for_client(text, text, integer) is
  'Claims only HCS dry-run work; it cannot claim or terminalize hidden-draft leases.';
comment on function orin_private.materialize_next_hcs_approved_draft_decision_for_client(text) is
  'Freezes only an exact version-bound HCS human approval for unpublished Shopify replay.';
comment on function orin_private.claim_next_hcs_approved_draft_job_for_client(text, text, integer) is
  'Claims only exact approval-bound HCS hidden-draft jobs for the temporary Shopify worker.';
