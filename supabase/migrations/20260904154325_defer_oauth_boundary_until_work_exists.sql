-- Keep the generic OAuth draft worker quiet while it has no actionable work.
--
-- The original worker asserted fresh OAuth credentials before it checked for a
-- pending approval or claimable job. Once an otherwise idle tenant's token
-- expired, every scheduler poll therefore raised an OperationalError. Preserve
-- the fail-closed credential boundary for real work, but evaluate it only after
-- an immutable approved decision/job has been selected.

create or replace function orin_private.materialize_next_oauth_approved_draft_decision(
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
  v_job_id uuid;
begin
  select decision.* into v_decision
  from public.content_decisions decision
  where decision.client_id = p_client_id
    and decision.processing_status = 'recorded'
    and decision.decision = 'approve_hidden_draft'
  order by decision.created_at, decision.decision_id
  for update of decision skip locked
  limit 1;
  if not found then return; end if;

  perform orin_private.assert_oauth_approved_draft_boundary(p_client_id);

  select * into v_item
  from public.content_plan_items item
  where item.client_id = p_client_id
    and item.content_item_id = v_decision.content_item_id
  for update;
  if not found then
    update public.content_decisions
    set processing_status = 'superseded',
        outcome = 'Content item no longer exists before OAuth Shopify replay.'
    where content_decisions.decision_id = v_decision.decision_id;
    return query select v_decision.decision_id, null::uuid, 'superseded'::text;
    return;
  end if;
  if v_decision.content_item_version <> v_item.version
     or v_item.status <> 'local_draft_created' then
    update public.content_decisions
    set processing_status = 'superseded',
        outcome = 'Content version or stage changed before OAuth Shopify replay.'
    where content_decisions.decision_id = v_decision.decision_id;
    return query select v_decision.decision_id, null::uuid, 'superseded'::text;
    return;
  end if;

  select * into v_draft
  from public.content_drafts draft
  where draft.client_id = p_client_id
    and draft.content_item_id = v_item.content_item_id
    and draft.content_item_version = v_item.version
  for update;
  if not found then return; end if;

  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_by, requested_mode,
    status, scheduled_for, payload, content_plan_item_id,
    approved_draft_id, approved_content_item_version, approved_body_sha256
  ) values (
    p_client_id,
    'decision:' || v_decision.decision_id::text,
    v_decision.request_id,
    v_decision.requested_by,
    'hidden-draft',
    'queued',
    statement_timestamp(),
    '{}'::jsonb,
    v_item.content_item_id,
    v_draft.draft_id,
    v_draft.content_item_version,
    v_draft.body_sha256
  ) returning content_jobs.job_id into v_job_id;

  update public.content_decisions
  set processing_status = 'consumed',
      consumed_at = statement_timestamp(),
      content_job_id = v_job_id,
      outcome = 'Exact OAuth-client reviewed HTML frozen for one unpublished Shopify draft.'
  where content_decisions.decision_id = v_decision.decision_id;

  return query select v_decision.decision_id, v_job_id, 'consumed'::text;
end;
$$;

create or replace function orin_private.claim_next_oauth_approved_draft_job(
  p_worker_id text,
  p_client_id text,
  p_lease_seconds integer default 1200
)
returns table (
  job_id uuid, client_id text, request_id uuid, requested_mode text,
  attempt_count smallint, payload jsonb, lease_expires_at timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_job_id uuid;
begin
  if p_client_id in ('hoverboard_store', 'hcs_gadgets') then
    raise exception 'dedicated production tenants cannot use the OAuth draft worker'
      using errcode = '42501';
  end if;
  if p_worker_id is null or length(p_worker_id) not between 8 and 128
     or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]+$' then
    raise exception 'invalid OAuth draft worker identifier' using errcode = '22023';
  end if;
  if p_lease_seconds not between 60 and 3600 then
    raise exception 'lease must be between 60 and 3600 seconds' using errcode = '22023';
  end if;

  if exists (
    select 1 from public.content_jobs active
    where active.client_id = p_client_id
      and active.status in ('leased', 'running')
      and active.lease_expires_at > statement_timestamp()
  ) then return; end if;

  select candidate.job_id into v_job_id
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
      (candidate.status = 'queued' and candidate.scheduled_for <= statement_timestamp())
      or (candidate.status in ('leased', 'running')
          and candidate.lease_expires_at <= statement_timestamp())
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
  order by case when candidate.status in ('leased', 'running') then 0 else 1 end,
           candidate.scheduled_for, candidate.created_at, candidate.job_id
  for update of candidate skip locked
  limit 1;
  if v_job_id is null then return; end if;

  perform orin_private.assert_oauth_approved_draft_boundary(p_client_id);

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
    and claimed.requested_mode = 'hidden-draft'
  returning claimed.job_id, claimed.client_id, claimed.request_id,
            claimed.requested_mode, claimed.attempt_count, claimed.payload,
            claimed.lease_expires_at;
end;
$$;
