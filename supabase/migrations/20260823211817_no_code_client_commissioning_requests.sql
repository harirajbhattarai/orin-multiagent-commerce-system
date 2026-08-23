-- Durable, fail-closed bridge between the no-code onboarding dashboard and a
-- trusted commissioning control-plane worker. Creating a request never opens
-- execution, scheduler, or Shopify gates.

create table public.client_commissioning_requests (
  commissioning_request_id uuid primary key,
  client_id text not null references public.clients(client_id) on delete cascade,
  onboarding_request_id uuid not null references public.client_onboarding_requests(request_id) on delete cascade,
  requested_by uuid not null references auth.users(id) on delete restrict,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  stage text not null default 'request_received'
    check (stage in ('request_received', 'worker_setup', 'dry_run_proof', 'scheduler_proof', 'watchdog_proof', 'complete')),
  attempt_count smallint not null default 0 check (attempt_count between 0 and 10),
  last_error text not null default '',
  requested_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  updated_at timestamptz not null default now(),
  unique (client_id, commissioning_request_id),
  check (started_at is null or started_at >= requested_at),
  check (finished_at is null or finished_at >= coalesce(started_at, requested_at)),
  check (
    (status in ('queued', 'running') and finished_at is null)
    or (status in ('succeeded', 'failed', 'cancelled') and finished_at is not null)
  )
);

create unique index client_commissioning_requests_one_active_idx
  on public.client_commissioning_requests(client_id)
  where status in ('queued', 'running');

create index client_commissioning_requests_client_created_idx
  on public.client_commissioning_requests(client_id, requested_at desc);

create table public.client_commissioning_events (
  event_id bigint generated always as identity primary key,
  commissioning_request_id uuid not null,
  client_id text not null,
  stage text not null
    check (stage in ('request_received', 'worker_setup', 'dry_run_proof', 'scheduler_proof', 'watchdog_proof', 'complete')),
  status text not null check (status in ('pending', 'running', 'passed', 'failed', 'cancelled')),
  summary text not null check (char_length(btrim(summary)) between 1 and 500),
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence) = 'object'),
  created_at timestamptz not null default now(),
  foreign key (client_id, commissioning_request_id)
    references public.client_commissioning_requests(client_id, commissioning_request_id)
    on delete cascade
);

create index client_commissioning_events_request_created_idx
  on public.client_commissioning_events(commissioning_request_id, created_at, event_id);

create trigger client_commissioning_requests_set_updated_at
before update on public.client_commissioning_requests
for each row execute function orin_private.set_updated_at();

alter table public.client_commissioning_requests enable row level security;
alter table public.client_commissioning_events enable row level security;

revoke all on table public.client_commissioning_requests from public, anon, authenticated;
revoke all on table public.client_commissioning_events from public, anon, authenticated;
revoke all on sequence public.client_commissioning_events_event_id_seq from public, anon, authenticated;

grant select (
  commissioning_request_id, client_id, onboarding_request_id, requested_by,
  status, stage, attempt_count, last_error, requested_at, started_at,
  finished_at, updated_at
) on table public.client_commissioning_requests to authenticated;

grant select (
  event_id, commissioning_request_id, client_id, stage, status, summary,
  evidence, created_at
) on table public.client_commissioning_events to authenticated;

create policy client_commissioning_requests_select_for_operators
on public.client_commissioning_requests for select to authenticated
using (
  exists (
    select 1 from public.platform_operators operator
    where operator.user_id = (select auth.uid()) and operator.active
  )
);

create policy client_commissioning_events_select_for_operators
on public.client_commissioning_events for select to authenticated
using (
  exists (
    select 1 from public.platform_operators operator
    where operator.user_id = (select auth.uid()) and operator.active
  )
);

create or replace function public.service_request_client_commissioning(
  p_operator_id uuid,
  p_client_id text,
  p_commissioning_request_id uuid
)
returns table (
  commissioning_request_id uuid,
  client_id text,
  status text,
  stage text,
  replayed boolean,
  requested_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_existing public.client_commissioning_requests%rowtype;
  v_onboarding public.client_onboarding_requests%rowtype;
  v_client_status text;
  v_request_intake boolean;
  v_automation boolean;
  v_shopify_writes boolean;
  v_approved_draft_writes boolean;
  v_allowed_mode text;
  v_scheduler_state text;
  v_scheduler_owner text;
begin
  perform orin_private.assume_verified_operator(p_operator_id);

  if p_commissioning_request_id is null then
    raise exception 'commissioning request id is required' using errcode = '22023';
  end if;

  select request.* into v_existing
  from public.client_commissioning_requests request
  where request.commissioning_request_id = p_commissioning_request_id;
  if found then
    if v_existing.client_id <> p_client_id or v_existing.requested_by <> p_operator_id then
      raise exception 'commissioning request id belongs to another request' using errcode = '22023';
    end if;
    return query select v_existing.commissioning_request_id, v_existing.client_id,
      v_existing.status, v_existing.stage, true, v_existing.requested_at;
    return;
  end if;

  select request.* into v_existing
  from public.client_commissioning_requests request
  where request.client_id = p_client_id
    and request.status in ('queued', 'running')
  order by request.requested_at desc
  limit 1;
  if found then
    return query select v_existing.commissioning_request_id, v_existing.client_id,
      v_existing.status, v_existing.stage, true, v_existing.requested_at;
    return;
  end if;

  select onboarding.* into v_onboarding
  from public.client_onboarding_requests onboarding
  where onboarding.client_id = p_client_id
    and onboarding.status = 'database_provisioned'
  order by onboarding.created_at desc
  limit 1;
  if not found or v_onboarding.commissioning_status <> 'identity_verified' then
    raise exception 'read-only identity verification must pass before commissioning'
      using errcode = '55000';
  end if;

  select client.status,
         settings.request_intake_enabled,
         settings.automation_enabled,
         settings.shopify_writes_enabled,
         settings.approved_draft_writes_enabled,
         settings.allowed_mode,
         health.state,
         health.scheduler_owner
  into v_client_status, v_request_intake, v_automation, v_shopify_writes,
       v_approved_draft_writes, v_allowed_mode, v_scheduler_state,
       v_scheduler_owner
  from public.clients client
  join public.client_runtime_settings settings using (client_id)
  join public.scheduler_health health using (client_id)
  where client.client_id = p_client_id;

  if not found then
    raise exception 'provisioned client runtime boundary not found' using errcode = 'P0002';
  end if;
  if v_client_status <> 'maintenance'
     or v_request_intake
     or v_automation
     or v_shopify_writes
     or v_approved_draft_writes
     or v_allowed_mode <> 'dry-run'
     or v_scheduler_state <> 'disabled'
     or v_scheduler_owner is not null then
    raise exception 'commissioning requires maintenance with every execution and Shopify gate closed'
      using errcode = '55000';
  end if;
  if exists (
    select 1 from public.content_jobs job
    where job.client_id = p_client_id and job.status in ('queued', 'leased', 'running')
  ) then
    raise exception 'commissioning requires zero active jobs' using errcode = '55000';
  end if;
  if exists (
    select 1 from public.incidents incident
    where incident.client_id = p_client_id and incident.status <> 'resolved'
  ) then
    raise exception 'commissioning requires zero open incidents' using errcode = '55000';
  end if;

  insert into public.client_commissioning_requests (
    commissioning_request_id, client_id, onboarding_request_id, requested_by
  ) values (
    p_commissioning_request_id, p_client_id, v_onboarding.request_id, p_operator_id
  ) returning * into v_existing;

  insert into public.client_commissioning_events (
    commissioning_request_id, client_id, stage, status, summary, evidence
  ) values (
    v_existing.commissioning_request_id,
    p_client_id,
    'request_received',
    'passed',
    'Safe commissioning requested with all execution and Shopify gates closed.',
    jsonb_build_object(
      'allowed_mode', v_allowed_mode,
      'active_jobs', 0,
      'open_incidents', 0,
      'shopify_writes_enabled', false,
      'approved_draft_writes_enabled', false
    )
  );

  update public.client_onboarding_requests onboarding
  set commissioning_status = 'worker_pending', last_error = ''
  where onboarding.request_id = v_onboarding.request_id;

  return query select v_existing.commissioning_request_id, v_existing.client_id,
    v_existing.status, v_existing.stage, false, v_existing.requested_at;
end;
$$;

revoke all on function public.service_request_client_commissioning(uuid, text, uuid)
  from public, anon, authenticated;
grant execute on function public.service_request_client_commissioning(uuid, text, uuid)
  to service_role;

comment on table public.client_commissioning_requests is
  'Durable, idempotent no-code commissioning requests. Creation never opens runtime, scheduler, or Shopify gates.';
comment on table public.client_commissioning_events is
  'Sanitized, append-only progress receipts for a client commissioning request.';
comment on function public.service_request_client_commissioning(uuid, text, uuid) is
  'Service-role-only fail-closed intake for no-code client commissioning.';
