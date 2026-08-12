-- Allow the permanent production worker to promote only an exact,
-- human-approved review draft while the scheduler remains dry-run-only.
--
-- This is deliberately separate from the legacy broad Shopify write switch.
-- The narrow gate can only be enabled when broad writes are disabled and the
-- client's allowed scheduler mode remains dry-run.

alter table public.client_runtime_settings
  add column approved_draft_writes_enabled boolean not null default false,
  add constraint client_runtime_settings_approved_draft_gate_check check (
    not approved_draft_writes_enabled
    or (allowed_mode = 'dry-run' and not shopify_writes_enabled)
  );

revoke all on table public.client_runtime_settings from authenticated;
grant select (
  client_id, request_intake_enabled, automation_enabled,
  shopify_writes_enabled, approved_draft_writes_enabled,
  max_concurrency, allowed_mode, updated_at
) on table public.client_runtime_settings to authenticated;

create or replace function orin_private.materialize_next_content_decision()
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
  v_mode text;
begin
  select decision.*
  into v_decision
  from public.content_decisions decision
  join public.content_plan_items item
    on item.client_id = decision.client_id
   and item.content_item_id = decision.content_item_id
  join public.clients client on client.client_id = decision.client_id
  join public.client_runtime_settings settings on settings.client_id = decision.client_id
  where decision.processing_status = 'recorded'
    and (
      decision.decision = 'request_changes'
      or decision.content_item_version <> item.version
      or (decision.decision = 'approve_concept' and item.status <> 'planned')
      or (decision.decision = 'approve_hidden_draft' and item.status <> 'local_draft_created')
      or (
        decision.decision = 'approve_concept'
        and client.status = 'active'
        and settings.request_intake_enabled
        and settings.automation_enabled
      )
      or (
        decision.decision = 'approve_hidden_draft'
        and client.status = 'active'
        and settings.request_intake_enabled
        and settings.automation_enabled
        and settings.approved_draft_writes_enabled
        and not settings.shopify_writes_enabled
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
     or (v_decision.decision = 'approve_concept' and v_item.status <> 'planned')
     or (v_decision.decision = 'approve_hidden_draft' and v_item.status <> 'local_draft_created') then
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

  if v_decision.decision = 'approve_concept' then
    if v_client.status <> 'active'
       or not v_settings.request_intake_enabled
       or not v_settings.automation_enabled then
      return;
    end if;
    v_mode := 'dry-run';
  else
    if v_client.status <> 'active'
       or not v_settings.request_intake_enabled
       or not v_settings.automation_enabled
       or not v_settings.approved_draft_writes_enabled
       or v_settings.shopify_writes_enabled
       or v_settings.allowed_mode <> 'dry-run' then
      return;
    end if;
    select draft.* into v_draft
    from public.content_drafts draft
    where draft.client_id = v_item.client_id
      and draft.content_item_id = v_item.content_item_id
      and draft.content_item_version = v_item.version
    for update;
    if not found then return; end if;
    v_mode := 'hidden-draft';
  end if;

  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_by, requested_mode,
    status, scheduled_for, payload, content_plan_item_id,
    approved_draft_id, approved_content_item_version, approved_body_sha256
  ) values (
    v_decision.client_id,
    'decision:' || v_decision.decision_id::text,
    v_decision.request_id,
    v_decision.requested_by,
    v_mode,
    'queued',
    statement_timestamp(),
    '{}'::jsonb,
    v_decision.content_item_id,
    case when v_mode = 'hidden-draft' then v_draft.draft_id else null end,
    case when v_mode = 'hidden-draft' then v_draft.content_item_version else null end,
    case when v_mode = 'hidden-draft' then v_draft.body_sha256 else null end
  ) returning content_jobs.job_id into v_job_id;

  if v_decision.decision = 'approve_concept' then
    update public.content_plan_items item
    set status = 'in_progress'
    where item.client_id = v_item.client_id
      and item.content_item_id = v_item.content_item_id;
  end if;

  update public.content_decisions decision
  set processing_status = 'consumed',
      consumed_at = statement_timestamp(),
      content_job_id = v_job_id,
      outcome = case
        when v_mode = 'dry-run' then 'Draft-generation job queued.'
        else 'Exact reviewed HTML frozen for approval-only unpublished Shopify-draft replay.'
      end
  where decision.decision_id = v_decision.decision_id;

  return query select v_decision.decision_id, v_job_id, 'consumed'::text;
end;
$$;

revoke all on function orin_private.materialize_next_content_decision()
  from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog,
       orin_prefect_shadow, orin_prefect_scheduler;
grant execute on function orin_private.materialize_next_content_decision()
  to orin_worker;

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
    and settings.request_intake_enabled
    and settings.automation_enabled
    and settings.max_concurrency = 1
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
        and candidate.payload = '{}'::jsonb
        and candidate.attempt_count < candidate.max_attempts
        and (
          (candidate.status = 'queued' and candidate.scheduled_for <= statement_timestamp())
          or (
            candidate.status in ('leased', 'running')
            and candidate.lease_expires_at <= statement_timestamp()
          )
        )
        and (
          (
            candidate.requested_mode = 'dry-run'
            and settings.allowed_mode = 'dry-run'
            and not settings.shopify_writes_enabled
          )
          or (
            candidate.requested_mode = 'hidden-draft'
            and settings.allowed_mode = 'dry-run'
            and not settings.shopify_writes_enabled
            and settings.approved_draft_writes_enabled
            and candidate.content_plan_item_id is not null
            and candidate.approved_draft_id is not null
            and candidate.approved_content_item_version is not null
            and candidate.approved_body_sha256 is not null
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
  join public.client_runtime_settings settings
    on settings.client_id = candidate.client_id
  where candidate.client_id = v_client_id
    and candidate.payload = '{}'::jsonb
    and candidate.attempt_count < candidate.max_attempts
    and (
      (candidate.status = 'queued' and candidate.scheduled_for <= statement_timestamp())
      or (
        candidate.status in ('leased', 'running')
        and candidate.lease_expires_at <= statement_timestamp()
      )
    )
    and (
      (
        candidate.requested_mode = 'dry-run'
        and settings.allowed_mode = 'dry-run'
        and not settings.shopify_writes_enabled
      )
      or (
        candidate.requested_mode = 'hidden-draft'
        and settings.allowed_mode = 'dry-run'
        and not settings.shopify_writes_enabled
        and settings.approved_draft_writes_enabled
        and candidate.content_plan_item_id is not null
        and candidate.approved_draft_id is not null
        and candidate.approved_content_item_version is not null
        and candidate.approved_body_sha256 is not null
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
      )
    )
  order by
    case when candidate.status in ('leased', 'running') then 0 else 1 end,
    candidate.scheduled_for,
    candidate.created_at,
    candidate.job_id
  for update of candidate skip locked
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

revoke all on function orin_private.claim_next_job(text, integer)
from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog,
     orin_prefect_shadow, orin_prefect_scheduler;
grant execute on function orin_private.claim_next_job(text, integer) to orin_worker;

comment on column public.client_runtime_settings.approved_draft_writes_enabled is
  'Allows only exact, consumed, version-and-hash-bound human approvals to create unpublished Shopify drafts.';
comment on function orin_private.materialize_next_content_decision() is
  'Materializes one gated review decision; hidden drafts require the narrow approval-only capability.';
comment on function orin_private.claim_next_job(text, integer) is
  'Claims dry-run work or an exact approval-bound hidden draft; broad hidden-draft mode is not claimable.';
