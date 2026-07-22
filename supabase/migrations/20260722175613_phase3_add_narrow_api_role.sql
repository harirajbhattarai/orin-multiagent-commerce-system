do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_api') then
    create role orin_api nologin noinherit nobypassrls;
  end if;
end;
$$;

revoke all on schema public from orin_api;
grant usage on schema public to orin_api;

revoke all on table public.clients from orin_api;
revoke all on table public.client_members from orin_api;
revoke all on table public.client_runtime_settings from orin_api;
revoke all on table public.content_jobs from orin_api;

grant select on table public.clients to orin_api;
grant select on table public.client_members to orin_api;
grant select on table public.client_runtime_settings to orin_api;
grant select on table public.content_jobs to orin_api;
grant insert (
  client_id,
  source_job_key,
  request_id,
  requested_mode,
  status,
  scheduled_for,
  payload
) on table public.content_jobs to orin_api;

create policy clients_api_select
on public.clients for select to orin_api
using (true);

create policy client_members_api_select
on public.client_members for select to orin_api
using (true);

create policy client_runtime_settings_api_select
on public.client_runtime_settings for select to orin_api
using (true);

create policy content_jobs_api_select
on public.content_jobs for select to orin_api
using (true);

create policy content_jobs_api_insert_dry_run_only
on public.content_jobs for insert to orin_api
with check (
  source_job_key = 'api:' || request_id::text
  and requested_mode = 'dry-run'
  and status = 'queued'
  and payload = '{}'::jsonb
  and attempt_count = 0
  and lock_owner is null
  and locked_at is null
  and lease_expires_at is null
);
