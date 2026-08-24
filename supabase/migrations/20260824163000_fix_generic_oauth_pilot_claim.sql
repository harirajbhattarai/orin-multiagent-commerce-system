-- Qualify the claim CTE output for already-migrated databases, where the
-- RETURNS TABLE client_id output variable otherwise makes the name ambiguous.
-- Fresh databases already receive the qualified definition in the prior file.

do $$
declare
  v_function_definition text;
begin
  select pg_get_functiondef(
    'orin_private.claim_next_generic_pilot_job(text,integer)'::regprocedure
  ) into v_function_definition;

  if strpos(
    v_function_definition,
    'select distinct client_id from exhausted'
  ) > 0 then
    execute replace(
      v_function_definition,
      'select distinct client_id from exhausted',
      'select distinct exhausted.client_id from exhausted'
    );
  elsif strpos(
    v_function_definition,
    'select distinct exhausted.client_id from exhausted'
  ) = 0 then
    raise exception 'generic pilot claim function has an unexpected definition'
      using errcode = '55000';
  end if;
end;
$$;

-- Operator-only recovery for a prepared job that failed before it was claimed.
-- This never opens Shopify or scheduler gates and refuses ambiguous worklists.
create or replace function orin_private.resume_generic_pilot_dry_run(
  p_client_id text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job_id uuid;
  v_job_count integer;
begin
  perform orin_private.assert_generic_pilot_boundary(p_client_id, false);

  select count(*), min(job.job_id::text)::uuid
  into v_job_count, v_job_id
  from public.content_jobs job
  join public.content_plan_items item
    on item.client_id = job.client_id
   and item.content_item_id = job.content_plan_item_id
  where job.client_id = p_client_id
    and job.source_job_key like 'pilot:' || p_client_id || ':%'
    and job.status = 'queued'
    and job.requested_mode = 'dry-run'
    and job.payload = '{}'::jsonb
    and job.attempt_count < job.max_attempts
    and item.status = 'in_progress';

  if v_job_count <> 1 or v_job_id is null then
    raise exception 'generic pilot recovery requires exactly one eligible queued job'
      using errcode = '55000';
  end if;
  if exists (
    select 1 from public.incidents incident
    where incident.client_id = p_client_id and incident.status <> 'resolved'
  ) then
    raise exception 'generic pilot recovery requires zero open incidents'
      using errcode = '55000';
  end if;

  update public.clients
  set status = 'active'
  where client_id = p_client_id;
  update public.client_runtime_settings
  set request_intake_enabled = true,
      automation_enabled = true,
      shopify_writes_enabled = false,
      approved_draft_writes_enabled = false,
      max_concurrency = 1,
      allowed_mode = 'dry-run'
  where client_id = p_client_id;
  update public.scheduler_health
  set state = 'disabled', scheduler_owner = null
  where client_id = p_client_id;
  update public.client_onboarding_requests
  set commissioning_status = 'dry_run_pending', last_error = ''
  where client_id = p_client_id and status = 'database_provisioned';

  return v_job_id;
end;
$$;

revoke all on function orin_private.resume_generic_pilot_dry_run(text)
  from public, anon, authenticated, orin_pilot_worker;

comment on function orin_private.resume_generic_pilot_dry_run(text) is
  'Operator-only recovery for one prepared generic pilot job; Shopify remains closed.';
