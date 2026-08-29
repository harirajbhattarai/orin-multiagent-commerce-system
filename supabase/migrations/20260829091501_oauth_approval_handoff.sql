-- Give generic OAuth tenants a no-code, fail-closed handoff between their
-- recurring dry-run scheduler and the exclusive unpublished-draft worker.
--
-- The scheduler is paused under the same row lock used by the enqueue path.
-- The exact version-bound decision is then recorded and materialized while
-- broad Shopify writes remain closed. A successful one-draft completion
-- restores only the recurring schedule that this handoff paused.

create table public.client_approval_handoffs (
  handoff_id uuid primary key default gen_random_uuid(),
  client_id text not null references public.clients(client_id) on delete restrict,
  request_id uuid not null,
  content_item_id uuid not null,
  content_item_version integer not null check (content_item_version >= 2),
  requested_by uuid not null,
  status text not null default 'preparing'
    check (status in ('preparing', 'processing', 'completed', 'blocked', 'cancelled')),
  resume_recurring_schedule boolean not null default false,
  prior_next_run_at timestamptz,
  decision_id uuid references public.content_decisions(decision_id) on delete restrict,
  content_job_id uuid references public.content_jobs(job_id) on delete restrict,
  last_error text not null default '' check (char_length(last_error) <= 500),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (client_id, request_id),
  foreign key (client_id, content_item_id)
    references public.content_plan_items(client_id, content_item_id) on delete restrict
);

create unique index client_approval_handoffs_one_active_client_idx
  on public.client_approval_handoffs(client_id)
  where status in ('preparing', 'processing');

create trigger client_approval_handoffs_set_updated_at
before update on public.client_approval_handoffs
for each row execute function orin_private.set_updated_at();

alter table public.client_approval_handoffs enable row level security;
revoke all on table public.client_approval_handoffs from public, anon, authenticated;
grant select on table public.client_approval_handoffs to authenticated;

create policy client_approval_handoffs_select_for_members
on public.client_approval_handoffs for select to authenticated
using (
  (select auth.uid()) is not null
  and exists (
    select 1
    from public.client_members membership
    where membership.client_id = client_approval_handoffs.client_id
      and membership.user_id = (select auth.uid())
  )
);

create or replace function orin_private.restore_oauth_approval_handoff(
  p_handoff_id uuid,
  p_terminal_status text,
  p_error text default ''
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_handoff public.client_approval_handoffs%rowtype;
  v_schedule public.client_recurring_pilot_schedules%rowtype;
  v_next_run timestamptz;
  v_local_date date;
begin
  if p_terminal_status not in ('completed', 'blocked', 'cancelled') then
    raise exception 'invalid approval handoff terminal status' using errcode = '22023';
  end if;

  select * into v_handoff
  from public.client_approval_handoffs handoff
  where handoff.handoff_id = p_handoff_id
  for update;
  if not found or v_handoff.status in ('completed', 'blocked', 'cancelled') then
    return;
  end if;

  if p_terminal_status in ('completed', 'cancelled')
     and v_handoff.resume_recurring_schedule then
    select * into v_schedule
    from public.client_recurring_pilot_schedules schedule
    where schedule.client_id = v_handoff.client_id
    for update;
    if not found then
      raise exception 'approval handoff lost its recurring schedule' using errcode = '55000';
    end if;
    if exists (
      select 1 from public.content_jobs job
      where job.client_id = v_handoff.client_id
        and job.status in ('queued', 'leased', 'running')
    ) or exists (
      select 1 from public.incidents incident
      where incident.client_id = v_handoff.client_id
        and incident.status <> 'resolved'
    ) then
      update public.client_approval_handoffs handoff
      set status = 'blocked',
          last_error = 'Recurring schedule remained paused because active work or an incident exists.',
          completed_at = statement_timestamp()
      where handoff.handoff_id = p_handoff_id;
      return;
    end if;

    v_next_run := v_handoff.prior_next_run_at;
    if v_next_run is null or v_next_run <= statement_timestamp() then
      v_local_date := (statement_timestamp() at time zone v_schedule.timezone)::date;
      v_next_run := (v_local_date::timestamp + v_schedule.local_run_time)
        at time zone v_schedule.timezone;
      if v_next_run <= statement_timestamp() then
        v_next_run := ((v_local_date + 1)::timestamp + v_schedule.local_run_time)
          at time zone v_schedule.timezone;
      end if;
    end if;

    update public.client_recurring_pilot_schedules schedule
    set enabled = true, next_run_at = v_next_run
    where schedule.client_id = v_handoff.client_id;
    update public.scheduler_health health
    set state = 'healthy',
        scheduler_owner = 'prefect:orin-tenant-pilot',
        last_expected_run_at = v_next_run
    where health.client_id = v_handoff.client_id;
  else
    update public.scheduler_health health
    set state = 'disabled', scheduler_owner = null
    where health.client_id = v_handoff.client_id;
  end if;

  update public.client_approval_handoffs handoff
  set status = p_terminal_status,
      last_error = left(coalesce(p_error, ''), 500),
      completed_at = statement_timestamp()
  where handoff.handoff_id = p_handoff_id;
end;
$$;

create or replace function public.service_begin_oauth_approval_handoff(
  p_operator_id uuid,
  p_client_id text,
  p_content_item_id uuid,
  p_content_item_version integer,
  p_request_id uuid
)
returns table (
  handoff_id uuid,
  decision_request_id uuid,
  status text,
  replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_existing public.client_approval_handoffs%rowtype;
  v_item public.content_plan_items%rowtype;
  v_schedule public.client_recurring_pilot_schedules%rowtype;
  v_health public.scheduler_health%rowtype;
  v_resume boolean := false;
  v_handoff_id uuid;
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  if p_client_id in ('hoverboard_store', 'hcs_gadgets')
     or p_content_item_id is null or p_content_item_version is null
     or p_request_id is null then
    raise exception 'valid generic OAuth approval identifiers are required'
      using errcode = '22023';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('oauth-approval:' || p_client_id, 0));

  select * into v_existing
  from public.client_approval_handoffs handoff
  where handoff.client_id = p_client_id
    and handoff.status in ('preparing', 'processing')
  for update;
  if found then
    if v_existing.requested_by <> p_operator_id
       or v_existing.content_item_id <> p_content_item_id
       or v_existing.content_item_version <> p_content_item_version then
      raise exception 'another approval handoff is already active for this client'
        using errcode = '55000';
    end if;
    return query select v_existing.handoff_id, v_existing.request_id,
      v_existing.status, true;
    return;
  end if;

  select * into v_item
  from public.content_plan_items item
  where item.client_id = p_client_id and item.content_item_id = p_content_item_id
  for update;
  if not found or v_item.version <> p_content_item_version
     or v_item.status <> 'local_draft_created'
     or not exists (
       select 1 from public.content_drafts draft
       where draft.client_id = p_client_id
         and draft.content_item_id = p_content_item_id
         and draft.content_item_version = p_content_item_version
     ) then
    raise exception 'the exact review draft is no longer approvable' using errcode = '40001';
  end if;

  if not exists (
    select 1
    from public.clients client
    join public.client_runtime_settings settings using (client_id)
    join public.client_profiles profile using (client_id)
    where client.client_id = p_client_id
      and client.status = 'active'
      and settings.request_intake_enabled
      and settings.automation_enabled
      and settings.approved_draft_writes_enabled
      and not settings.shopify_writes_enabled
      and settings.allowed_mode = 'dry-run'
      and settings.max_concurrency = 1
      and profile.shopify_connection_method = 'oauth'
  ) then
    raise exception 'OAuth approval-only execution gates are not open safely'
      using errcode = '55000';
  end if;
  if exists (
    select 1 from public.content_jobs job
    where job.client_id = p_client_id
      and job.status in ('queued', 'leased', 'running')
  ) or exists (
    select 1 from public.incidents incident
    where incident.client_id = p_client_id and incident.status <> 'resolved'
  ) then
    raise exception 'approval requires zero active jobs and incidents' using errcode = '55000';
  end if;

  select * into v_schedule
  from public.client_recurring_pilot_schedules schedule
  where schedule.client_id = p_client_id
  for update;
  select * into v_health
  from public.scheduler_health health
  where health.client_id = p_client_id
  for update;
  if not found then
    raise exception 'scheduler health boundary is unavailable' using errcode = 'P0002';
  end if;

  if v_schedule.client_id is not null and v_schedule.enabled then
    if v_health.state <> 'healthy'
       or v_health.scheduler_owner <> 'prefect:orin-tenant-pilot' then
      raise exception 'the recurring scheduler is not healthy enough to hand off'
        using errcode = '55000';
    end if;
    v_resume := true;
    update public.client_recurring_pilot_schedules schedule
    set enabled = false where schedule.client_id = p_client_id;
  elsif v_health.state <> 'disabled' or v_health.scheduler_owner is not null then
    raise exception 'scheduler ownership cannot be handed off safely' using errcode = '55000';
  end if;

  update public.scheduler_health health
  set state = 'disabled', scheduler_owner = null
  where health.client_id = p_client_id;

  insert into public.client_approval_handoffs (
    client_id, request_id, content_item_id, content_item_version,
    requested_by, resume_recurring_schedule, prior_next_run_at
  ) values (
    p_client_id, p_request_id, p_content_item_id, p_content_item_version,
    p_operator_id, v_resume, v_schedule.next_run_at
  ) returning client_approval_handoffs.handoff_id into v_handoff_id;

  return query select v_handoff_id, p_request_id, 'preparing'::text, false;
end;
$$;

create or replace function public.service_bind_oauth_approval_handoff(
  p_operator_id uuid,
  p_handoff_id uuid,
  p_decision_id uuid
)
returns table (
  handoff_id uuid,
  decision_id uuid,
  content_job_id uuid,
  status text,
  replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_handoff public.client_approval_handoffs%rowtype;
  v_decision public.content_decisions%rowtype;
  v_materialized record;
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  select * into v_handoff
  from public.client_approval_handoffs handoff
  where handoff.handoff_id = p_handoff_id
  for update;
  if not found or v_handoff.requested_by <> p_operator_id then
    raise exception 'approval handoff was not found' using errcode = 'P0002';
  end if;
  if v_handoff.status = 'processing' then
    return query select v_handoff.handoff_id, v_handoff.decision_id,
      v_handoff.content_job_id, v_handoff.status, true;
    return;
  end if;
  if v_handoff.status <> 'preparing' then
    raise exception 'approval handoff is no longer active' using errcode = '55000';
  end if;

  select * into v_decision
  from public.content_decisions decision
  where decision.decision_id = p_decision_id
  for update;
  if not found
     or v_decision.client_id <> v_handoff.client_id
     or v_decision.requested_by <> p_operator_id
     or v_decision.request_id <> v_handoff.request_id
     or v_decision.content_item_id <> v_handoff.content_item_id
     or v_decision.content_item_version <> v_handoff.content_item_version
     or v_decision.decision <> 'approve_hidden_draft'
     or v_decision.processing_status <> 'recorded' then
    raise exception 'approval decision does not match the active handoff'
      using errcode = '55000';
  end if;

  select * into v_materialized
  from orin_private.materialize_next_oauth_approved_draft_decision(v_handoff.client_id);
  if v_materialized.decision_id is distinct from v_decision.decision_id
     or v_materialized.job_id is null
     or v_materialized.processing_status <> 'consumed' then
    raise exception 'approval decision could not be materialized exactly once'
      using errcode = '55000';
  end if;

  update public.client_approval_handoffs handoff
  set status = 'processing', decision_id = v_decision.decision_id,
      content_job_id = v_materialized.job_id
  where handoff.handoff_id = p_handoff_id
  returning handoff.* into v_handoff;
  return query select v_handoff.handoff_id, v_handoff.decision_id,
    v_handoff.content_job_id, v_handoff.status, false;
end;
$$;

create or replace function public.service_cancel_oauth_approval_handoff(
  p_operator_id uuid,
  p_handoff_id uuid,
  p_error text default ''
)
returns table (handoff_id uuid, status text, restored boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_handoff public.client_approval_handoffs%rowtype;
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  select * into v_handoff
  from public.client_approval_handoffs handoff
  where handoff.handoff_id = p_handoff_id
  for update;
  if not found or v_handoff.requested_by <> p_operator_id then
    raise exception 'approval handoff was not found' using errcode = 'P0002';
  end if;
  if v_handoff.status <> 'preparing'
     or exists (
       select 1 from public.content_decisions decision
       where decision.client_id = v_handoff.client_id
         and decision.request_id = v_handoff.request_id
     ) then
    return query select v_handoff.handoff_id, v_handoff.status, false;
    return;
  end if;
  perform orin_private.restore_oauth_approval_handoff(
    v_handoff.handoff_id, 'cancelled', p_error
  );
  return query select v_handoff.handoff_id, 'cancelled'::text, true;
end;
$$;

create or replace function orin_private.complete_oauth_approved_draft_job(
  p_job_id uuid,
  p_worker_id text,
  p_final_result jsonb
)
returns table (run_id text, status text, replayed boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.content_jobs%rowtype;
  v_result record;
  v_handoff public.client_approval_handoffs%rowtype;
begin
  select * into v_job
  from public.content_jobs job
  where job.job_id = p_job_id;
  if not found or v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.requested_mode <> 'hidden-draft'
     or v_job.source_job_key not like 'decision:%' then
    raise exception 'job is outside the OAuth approval boundary' using errcode = '42501';
  end if;
  select * into v_result
  from orin_private.complete_job_with_review_draft(
    p_job_id, p_worker_id, p_final_result, null::jsonb
  );

  select * into v_handoff
  from public.client_approval_handoffs handoff
  where handoff.content_job_id = p_job_id
  for update;
  if found and v_handoff.status = 'processing' then
    if v_result.status = 'completed'
       and p_final_result ->> 'status' = 'completed'
       and coalesce((p_final_result ->> 'shopify_create_count')::integer, 0) = 1
       and coalesce((p_final_result ->> 'shopify_published')::boolean, true) = false then
      perform orin_private.restore_oauth_approval_handoff(
        v_handoff.handoff_id, 'completed', ''
      );
    else
      perform orin_private.restore_oauth_approval_handoff(
        v_handoff.handoff_id, 'blocked',
        'The unpublished Shopify draft did not complete with the exact one-create receipt.'
      );
    end if;
  end if;
  return query select v_result.run_id, v_result.status, v_result.replayed;
end;
$$;

create or replace function orin_private.defer_oauth_approved_draft_job(
  p_job_id uuid,
  p_worker_id text,
  p_final_result jsonb
)
returns table (run_id text, status text, replayed boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.content_jobs%rowtype;
  v_result record;
  v_handoff public.client_approval_handoffs%rowtype;
begin
  select * into v_job
  from public.content_jobs job
  where job.job_id = p_job_id;
  if not found or v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.requested_mode <> 'hidden-draft'
     or v_job.source_job_key not like 'decision:%' then
    raise exception 'job is outside the OAuth approval boundary' using errcode = '42501';
  end if;
  select * into v_result
  from orin_private.defer_job(p_job_id, p_worker_id, p_final_result);
  if v_result.status = 'failed' then
    select * into v_handoff
    from public.client_approval_handoffs handoff
    where handoff.content_job_id = p_job_id
    for update;
    if found and v_handoff.status = 'processing' then
      perform orin_private.restore_oauth_approval_handoff(
        v_handoff.handoff_id, 'blocked',
        coalesce(p_final_result ->> 'error_code', 'OAuth draft attempts were exhausted.')
      );
    end if;
  end if;
  return query select v_result.run_id, v_result.status, v_result.replayed;
end;
$$;

revoke all on function orin_private.restore_oauth_approval_handoff(uuid, text, text)
  from public, anon, authenticated, orin_oauth_draft_worker;
revoke all on function public.service_begin_oauth_approval_handoff(uuid, text, uuid, integer, uuid)
  from public, anon, authenticated;
revoke all on function public.service_bind_oauth_approval_handoff(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke all on function public.service_cancel_oauth_approval_handoff(uuid, uuid, text)
  from public, anon, authenticated;
grant execute on function public.service_begin_oauth_approval_handoff(uuid, text, uuid, integer, uuid)
  to service_role;
grant execute on function public.service_bind_oauth_approval_handoff(uuid, uuid, uuid)
  to service_role;
grant execute on function public.service_cancel_oauth_approval_handoff(uuid, uuid, text)
  to service_role;

revoke all on function orin_private.complete_oauth_approved_draft_job(uuid, text, jsonb)
  from public, anon, authenticated;
revoke all on function orin_private.defer_oauth_approved_draft_job(uuid, text, jsonb)
  from public, anon, authenticated;
grant execute on function orin_private.complete_oauth_approved_draft_job(uuid, text, jsonb)
  to orin_oauth_draft_worker;
grant execute on function orin_private.defer_oauth_approved_draft_job(uuid, text, jsonb)
  to orin_oauth_draft_worker;

comment on table public.client_approval_handoffs is
  'Durable exclusive handoff from a generic recurring dry-run scheduler to one exact OAuth unpublished-draft approval.';
