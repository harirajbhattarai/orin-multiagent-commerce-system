alter table public.content_jobs
add column requested_by uuid references auth.users(id) on delete restrict;

create index content_jobs_requested_by_idx
  on public.content_jobs(requested_by, client_id)
  where requested_by is not null;

grant insert (requested_by) on table public.content_jobs to orin_api;

drop policy content_jobs_api_insert_dry_run_only on public.content_jobs;

create policy content_jobs_api_insert_dry_run_only
on public.content_jobs for insert to orin_api
with check (
  requested_by is not null
  and source_job_key = 'api:' || request_id::text
  and requested_mode = 'dry-run'
  and status = 'queued'
  and payload = '{}'::jsonb
  and attempt_count = 0
  and lock_owner is null
  and locked_at is null
  and lease_expires_at is null
  and exists (
    select 1
    from public.clients client
    join public.client_runtime_settings settings using (client_id)
    join public.client_members membership using (client_id)
    where client.client_id = content_jobs.client_id
      and client.status = 'active'
      and settings.request_intake_enabled
      and settings.allowed_mode = 'dry-run'
      and membership.user_id = content_jobs.requested_by
      and membership.role in ('owner', 'operator')
  )
);
