-- Turn an accepted request-changes decision into a real, version-bound
-- regeneration job.  The previous materializers advanced the item version
-- and consumed the decision, but left no job for a worker to execute.
--
-- A trigger keeps the repair common to the tenant-bound Hoverboard and HCS
-- materializers.  The public job payload remains empty; the private,
-- lease-bound snapshot attaches the exact human revision note instead.

create or replace function orin_private.queue_consumed_content_revision()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_item public.content_plan_items%rowtype;
  v_job_id uuid;
begin
  if old.processing_status <> 'recorded'
     or new.processing_status <> 'consumed'
     or new.decision <> 'request_changes'
     or new.content_job_id is not null
     or new.client_id not in ('hoverboard_store', 'hcs_gadgets') then
    return new;
  end if;

  select * into v_item
  from public.content_plan_items item
  where item.client_id = new.client_id
    and item.content_item_id = new.content_item_id
  for update;

  if not found
     or v_item.status <> 'needs_human_review'
     or v_item.version <> new.content_item_version + 1 then
    raise exception 'consumed revision is not bound to the expected content version'
      using errcode = '23514';
  end if;

  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_by, requested_mode,
    status, scheduled_for, payload, content_plan_item_id
  ) values (
    new.client_id,
    'decision:' || new.decision_id::text,
    new.request_id,
    new.requested_by,
    'dry-run',
    'queued',
    statement_timestamp(),
    '{}'::jsonb,
    new.content_item_id
  ) returning content_jobs.job_id into v_job_id;

  update public.content_plan_items item
  set status = 'in_progress'
  where item.client_id = new.client_id
    and item.content_item_id = new.content_item_id;

  new.content_job_id := v_job_id;
  new.outcome := 'Revision draft-generation job queued.';
  return new;
end;
$$;

revoke all on function orin_private.queue_consumed_content_revision()
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
       orin_watchdog, orin_hcs_worker, orin_hcs_shopify_worker;

drop trigger if exists content_decisions_queue_consumed_revision
  on public.content_decisions;
create trigger content_decisions_queue_consumed_revision
before update of processing_status, content_job_id
on public.content_decisions
for each row execute function orin_private.queue_consumed_content_revision();

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
  v_revision_note text := null;
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

  select nullif(btrim(decision.note), '')
  into v_revision_note
  from public.content_decisions decision
  where decision.client_id = v_job.client_id
    and decision.content_item_id = v_selected.content_item_id
    and decision.content_job_id = v_job.job_id
    and decision.decision = 'request_changes'
    and decision.processing_status = 'consumed'
  order by decision.created_at desc, decision.decision_id desc
  limit 1;

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
        'notes', case
          when item.content_item_id = v_selected.content_item_id
               and v_revision_note is not null then
            concat_ws(
              E'\n\n',
              nullif(btrim(item.notes), ''),
              'Human revision request (must be applied):' || E'\n' || v_revision_note
            )
          else item.notes
        end,
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
    'revision_request', v_revision_note,
    'items', v_items,
    'approved_draft', v_approved_draft
  );
end;
$$;

revoke all on function orin_private.get_content_plan_snapshot(uuid, text)
  from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog,
       orin_hcs_shopify_worker;
grant execute on function orin_private.get_content_plan_snapshot(uuid, text)
  to orin_worker, orin_hcs_worker;

comment on function orin_private.get_content_plan_snapshot(uuid, text) is
  'Lease-bound worker snapshot; revision jobs receive only their exact human change request and hidden-draft jobs receive only their frozen reviewed HTML.';
