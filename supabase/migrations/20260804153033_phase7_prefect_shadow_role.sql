-- Phase 7: isolated, read-only Prefect shadow observation boundary.
--
-- This migration creates no login credential, schedule, job enqueue path, or
-- Shopify capability. The role can execute one fixed-client projection only.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_prefect_shadow') then
    create role orin_prefect_shadow
      nologin
      noinherit
      nosuperuser
      nocreaterole
      nocreatedb
      noreplication
      nobypassrls;
  end if;
end;
$$;

alter role orin_prefect_shadow
  nologin
  noinherit
  nocreaterole
  nocreatedb;

do $$
begin
  if exists (
    select 1
    from pg_roles
    where rolname = 'orin_prefect_shadow'
      and (
        rolsuper
        or rolcreaterole
        or rolcreatedb
        or rolreplication
        or rolbypassrls
      )
  ) then
    raise exception 'orin_prefect_shadow has prohibited privileged attributes'
      using errcode = '42501';
  end if;
end;
$$;

revoke all on schema public from orin_prefect_shadow;
revoke all on schema orin_private from orin_prefect_shadow;
revoke all on all tables in schema public from orin_prefect_shadow;
revoke all on all sequences in schema public from orin_prefect_shadow;
revoke all on all functions in schema public from orin_prefect_shadow;
revoke all on all functions in schema orin_private from orin_prefect_shadow;

grant usage on schema orin_private to orin_prefect_shadow;

create or replace function orin_private.get_prefect_shadow_snapshot(
  p_client_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_client public.clients%rowtype;
  v_settings public.client_runtime_settings%rowtype;
  v_scheduler public.scheduler_health%rowtype;
  v_items jsonb;
  v_latest jsonb;
  v_active_jobs integer;
  v_open_incidents integer;
begin
  if p_client_id is distinct from 'hoverboard_store' then
    raise exception 'Prefect shadow access is fixed to Hoverboard Store'
      using errcode = '42501';
  end if;

  select * into strict v_client
  from public.clients client
  where client.client_id = p_client_id;

  select * into strict v_settings
  from public.client_runtime_settings settings
  where settings.client_id = p_client_id;

  select * into strict v_scheduler
  from public.scheduler_health scheduler
  where scheduler.client_id = p_client_id;

  select count(*)::integer into v_active_jobs
  from public.content_jobs job
  where job.client_id = p_client_id
    and job.status in ('queued', 'leased', 'running');

  select count(*)::integer into v_open_incidents
  from public.incidents incident
  where incident.client_id = p_client_id
    and incident.status in ('open', 'acknowledged');

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'item_number', item.item_number,
        'target_date', item.target_date,
        'expected_draft_date', item.expected_draft_date,
        'decision', item.decision,
        'status', item.status,
        'topic', item.topic,
        'target_keyword', item.target_keyword,
        'version', item.version,
        'shopify_article_id', item.shopify_article_id,
        'shopify_handle', item.shopify_handle
      ) order by item.item_number
    ),
    '[]'::jsonb
  ) into v_items
  from public.content_plan_items item
  where item.client_id = p_client_id;

  select jsonb_build_object(
    'run_id', run.run_id,
    'source_job_key', job.source_job_key,
    'business_date',
      (job.scheduled_for at time zone 'Europe/London')::date,
    'finished_at', run.finished_at,
    'status', run.status,
    'decision', run.decision,
    'selected_job_number', case
      when coalesce(run.final_result ->> 'selected_job', '') ~ '^[0-9]+$'
        then (run.final_result ->> 'selected_job')::integer
      when coalesce(run.final_result ->> 'job_id', '') ~ '^[0-9]+$'
        then (run.final_result ->> 'job_id')::integer
      else null
    end,
    'shopify_create_count', run.shopify_create_count,
    'shopify_published', run.shopify_published,
    'queue_changed', run.queue_changed,
    'reconciliation_status', run.reconciliation_status,
    'error_code', run.error_code
  ) into v_latest
  from public.runs run
  join public.content_jobs job
    on job.client_id = run.client_id
   and job.job_id = run.job_id
  where run.client_id = p_client_id
    and run.requested_mode = 'dry-run'
    and run.status = 'completed'
    and job.source_job_key like 'scheduler:orin-hbstore-prod:%'
  order by run.finished_at desc, run.run_id desc
  limit 1;

  return jsonb_build_object(
    'schema', 'orin.prefect-shadow-snapshot/v1',
    'observed_at', statement_timestamp(),
    'client_id', p_client_id,
    'client_status', v_client.status,
    'runtime', jsonb_build_object(
      'request_intake_enabled', v_settings.request_intake_enabled,
      'automation_enabled', v_settings.automation_enabled,
      'shopify_writes_enabled', v_settings.shopify_writes_enabled,
      'max_concurrency', v_settings.max_concurrency,
      'allowed_mode', v_settings.allowed_mode
    ),
    'scheduler', jsonb_build_object(
      'state', v_scheduler.state,
      'owner', v_scheduler.scheduler_owner
    ),
    'active_jobs', v_active_jobs,
    'open_incidents', v_open_incidents,
    'items', v_items,
    'latest_scheduler_dry_run', v_latest
  );
end;
$$;

revoke all on function orin_private.get_prefect_shadow_snapshot(text)
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler,
       orin_watchdog;
grant execute on function orin_private.get_prefect_shadow_snapshot(text)
  to orin_prefect_shadow;

-- Let the migration owner impersonate the NOLOGIN role for pgTAP verification.
-- This grants no additional capability to orin_prefect_shadow itself.
grant orin_prefect_shadow to postgres with set true;

comment on role orin_prefect_shadow is
  'NOLOGIN fixed-client read-only Prefect shadow role; no direct table access';
comment on function orin_private.get_prefect_shadow_snapshot(text) is
  'Sanitized HBStore-only observation projection for the isolated Prefect shadow flow.';
