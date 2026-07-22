-- ORIN Phase 2 foundation.
-- This migration deliberately creates no cron job, webhook, queue consumer, or
-- Shopify write path. All automation and write gates default to disabled.

create schema if not exists orin_private;
revoke all on schema orin_private from public, anon, authenticated;

create or replace function orin_private.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

revoke all on function orin_private.set_updated_at() from public, anon, authenticated;

create table public.clients (
  client_id text primary key,
  display_name text not null,
  status text not null default 'maintenance'
    check (status in ('maintenance', 'active', 'suspended', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (client_id ~ '^[a-z0-9][a-z0-9_]{1,62}$')
);

create table public.client_members (
  client_id text not null references public.clients(client_id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'viewer'
    check (role in ('owner', 'operator', 'viewer')),
  created_at timestamptz not null default now(),
  primary key (client_id, user_id)
);

create index client_members_user_id_idx
  on public.client_members(user_id, client_id);

create table public.client_runtime_settings (
  client_id text primary key references public.clients(client_id) on delete cascade,
  automation_enabled boolean not null default false,
  shopify_writes_enabled boolean not null default false,
  max_concurrency smallint not null default 1 check (max_concurrency = 1),
  allowed_mode text not null default 'dry-run'
    check (allowed_mode in ('dry-run', 'hidden-draft')),
  updated_at timestamptz not null default now(),
  check (not shopify_writes_enabled or allowed_mode = 'hidden-draft')
);

create table public.content_jobs (
  job_id uuid primary key default gen_random_uuid(),
  client_id text not null references public.clients(client_id) on delete cascade,
  source_job_key text not null,
  request_id uuid not null,
  requested_mode text not null default 'dry-run'
    check (requested_mode in ('dry-run', 'hidden-draft')),
  status text not null default 'queued'
    check (status in ('queued', 'leased', 'running', 'completed', 'blocked', 'failed', 'cancelled')),
  scheduled_for timestamptz not null,
  attempt_count smallint not null default 0 check (attempt_count >= 0),
  max_attempts smallint not null default 3 check (max_attempts between 1 and 10),
  lock_owner text,
  locked_at timestamptz,
  lease_expires_at timestamptz,
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload) = 'object'),
  last_error_code text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (client_id, source_job_key),
  unique (client_id, request_id),
  unique (client_id, job_id),
  check (attempt_count <= max_attempts),
  check (
    (status in ('leased', 'running') and lock_owner is not null and locked_at is not null and lease_expires_at is not null)
    or
    (status not in ('leased', 'running') and lock_owner is null and locked_at is null and lease_expires_at is null)
  ),
  check (lease_expires_at is null or lease_expires_at > locked_at)
);

create index content_jobs_claim_idx
  on public.content_jobs(client_id, status, scheduled_for, created_at)
  where status = 'queued';

create index content_jobs_expired_lease_idx
  on public.content_jobs(lease_expires_at)
  where status in ('leased', 'running');

create table public.runs (
  run_id text primary key,
  client_id text not null references public.clients(client_id) on delete restrict,
  request_id uuid not null,
  job_id uuid,
  attempt smallint not null default 1 check (attempt >= 1),
  requested_mode text not null check (requested_mode in ('dry-run', 'hidden-draft')),
  effective_mode text not null,
  status text not null check (status in ('running', 'completed', 'blocked', 'failed')),
  decision text not null,
  code_version text not null,
  config_version text,
  idempotency_key text generated always as (client_id || ':' || request_id::text) stored,
  shopify_article_id text,
  shopify_create_count smallint not null default 0 check (shopify_create_count between 0 and 1),
  shopify_published boolean not null default false check (not shopify_published),
  queue_changed boolean not null default false,
  reconciliation_status text not null default 'not_started'
    check (reconciliation_status in ('not_started', 'not_required', 'pending', 'reconciled', 'needs_review', 'failed')),
  artifact_prefix text not null,
  final_result jsonb check (final_result is null or jsonb_typeof(final_result) = 'object'),
  error_code text,
  pipeline_exit_code integer,
  started_at timestamptz not null,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (client_id, request_id),
  unique (idempotency_key),
  unique (client_id, run_id),
  foreign key (client_id, job_id)
    references public.content_jobs(client_id, job_id) on delete restrict,
  check (artifact_prefix = client_id || '/' || run_id || '/'),
  check (finished_at is null or finished_at >= started_at),
  check ((status = 'running' and finished_at is null) or (status <> 'running' and finished_at is not null)),
  check (status = 'running' or final_result is not null)
);

create index runs_client_started_idx
  on public.runs(client_id, started_at desc);

create table public.run_artifacts (
  artifact_id uuid primary key default gen_random_uuid(),
  client_id text not null,
  run_id text not null,
  kind text not null check (kind in ('final_result', 'events', 'stdout', 'stderr', 'pipeline_preview', 'other')),
  object_path text not null unique,
  mime_type text not null,
  byte_count bigint not null check (byte_count >= 0),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  foreign key (client_id, run_id)
    references public.runs(client_id, run_id) on delete cascade,
  check (object_path like client_id || '/' || run_id || '/%')
);

create index run_artifacts_run_idx
  on public.run_artifacts(client_id, run_id);

create table public.incidents (
  incident_id uuid primary key default gen_random_uuid(),
  client_id text not null references public.clients(client_id) on delete restrict,
  run_id text,
  severity text not null check (severity in ('info', 'warning', 'critical')),
  status text not null default 'open' check (status in ('open', 'acknowledged', 'resolved')),
  code text not null,
  summary text not null,
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details) = 'object'),
  opened_at timestamptz not null default now(),
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (client_id, run_id)
    references public.runs(client_id, run_id) on delete restrict,
  check ((status = 'resolved' and resolved_at is not null) or (status <> 'resolved' and resolved_at is null)),
  check (resolved_at is null or resolved_at >= opened_at)
);

create index incidents_client_status_idx
  on public.incidents(client_id, status, opened_at desc);

create table public.scheduler_health (
  client_id text primary key references public.clients(client_id) on delete cascade,
  scheduler_owner text,
  state text not null default 'disabled' check (state in ('disabled', 'healthy', 'late', 'error')),
  last_heartbeat_at timestamptz,
  last_expected_run_at timestamptz,
  last_observed_run_id text,
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details) = 'object'),
  updated_at timestamptz not null default now(),
  foreign key (client_id, last_observed_run_id)
    references public.runs(client_id, run_id) on delete restrict,
  check ((state = 'disabled' and scheduler_owner is null) or state <> 'disabled')
);

create trigger clients_set_updated_at
before update on public.clients
for each row execute function orin_private.set_updated_at();

create trigger client_runtime_settings_set_updated_at
before update on public.client_runtime_settings
for each row execute function orin_private.set_updated_at();

create trigger content_jobs_set_updated_at
before update on public.content_jobs
for each row execute function orin_private.set_updated_at();

create trigger runs_set_updated_at
before update on public.runs
for each row execute function orin_private.set_updated_at();

create trigger incidents_set_updated_at
before update on public.incidents
for each row execute function orin_private.set_updated_at();

create trigger scheduler_health_set_updated_at
before update on public.scheduler_health
for each row execute function orin_private.set_updated_at();

alter table public.clients enable row level security;
alter table public.client_members enable row level security;
alter table public.client_runtime_settings enable row level security;
alter table public.content_jobs enable row level security;
alter table public.runs enable row level security;
alter table public.run_artifacts enable row level security;
alter table public.incidents enable row level security;
alter table public.scheduler_health enable row level security;

revoke all on table public.clients from anon, authenticated;
revoke all on table public.client_members from anon, authenticated;
revoke all on table public.client_runtime_settings from anon, authenticated;
revoke all on table public.content_jobs from anon, authenticated;
revoke all on table public.runs from anon, authenticated;
revoke all on table public.run_artifacts from anon, authenticated;
revoke all on table public.incidents from anon, authenticated;
revoke all on table public.scheduler_health from anon, authenticated;

grant select on table public.clients to authenticated;
grant select on table public.client_members to authenticated;
grant select on table public.client_runtime_settings to authenticated;
grant select on table public.content_jobs to authenticated;
grant select on table public.runs to authenticated;
grant select on table public.run_artifacts to authenticated;
grant select on table public.incidents to authenticated;
grant select on table public.scheduler_health to authenticated;

create policy clients_select_for_members
on public.clients for select to authenticated
using (
  exists (
    select 1
    from public.client_members membership
    where membership.client_id = clients.client_id
      and membership.user_id = (select auth.uid())
  )
);

create policy client_members_select_self
on public.client_members for select to authenticated
using ((select auth.uid()) is not null and user_id = (select auth.uid()));

create policy client_runtime_settings_select_for_members
on public.client_runtime_settings for select to authenticated
using (
  exists (
    select 1 from public.client_members membership
    where membership.client_id = client_runtime_settings.client_id
      and membership.user_id = (select auth.uid())
  )
);

create policy content_jobs_select_for_members
on public.content_jobs for select to authenticated
using (
  exists (
    select 1 from public.client_members membership
    where membership.client_id = content_jobs.client_id
      and membership.user_id = (select auth.uid())
  )
);

create policy runs_select_for_members
on public.runs for select to authenticated
using (
  exists (
    select 1 from public.client_members membership
    where membership.client_id = runs.client_id
      and membership.user_id = (select auth.uid())
  )
);

create policy run_artifacts_select_for_members
on public.run_artifacts for select to authenticated
using (
  exists (
    select 1 from public.client_members membership
    where membership.client_id = run_artifacts.client_id
      and membership.user_id = (select auth.uid())
  )
);

create policy incidents_select_for_members
on public.incidents for select to authenticated
using (
  exists (
    select 1 from public.client_members membership
    where membership.client_id = incidents.client_id
      and membership.user_id = (select auth.uid())
  )
);

create policy scheduler_health_select_for_members
on public.scheduler_health for select to authenticated
using (
  exists (
    select 1 from public.client_members membership
    where membership.client_id = scheduler_health.client_id
      and membership.user_id = (select auth.uid())
  )
);

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'orin-evidence',
  'orin-evidence',
  false,
  26214400,
  array['application/json', 'application/x-ndjson', 'text/plain', 'text/html']
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

create policy orin_evidence_bucket_select_for_members
on storage.buckets for select to authenticated
using (
  id = 'orin-evidence'
  and exists (
    select 1 from public.client_members membership
    where membership.user_id = (select auth.uid())
  )
);

create policy orin_evidence_objects_select_for_members
on storage.objects for select to authenticated
using (
  bucket_id = 'orin-evidence'
  and exists (
    select 1 from public.client_members membership
    where membership.client_id = (storage.foldername(name))[1]
      and membership.user_id = (select auth.uid())
  )
);

insert into public.clients (client_id, display_name, status)
values ('hoverboard_store', 'Hoverboard Store', 'maintenance');

insert into public.client_runtime_settings (
  client_id,
  automation_enabled,
  shopify_writes_enabled,
  max_concurrency,
  allowed_mode
)
values ('hoverboard_store', false, false, 1, 'dry-run');

insert into public.scheduler_health (client_id, state)
values ('hoverboard_store', 'disabled');
