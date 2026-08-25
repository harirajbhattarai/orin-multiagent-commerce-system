-- Approval-only Shopify worker for generic OAuth-connected tenants.
--
-- The role can materialize and claim only an exact human-approved immutable
-- review draft. It receives one fresh access token for the leased client, but
-- never receives the refresh token or Shopify application secret. The broad
-- Shopify write gate must remain closed and live publishing is unsupported.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'orin_oauth_draft_worker') then
    create role orin_oauth_draft_worker nologin nosuperuser nocreatedb nocreaterole
      noinherit noreplication nobypassrls;
  end if;
end;
$$;

revoke all on schema public from orin_oauth_draft_worker;
revoke all on schema orin_private from orin_oauth_draft_worker;
grant usage on schema orin_private to orin_oauth_draft_worker;
revoke all on all tables in schema public from orin_oauth_draft_worker;
revoke all on all sequences in schema public from orin_oauth_draft_worker;
revoke all on all functions in schema public from orin_oauth_draft_worker;
revoke all on all functions in schema orin_private from orin_oauth_draft_worker;

create or replace function orin_private.assert_oauth_approved_draft_boundary(
  p_client_id text
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
  v_profile public.client_profiles%rowtype;
  v_onboarding public.client_onboarding_requests%rowtype;
begin
  if p_client_id in ('hoverboard_store', 'hcs_gadgets') then
    raise exception 'dedicated production tenants cannot use the OAuth draft worker'
      using errcode = '42501';
  end if;

  select * into v_client from public.clients where client_id = p_client_id;
  select * into v_settings from public.client_runtime_settings where client_id = p_client_id;
  select * into v_health from public.scheduler_health where client_id = p_client_id;
  select * into v_profile from public.client_profiles where client_id = p_client_id;
  select * into v_onboarding
  from public.client_onboarding_requests
  where client_id = p_client_id and status = 'database_provisioned';

  if v_client.client_id is null or v_settings.client_id is null
     or v_health.client_id is null or v_profile.client_id is null
     or v_onboarding.client_id is null then
    raise exception 'OAuth draft tenant boundary is incomplete' using errcode = 'P0002';
  end if;
  if v_profile.shopify_connection_method <> 'oauth'
     or v_profile.shopify_credential_secret_id is null
     or v_profile.shopify_access_token_expires_at is null
     or v_profile.shopify_access_token_expires_at <= statement_timestamp() + interval '2 minutes'
     or nullif(v_profile.shopify_store_domain, '') is null
     or nullif(v_profile.shopify_blog_gid, '') is null then
    raise exception 'fresh OAuth Shopify access is unavailable' using errcode = '55000';
  end if;
  if v_client.status <> 'active'
     or not v_settings.request_intake_enabled
     or not v_settings.automation_enabled
     or not v_settings.approved_draft_writes_enabled
     or v_settings.shopify_writes_enabled
     or v_settings.allowed_mode <> 'dry-run'
     or v_settings.max_concurrency <> 1
     or v_health.state <> 'disabled'
     or v_health.scheduler_owner is not null then
    raise exception 'OAuth approval-only execution gates are not open safely'
      using errcode = '55000';
  end if;
end;
$$;

create or replace function orin_private.materialize_next_oauth_approved_draft_decision(
  p_client_id text
)
returns table (decision_id uuid, job_id uuid, processing_status text)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_decision public.content_decisions%rowtype;
  v_item public.content_plan_items%rowtype;
  v_draft public.content_drafts%rowtype;
  v_job_id uuid;
begin
  perform orin_private.assert_oauth_approved_draft_boundary(p_client_id);

  select decision.* into v_decision
  from public.content_decisions decision
  where decision.client_id = p_client_id
    and decision.processing_status = 'recorded'
    and decision.decision = 'approve_hidden_draft'
  order by decision.created_at, decision.decision_id
  for update of decision skip locked
  limit 1;
  if not found then return; end if;

  select * into v_item
  from public.content_plan_items item
  where item.client_id = p_client_id
    and item.content_item_id = v_decision.content_item_id
  for update;
  if not found then
    update public.content_decisions
    set processing_status = 'superseded',
        outcome = 'Content item no longer exists before OAuth Shopify replay.'
    where content_decisions.decision_id = v_decision.decision_id;
    return query select v_decision.decision_id, null::uuid, 'superseded'::text;
    return;
  end if;
  if v_decision.content_item_version <> v_item.version
     or v_item.status <> 'local_draft_created' then
    update public.content_decisions
    set processing_status = 'superseded',
        outcome = 'Content version or stage changed before OAuth Shopify replay.'
    where content_decisions.decision_id = v_decision.decision_id;
    return query select v_decision.decision_id, null::uuid, 'superseded'::text;
    return;
  end if;

  select * into v_draft
  from public.content_drafts draft
  where draft.client_id = p_client_id
    and draft.content_item_id = v_item.content_item_id
    and draft.content_item_version = v_item.version
  for update;
  if not found then return; end if;

  insert into public.content_jobs (
    client_id, source_job_key, request_id, requested_by, requested_mode,
    status, scheduled_for, payload, content_plan_item_id,
    approved_draft_id, approved_content_item_version, approved_body_sha256
  ) values (
    p_client_id,
    'decision:' || v_decision.decision_id::text,
    v_decision.request_id,
    v_decision.requested_by,
    'hidden-draft',
    'queued',
    statement_timestamp(),
    '{}'::jsonb,
    v_item.content_item_id,
    v_draft.draft_id,
    v_draft.content_item_version,
    v_draft.body_sha256
  ) returning content_jobs.job_id into v_job_id;

  update public.content_decisions
  set processing_status = 'consumed',
      consumed_at = statement_timestamp(),
      content_job_id = v_job_id,
      outcome = 'Exact OAuth-client reviewed HTML frozen for one unpublished Shopify draft.'
  where content_decisions.decision_id = v_decision.decision_id;

  return query select v_decision.decision_id, v_job_id, 'consumed'::text;
end;
$$;

create or replace function orin_private.claim_next_oauth_approved_draft_job(
  p_worker_id text,
  p_client_id text,
  p_lease_seconds integer default 1200
)
returns table (
  job_id uuid, client_id text, request_id uuid, requested_mode text,
  attempt_count smallint, payload jsonb, lease_expires_at timestamptz
)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  v_job_id uuid;
begin
  if p_client_id in ('hoverboard_store', 'hcs_gadgets') then
    raise exception 'dedicated production tenants cannot use the OAuth draft worker'
      using errcode = '42501';
  end if;
  if p_worker_id is null or length(p_worker_id) not between 8 and 128
     or p_worker_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]+$' then
    raise exception 'invalid OAuth draft worker identifier' using errcode = '22023';
  end if;
  if p_lease_seconds not between 60 and 3600 then
    raise exception 'lease must be between 60 and 3600 seconds' using errcode = '22023';
  end if;
  perform orin_private.assert_oauth_approved_draft_boundary(p_client_id);

  if exists (
    select 1 from public.content_jobs active
    where active.client_id = p_client_id
      and active.status in ('leased', 'running')
      and active.lease_expires_at > statement_timestamp()
  ) then return; end if;

  select candidate.job_id into v_job_id
  from public.content_jobs candidate
  where candidate.client_id = p_client_id
    and candidate.requested_mode = 'hidden-draft'
    and candidate.payload = '{}'::jsonb
    and candidate.attempt_count < candidate.max_attempts
    and candidate.content_plan_item_id is not null
    and candidate.approved_draft_id is not null
    and candidate.approved_content_item_version is not null
    and candidate.approved_body_sha256 is not null
    and (
      (candidate.status = 'queued' and candidate.scheduled_for <= statement_timestamp())
      or (candidate.status in ('leased', 'running')
          and candidate.lease_expires_at <= statement_timestamp())
    )
    and exists (
      select 1
      from public.content_decisions decision
      join public.content_drafts draft
        on draft.client_id = candidate.client_id
       and draft.draft_id = candidate.approved_draft_id
       and draft.content_item_id = candidate.content_plan_item_id
       and draft.content_item_version = candidate.approved_content_item_version
       and draft.body_sha256 = candidate.approved_body_sha256
      where decision.client_id = candidate.client_id
        and decision.content_job_id = candidate.job_id
        and decision.request_id = candidate.request_id
        and decision.content_item_id = candidate.content_plan_item_id
        and decision.content_item_version = candidate.approved_content_item_version
        and decision.decision = 'approve_hidden_draft'
        and decision.processing_status = 'consumed'
        and candidate.source_job_key = 'decision:' || decision.decision_id::text
    )
  order by case when candidate.status in ('leased', 'running') then 0 else 1 end,
           candidate.scheduled_for, candidate.created_at, candidate.job_id
  for update of candidate skip locked
  limit 1;
  if v_job_id is null then return; end if;

  return query
  update public.content_jobs claimed
  set status = 'leased',
      attempt_count = claimed.attempt_count + 1,
      lock_owner = p_worker_id,
      locked_at = statement_timestamp(),
      lease_expires_at = statement_timestamp() + make_interval(secs => p_lease_seconds),
      last_error_code = null
  where claimed.job_id = v_job_id
    and claimed.client_id = p_client_id
    and claimed.requested_mode = 'hidden-draft'
  returning claimed.job_id, claimed.client_id, claimed.request_id,
            claimed.requested_mode, claimed.attempt_count, claimed.payload,
            claimed.lease_expires_at;
end;
$$;

create or replace function orin_private.get_oauth_approved_draft_context(
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
  v_profile public.client_profiles%rowtype;
  v_display_name text;
  v_access_token text;
  v_snapshot jsonb;
begin
  select * into v_job
  from public.content_jobs job
  where job.job_id = p_job_id;
  if not found or v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.status not in ('leased', 'running')
     or v_job.lock_owner is distinct from p_worker_id
     or v_job.lease_expires_at <= statement_timestamp()
     or v_job.requested_mode <> 'hidden-draft'
     or v_job.payload <> '{}'::jsonb then
    raise exception 'worker does not own an eligible OAuth draft lease'
      using errcode = '42501';
  end if;
  perform orin_private.assert_oauth_approved_draft_boundary(v_job.client_id);

  select * into v_profile
  from public.client_profiles profile
  where profile.client_id = v_job.client_id;
  select client.display_name into v_display_name
  from public.clients client
  where client.client_id = v_job.client_id;

  select secret.decrypted_secret into v_access_token
  from vault.decrypted_secrets secret
  where secret.id = v_profile.shopify_credential_secret_id;
  if nullif(v_access_token, '') is null then
    raise exception 'OAuth Shopify access token is unavailable' using errcode = '55000';
  end if;

  v_snapshot := orin_private.get_content_plan_snapshot(p_job_id, p_worker_id);
  return jsonb_build_object(
    'schema', 'orin.oauth-approved-draft-context/v1',
    'client_id', v_job.client_id,
    'snapshot', v_snapshot,
    'shopify', jsonb_build_object(
      'store_domain', v_profile.shopify_store_domain,
      'access_token', v_access_token,
      'api_version', '2026-07',
      'blog_id', v_profile.shopify_blog_gid,
      'author_name', v_display_name
    )
  );
end;
$$;

create or replace function orin_private.complete_oauth_approved_draft_job(
  p_job_id uuid,
  p_worker_id text,
  p_final_result jsonb
)
returns table (run_id text, status text, replayed boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.content_jobs%rowtype;
begin
  select * into v_job
  from public.content_jobs job
  where job.job_id = p_job_id;
  if not found or v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.requested_mode <> 'hidden-draft'
     or v_job.source_job_key not like 'decision:%' then
    raise exception 'job is outside the OAuth approval boundary' using errcode = '42501';
  end if;
  return query
  select result.run_id, result.status, result.replayed
  from orin_private.complete_job_with_review_draft(
    p_job_id, p_worker_id, p_final_result, null::jsonb
  ) result;
end;
$$;

create or replace function orin_private.defer_oauth_approved_draft_job(
  p_job_id uuid,
  p_worker_id text,
  p_final_result jsonb
)
returns table (run_id text, status text, replayed boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.content_jobs%rowtype;
begin
  select * into v_job
  from public.content_jobs job
  where job.job_id = p_job_id;
  if not found or v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.requested_mode <> 'hidden-draft'
     or v_job.source_job_key not like 'decision:%' then
    raise exception 'job is outside the OAuth approval boundary' using errcode = '42501';
  end if;
  return query
  select result.run_id, result.status, result.replayed
  from orin_private.defer_job(p_job_id, p_worker_id, p_final_result) result;
end;
$$;

revoke all on function orin_private.assert_oauth_approved_draft_boundary(text)
  from public, anon, authenticated, orin_oauth_draft_worker;
revoke all on function orin_private.materialize_next_oauth_approved_draft_decision(text)
  from public, anon, authenticated;
revoke all on function orin_private.claim_next_oauth_approved_draft_job(text, text, integer)
  from public, anon, authenticated;
revoke all on function orin_private.get_oauth_approved_draft_context(uuid, text)
  from public, anon, authenticated;
revoke all on function orin_private.complete_oauth_approved_draft_job(uuid, text, jsonb)
  from public, anon, authenticated;
revoke all on function orin_private.defer_oauth_approved_draft_job(uuid, text, jsonb)
  from public, anon, authenticated;

grant execute on function orin_private.materialize_next_oauth_approved_draft_decision(text)
  to orin_oauth_draft_worker;
grant execute on function orin_private.claim_next_oauth_approved_draft_job(text, text, integer)
  to orin_oauth_draft_worker;
grant execute on function orin_private.get_oauth_approved_draft_context(uuid, text)
  to orin_oauth_draft_worker;
grant execute on function orin_private.complete_oauth_approved_draft_job(uuid, text, jsonb)
  to orin_oauth_draft_worker;
grant execute on function orin_private.defer_oauth_approved_draft_job(uuid, text, jsonb)
  to orin_oauth_draft_worker;
grant execute on function orin_private.renew_job_lease(uuid, text, integer)
  to orin_oauth_draft_worker;

comment on role orin_oauth_draft_worker is
  'Function-only worker for exact human-approved unpublished drafts on generic OAuth clients.';

-- Service-role-only OAuth refresh boundary used immediately before the browser
-- records an approved-draft decision. These functions never return credentials
-- to the browser; the Edge Function consumes them server-side.
create or replace function public.service_get_client_shopify_approval_connection(
  p_operator_id uuid,
  p_client_id text
)
returns table (
  store_domain text,
  blog_gid text,
  blog_title text,
  access_token text,
  connection_method text,
  refresh_token text,
  access_token_expires_at timestamptz,
  refresh_token_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_profile public.client_profiles%rowtype;
  v_access_token text;
  v_refresh_token text;
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  if p_client_id in ('hoverboard_store', 'hcs_gadgets') then
    raise exception 'dedicated clients do not use OAuth approval refresh'
      using errcode = '42501';
  end if;
  if not exists (
    select 1
    from public.clients client
    join public.client_runtime_settings settings using (client_id)
    join public.scheduler_health health using (client_id)
    where client.client_id = p_client_id
      and client.status = 'active'
      and settings.request_intake_enabled
      and settings.automation_enabled
      and settings.approved_draft_writes_enabled
      and not settings.shopify_writes_enabled
      and settings.allowed_mode = 'dry-run'
      and settings.max_concurrency = 1
      and health.state = 'disabled'
      and health.scheduler_owner is null
  ) then
    raise exception 'OAuth approval-only gates are not open safely' using errcode = '55000';
  end if;

  select * into v_profile
  from public.client_profiles profile
  where profile.client_id = p_client_id;
  if not found or v_profile.shopify_connection_method <> 'oauth'
     or v_profile.shopify_refresh_secret_id is null then
    raise exception 'OAuth client profile is unavailable' using errcode = 'P0002';
  end if;
  select decrypted_secret into v_access_token
  from vault.decrypted_secrets where id = v_profile.shopify_credential_secret_id;
  select decrypted_secret into v_refresh_token
  from vault.decrypted_secrets where id = v_profile.shopify_refresh_secret_id;
  if nullif(v_access_token, '') is null or nullif(v_refresh_token, '') is null then
    raise exception 'OAuth Shopify credentials are unavailable' using errcode = '55000';
  end if;
  return query select
    v_profile.shopify_store_domain, v_profile.shopify_blog_gid,
    v_profile.shopify_blog_title, v_access_token,
    v_profile.shopify_connection_method, v_refresh_token,
    v_profile.shopify_access_token_expires_at,
    v_profile.shopify_refresh_token_expires_at;
end;
$$;

create or replace function public.service_rotate_client_shopify_approval_tokens(
  p_operator_id uuid,
  p_client_id text,
  p_previous_refresh_token text,
  p_access_token text,
  p_refresh_token text,
  p_access_token_expires_at timestamptz,
  p_refresh_token_expires_at timestamptz
)
returns table (
  client_id text,
  access_token_expires_at timestamptz,
  refresh_token_expires_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_profile public.client_profiles%rowtype;
  v_stored_refresh_token text;
  v_access_name text;
  v_refresh_name text;
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  if p_client_id in ('hoverboard_store', 'hcs_gadgets')
     or nullif(btrim(p_previous_refresh_token), '') is null
     or nullif(btrim(p_access_token), '') is null
     or nullif(btrim(p_refresh_token), '') is null
     or char_length(p_previous_refresh_token) > 512
     or char_length(p_access_token) > 512
     or char_length(p_refresh_token) > 512
     or p_access_token_expires_at <= statement_timestamp()
     or p_refresh_token_expires_at <= p_access_token_expires_at then
    raise exception 'valid OAuth approval rotation values are required'
      using errcode = '22023';
  end if;
  if not exists (
    select 1
    from public.clients client
    join public.client_runtime_settings settings using (client_id)
    join public.scheduler_health health using (client_id)
    where client.client_id = p_client_id
      and client.status = 'active'
      and settings.request_intake_enabled
      and settings.automation_enabled
      and settings.approved_draft_writes_enabled
      and not settings.shopify_writes_enabled
      and settings.allowed_mode = 'dry-run'
      and settings.max_concurrency = 1
      and health.state = 'disabled'
      and health.scheduler_owner is null
  ) then
    raise exception 'OAuth approval-only gates are not open safely' using errcode = '55000';
  end if;

  select * into v_profile
  from public.client_profiles profile
  where profile.client_id = p_client_id
  for update;
  if not found or v_profile.shopify_connection_method <> 'oauth'
     or v_profile.shopify_refresh_secret_id is null then
    raise exception 'OAuth client profile is unavailable' using errcode = 'P0002';
  end if;
  select decrypted_secret into v_stored_refresh_token
  from vault.decrypted_secrets where id = v_profile.shopify_refresh_secret_id;
  if v_stored_refresh_token is distinct from p_previous_refresh_token then
    raise exception 'Shopify OAuth refresh credential was already rotated'
      using errcode = '40001';
  end if;

  v_access_name := 'orin_shopify_' || p_client_id || '_'
    || replace(v_profile.onboarding_request_id::text, '-', '');
  v_refresh_name := 'orin_shopify_refresh_' || p_client_id || '_'
    || replace(v_profile.onboarding_request_id::text, '-', '');
  perform vault.update_secret(
    v_profile.shopify_credential_secret_id, p_access_token, v_access_name,
    'ORIN Shopify OAuth offline token for onboarding request '
      || v_profile.onboarding_request_id::text, null
  );
  perform vault.update_secret(
    v_profile.shopify_refresh_secret_id, p_refresh_token, v_refresh_name,
    'ORIN Shopify OAuth refresh token for onboarding request '
      || v_profile.onboarding_request_id::text, null
  );
  update public.client_profiles
  set shopify_access_token_expires_at = p_access_token_expires_at,
      shopify_refresh_token_expires_at = p_refresh_token_expires_at
  where client_profiles.client_id = p_client_id;
  update public.client_onboarding_requests
  set shopify_access_token_expires_at = p_access_token_expires_at,
      shopify_refresh_token_expires_at = p_refresh_token_expires_at,
      last_error = ''
  where request_id = v_profile.onboarding_request_id;
  return query select p_client_id, p_access_token_expires_at, p_refresh_token_expires_at;
end;
$$;

revoke all on function public.service_get_client_shopify_approval_connection(uuid, text)
  from public, anon, authenticated;
revoke all on function public.service_rotate_client_shopify_approval_tokens(
  uuid, text, text, text, text, timestamptz, timestamptz
) from public, anon, authenticated;
grant execute on function public.service_get_client_shopify_approval_connection(uuid, text)
  to service_role;
grant execute on function public.service_rotate_client_shopify_approval_tokens(
  uuid, text, text, text, text, timestamptz, timestamptz
) to service_role;
