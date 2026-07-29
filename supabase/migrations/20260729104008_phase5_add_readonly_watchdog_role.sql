-- Phase 5 preparation: a fixed-client, read-only watchdog role.
-- This migration creates no login, credential, schedule, alert delivery, or
-- write capability. Activation remains blocked on Phase 4 scheduler proof.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_watchdog') then
    create role orin_watchdog
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

alter role orin_watchdog
  nologin
  noinherit
  nosuperuser
  nocreaterole
  nocreatedb
  noreplication
  nobypassrls;

revoke all on schema public from orin_watchdog;
revoke all on schema orin_private from orin_watchdog;
revoke all on all tables in schema public from orin_watchdog;
revoke all on all sequences in schema public from orin_watchdog;
revoke all on all functions in schema public from orin_watchdog;
revoke all on all functions in schema orin_private from orin_watchdog;

grant usage on schema public to orin_watchdog;

grant select (client_id, status)
on table public.clients to orin_watchdog;

grant select (
  client_id,
  request_intake_enabled,
  automation_enabled,
  shopify_writes_enabled,
  max_concurrency,
  allowed_mode
)
on table public.client_runtime_settings to orin_watchdog;

grant select (
  client_id,
  scheduler_owner,
  state,
  last_heartbeat_at,
  last_expected_run_at,
  last_observed_run_id
)
on table public.scheduler_health to orin_watchdog;

grant select (
  job_id,
  client_id,
  source_job_key,
  request_id,
  requested_mode,
  status,
  scheduled_for,
  attempt_count,
  last_error_code,
  created_at,
  updated_at
)
on table public.content_jobs to orin_watchdog;

grant select (
  run_id,
  client_id,
  request_id,
  job_id,
  requested_mode,
  effective_mode,
  status,
  decision,
  code_version,
  shopify_create_count,
  shopify_published,
  queue_changed,
  reconciliation_status,
  error_code,
  started_at,
  finished_at
)
on table public.runs to orin_watchdog;

create policy clients_watchdog_select_hbstore
on public.clients for select to orin_watchdog
using (client_id = 'hoverboard_store');

create policy client_runtime_settings_watchdog_select_hbstore
on public.client_runtime_settings for select to orin_watchdog
using (client_id = 'hoverboard_store');

create policy scheduler_health_watchdog_select_hbstore
on public.scheduler_health for select to orin_watchdog
using (client_id = 'hoverboard_store');

create policy content_jobs_watchdog_select_hbstore
on public.content_jobs for select to orin_watchdog
using (client_id = 'hoverboard_store');

create policy runs_watchdog_select_hbstore
on public.runs for select to orin_watchdog
using (client_id = 'hoverboard_store');

comment on role orin_watchdog is
  'NOLOGIN read-only HBStore scheduler observation role; activate only after Phase 4 proof';
