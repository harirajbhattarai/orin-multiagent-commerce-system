-- Resolve the activation function's output-column name against the schedule PK.

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

revoke all on function public.service_activate_client_recurring_pilot(uuid, text, uuid)
  from public, anon, authenticated;
grant execute on function public.service_activate_client_recurring_pilot(uuid, text, uuid)
  to service_role;
