-- Phase 6: durable, version-bound content review workflow.
--
-- Browser users may record decisions, but only the narrow orin_worker role can
-- materialize an eligible decision into a job. A concept approval can only
-- create a dry-run job. A hidden-draft approval additionally requires a
-- matching immutable draft and all existing Shopify write gates.

create table public.content_drafts (
  draft_id uuid primary key default gen_random_uuid(),
  client_id text not null,
  content_item_id uuid not null,
  content_item_version integer not null check (content_item_version >= 2),
  source_run_id text not null,
  title text not null check (nullif(btrim(title), '') is not null),
  body_html text not null
    check (nullif(btrim(body_html), '') is not null and char_length(body_html) <= 500000),
  body_sha256 text not null check (body_sha256 ~ '^[0-9a-f]{64}$'),
  word_count integer not null check (word_count > 0),
  meta_title text not null default '' check (char_length(meta_title) <= 300),
  meta_description text not null default '' check (char_length(meta_description) <= 1000),
  quality_score smallint check (quality_score between 0 and 100),
  checks jsonb not null default '[]'::jsonb check (jsonb_typeof(checks) = 'array'),
  created_at timestamptz not null default now(),
  unique (client_id, content_item_id, content_item_version),
  unique (client_id, draft_id),
  foreign key (client_id, content_item_id)
    references public.content_plan_items(client_id, content_item_id) on delete restrict,
  foreign key (client_id, source_run_id)
    references public.runs(client_id, run_id) on delete restrict
);

create index content_drafts_item_idx
  on public.content_drafts(client_id, content_item_id, content_item_version desc);

alter table public.content_drafts enable row level security;
revoke all on table public.content_drafts
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler, orin_watchdog;
grant select on table public.content_drafts to authenticated;

create policy content_drafts_select_for_members
on public.content_drafts for select to authenticated
using (
  (select auth.uid()) is not null
  and exists (
    select 1
    from public.client_members membership
    where membership.client_id = content_drafts.client_id
      and membership.user_id = (select auth.uid())
  )
);

alter table public.content_decisions
  drop constraint content_decisions_decision_check,
  add constraint content_decisions_decision_check
    check (decision in ('approve_concept', 'approve_hidden_draft', 'request_changes')),
  add column content_job_id uuid,
  add column outcome text not null default '' check (char_length(outcome) <= 500),
  add constraint content_decisions_content_job_fkey
    foreign key (client_id, content_job_id)
    references public.content_jobs(client_id, job_id) on delete restrict;

create unique index content_decisions_one_action_per_version_idx
  on public.content_decisions(client_id, content_item_id, content_item_version, decision);

-- Earlier Phase 6 receipts were explicitly evidence-only. Preserve them, but
-- never reinterpret one as executable intent after this consumer is deployed.
update public.content_decisions
set processing_status = 'superseded',
    outcome = 'Recorded before the durable review workflow; preserved as evidence only.'
where processing_status = 'recorded';

create or replace function orin_private.validate_content_decision()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_item public.content_plan_items%rowtype;
begin
  if v_uid is null then
    raise exception 'authenticated user required' using errcode = '42501';
  end if;

  if not exists (
    select 1
    from public.client_members membership
    where membership.client_id = new.client_id
      and membership.user_id = v_uid
      and membership.role in ('owner', 'operator')
  ) then
    raise exception 'client operator membership required' using errcode = '42501';
  end if;

  select item.*
  into v_item
  from public.content_plan_items item
  where item.client_id = new.client_id
    and item.content_item_id = new.content_item_id;

  if not found then
    raise exception 'content item not found' using errcode = 'P0002';
  end if;
  if new.content_item_version is distinct from v_item.version then
    raise exception 'content item version changed; refresh before deciding'
      using errcode = '40001';
  end if;

  if new.decision = 'approve_concept' and v_item.status <> 'planned' then
    raise exception 'concept approval requires a planned item' using errcode = '23514';
  elsif new.decision = 'approve_hidden_draft' then
    if v_item.status <> 'local_draft_created' or not exists (
      select 1
      from public.content_drafts draft
      where draft.client_id = new.client_id
        and draft.content_item_id = new.content_item_id
        and draft.content_item_version = new.content_item_version
    ) then
      raise exception 'hidden-draft approval requires the matching review draft'
        using errcode = '23514';
    end if;
  elsif new.decision = 'request_changes'
    and v_item.status not in ('planned', 'local_draft_created', 'checks_failed', 'needs_human_review') then
    raise exception 'change request is not valid for the current content stage'
      using errcode = '23514';
  end if;

  new.requested_by := v_uid;
  new.processing_status := 'recorded';
  new.consumed_at := null;
  new.content_job_id := null;
  new.outcome := '';
  return new;
end;
$$;

revoke all on function orin_private.validate_content_decision()
  from public, anon, authenticated;

-- Process at most one eligible dashboard decision. Closed runtime gates leave
-- approvals recorded and visible without creating work. Change requests and
-- stale decisions can still terminalize while gates are closed.
create or replace function orin_private.materialize_next_content_decision()
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

  if not found then
    return;
  end if;

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
    set status = 'needs_human_review',
        version = item.version + 1
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
       or v_settings.allowed_mode <> 'hidden-draft'
       or not exists (
         select 1 from public.content_drafts draft
         where draft.client_id = v_item.client_id
           and draft.content_item_id = v_item.content_item_id
           and draft.content_item_version = v_item.version
       ) then
      return;
    end if;
    v_mode := 'hidden-draft';
  end if;

  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_by, requested_mode,
    status, scheduled_for, payload, content_plan_item_id
  ) values (
    v_decision.client_id,
    'decision:' || v_decision.decision_id::text,
    v_decision.request_id,
    v_decision.requested_by,
    v_mode,
    'queued',
    statement_timestamp(),
    '{}'::jsonb,
    v_decision.content_item_id
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
        else 'Unpublished Shopify-draft job queued.'
      end
  where decision.decision_id = v_decision.decision_id;

  return query select v_decision.decision_id, v_job_id, 'consumed'::text;
end;
$$;

revoke all on function orin_private.materialize_next_content_decision()
  from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog;
grant execute on function orin_private.materialize_next_content_decision()
  to orin_worker;

-- Finalize a normal worker result and, for a selected successful dry-run,
-- atomically persist the exact generated HTML as the next content version.
create or replace function orin_private.complete_job_with_review_draft(
  p_job_id uuid,
  p_worker_id text,
  p_final_result jsonb,
  p_review_draft jsonb default null
)
returns table (run_id text, status text, replayed boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_completion record;
  v_job public.content_jobs%rowtype;
  v_item public.content_plan_items%rowtype;
  v_new_version integer;
  v_result_status text := p_final_result ->> 'status';
  v_result_run_id text := p_final_result ->> 'run_id';
begin
  select * into v_completion
  from orin_private.complete_job(p_job_id, p_worker_id, p_final_result);

  if v_completion.replayed then
    return query select v_completion.run_id, v_completion.status, true;
    return;
  end if;

  select * into v_job
  from public.content_jobs job
  where job.job_id = p_job_id;

  if v_job.requested_mode = 'dry-run' and v_job.content_plan_item_id is not null then
    select * into v_item
    from public.content_plan_items item
    where item.client_id = v_job.client_id
      and item.content_item_id = v_job.content_plan_item_id
    for update;

    if v_result_status = 'completed' and p_final_result ->> 'job_id' is not null then
      if jsonb_typeof(p_review_draft) <> 'object'
         or p_review_draft ->> 'content_item_id' is distinct from v_item.content_item_id::text
         or (p_review_draft ->> 'content_item_version')::integer is distinct from v_item.version
         or p_review_draft ->> 'title' is null
         or p_review_draft ->> 'body_html' is null
         or p_review_draft ->> 'body_sha256' !~ '^[0-9a-f]{64}$'
         or coalesce((p_review_draft ->> 'word_count')::integer, 0) <= 0 then
        raise exception 'selected dry-run is missing a valid version-bound review draft'
          using errcode = '23514';
      end if;

      v_new_version := v_item.version + 1;
      insert into public.content_drafts (
        client_id, content_item_id, content_item_version, source_run_id,
        title, body_html, body_sha256, word_count, meta_title,
        meta_description, quality_score, checks
      ) values (
        v_item.client_id,
        v_item.content_item_id,
        v_new_version,
        v_result_run_id,
        p_review_draft ->> 'title',
        p_review_draft ->> 'body_html',
        p_review_draft ->> 'body_sha256',
        (p_review_draft ->> 'word_count')::integer,
        coalesce(p_review_draft ->> 'meta_title', ''),
        coalesce(p_review_draft ->> 'meta_description', ''),
        (p_review_draft ->> 'quality_score')::smallint,
        coalesce(p_review_draft -> 'checks', '[]'::jsonb)
      );

      update public.content_plan_items item
      set status = 'local_draft_created',
          version = v_new_version,
          last_run_id = v_result_run_id
      where item.client_id = v_item.client_id
        and item.content_item_id = v_item.content_item_id;
    elsif v_result_status in ('blocked', 'failed') then
      update public.content_plan_items item
      set status = 'checks_failed',
          version = item.version + 1,
          last_run_id = v_result_run_id
      where item.client_id = v_item.client_id
        and item.content_item_id = v_item.content_item_id;
    end if;
  end if;

  return query select v_completion.run_id, v_completion.status, false;
end;
$$;

revoke all on function orin_private.complete_job_with_review_draft(uuid, text, jsonb, jsonb)
  from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog;
grant execute on function orin_private.complete_job_with_review_draft(uuid, text, jsonb, jsonb)
  to orin_worker;

-- Permit the approved local review draft to advance to an unpublished Shopify
-- draft. The existing reconciliation and never-publish checks remain intact.
create or replace function orin_private.apply_content_plan_run_result()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_item_id uuid;
  v_item_number integer;
  v_reported_number text;
begin
  if new.job_id is null then return new; end if;

  select job.content_plan_item_id into v_item_id
  from public.content_jobs job
  where job.client_id = new.client_id and job.job_id = new.job_id;
  if v_item_id is null then return new; end if;

  select item.item_number into v_item_number
  from public.content_plan_items item
  where item.client_id = new.client_id and item.content_item_id = v_item_id;

  v_reported_number := new.final_result ->> 'job_id';
  if v_reported_number is not null and v_reported_number is distinct from v_item_number::text then
    raise exception 'run result content item does not match database ownership'
      using errcode = '23514';
  end if;

  if new.requested_mode = 'hidden-draft'
     and new.shopify_create_count = 1
     and new.shopify_article_id is not null
     and new.reconciliation_status = 'reconciled'
     and not new.shopify_published then
    update public.content_plan_items item
    set status = 'draft_created',
        shopify_article_id = new.shopify_article_id,
        last_run_id = new.run_id,
        version = item.version + 1
    where item.client_id = new.client_id
      and item.content_item_id = v_item_id
      and (
        item.status = 'local_draft_created'
        or (item.status = 'draft_created' and item.shopify_article_id = new.shopify_article_id)
      );
    if not found then
      raise exception 'content-plan state transition rejected' using errcode = '23514';
    end if;
  end if;
  return new;
end;
$$;

revoke all on function orin_private.apply_content_plan_run_result()
  from public, anon, authenticated, orin_api, orin_worker;

create view public.client_content_review_items
with (security_invoker = true)
as
select
  item.client_id,
  item.item_number,
  item.content_item_id,
  item.version,
  item.status,
  case
    when item.status = 'planned' then 'concept'
    when item.status = 'local_draft_created' then 'draft'
    else 'unavailable'
  end as review_kind,
  coalesce(draft.title, item.topic, 'Untitled content concept') as title,
  coalesce(item.target_keyword, '') as target_keyword,
  coalesce(item.cluster, 'Content plan') as cluster,
  item.expected_draft_date,
  draft.content_item_version as draft_version,
  draft.body_html,
  draft.body_sha256,
  draft.word_count,
  draft.meta_title,
  draft.meta_description,
  draft.quality_score,
  draft.checks,
  draft.source_run_id,
  latest_decision.decision as latest_decision,
  latest_decision.processing_status as latest_decision_status,
  latest_decision.outcome as latest_decision_outcome,
  latest_decision.created_at as latest_decision_at
from public.content_plan_items item
left join public.content_drafts draft
  on draft.client_id = item.client_id
 and draft.content_item_id = item.content_item_id
 and draft.content_item_version = item.version
left join lateral (
  select decision.decision, decision.processing_status, decision.outcome, decision.created_at
  from public.content_decisions decision
  where decision.client_id = item.client_id
    and decision.content_item_id = item.content_item_id
    and decision.content_item_version = item.version
  order by decision.created_at desc, decision.decision_id desc
  limit 1
) latest_decision on true;

revoke all on table public.client_content_review_items from public, anon, authenticated;
grant select on table public.client_content_review_items to authenticated;

comment on table public.content_drafts is
  'Immutable tenant-scoped HTML review drafts, bound to a content-plan version and source run.';
comment on function orin_private.materialize_next_content_decision() is
  'Worker-only decision consumer; closed runtime gates never create approval jobs.';
comment on view public.client_content_review_items is
  'Tenant-safe, version-bound concept and full-draft review projection.';
