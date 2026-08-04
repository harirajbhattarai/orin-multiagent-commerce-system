-- Phase 6: freeze the exact reviewed draft onto each hidden-draft job.
--
-- The worker snapshot is the only boundary that exposes the immutable HTML,
-- and only to the narrow orin_worker role while it owns an active lease.

alter table public.content_jobs
  add column approved_draft_id uuid,
  add column approved_content_item_version integer
    check (approved_content_item_version is null or approved_content_item_version >= 2),
  add column approved_body_sha256 text
    check (approved_body_sha256 is null or approved_body_sha256 ~ '^[0-9a-f]{64}$'),
  add constraint content_jobs_approved_draft_fkey
    foreign key (client_id, approved_draft_id)
    references public.content_drafts(client_id, draft_id) on delete restrict,
  add constraint content_jobs_hidden_draft_binding_check check (
    (
      approved_draft_id is null
      and approved_content_item_version is null
      and approved_body_sha256 is null
    )
    or (
      requested_mode = 'hidden-draft'
      and content_plan_item_id is not null
      and approved_draft_id is not null
      and approved_content_item_version is not null
      and approved_body_sha256 is not null
    )
  );

create index content_jobs_approved_draft_idx
  on public.content_jobs(client_id, approved_draft_id)
  where approved_draft_id is not null;

create or replace function orin_private.validate_content_draft_hash()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.body_sha256 is distinct from encode(
    extensions.digest(convert_to(new.body_html, 'UTF8'), 'sha256'),
    'hex'
  ) then
    raise exception 'content draft body hash does not match its HTML'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

revoke all on function orin_private.validate_content_draft_hash()
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler, orin_watchdog;

create trigger content_drafts_validate_hash
before insert or update of body_html, body_sha256 on public.content_drafts
for each row execute function orin_private.validate_content_draft_hash();

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
        and settings.shopify_writes_enabled
        and settings.allowed_mode = 'hidden-draft'
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
       or not v_settings.shopify_writes_enabled
       or v_settings.allowed_mode <> 'hidden-draft' then
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
        else 'Exact reviewed HTML frozen for unpublished Shopify-draft replay.'
      end
  where decision.decision_id = v_decision.decision_id;

  return query select v_decision.decision_id, v_job_id, 'consumed'::text;
end;
$$;

revoke all on function orin_private.materialize_next_content_decision()
  from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog;
grant execute on function orin_private.materialize_next_content_decision()
  to orin_worker;

create or replace function orin_private.get_content_plan_snapshot(
  p_job_id uuid,
  p_worker_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.content_jobs%rowtype;
  v_selected public.content_plan_items%rowtype;
  v_draft public.content_drafts%rowtype;
  v_items jsonb;
  v_approved_draft jsonb := null;
  v_handle text;
begin
  select * into v_job
  from public.content_jobs job
  where job.job_id = p_job_id
  for update;
  if not found then raise exception 'job not found' using errcode = 'P0002'; end if;
  if v_job.status not in ('leased', 'running')
     or v_job.lock_owner is distinct from p_worker_id
     or v_job.lease_expires_at <= statement_timestamp() then
    raise exception 'worker does not own an active job lease' using errcode = '42501';
  end if;

  if v_job.content_plan_item_id is not null then
    select * into v_selected
    from public.content_plan_items item
    where item.client_id = v_job.client_id
      and item.content_item_id = v_job.content_plan_item_id;
  else
    select * into v_selected
    from public.content_plan_items item
    where item.client_id = v_job.client_id
      and item.status = 'planned'
      and item.expected_draft_date <=
        (statement_timestamp() at time zone 'Europe/London')::date
    order by item.item_number, item.content_item_id
    for update skip locked
    limit 1;
    if found then
      update public.content_jobs job
      set content_plan_item_id = v_selected.content_item_id
      where job.job_id = v_job.job_id;
    end if;
  end if;

  if v_job.requested_mode = 'hidden-draft' then
    if v_selected.content_item_id is null
       or v_job.approved_draft_id is null
       or v_job.approved_content_item_version is null
       or v_job.approved_body_sha256 is null then
      raise exception 'hidden-draft job is missing its frozen review draft'
        using errcode = '23514';
    end if;
    select draft.* into v_draft
    from public.content_drafts draft
    where draft.client_id = v_job.client_id
      and draft.draft_id = v_job.approved_draft_id
      and draft.content_item_id = v_selected.content_item_id
      and draft.content_item_version = v_job.approved_content_item_version
      and draft.body_sha256 = v_job.approved_body_sha256;
    if not found or v_selected.version <> v_draft.content_item_version
       or v_selected.status <> 'local_draft_created' then
      raise exception 'frozen review draft no longer matches the selected content version'
        using errcode = '23514';
    end if;
    v_handle := coalesce(
      nullif(v_selected.shopify_handle, ''),
      regexp_replace(regexp_replace(v_selected.draft_path, '^.*/', ''), '\.html$', '')
    );
    if v_handle !~ '^[a-z0-9]+(-[a-z0-9]+)*$' then
      raise exception 'approved review draft has no canonical Shopify handle'
        using errcode = '23514';
    end if;
    v_approved_draft := jsonb_build_object(
      'draft_id', v_draft.draft_id,
      'content_item_id', v_draft.content_item_id,
      'content_item_version', v_draft.content_item_version,
      'source_run_id', v_draft.source_run_id,
      'title', v_draft.title,
      'body_html', v_draft.body_html,
      'body_sha256', v_draft.body_sha256,
      'handle', v_handle
    );
  end if;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'content_item_id', item.content_item_id,
        'item_number', item.item_number,
        'target_date', item.target_date,
        'expected_draft_date', item.expected_draft_date,
        'cluster', item.cluster,
        'decision', item.decision,
        'status', item.status,
        'topic', item.topic,
        'target_keyword', item.target_keyword,
        'draft_path', item.draft_path,
        'notes', item.notes,
        'shopify_article_id', item.shopify_article_id,
        'shopify_handle', item.shopify_handle,
        'version', item.version
      ) order by item.item_number
    ),
    '[]'::jsonb
  ) into v_items
  from public.content_plan_items item
  where item.client_id = v_job.client_id;

  return jsonb_build_object(
    'schema', 'orin.content-plan-snapshot/v1',
    'client_id', v_job.client_id,
    'execution_job_id', v_job.job_id,
    'selected_item_id', v_selected.content_item_id,
    'selected_item_number', v_selected.item_number,
    'generated_at', statement_timestamp(),
    'items', v_items,
    'approved_draft', v_approved_draft
  );
end;
$$;

revoke all on function orin_private.get_content_plan_snapshot(uuid, text)
  from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog;
grant execute on function orin_private.get_content_plan_snapshot(uuid, text)
  to orin_worker;

comment on column public.content_jobs.approved_draft_id is
  'Immutable review draft frozen onto a hidden-draft job when approval is consumed.';
comment on function orin_private.get_content_plan_snapshot(uuid, text) is
  'Lease-bound worker snapshot; hidden-draft jobs include only their exact frozen reviewed HTML.';
