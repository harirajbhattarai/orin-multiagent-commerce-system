-- Trusted, lease-bound consumer for no-code client commissioning requests.
--
-- The commissioner can inspect only one claimed onboarding bundle through
-- narrow functions. It cannot write Shopify content, enqueue content jobs, or
-- enable runtime/scheduler gates. Every terminal path closes all gates.

alter table public.client_commissioning_requests
  add column worker_id text,
  add column lease_expires_at timestamptz,
  add column heartbeat_at timestamptz;

alter table public.client_commissioning_requests
  add constraint client_commissioning_requests_worker_id_check
    check (worker_id is null or char_length(worker_id) between 3 and 160),
  add constraint client_commissioning_requests_lease_state_check
    check (
      (status = 'running' and worker_id is not null and lease_expires_at is not null)
      or (status <> 'running' and worker_id is null and lease_expires_at is null)
    );

create index client_commissioning_requests_claim_idx
  on public.client_commissioning_requests(status, lease_expires_at, requested_at)
  where status in ('queued', 'running');

grant select (worker_id, lease_expires_at, heartbeat_at)
  on table public.client_commissioning_requests to authenticated;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_commissioner') then
    create role orin_commissioner nologin nosuperuser nocreatedb nocreaterole
      noinherit noreplication nobypassrls;
  end if;
end;
$$;

revoke all on schema orin_private from orin_commissioner;
grant usage on schema orin_private to orin_commissioner;
revoke all on all tables in schema public from orin_commissioner;
revoke all on all sequences in schema public from orin_commissioner;
revoke all on all functions in schema public from orin_commissioner;
revoke all on all functions in schema orin_private from orin_commissioner;

create or replace function orin_private.assert_commissioning_boundary_closed(
  p_client_id text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_client_status text;
  v_request_intake boolean;
  v_automation boolean;
  v_shopify_writes boolean;
  v_approved_draft_writes boolean;
  v_allowed_mode text;
  v_scheduler_state text;
  v_scheduler_owner text;
begin
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
    raise exception 'commissioning runtime boundary is missing' using errcode = 'P0002';
  end if;
  if v_client_status <> 'maintenance'
     or v_request_intake
     or v_automation
     or v_shopify_writes
     or v_approved_draft_writes
     or v_allowed_mode <> 'dry-run'
     or v_scheduler_state <> 'disabled'
     or v_scheduler_owner is not null then
    raise exception 'commissioning boundary is not fail-closed' using errcode = '55000';
  end if;
  if exists (
    select 1 from public.content_jobs job
    where job.client_id = p_client_id
      and job.status in ('queued', 'leased', 'running')
  ) then
    raise exception 'commissioning requires zero active jobs' using errcode = '55000';
  end if;
  if exists (
    select 1 from public.incidents incident
    where incident.client_id = p_client_id and incident.status <> 'resolved'
  ) then
    raise exception 'commissioning requires zero open incidents' using errcode = '55000';
  end if;
end;
$$;

create or replace function orin_private.claim_next_client_commissioning(
  p_worker_id text,
  p_lease_seconds integer
)
returns table (
  commissioning_request_id uuid,
  client_id text,
  onboarding_request_id uuid,
  attempt_count smallint,
  lease_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.client_commissioning_requests%rowtype;
begin
  if nullif(btrim(p_worker_id), '') is null
     or char_length(p_worker_id) not between 3 and 160 then
    raise exception 'invalid commissioner worker id' using errcode = '22023';
  end if;
  if p_lease_seconds not between 30 and 1800 then
    raise exception 'commissioner lease must be between 30 and 1800 seconds'
      using errcode = '22023';
  end if;

  select request.* into v_request
  from public.client_commissioning_requests request
  where (
      request.status = 'queued'
      or (
        request.status = 'running'
        and request.lease_expires_at <= statement_timestamp()
      )
    )
    and request.attempt_count < 10
  order by request.requested_at, request.commissioning_request_id
  for update skip locked
  limit 1;

  if not found then
    return;
  end if;

  perform orin_private.assert_commissioning_boundary_closed(v_request.client_id);

  update public.client_commissioning_requests request
  set status = 'running',
      stage = 'worker_setup',
      worker_id = btrim(p_worker_id),
      lease_expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds),
      heartbeat_at = statement_timestamp(),
      attempt_count = request.attempt_count + 1,
      started_at = coalesce(request.started_at, statement_timestamp()),
      last_error = ''
  where request.commissioning_request_id = v_request.commissioning_request_id
  returning request.* into v_request;

  insert into public.client_commissioning_events (
    commissioning_request_id, client_id, stage, status, summary, evidence
  ) values (
    v_request.commissioning_request_id,
    v_request.client_id,
    'worker_setup',
    'running',
    'Trusted commissioner claimed the isolated request with every execution and Shopify gate closed.',
    jsonb_build_object('attempt', v_request.attempt_count)
  );

  update public.client_onboarding_requests onboarding
  set commissioning_status = 'worker_pending', last_error = ''
  where onboarding.request_id = v_request.onboarding_request_id;

  return query select v_request.commissioning_request_id, v_request.client_id,
    v_request.onboarding_request_id, v_request.attempt_count,
    v_request.lease_expires_at;
end;
$$;

create or replace function orin_private.renew_client_commissioning_lease(
  p_commissioning_request_id uuid,
  p_worker_id text,
  p_lease_seconds integer
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_lease_seconds not between 30 and 1800 then
    raise exception 'commissioner lease must be between 30 and 1800 seconds'
      using errcode = '22023';
  end if;
  update public.client_commissioning_requests request
  set lease_expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds),
      heartbeat_at = statement_timestamp()
  where request.commissioning_request_id = p_commissioning_request_id
    and request.status = 'running'
    and request.worker_id = p_worker_id
    and request.lease_expires_at > statement_timestamp();
  return found;
end;
$$;

create or replace function orin_private.get_client_commissioning_context(
  p_commissioning_request_id uuid,
  p_worker_id text
)
returns table (
  commissioning_request_id uuid,
  client_id text,
  onboarding_request_id uuid,
  display_name text,
  owner_email text,
  shopify_store_domain text,
  shopify_blog_gid text,
  shopify_blog_title text,
  market_country text,
  timezone text,
  brand_voice text,
  content_categories text[],
  product_scope jsonb,
  shopify_access_token text,
  attempt_count smallint,
  lease_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.client_commissioning_requests%rowtype;
begin
  select request.* into v_request
  from public.client_commissioning_requests request
  where request.commissioning_request_id = p_commissioning_request_id
    and request.status = 'running'
    and request.worker_id = p_worker_id
    and request.lease_expires_at > statement_timestamp();
  if not found then
    raise exception 'commissioning lease is not owned by this worker' using errcode = '42501';
  end if;

  perform orin_private.assert_commissioning_boundary_closed(v_request.client_id);

  return query
  select v_request.commissioning_request_id,
         profile.client_id,
         profile.onboarding_request_id,
         onboarding.display_name,
         profile.owner_email,
         profile.shopify_store_domain,
         profile.shopify_blog_gid,
         profile.shopify_blog_title,
         profile.market_country,
         profile.timezone,
         profile.brand_voice,
         profile.content_categories,
         profile.product_scope,
         secret.decrypted_secret,
         v_request.attempt_count,
         v_request.lease_expires_at
  from public.client_profiles profile
  join public.client_onboarding_requests onboarding
    on onboarding.request_id = profile.onboarding_request_id
  join vault.decrypted_secrets secret
    on secret.id = profile.shopify_credential_secret_id
  where profile.client_id = v_request.client_id
    and profile.onboarding_request_id = v_request.onboarding_request_id
    and onboarding.status = 'database_provisioned'
    and onboarding.commissioning_status in ('identity_verified', 'worker_pending');

  if not found then
    raise exception 'verified commissioning profile or credential is unavailable'
      using errcode = 'P0002';
  end if;
end;
$$;

create or replace function orin_private.client_commissioning_boundary_snapshot(
  p_commissioning_request_id uuid,
  p_worker_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.client_commissioning_requests%rowtype;
  v_active_requests integer;
  v_exact_requests integer;
begin
  select request.* into v_request
  from public.client_commissioning_requests request
  where request.commissioning_request_id = p_commissioning_request_id
    and request.status = 'running'
    and request.worker_id = p_worker_id
    and request.lease_expires_at > statement_timestamp();
  if not found then
    raise exception 'commissioning lease is not owned by this worker' using errcode = '42501';
  end if;
  perform orin_private.assert_commissioning_boundary_closed(v_request.client_id);

  select count(*)::integer into v_active_requests
  from public.client_commissioning_requests request
  where request.client_id = v_request.client_id
    and request.status in ('queued', 'running');
  select count(*)::integer into v_exact_requests
  from public.client_commissioning_requests request
  where request.commissioning_request_id = p_commissioning_request_id;

  return jsonb_build_object(
    'client_id', v_request.client_id,
    'commissioning_request_id', v_request.commissioning_request_id,
    'lease_owned', true,
    'active_request_count', v_active_requests,
    'exact_request_count', v_exact_requests,
    'active_job_count', 0,
    'open_incident_count', 0,
    'shopify_writes_enabled', false,
    'approved_draft_writes_enabled', false,
    'scheduler_state', 'disabled'
  );
end;
$$;

create or replace function orin_private.record_client_commissioning_stage(
  p_commissioning_request_id uuid,
  p_worker_id text,
  p_stage text,
  p_summary text,
  p_evidence jsonb
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.client_commissioning_requests%rowtype;
  v_current_rank integer;
  v_new_rank integer;
begin
  if p_stage not in ('worker_setup', 'dry_run_proof', 'scheduler_proof', 'watchdog_proof') then
    raise exception 'invalid commissioning stage' using errcode = '22023';
  end if;
  if char_length(btrim(coalesce(p_summary, ''))) not between 1 and 500 then
    raise exception 'invalid commissioning summary' using errcode = '22023';
  end if;
  if jsonb_typeof(coalesce(p_evidence, '{}'::jsonb)) <> 'object'
     or pg_column_size(coalesce(p_evidence, '{}'::jsonb)) > 16384
     or coalesce(p_evidence, '{}'::jsonb)::text ~* '(access[_ -]?token|authorization|bearer[[:space:]]|shpat_|shpca_|shpss_)' then
    raise exception 'commissioning evidence is unsafe' using errcode = '22023';
  end if;

  select request.* into v_request
  from public.client_commissioning_requests request
  where request.commissioning_request_id = p_commissioning_request_id
    and request.status = 'running'
    and request.worker_id = p_worker_id
    and request.lease_expires_at > statement_timestamp()
  for update;
  if not found then
    raise exception 'commissioning lease is not owned by this worker' using errcode = '42501';
  end if;

  v_current_rank := case v_request.stage
    when 'request_received' then 0 when 'worker_setup' then 1
    when 'dry_run_proof' then 2 when 'scheduler_proof' then 3
    when 'watchdog_proof' then 4 when 'complete' then 5 end;
  v_new_rank := case p_stage
    when 'worker_setup' then 1 when 'dry_run_proof' then 2
    when 'scheduler_proof' then 3 when 'watchdog_proof' then 4 end;
  if v_new_rank < v_current_rank or v_new_rank > v_current_rank + 1 then
    raise exception 'commissioning stage transition is not monotonic' using errcode = '55000';
  end if;

  perform orin_private.assert_commissioning_boundary_closed(v_request.client_id);
  update public.client_commissioning_requests request
  set stage = p_stage, heartbeat_at = statement_timestamp()
  where request.commissioning_request_id = p_commissioning_request_id;
  insert into public.client_commissioning_events (
    commissioning_request_id, client_id, stage, status, summary, evidence
  ) values (
    p_commissioning_request_id, v_request.client_id, p_stage, 'passed',
    btrim(p_summary), coalesce(p_evidence, '{}'::jsonb)
  );
end;
$$;

create or replace function orin_private.finish_client_commissioning(
  p_commissioning_request_id uuid,
  p_worker_id text,
  p_succeeded boolean,
  p_error_code text,
  p_evidence jsonb
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.client_commissioning_requests%rowtype;
  v_summary text;
begin
  if char_length(coalesce(p_error_code, '')) > 120
     or coalesce(p_error_code, '') !~ '^[A-Z0-9_]*$' then
    raise exception 'invalid commissioning error code' using errcode = '22023';
  end if;
  if jsonb_typeof(coalesce(p_evidence, '{}'::jsonb)) <> 'object'
     or pg_column_size(coalesce(p_evidence, '{}'::jsonb)) > 16384
     or coalesce(p_evidence, '{}'::jsonb)::text ~* '(access[_ -]?token|authorization|bearer[[:space:]]|shpat_|shpca_|shpss_)' then
    raise exception 'commissioning evidence is unsafe' using errcode = '22023';
  end if;

  select request.* into v_request
  from public.client_commissioning_requests request
  where request.commissioning_request_id = p_commissioning_request_id
    and request.status = 'running'
    and request.worker_id = p_worker_id
  for update;
  if not found then
    raise exception 'commissioning lease is not owned by this worker' using errcode = '42501';
  end if;

  update public.clients client
  set status = 'maintenance'
  where client.client_id = v_request.client_id;
  update public.client_runtime_settings settings
  set request_intake_enabled = false,
      automation_enabled = false,
      shopify_writes_enabled = false,
      approved_draft_writes_enabled = false,
      allowed_mode = 'dry-run'
  where settings.client_id = v_request.client_id;
  update public.scheduler_health health
  set state = 'disabled', scheduler_owner = null
  where health.client_id = v_request.client_id;

  if p_succeeded then
    if v_request.stage <> 'watchdog_proof'
       or exists (
         select required.stage
         from (values ('worker_setup'), ('dry_run_proof'), ('scheduler_proof'), ('watchdog_proof')) required(stage)
         where not exists (
           select 1 from public.client_commissioning_events event
           where event.commissioning_request_id = p_commissioning_request_id
             and event.stage = required.stage and event.status = 'passed'
         )
       ) then
      raise exception 'commissioning proof set is incomplete' using errcode = '55000';
    end if;
    v_summary := 'Trusted read-only commissioning completed. Recurring content execution remains disabled pending a separate pilot promotion.';
    update public.client_commissioning_requests request
    set status = 'succeeded', stage = 'complete', finished_at = statement_timestamp(),
        worker_id = null, lease_expires_at = null, heartbeat_at = statement_timestamp(),
        last_error = ''
    where request.commissioning_request_id = p_commissioning_request_id;
    update public.client_onboarding_requests onboarding
    set commissioning_status = 'pilot_pending', last_error = ''
    where onboarding.request_id = v_request.onboarding_request_id;
    insert into public.client_commissioning_events (
      commissioning_request_id, client_id, stage, status, summary, evidence
    ) values (
      p_commissioning_request_id, v_request.client_id, 'complete', 'passed',
      v_summary, coalesce(p_evidence, '{}'::jsonb)
    );
  else
    v_summary := 'Commissioning stopped safely. Every execution, scheduler, and Shopify gate remains closed.';
    update public.client_commissioning_requests request
    set status = 'failed', finished_at = statement_timestamp(),
        worker_id = null, lease_expires_at = null, heartbeat_at = statement_timestamp(),
        last_error = coalesce(nullif(p_error_code, ''), 'ORIN_COMMISSIONING_FAILED')
    where request.commissioning_request_id = p_commissioning_request_id;
    update public.client_onboarding_requests onboarding
    set commissioning_status = 'identity_verified',
        last_error = coalesce(nullif(p_error_code, ''), 'ORIN_COMMISSIONING_FAILED')
    where onboarding.request_id = v_request.onboarding_request_id;
    insert into public.client_commissioning_events (
      commissioning_request_id, client_id, stage, status, summary, evidence
    ) values (
      p_commissioning_request_id, v_request.client_id, v_request.stage, 'failed',
      v_summary, coalesce(p_evidence, '{}'::jsonb)
    );
  end if;
end;
$$;

revoke all on function orin_private.assert_commissioning_boundary_closed(text)
  from public, anon, authenticated, service_role, orin_commissioner;
revoke all on function orin_private.claim_next_client_commissioning(text, integer)
  from public, anon, authenticated, service_role;
revoke all on function orin_private.renew_client_commissioning_lease(uuid, text, integer)
  from public, anon, authenticated, service_role;
revoke all on function orin_private.get_client_commissioning_context(uuid, text)
  from public, anon, authenticated, service_role;
revoke all on function orin_private.client_commissioning_boundary_snapshot(uuid, text)
  from public, anon, authenticated, service_role;
revoke all on function orin_private.record_client_commissioning_stage(uuid, text, text, text, jsonb)
  from public, anon, authenticated, service_role;
revoke all on function orin_private.finish_client_commissioning(uuid, text, boolean, text, jsonb)
  from public, anon, authenticated, service_role;

grant execute on function orin_private.claim_next_client_commissioning(text, integer)
  to orin_commissioner;
grant execute on function orin_private.renew_client_commissioning_lease(uuid, text, integer)
  to orin_commissioner;
grant execute on function orin_private.get_client_commissioning_context(uuid, text)
  to orin_commissioner;
grant execute on function orin_private.client_commissioning_boundary_snapshot(uuid, text)
  to orin_commissioner;
grant execute on function orin_private.record_client_commissioning_stage(uuid, text, text, text, jsonb)
  to orin_commissioner;
grant execute on function orin_private.finish_client_commissioning(uuid, text, boolean, text, jsonb)
  to orin_commissioner;

grant orin_commissioner to postgres with set true;

comment on role orin_commissioner is
  'NOLOGIN trusted no-code commissioner; function-only, read-only Shopify proof, no content or gate privileges';
comment on function orin_private.get_client_commissioning_context(uuid, text) is
  'Returns one lease-bound onboarding bundle to the isolated commissioner, including the Vault token; never expose via Data API.';
comment on function orin_private.finish_client_commissioning(uuid, text, boolean, text, jsonb) is
  'Terminalizes commissioning and force-closes every execution, scheduler, and Shopify gate.';
