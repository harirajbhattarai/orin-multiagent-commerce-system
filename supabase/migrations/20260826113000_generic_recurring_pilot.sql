-- Shared recurring dry-run scheduling for safely commissioned OAuth tenants.
--
-- The browser can request enrollment only through an operator-authenticated
-- service boundary. The scheduler receives no tenant-controlled parameters and
-- can enqueue dry-run work only. Shopify live publishing remains impossible;
-- the broad Shopify write gate must stay closed.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_tenant_prefect_scheduler') then
    create role orin_tenant_prefect_scheduler nologin nosuperuser nocreatedb nocreaterole
      noinherit noreplication nobypassrls;
  end if;
end;
$$;

revoke all on schema public from orin_tenant_prefect_scheduler;
revoke all on schema orin_private from orin_tenant_prefect_scheduler;
grant usage on schema orin_private to orin_tenant_prefect_scheduler;
revoke all on all tables in schema public from orin_tenant_prefect_scheduler;
revoke all on all sequences in schema public from orin_tenant_prefect_scheduler;
revoke all on all functions in schema public from orin_tenant_prefect_scheduler;
revoke all on all functions in schema orin_private from orin_tenant_prefect_scheduler;

create table public.client_recurring_pilot_schedules (
  client_id text primary key references public.clients(client_id) on delete cascade,
  activation_request_id uuid not null unique,
  activated_by uuid not null references auth.users(id) on delete restrict,
  enabled boolean not null default false,
  local_run_time time not null default '11:00:00',
  timezone text not null,
  next_run_at timestamptz not null,
  last_enqueued_date date,
  last_enqueued_job_id uuid,
  activated_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (client_id, last_enqueued_job_id)
    references public.content_jobs(client_id, job_id) on delete restrict,
  check (client_id not in ('hoverboard_store', 'hcs_gadgets')),
  check (char_length(btrim(timezone)) between 3 and 80),
  check (local_run_time = '11:00:00')
);

create index client_recurring_pilot_due_idx
  on public.client_recurring_pilot_schedules(next_run_at, client_id)
  where enabled;

create trigger client_recurring_pilot_schedules_set_updated_at
before update on public.client_recurring_pilot_schedules
for each row execute function orin_private.set_updated_at();

alter table public.client_recurring_pilot_schedules enable row level security;
revoke all on table public.client_recurring_pilot_schedules from public, anon, authenticated;
grant select (
  client_id, activation_request_id, enabled, local_run_time, timezone,
  next_run_at, last_enqueued_date, last_enqueued_job_id, activated_at, updated_at
) on table public.client_recurring_pilot_schedules to authenticated;

create policy client_recurring_pilot_schedules_select_for_operators
on public.client_recurring_pilot_schedules for select to authenticated
using (
  exists (
    select 1 from public.platform_operators operator
    where operator.user_id = (select auth.uid()) and operator.active
  )
);

create or replace function public.service_activate_client_recurring_pilot(
  p_operator_id uuid,
  p_client_id text,
  p_activation_request_id uuid
)
returns table (
  client_id text,
  enabled boolean,
  next_run_at timestamptz,
  scheduler_owner text,
  replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_existing public.client_recurring_pilot_schedules%rowtype;
  v_onboarding public.client_onboarding_requests%rowtype;
  v_profile public.client_profiles%rowtype;
  v_runtime public.client_runtime_settings%rowtype;
  v_commissioning public.client_commissioning_requests%rowtype;
  v_next_run timestamptz := statement_timestamp() + interval '2 minutes';
begin
  if not exists (
    select 1 from public.platform_operators operator
    where operator.user_id = p_operator_id and operator.active
  ) then
    raise exception 'active platform operator required' using errcode = '42501';
  end if;
  if p_client_id in ('hoverboard_store', 'hcs_gadgets') then
    raise exception 'dedicated production tenants use dedicated schedules' using errcode = '42501';
  end if;

  select * into v_existing
  from public.client_recurring_pilot_schedules schedule
  where schedule.activation_request_id = p_activation_request_id;
  if found then
    if v_existing.client_id <> p_client_id then
      raise exception 'activation request belongs to another client' using errcode = '23505';
    end if;
    return query
    select v_existing.client_id, v_existing.enabled, v_existing.next_run_at,
           'prefect:orin-tenant-pilot'::text, true;
    return;
  end if;

  select * into v_onboarding
  from public.client_onboarding_requests onboarding
  where onboarding.client_id = p_client_id;
  select * into v_profile
  from public.client_profiles profile
  where profile.client_id = p_client_id;
  select * into v_runtime
  from public.client_runtime_settings settings
  where settings.client_id = p_client_id;
  select * into v_commissioning
  from public.client_commissioning_requests request
  where request.client_id = p_client_id
  order by request.requested_at desc
  limit 1;

  if v_onboarding.client_id is null or v_profile.client_id is null or v_runtime.client_id is null then
    raise exception 'client boundary is incomplete' using errcode = 'P0002';
  end if;
  if v_profile.shopify_connection_method <> 'oauth'
     or v_onboarding.status <> 'database_provisioned'
     or v_onboarding.commissioning_status <> 'pilot_pending'
     or v_commissioning.status <> 'succeeded' then
    raise exception 'successful OAuth commissioning and pilot proof are required'
      using errcode = '55000';
  end if;
  if v_runtime.shopify_writes_enabled
     or v_runtime.allowed_mode <> 'dry-run'
     or v_runtime.max_concurrency <> 1 then
    raise exception 'recurring pilot requires dry-run mode and broad Shopify writes closed'
      using errcode = '55000';
  end if;
  if exists (
    select 1 from public.content_jobs job
    where job.client_id = p_client_id and job.status in ('queued', 'leased', 'running')
  ) or exists (
    select 1 from public.incidents incident
    where incident.client_id = p_client_id and incident.status <> 'resolved'
  ) then
    raise exception 'recurring pilot requires zero active jobs and incidents'
      using errcode = '55000';
  end if;

  insert into public.client_recurring_pilot_schedules (
    client_id, activation_request_id, activated_by, enabled, timezone, next_run_at
  ) values (
    p_client_id, p_activation_request_id, p_operator_id, true, v_profile.timezone, v_next_run
  )
  on conflict on constraint client_recurring_pilot_schedules_pkey do update
  set activation_request_id = excluded.activation_request_id,
      activated_by = excluded.activated_by,
      enabled = true,
      timezone = excluded.timezone,
      next_run_at = excluded.next_run_at,
      activated_at = statement_timestamp();

  update public.clients set status = 'active' where clients.client_id = p_client_id;
  update public.client_runtime_settings settings
  set request_intake_enabled = true,
      automation_enabled = true,
      shopify_writes_enabled = false,
      max_concurrency = 1,
      allowed_mode = 'dry-run'
  where settings.client_id = p_client_id;
  update public.scheduler_health health
  set state = 'healthy',
      scheduler_owner = 'prefect:orin-tenant-pilot',
      last_expected_run_at = v_next_run
  where health.client_id = p_client_id;
  update public.client_onboarding_requests onboarding
  set commissioning_status = 'ready', last_error = ''
  where onboarding.client_id = p_client_id;

  return query
  select p_client_id, true, v_next_run, 'prefect:orin-tenant-pilot'::text, false;
end;
$$;

create or replace function orin_private.enqueue_due_tenant_prefect_jobs()
returns table (
  job_id uuid,
  client_id text,
  request_id uuid,
  requested_mode text,
  job_status text,
  scheduled_for timestamptz,
  created_at timestamptz,
  replayed boolean
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_schedule public.client_recurring_pilot_schedules%rowtype;
  v_item_id uuid;
  v_job public.content_jobs%rowtype;
  v_source_key text;
  v_local_date date;
  v_request_id uuid;
begin
  select schedule.* into v_schedule
  from public.client_recurring_pilot_schedules schedule
  join public.clients client using (client_id)
  join public.client_runtime_settings settings using (client_id)
  join public.scheduler_health health using (client_id)
  join public.client_profiles profile using (client_id)
  join public.client_onboarding_requests onboarding using (client_id)
  where schedule.enabled
    and schedule.next_run_at <= statement_timestamp()
    and schedule.client_id not in ('hoverboard_store', 'hcs_gadgets')
    and client.status = 'active'
    and settings.request_intake_enabled
    and settings.automation_enabled
    and not settings.shopify_writes_enabled
    and settings.allowed_mode = 'dry-run'
    and settings.max_concurrency = 1
    and health.state = 'healthy'
    and health.scheduler_owner = 'prefect:orin-tenant-pilot'
    and profile.shopify_connection_method = 'oauth'
    and onboarding.status = 'database_provisioned'
    and onboarding.commissioning_status = 'ready'
    and not exists (
      select 1 from public.incidents incident
      where incident.client_id = schedule.client_id and incident.status <> 'resolved'
    )
    and not exists (
      select 1 from public.content_jobs active_job
      where active_job.client_id = schedule.client_id
        and active_job.status in ('queued', 'leased', 'running')
    )
  order by schedule.next_run_at, schedule.client_id
  for update of schedule skip locked
  limit 1;

  if not found then return; end if;
  v_local_date := (v_schedule.next_run_at at time zone v_schedule.timezone)::date;
  v_source_key := 'scheduler:orin-tenant-pilot:' || v_schedule.client_id || ':' || v_local_date::text;
  perform pg_advisory_xact_lock(hashtextextended(v_source_key, 0));

  select * into v_job from public.content_jobs existing
  where existing.client_id = v_schedule.client_id and existing.source_job_key = v_source_key;
  if found then
    update public.client_recurring_pilot_schedules schedule
    set next_run_at = ((v_local_date + 1)::timestamp + schedule.local_run_time) at time zone schedule.timezone,
        last_enqueued_date = v_local_date,
        last_enqueued_job_id = v_job.job_id
    where schedule.client_id = v_schedule.client_id;
    return query select v_job.job_id, v_job.client_id, v_job.request_id,
      v_job.requested_mode, v_job.status, v_job.scheduled_for, v_job.created_at, true;
    return;
  end if;

  select item.content_item_id into v_item_id
  from public.content_plan_items item
  where item.client_id = v_schedule.client_id
    and item.status = 'planned'
    and coalesce(item.expected_draft_date, item.target_date) <= v_local_date
  order by coalesce(item.expected_draft_date, item.target_date), item.item_number
  for update skip locked
  limit 1;

  if v_item_id is not null then
    update public.content_plan_items item
    set status = 'in_progress', version = item.version + 1
    where item.client_id = v_schedule.client_id and item.content_item_id = v_item_id;
  end if;

  v_request_id := gen_random_uuid();
  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_mode, status,
    scheduled_for, payload, content_plan_item_id, max_attempts
  ) values (
    v_schedule.client_id, v_source_key, v_request_id, 'dry-run', 'queued',
    statement_timestamp(), '{}'::jsonb, v_item_id, 2
  ) returning * into v_job;

  update public.client_recurring_pilot_schedules schedule
  set next_run_at = ((v_local_date + 1)::timestamp + schedule.local_run_time) at time zone schedule.timezone,
      last_enqueued_date = v_local_date,
      last_enqueued_job_id = v_job.job_id
  where schedule.client_id = v_schedule.client_id;
  update public.scheduler_health health
  set last_expected_run_at = statement_timestamp()
  where health.client_id = v_schedule.client_id;

  return query select v_job.job_id, v_job.client_id, v_job.request_id,
    v_job.requested_mode, v_job.status, v_job.scheduled_for, v_job.created_at, false;
end;
$$;

-- Extend the existing generic worker to accept either the one-shot pilot source
-- or the platform-owned recurring source. Scheduled jobs may intentionally have
-- no content item; the worker then records a zero-write no_job_due receipt.
create or replace function orin_private.claim_next_generic_pilot_job(
  p_worker_id text,
  p_lease_seconds integer default 1200
)
returns table (
  job_id uuid, client_id text, request_id uuid, requested_mode text,
  attempt_count smallint, payload jsonb, lease_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job_id uuid;
begin
  if p_worker_id is null or char_length(p_worker_id) not between 8 and 128
     or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]+$' then
    raise exception 'invalid generic pilot worker identifier' using errcode = '22023';
  end if;
  if p_lease_seconds not between 60 and 3600 then
    raise exception 'lease must be between 60 and 3600 seconds' using errcode = '22023';
  end if;

  select candidate.job_id into v_job_id
  from public.content_jobs candidate
  join public.clients client using (client_id)
  join public.client_runtime_settings settings using (client_id)
  join public.client_profiles profile using (client_id)
  join public.client_onboarding_requests onboarding using (client_id)
  left join public.scheduler_health health using (client_id)
  left join public.client_recurring_pilot_schedules schedule using (client_id)
  left join public.content_plan_items item
    on item.client_id = candidate.client_id and item.content_item_id = candidate.content_plan_item_id
  where candidate.client_id not in ('hoverboard_store', 'hcs_gadgets')
    and candidate.requested_mode = 'dry-run'
    and candidate.payload = '{}'::jsonb
    and candidate.attempt_count < candidate.max_attempts
    and (
      (candidate.status = 'queued' and candidate.scheduled_for <= statement_timestamp())
      or (candidate.status in ('leased', 'running') and candidate.lease_expires_at <= statement_timestamp())
    )
    and client.status = 'active'
    and settings.request_intake_enabled and settings.automation_enabled
    and not settings.shopify_writes_enabled
    and settings.allowed_mode = 'dry-run' and settings.max_concurrency = 1
    and profile.shopify_connection_method = 'oauth'
    and onboarding.status = 'database_provisioned'
    and (
      (
        candidate.source_job_key like 'pilot:' || candidate.client_id || ':%'
        and onboarding.commissioning_status = 'dry_run_pending'
        and not settings.approved_draft_writes_enabled
        and candidate.content_plan_item_id is not null
        and item.status = 'in_progress'
      ) or (
        candidate.source_job_key like 'scheduler:orin-tenant-pilot:' || candidate.client_id || ':%'
        and onboarding.commissioning_status = 'ready'
        and schedule.enabled
        and health.state = 'healthy'
        and health.scheduler_owner = 'prefect:orin-tenant-pilot'
        and (candidate.content_plan_item_id is null or item.status = 'in_progress')
      )
    )
  order by candidate.created_at, candidate.job_id
  for update of candidate skip locked
  limit 1;

  if v_job_id is null then return; end if;
  return query
  update public.content_jobs claimed
  set status = 'leased', attempt_count = claimed.attempt_count + 1,
      lock_owner = p_worker_id, locked_at = statement_timestamp(),
      lease_expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds),
      last_error_code = null
  where claimed.job_id = v_job_id
  returning claimed.job_id, claimed.client_id, claimed.request_id,
    claimed.requested_mode, claimed.attempt_count, claimed.payload, claimed.lease_expires_at;
end;
$$;

create or replace function orin_private.get_generic_pilot_context(
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
  v_item public.content_plan_items%rowtype;
  v_profile public.client_profiles%rowtype;
  v_display_name text;
  v_recurring boolean;
begin
  select * into v_job from public.content_jobs job where job.job_id = p_job_id for update;
  if v_job.job_id is null then
    raise exception 'worker does not own an eligible generic lease' using errcode = '42501';
  end if;
  v_recurring := v_job.source_job_key like 'scheduler:orin-tenant-pilot:' || v_job.client_id || ':%';
  if v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.status not in ('leased', 'running')
     or v_job.lock_owner is distinct from p_worker_id
     or v_job.lease_expires_at <= statement_timestamp()
     or v_job.requested_mode <> 'dry-run' or v_job.payload <> '{}'::jsonb
     or not (v_recurring or v_job.source_job_key like 'pilot:' || v_job.client_id || ':%') then
    raise exception 'worker does not own an eligible generic lease' using errcode = '42501';
  end if;
  select * into v_profile from public.client_profiles profile
  where profile.client_id = v_job.client_id;
  select client.display_name into v_display_name from public.clients client
  where client.client_id = v_job.client_id;
  if v_job.content_plan_item_id is not null then
    select * into v_item from public.content_plan_items item
    where item.client_id = v_job.client_id and item.content_item_id = v_job.content_plan_item_id;
    if v_item.content_item_id is null or v_item.status <> 'in_progress' then
      raise exception 'generic content item is not execution-bound' using errcode = '55000';
    end if;
  end if;
  return jsonb_build_object(
    'schema', 'orin.generic-pilot-context/v2',
    'client_id', v_job.client_id,
    'source_kind', case when v_recurring then 'recurring' else 'pilot' end,
    'display_name', v_display_name,
    'market_country', v_profile.market_country,
    'timezone', v_profile.timezone,
    'brand_voice', v_profile.brand_voice,
    'content_categories', to_jsonb(v_profile.content_categories),
    'product_scope', v_profile.product_scope,
    'content_item', case when v_item.content_item_id is null then null else jsonb_build_object(
      'content_item_id', v_item.content_item_id, 'item_number', v_item.item_number,
      'target_date', v_item.target_date, 'expected_draft_date', v_item.expected_draft_date,
      'cluster', v_item.cluster, 'status', v_item.status, 'topic', v_item.topic,
      'target_keyword', v_item.target_keyword, 'draft_path', v_item.draft_path,
      'notes', v_item.notes, 'version', v_item.version
    ) end
  );
end;
$$;

create or replace function orin_private.complete_generic_pilot_job(
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
  v_job public.content_jobs%rowtype;
  v_completion record;
  v_recurring boolean;
begin
  select * into v_job from public.content_jobs job where job.job_id = p_job_id for update;
  if v_job.job_id is null then
    raise exception 'job is not an eligible generic pilot' using errcode = '42501';
  end if;
  v_recurring := v_job.source_job_key like 'scheduler:orin-tenant-pilot:' || v_job.client_id || ':%';
  if v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.requested_mode <> 'dry-run'
     or not (v_recurring or v_job.source_job_key like 'pilot:' || v_job.client_id || ':%') then
    raise exception 'job is not an eligible generic pilot' using errcode = '42501';
  end if;
  select * into v_completion
  from orin_private.complete_job_with_review_draft(p_job_id, p_worker_id, p_final_result, p_review_draft);

  if v_recurring then
    if p_final_result ->> 'status' = 'completed'
       and coalesce((p_final_result ->> 'shopify_create_count')::integer, 0) = 0
       and coalesce((p_final_result ->> 'shopify_published')::boolean, false) = false then
      update public.scheduler_health health
      set state = 'healthy', scheduler_owner = 'prefect:orin-tenant-pilot',
          last_heartbeat_at = statement_timestamp(), last_observed_run_id = v_completion.run_id
      where health.client_id = v_job.client_id;
    else
      update public.client_recurring_pilot_schedules schedule set enabled = false
      where schedule.client_id = v_job.client_id;
      update public.clients set status = 'maintenance' where client_id = v_job.client_id;
      update public.client_runtime_settings settings
      set request_intake_enabled = false, automation_enabled = false,
          shopify_writes_enabled = false, approved_draft_writes_enabled = false,
          allowed_mode = 'dry-run'
      where settings.client_id = v_job.client_id;
      update public.scheduler_health health set state = 'error', scheduler_owner = null
      where health.client_id = v_job.client_id;
    end if;
  else
    perform orin_private.close_generic_pilot_gates(v_job.client_id);
  end if;
  return query select v_completion.run_id, v_completion.status, v_completion.replayed;
end;
$$;

revoke all on function public.service_activate_client_recurring_pilot(uuid, text, uuid)
  from public, anon, authenticated;
grant execute on function public.service_activate_client_recurring_pilot(uuid, text, uuid)
  to service_role;
revoke all on function orin_private.enqueue_due_tenant_prefect_jobs()
  from public, anon, authenticated;
grant execute on function orin_private.enqueue_due_tenant_prefect_jobs()
  to orin_tenant_prefect_scheduler;
revoke all on function orin_private.claim_next_generic_pilot_job(text, integer)
  from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog,
       orin_worker, orin_tenant_prefect_scheduler;
revoke all on function orin_private.get_generic_pilot_context(uuid, text)
  from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog,
       orin_worker, orin_tenant_prefect_scheduler;
revoke all on function orin_private.complete_generic_pilot_job(uuid, text, jsonb, jsonb)
  from public, anon, authenticated, orin_api, orin_scheduler, orin_watchdog,
       orin_worker, orin_tenant_prefect_scheduler;
grant execute on function orin_private.claim_next_generic_pilot_job(text, integer) to orin_pilot_worker;
grant execute on function orin_private.get_generic_pilot_context(uuid, text) to orin_pilot_worker;
grant execute on function orin_private.complete_generic_pilot_job(uuid, text, jsonb, jsonb) to orin_pilot_worker;

comment on table public.client_recurring_pilot_schedules is
  'Operator-visible, platform-owned recurring dry-run enrollment. Never grants Shopify publishing.';
comment on function orin_private.enqueue_due_tenant_prefect_jobs() is
  'Zero-argument shared scheduler boundary. Enqueues at most one due dry-run tenant job.';
comment on role orin_tenant_prefect_scheduler is
  'NOLOGIN shared Prefect scheduler; function-only, no table, Vault, or Shopify access.';
