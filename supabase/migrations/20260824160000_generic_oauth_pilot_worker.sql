-- Least-privilege dry-run worker for newly OAuth-connected tenants.
--
-- The worker can claim one explicitly prepared pilot job, read a credential-free
-- content context, renew its own lease, and persist one review draft. It cannot
-- read Vault, OAuth tokens, Shopify identifiers required for mutation, or any
-- public table directly. Both Shopify write gates remain closed throughout.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_pilot_worker') then
    create role orin_pilot_worker nologin nosuperuser nocreatedb nocreaterole
      noinherit noreplication nobypassrls;
  end if;
end;
$$;

revoke all on schema public from orin_pilot_worker;
revoke all on schema orin_private from orin_pilot_worker;
grant usage on schema orin_private to orin_pilot_worker;
revoke all on all tables in schema public from orin_pilot_worker;
revoke all on all sequences in schema public from orin_pilot_worker;
revoke all on all functions in schema public from orin_pilot_worker;
revoke all on all functions in schema orin_private from orin_pilot_worker;

create or replace function orin_private.assert_generic_pilot_boundary(
  p_client_id text,
  p_require_open boolean default false
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_client public.clients%rowtype;
  v_settings public.client_runtime_settings%rowtype;
  v_health public.scheduler_health%rowtype;
  v_onboarding public.client_onboarding_requests%rowtype;
  v_profile public.client_profiles%rowtype;
begin
  if p_client_id in ('hoverboard_store', 'hcs_gadgets') then
    raise exception 'dedicated production tenants are not generic pilot clients'
      using errcode = '42501';
  end if;

  select * into v_client from public.clients where client_id = p_client_id;
  select * into v_settings from public.client_runtime_settings where client_id = p_client_id;
  select * into v_health from public.scheduler_health where client_id = p_client_id;
  select * into v_profile from public.client_profiles where client_id = p_client_id;
  select * into v_onboarding
  from public.client_onboarding_requests
  where client_id = p_client_id;

  if v_client.client_id is null
     or v_settings.client_id is null
     or v_health.client_id is null
     or v_profile.client_id is null
     or v_onboarding.client_id is null then
    raise exception 'generic pilot tenant boundary is incomplete' using errcode = 'P0002';
  end if;
  if v_onboarding.status <> 'database_provisioned'
     or v_onboarding.commissioning_status not in ('pilot_pending', 'dry_run_pending')
     or v_profile.shopify_connection_method <> 'oauth' then
    raise exception 'generic pilot requires a provisioned OAuth tenant'
      using errcode = '55000';
  end if;
  if v_settings.shopify_writes_enabled
     or v_settings.approved_draft_writes_enabled
     or v_settings.allowed_mode <> 'dry-run'
     or v_settings.max_concurrency <> 1
     or v_health.state <> 'disabled'
     or v_health.scheduler_owner is not null then
    raise exception 'generic pilot Shopify or scheduler boundary is not closed'
      using errcode = '55000';
  end if;

  if p_require_open then
    if v_client.status <> 'active'
       or not v_settings.request_intake_enabled
       or not v_settings.automation_enabled
       or v_onboarding.commissioning_status <> 'dry_run_pending' then
      raise exception 'generic pilot execution gates are not open'
        using errcode = '55000';
    end if;
  elsif v_client.status <> 'maintenance'
        or v_settings.request_intake_enabled
        or v_settings.automation_enabled then
    raise exception 'generic pilot preparation requires closed execution gates'
      using errcode = '55000';
  end if;
end;
$$;

create or replace function orin_private.close_generic_pilot_gates(p_client_id text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_client_id in ('hoverboard_store', 'hcs_gadgets') then
    raise exception 'dedicated production tenants are not generic pilot clients'
      using errcode = '42501';
  end if;
  update public.clients set status = 'maintenance' where client_id = p_client_id;
  update public.client_runtime_settings
  set request_intake_enabled = false,
      automation_enabled = false,
      shopify_writes_enabled = false,
      approved_draft_writes_enabled = false,
      max_concurrency = 1,
      allowed_mode = 'dry-run'
  where client_id = p_client_id;
  update public.scheduler_health
  set state = 'disabled', scheduler_owner = null
  where client_id = p_client_id;
  update public.client_onboarding_requests
  set commissioning_status = 'pilot_pending', last_error = ''
  where client_id = p_client_id and status = 'database_provisioned';
end;
$$;

-- Operator-only preparation. This function intentionally receives no grant.
create or replace function orin_private.prepare_generic_pilot_dry_run(
  p_client_id text,
  p_topic text,
  p_target_keyword text,
  p_cluster text,
  p_notes text default ''
)
returns table (content_item_id uuid, job_id uuid, request_id uuid)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_item_id uuid;
  v_job_id uuid;
  v_request_id uuid := gen_random_uuid();
  v_item_number integer;
  v_slug text;
  v_source_revision text;
begin
  perform orin_private.assert_generic_pilot_boundary(p_client_id, false);
  if nullif(btrim(p_topic), '') is null
     or char_length(p_topic) > 240
     or nullif(btrim(p_target_keyword), '') is null
     or char_length(p_target_keyword) > 160
     or nullif(btrim(p_cluster), '') is null
     or char_length(p_notes) > 4000 then
    raise exception 'invalid generic pilot content scope' using errcode = '22023';
  end if;
  if exists (
    select 1 from public.content_jobs job
    where job.client_id = p_client_id
      and job.status in ('queued', 'leased', 'running')
  ) or exists (
    select 1 from public.incidents incident
    where incident.client_id = p_client_id and incident.status <> 'resolved'
  ) then
    raise exception 'generic pilot requires zero active jobs and incidents'
      using errcode = '55000';
  end if;
  if exists (
    select 1 from public.content_plan_items item where item.client_id = p_client_id
  ) then
    raise exception 'first generic pilot refuses to merge into an existing content plan'
      using errcode = '23505';
  end if;

  select coalesce(max(item_number), 0) + 1 into v_item_number
  from public.content_plan_items where client_id = p_client_id;
  v_slug := trim(both '-' from lower(regexp_replace(btrim(p_topic), '[^[:alnum:]]+', '-', 'g')));
  v_source_revision := encode(
    extensions.digest(
      convert_to(p_client_id || E'\n' || p_topic || E'\n' || p_target_keyword || E'\n' || p_cluster, 'UTF8'),
      'sha256'
    ),
    'hex'
  );

  insert into public.content_plan_items (
    client_id, item_number, target_date, cluster, decision, status, topic,
    target_keyword, draft_path, notes, source_document, source_revision
  ) values (
    p_client_id, v_item_number,
    (statement_timestamp() at time zone 'Europe/London')::date + 14,
    btrim(p_cluster), 'create_new', 'in_progress', btrim(p_topic),
    btrim(p_target_keyword),
    'clients/' || p_client_id || '/content_engine/drafts/' || v_slug || '.html',
    btrim(coalesce(p_notes, '')), 'database:onboarding-pilot', v_source_revision
  ) returning public.content_plan_items.content_item_id into v_item_id;

  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_mode, status,
    scheduled_for, payload, content_plan_item_id, max_attempts
  ) values (
    p_client_id,
    'pilot:' || p_client_id || ':' || v_item_id::text || ':v1',
    v_request_id, 'dry-run', 'queued', statement_timestamp(), '{}'::jsonb,
    v_item_id, 2
  ) returning public.content_jobs.job_id into v_job_id;

  update public.clients set status = 'active' where client_id = p_client_id;
  update public.client_runtime_settings
  set request_intake_enabled = true,
      automation_enabled = true,
      shopify_writes_enabled = false,
      approved_draft_writes_enabled = false,
      max_concurrency = 1,
      allowed_mode = 'dry-run'
  where client_id = p_client_id;
  update public.client_onboarding_requests
  set commissioning_status = 'dry_run_pending', last_error = ''
  where client_id = p_client_id and status = 'database_provisioned';

  return query select v_item_id, v_job_id, v_request_id;
end;
$$;

create or replace function orin_private.claim_next_generic_pilot_job(
  p_worker_id text,
  p_lease_seconds integer default 1200
)
returns table (
  job_id uuid,
  client_id text,
  request_id uuid,
  requested_mode text,
  attempt_count smallint,
  payload jsonb,
  lease_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job_id uuid;
  v_client_id text;
begin
  if p_worker_id is null
     or char_length(p_worker_id) not between 8 and 128
     or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]+$' then
    raise exception 'invalid generic pilot worker identifier' using errcode = '22023';
  end if;
  if p_lease_seconds not between 60 and 3600 then
    raise exception 'lease must be between 60 and 3600 seconds' using errcode = '22023';
  end if;

  with exhausted as (
    update public.content_jobs job
    set status = 'failed', lock_owner = null, locked_at = null,
        lease_expires_at = null,
        last_error_code = 'ORIN_GENERIC_PILOT_MAX_ATTEMPTS_EXCEEDED'
    where job.client_id not in ('hoverboard_store', 'hcs_gadgets')
      and job.source_job_key like 'pilot:%'
      and job.status in ('leased', 'running')
      and job.lease_expires_at <= statement_timestamp()
      and job.attempt_count >= job.max_attempts
    returning job.client_id, job.job_id
  ), closed_clients as (
    select distinct client_id from exhausted
  ), closed_gates as (
    update public.clients client
    set status = 'maintenance'
    from closed_clients closed
    where client.client_id = closed.client_id
    returning client.client_id
  ), closed_settings as (
    update public.client_runtime_settings settings
    set request_intake_enabled = false,
        automation_enabled = false,
        shopify_writes_enabled = false,
        approved_draft_writes_enabled = false,
        allowed_mode = 'dry-run'
    from closed_clients closed
    where settings.client_id = closed.client_id
    returning settings.client_id
  ), closed_health as (
    update public.scheduler_health health
    set state = 'disabled', scheduler_owner = null
    from closed_clients closed
    where health.client_id = closed.client_id
    returning health.client_id
  ), closed_onboarding as (
    update public.client_onboarding_requests onboarding
    set commissioning_status = 'pilot_pending',
        last_error = 'Generic pilot lease expired after the maximum number of claims.'
    from closed_clients closed
    where onboarding.client_id = closed.client_id
      and onboarding.status = 'database_provisioned'
    returning onboarding.client_id
  )
  insert into public.incidents (client_id, severity, code, summary, details)
  select exhausted.client_id, 'critical',
         'ORIN_GENERIC_PILOT_MAX_ATTEMPTS_EXCEEDED',
         'Generic OAuth pilot lease expired after the maximum number of claims',
         jsonb_build_object('job_id', exhausted.job_id)
  from exhausted;

  if exists (
    select 1 from public.content_jobs active_job
    where active_job.status in ('leased', 'running')
      and active_job.source_job_key like 'pilot:%'
      and active_job.lease_expires_at > statement_timestamp()
  ) then
    return;
  end if;

  select candidate.job_id, candidate.client_id
  into v_job_id, v_client_id
  from public.content_jobs candidate
  join public.clients client using (client_id)
  join public.client_runtime_settings settings using (client_id)
  join public.client_profiles profile using (client_id)
  join public.client_onboarding_requests onboarding using (client_id)
  join public.content_plan_items item
    on item.client_id = candidate.client_id
   and item.content_item_id = candidate.content_plan_item_id
  where candidate.client_id not in ('hoverboard_store', 'hcs_gadgets')
    and candidate.source_job_key like 'pilot:' || candidate.client_id || ':%'
    and candidate.requested_mode = 'dry-run'
    and candidate.payload = '{}'::jsonb
    and candidate.attempt_count < candidate.max_attempts
    and (
      (candidate.status = 'queued' and candidate.scheduled_for <= statement_timestamp())
      or (
        candidate.status in ('leased', 'running')
        and candidate.lease_expires_at <= statement_timestamp()
      )
    )
    and item.status = 'in_progress'
    and client.status = 'active'
    and settings.request_intake_enabled
    and settings.automation_enabled
    and not settings.shopify_writes_enabled
    and not settings.approved_draft_writes_enabled
    and settings.allowed_mode = 'dry-run'
    and settings.max_concurrency = 1
    and profile.shopify_connection_method = 'oauth'
    and onboarding.status = 'database_provisioned'
    and onboarding.commissioning_status = 'dry_run_pending'
  order by candidate.created_at, candidate.job_id
  for update of candidate skip locked
  limit 1;

  if v_job_id is null then return; end if;
  perform orin_private.assert_generic_pilot_boundary(v_client_id, true);

  return query
  update public.content_jobs claimed
  set status = 'leased',
      attempt_count = claimed.attempt_count + 1,
      lock_owner = p_worker_id,
      locked_at = statement_timestamp(),
      lease_expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds),
      last_error_code = null
  where claimed.job_id = v_job_id
  returning claimed.job_id, claimed.client_id, claimed.request_id,
            claimed.requested_mode, claimed.attempt_count, claimed.payload,
            claimed.lease_expires_at;
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
begin
  select * into v_job
  from public.content_jobs job
  where job.job_id = p_job_id
  for update;
  if not found
     or v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.status not in ('leased', 'running')
     or v_job.lock_owner is distinct from p_worker_id
     or v_job.lease_expires_at <= statement_timestamp()
     or v_job.requested_mode <> 'dry-run'
     or v_job.payload <> '{}'::jsonb
     or v_job.source_job_key not like 'pilot:' || v_job.client_id || ':%' then
    raise exception 'worker does not own an eligible generic pilot lease'
      using errcode = '42501';
  end if;
  perform orin_private.assert_generic_pilot_boundary(v_job.client_id, true);

  select * into v_item from public.content_plan_items item
  where item.client_id = v_job.client_id
    and item.content_item_id = v_job.content_plan_item_id;
  select * into v_profile from public.client_profiles profile
  where profile.client_id = v_job.client_id;
  select display_name into v_display_name from public.clients
  where client_id = v_job.client_id;
  if v_item.content_item_id is null or v_item.status <> 'in_progress' then
    raise exception 'generic pilot content item is not execution-bound'
      using errcode = '55000';
  end if;

  return jsonb_build_object(
    'schema', 'orin.generic-pilot-context/v1',
    'client_id', v_job.client_id,
    'display_name', v_display_name,
    'market_country', v_profile.market_country,
    'timezone', v_profile.timezone,
    'brand_voice', v_profile.brand_voice,
    'content_categories', to_jsonb(v_profile.content_categories),
    'product_scope', v_profile.product_scope,
    'content_item', jsonb_build_object(
      'content_item_id', v_item.content_item_id,
      'item_number', v_item.item_number,
      'target_date', v_item.target_date,
      'expected_draft_date', v_item.expected_draft_date,
      'cluster', v_item.cluster,
      'status', v_item.status,
      'topic', v_item.topic,
      'target_keyword', v_item.target_keyword,
      'draft_path', v_item.draft_path,
      'notes', v_item.notes,
      'version', v_item.version
    )
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
begin
  select * into v_job from public.content_jobs where job_id = p_job_id for update;
  if not found
     or v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.source_job_key not like 'pilot:' || v_job.client_id || ':%'
     or v_job.requested_mode <> 'dry-run' then
    raise exception 'job is not an eligible generic pilot' using errcode = '42501';
  end if;
  perform orin_private.assert_generic_pilot_boundary(v_job.client_id, true);

  select * into v_completion
  from orin_private.complete_job_with_review_draft(
    p_job_id, p_worker_id, p_final_result, p_review_draft
  );
  perform orin_private.close_generic_pilot_gates(v_job.client_id);
  return query select v_completion.run_id, v_completion.status, v_completion.replayed;
end;
$$;

revoke all on function orin_private.assert_generic_pilot_boundary(text, boolean)
  from public, anon, authenticated, orin_pilot_worker;
revoke all on function orin_private.close_generic_pilot_gates(text)
  from public, anon, authenticated, orin_pilot_worker;
revoke all on function orin_private.prepare_generic_pilot_dry_run(text, text, text, text, text)
  from public, anon, authenticated, orin_pilot_worker;
revoke all on function orin_private.claim_next_generic_pilot_job(text, integer)
  from public, anon, authenticated;
revoke all on function orin_private.get_generic_pilot_context(uuid, text)
  from public, anon, authenticated;
revoke all on function orin_private.complete_generic_pilot_job(uuid, text, jsonb, jsonb)
  from public, anon, authenticated;

grant execute on function orin_private.claim_next_generic_pilot_job(text, integer)
  to orin_pilot_worker;
grant execute on function orin_private.get_generic_pilot_context(uuid, text)
  to orin_pilot_worker;
grant execute on function orin_private.renew_job_lease(uuid, text, integer)
  to orin_pilot_worker;
grant execute on function orin_private.complete_generic_pilot_job(uuid, text, jsonb, jsonb)
  to orin_pilot_worker;

comment on role orin_pilot_worker is
  'NOLOGIN generic OAuth pilot writer: function-only, no Vault or Shopify access.';
comment on function orin_private.get_generic_pilot_context(uuid, text) is
  'Returns only credential-free tenant and version-bound content context.';
