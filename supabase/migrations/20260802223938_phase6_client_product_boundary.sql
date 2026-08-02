-- Phase 6 client-product boundary.
--
-- This migration adds a tenant-scoped, redacted dashboard projection and an
-- immutable review-decision ledger. Decisions are evidence only: they do not
-- enqueue work, change runtime gates, or write to Shopify.

create table public.content_decisions (
  decision_id uuid primary key default gen_random_uuid(),
  client_id text not null references public.clients(client_id) on delete cascade,
  content_item_id uuid not null,
  content_item_version integer not null check (content_item_version >= 1),
  decision text not null
    check (decision in ('approve_hidden_draft', 'request_changes')),
  note text not null default '' check (char_length(note) <= 4000),
  requested_by uuid not null references auth.users(id) on delete restrict,
  request_id uuid not null,
  processing_status text not null default 'recorded'
    check (processing_status in ('recorded', 'consumed', 'superseded')),
  created_at timestamptz not null default now(),
  consumed_at timestamptz,
  unique (client_id, request_id),
  foreign key (client_id, content_item_id)
    references public.content_plan_items(client_id, content_item_id)
    on delete restrict,
  check (decision <> 'request_changes' or nullif(btrim(note), '') is not null),
  check (
    (processing_status = 'consumed' and consumed_at is not null)
    or (processing_status <> 'consumed' and consumed_at is null)
  )
);

create index content_decisions_item_idx
  on public.content_decisions(client_id, content_item_id, created_at desc);

create index content_decisions_requester_idx
  on public.content_decisions(requested_by, created_at desc);

alter table public.content_decisions enable row level security;

revoke all on table public.content_decisions from public, anon, authenticated;
grant select, insert on table public.content_decisions to authenticated;

create policy content_decisions_select_for_members
on public.content_decisions for select to authenticated
using (
  (select auth.uid()) is not null
  and client_id in (
    select membership.client_id
    from public.client_members membership
    where membership.user_id = (select auth.uid())
  )
);

create policy content_decisions_insert_for_operators
on public.content_decisions for insert to authenticated
with check (
  requested_by = (select auth.uid())
  and exists (
    select 1
    from public.client_members membership
    where membership.client_id = content_decisions.client_id
      and membership.user_id = (select auth.uid())
      and membership.role in ('owner', 'operator')
  )
);

create or replace function orin_private.validate_content_decision()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_current_version integer;
begin
  if v_uid is null then
    raise exception 'authenticated user required' using errcode = '42501';
  end if;

  if not exists (
    select 1
    from public.client_members membership
    where membership.client_id = new.client_id
      and membership.user_id = v_uid
      and membership.role in ('owner', 'operator')
  ) then
    raise exception 'client operator membership required' using errcode = '42501';
  end if;

  select item.version
  into v_current_version
  from public.content_plan_items item
  where item.client_id = new.client_id
    and item.content_item_id = new.content_item_id;

  if not found then
    raise exception 'content item not found' using errcode = 'P0002';
  end if;
  if new.content_item_version is distinct from v_current_version then
    raise exception 'content item version changed; refresh before deciding'
      using errcode = '40001';
  end if;

  new.requested_by := v_uid;
  new.processing_status := 'recorded';
  new.consumed_at := null;
  return new;
end;
$$;

revoke all on function orin_private.validate_content_decision()
  from public, anon, authenticated;

create trigger content_decisions_validate_insert
before insert on public.content_decisions
for each row execute function orin_private.validate_content_decision();

-- Keep scheduler evidence current at the same transaction boundary that
-- persists a scheduler-owned run. The read-only watchdog remains read-only.
create or replace function orin_private.refresh_scheduler_health_from_run()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.content_jobs%rowtype;
begin
  if new.job_id is null then
    return new;
  end if;

  select job.*
  into v_job
  from public.content_jobs job
  where job.client_id = new.client_id
    and job.job_id = new.job_id;

  if not found or v_job.source_job_key !~ '^scheduler:[a-z0-9_-]+:[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
    return new;
  end if;

  update public.scheduler_health health
  set last_heartbeat_at = coalesce(new.finished_at, new.started_at),
      last_expected_run_at = v_job.scheduled_for,
      last_observed_run_id = new.run_id,
      details = coalesce(health.details, '{}'::jsonb) || jsonb_build_object(
        'last_source_job_key', v_job.source_job_key,
        'last_run_status', new.status,
        'last_run_decision', new.decision,
        'last_requested_mode', new.requested_mode,
        'last_shopify_create_count', new.shopify_create_count,
        'last_shopify_published', new.shopify_published,
        'last_queue_changed', new.queue_changed,
        'last_reconciliation_status', new.reconciliation_status
      )
  where health.client_id = new.client_id;

  return new;
end;
$$;

revoke all on function orin_private.refresh_scheduler_health_from_run()
  from public, anon, authenticated, orin_api, orin_worker, orin_scheduler, orin_watchdog;

create trigger runs_refresh_scheduler_health
after insert on public.runs
for each row execute function orin_private.refresh_scheduler_health_from_run();

-- Backfill health from the latest already-recorded scheduled run.
with latest_scheduler_run as (
  select distinct on (run.client_id)
    run.client_id,
    run.run_id,
    run.status,
    run.decision,
    run.requested_mode,
    run.shopify_create_count,
    run.shopify_published,
    run.queue_changed,
    run.reconciliation_status,
    coalesce(run.finished_at, run.started_at) as observed_at,
    job.scheduled_for,
    job.source_job_key
  from public.runs run
  join public.content_jobs job
    on job.client_id = run.client_id
   and job.job_id = run.job_id
  where job.source_job_key ~ '^scheduler:[a-z0-9_-]+:[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  order by run.client_id, coalesce(run.finished_at, run.started_at) desc, run.run_id desc
)
update public.scheduler_health health
set last_heartbeat_at = latest.observed_at,
    last_expected_run_at = latest.scheduled_for,
    last_observed_run_id = latest.run_id,
    details = coalesce(health.details, '{}'::jsonb) || jsonb_build_object(
      'last_source_job_key', latest.source_job_key,
      'last_run_status', latest.status,
      'last_run_decision', latest.decision,
      'last_requested_mode', latest.requested_mode,
      'last_shopify_create_count', latest.shopify_create_count,
      'last_shopify_published', latest.shopify_published,
      'last_queue_changed', latest.queue_changed,
      'last_reconciliation_status', latest.reconciliation_status
    )
from latest_scheduler_run latest
where health.client_id = latest.client_id;

-- Remove broad customer reads from operational tables. The dashboard view
-- below uses only explicitly granted, redacted columns and underlying RLS.
revoke all on table public.clients from authenticated;
revoke all on table public.client_members from authenticated;
revoke all on table public.client_runtime_settings from authenticated;
revoke all on table public.content_jobs from authenticated;
revoke all on table public.runs from authenticated;
revoke all on table public.run_artifacts from authenticated;
revoke all on table public.incidents from authenticated;
revoke all on table public.scheduler_health from authenticated;
revoke all on table public.content_plan_items from authenticated;

grant select, insert on table public.run_artifacts to service_role;

grant select (client_id, display_name, status, updated_at)
  on table public.clients to authenticated;
grant select (client_id, user_id, role, created_at)
  on table public.client_members to authenticated;
grant select (
  client_id, request_intake_enabled, automation_enabled,
  shopify_writes_enabled, max_concurrency, allowed_mode, updated_at
) on table public.client_runtime_settings to authenticated;
grant select (
  content_item_id, client_id, item_number, target_date, expected_draft_date,
  cluster, status, topic, target_keyword, shopify_article_id, shopify_handle,
  version, last_run_id, created_at, updated_at
) on table public.content_plan_items to authenticated;
grant select (
  run_id, client_id, job_id, requested_mode, effective_mode, status, decision,
  code_version, shopify_article_id, shopify_create_count, shopify_published,
  queue_changed, reconciliation_status, error_code, started_at, finished_at
) on table public.runs to authenticated;
grant select (
  artifact_id, client_id, run_id, kind, object_path, mime_type,
  byte_count, sha256, created_at
) on table public.run_artifacts to authenticated;
grant select (
  incident_id, client_id, run_id, severity, status, code, summary,
  opened_at, resolved_at, created_at, updated_at
) on table public.incidents to authenticated;
grant select (
  client_id, scheduler_owner, state, last_heartbeat_at,
  last_expected_run_at, last_observed_run_id, updated_at
) on table public.scheduler_health to authenticated;

create view public.client_dashboard_snapshot
with (security_invoker = true)
as
select
  client.client_id,
  jsonb_build_object(
    'schema', 'orin.client-dashboard/v1',
    'generatedAt', statement_timestamp(),
    'client', jsonb_build_object(
      'id', client.client_id,
      'name', client.display_name,
      'shortName', upper(left(client.display_name, 1) || right(client.display_name, 1)),
      'plan', 'Pilot workspace'
    ),
    'operations', jsonb_build_object(
      'scheduler', initcap(health.state),
      'worker', case
        when health.last_heartbeat_at is not null
         and health.last_heartbeat_at >= statement_timestamp() - interval '48 hours'
          then 'Online'
        else 'Needs attention'
      end,
      'shopifyWrites', case
        when settings.shopify_writes_enabled then 'Hidden drafts enabled'
        else 'Disabled'
      end,
      'lastChecked', coalesce(health.last_heartbeat_at, health.updated_at),
      'allowedMode', settings.allowed_mode,
      'automationEnabled', settings.automation_enabled,
      'requestIntakeEnabled', settings.request_intake_enabled
    ),
    'counts', jsonb_build_object(
      'planned', (select count(*) from public.content_plan_items item where item.client_id = client.client_id and item.status = 'planned'),
      'drafting', (select count(*) from public.content_plan_items item where item.client_id = client.client_id and item.status = 'in_progress'),
      'review', (select count(*) from public.content_plan_items item where item.client_id = client.client_id and item.status in ('local_draft_created', 'checks_failed', 'needs_human_review')),
      'approved', (select count(*) from public.content_plan_items item where item.client_id = client.client_id and item.status in ('draft_created', 'published_live'))
    ),
    'nextArticle', coalesce((
      select jsonb_build_object(
        'id', item.item_number,
        'contentItemId', item.content_item_id,
        'version', item.version,
        'title', coalesce(item.topic, 'Untitled content concept'),
        'keyword', coalesce(item.target_keyword, ''),
        'intent', coalesce(item.cluster, 'Content plan'),
        'status', case when item.status = 'planned' then 'Ready for drafting' else 'Ready for review' end,
        'dueLabel', coalesce(to_char(item.expected_draft_date, 'DD Mon'), 'Not scheduled'),
        'wordCount', null,
        'readingTime', 'Concept review',
        'qualityScore', null,
        'checks', jsonb_build_array(
          'Tenant and version binding verified',
          'Shopify publishing remains blocked',
          'Decision is recorded without execution'
        )
      )
      from public.content_plan_items item
      where item.client_id = client.client_id
        and item.status in ('planned', 'local_draft_created', 'checks_failed', 'needs_human_review')
      order by
        case item.status when 'local_draft_created' then 0 when 'checks_failed' then 1 when 'planned' then 2 else 3 end,
        item.expected_draft_date nulls last,
        item.item_number
      limit 1
    ), '{}'::jsonb),
    'recentContent', coalesce((
      select jsonb_agg(recent.payload order by recent.updated_at desc, recent.item_number desc)
      from (
        select
          item.item_number,
          item.updated_at,
          jsonb_build_object(
            'id', item.item_number,
            'contentItemId', item.content_item_id,
            'version', item.version,
            'title', coalesce(item.topic, 'Untitled content concept'),
            'stage', case item.status
              when 'draft_created' then 'Shopify draft'
              when 'published_live' then 'Published'
              when 'local_draft_created' then 'Review'
              when 'needs_human_review' then 'Review'
              when 'in_progress' then 'Drafting'
              else initcap(replace(item.status, '_', ' '))
            end,
            'updated', item.updated_at,
            'owner', 'ORIN'
          ) as payload
        from public.content_plan_items item
        where item.client_id = client.client_id
        order by item.updated_at desc, item.item_number desc
        limit 5
      ) recent
    ), '[]'::jsonb),
    'queue', coalesce((
      select jsonb_agg(queue.payload order by queue.sort_date, queue.item_number)
      from (
        select
          item.item_number,
          coalesce(item.expected_draft_date, item.target_date, '9999-12-31'::date) as sort_date,
          jsonb_build_object(
            'id', item.item_number,
            'contentItemId', item.content_item_id,
            'version', item.version,
            'title', coalesce(item.topic, 'Untitled content concept'),
            'keyword', coalesce(item.target_keyword, ''),
            'stage', case item.status
              when 'planned' then 'Planned'
              when 'in_progress' then 'Drafting'
              when 'local_draft_created' then 'Review'
              when 'checks_failed' then 'Review'
              when 'needs_human_review' then 'Review'
              when 'draft_created' then 'Approved'
              when 'published_live' then 'Approved'
              else 'Planned'
            end,
            'status', case item.status
              when 'planned' then 'Queued'
              when 'in_progress' then 'Writing'
              when 'checks_failed' then 'Checks failed'
              when 'needs_human_review' then 'Needs you'
              when 'local_draft_created' then 'Needs you'
              when 'draft_created' then 'Shopify draft'
              when 'published_live' then 'Published'
              else initcap(replace(item.status, '_', ' '))
            end,
            'priority', case when item.status in ('checks_failed', 'needs_human_review', 'local_draft_created') then 'High' else 'Normal' end,
            'due', coalesce(to_char(item.expected_draft_date, 'DD Mon'), 'Not scheduled')
          ) as payload
        from public.content_plan_items item
        where item.client_id = client.client_id
          and item.status not in ('archived', 'skipped_duplicate')
        order by
          case when item.status in ('checks_failed', 'needs_human_review', 'local_draft_created') then 0 else 1 end,
          coalesce(item.expected_draft_date, item.target_date, '9999-12-31'::date),
          item.item_number
        limit 60
      ) queue
    ), '[]'::jsonb),
    'activity', coalesce((
      select jsonb_agg(activity.payload order by activity.occurred_at desc)
      from (
        select *
        from (
          select
            coalesce(run.finished_at, run.started_at) as occurred_at,
            jsonb_build_object(
              'time', coalesce(run.finished_at, run.started_at),
              'label', 'Run ' || run.run_id || ' ' || run.status || ' with ' || run.shopify_create_count || ' Shopify creates'
            ) as payload
          from public.runs run
          where run.client_id = client.client_id
          union all
          select
            decision.created_at as occurred_at,
            jsonb_build_object(
              'time', decision.created_at,
              'label', case decision.decision
                when 'approve_hidden_draft' then 'Hidden-draft approval recorded'
                else 'Content changes requested'
              end
            ) as payload
          from public.content_decisions decision
          where decision.client_id = client.client_id
        ) combined
        order by occurred_at desc
        limit 10
      ) activity
    ), '[]'::jsonb),
    'article', coalesce((
      select jsonb_build_object(
        'id', item.item_number,
        'contentItemId', item.content_item_id,
        'version', item.version,
        'title', coalesce(item.topic, 'Untitled content concept'),
        'dek', 'Review this approved content concept before it enters the controlled drafting workflow.',
        'keyword', coalesce(item.target_keyword, ''),
        'metaTitle', coalesce(item.topic, 'Untitled content concept'),
        'metaDescription', 'Metadata will be generated and quality-checked during drafting.',
        'sections', jsonb_build_array(jsonb_build_object(
          'heading', 'Content brief',
          'paragraphs', jsonb_build_array(
            'Cluster: ' || coalesce(item.cluster, 'Not assigned') || '.',
            'This decision is version-bound and cannot publish or create a Shopify article by itself.'
          )
        )),
        'evidence', jsonb_build_array(
          'Authoritative content item: ' || item.content_item_id::text,
          'Content version: ' || item.version::text,
          'Shopify publishing is outside this dashboard boundary',
          'All review decisions are immutable and tenant-scoped'
        )
      )
      from public.content_plan_items item
      where item.client_id = client.client_id
        and item.status in ('planned', 'local_draft_created', 'checks_failed', 'needs_human_review')
      order by
        case item.status when 'local_draft_created' then 0 when 'checks_failed' then 1 when 'planned' then 2 else 3 end,
        item.expected_draft_date nulls last,
        item.item_number
      limit 1
    ), '{}'::jsonb)
  ) as snapshot
from public.clients client
join public.client_runtime_settings settings using (client_id)
join public.scheduler_health health using (client_id);

revoke all on table public.client_dashboard_snapshot from public, anon, authenticated;
grant select on table public.client_dashboard_snapshot to authenticated;

comment on table public.content_decisions is
  'Immutable tenant-scoped client review ledger. Rows are not execution requests.';
comment on view public.client_dashboard_snapshot is
  'Security-invoker tenant dashboard projection; excludes raw runner payloads and credentials.';
