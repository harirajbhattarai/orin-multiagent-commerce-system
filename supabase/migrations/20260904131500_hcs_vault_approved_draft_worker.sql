-- Keep HCS approval execution durable without duplicating its Shopify token on
-- the VPS. The fixed client still uses its exact approval-bound claim path;
-- only the leased worker can receive the Vault credential, and it remains
-- unable to publish live.

create or replace function orin_private.materialize_next_hcs_vault_approved_draft_decision(
  p_client_id text
)
returns table (decision_id uuid, job_id uuid, processing_status text)
language sql
security definer
set search_path = ''
as $$
  select *
  from orin_private.materialize_next_hcs_approved_draft_decision_for_client(p_client_id)
$$;

create or replace function orin_private.claim_next_hcs_vault_approved_draft_job(
  p_worker_id text,
  p_client_id text,
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
language sql
security definer
set search_path = ''
as $$
  select *
  from orin_private.claim_next_hcs_approved_draft_job_for_client(
    p_worker_id, p_client_id, p_lease_seconds
  )
$$;

create or replace function orin_private.get_hcs_vault_approved_draft_context(
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
  if not found
     or v_job.client_id <> 'hcs_gadgets'
     or v_job.status not in ('leased', 'running')
     or v_job.lock_owner is distinct from p_worker_id
     or v_job.lease_expires_at <= statement_timestamp()
     or v_job.requested_mode <> 'hidden-draft'
     or v_job.payload <> '{}'::jsonb
     or v_job.source_job_key not like 'decision:%' then
    raise exception 'worker does not own an eligible HCS draft lease'
      using errcode = '42501';
  end if;

  if not exists (
    select 1
    from public.clients client
    join public.client_runtime_settings settings using (client_id)
    where client.client_id = 'hcs_gadgets'
      and client.status = 'active'
      and settings.request_intake_enabled
      and settings.automation_enabled
      and settings.approved_draft_writes_enabled
      and not settings.shopify_writes_enabled
      and settings.allowed_mode = 'dry-run'
      and settings.max_concurrency = 1
  ) then
    raise exception 'HCS approval-only gates are not open safely'
      using errcode = '55000';
  end if;

  select * into v_profile
  from public.client_profiles profile
  where profile.client_id = 'hcs_gadgets';
  if not found or v_profile.shopify_connection_method <> 'manual_token' then
    raise exception 'HCS manual-token profile is unavailable' using errcode = 'P0002';
  end if;
  select client.display_name into v_display_name
  from public.clients client
  where client.client_id = 'hcs_gadgets';
  select secret.decrypted_secret into v_access_token
  from vault.decrypted_secrets secret
  where secret.id = v_profile.shopify_credential_secret_id;
  if nullif(v_access_token, '') is null then
    raise exception 'HCS Shopify access token is unavailable' using errcode = '55000';
  end if;

  v_snapshot := orin_private.get_content_plan_snapshot(p_job_id, p_worker_id);
  return jsonb_build_object(
    'schema', 'orin.hcs-vault-approved-draft-context/v1',
    'client_id', 'hcs_gadgets',
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

create or replace function orin_private.complete_hcs_vault_approved_draft_job(
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
  if not found
     or v_job.client_id <> 'hcs_gadgets'
     or v_job.requested_mode <> 'hidden-draft'
     or v_job.source_job_key not like 'decision:%' then
    raise exception 'job is outside the HCS Vault approval boundary'
      using errcode = '42501';
  end if;
  return query
  select result.run_id, result.status, result.replayed
  from orin_private.complete_job_with_review_draft(
    p_job_id, p_worker_id, p_final_result, null::jsonb
  ) result;
end;
$$;

create or replace function orin_private.defer_hcs_vault_approved_draft_job(
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
  if not found
     or v_job.client_id <> 'hcs_gadgets'
     or v_job.requested_mode <> 'hidden-draft'
     or v_job.source_job_key not like 'decision:%' then
    raise exception 'job is outside the HCS Vault approval boundary'
      using errcode = '42501';
  end if;
  return query
  select result.run_id, result.status, result.replayed
  from orin_private.defer_job(p_job_id, p_worker_id, p_final_result) result;
end;
$$;

revoke all on function orin_private.materialize_next_hcs_vault_approved_draft_decision(text)
  from public, anon, authenticated;
revoke all on function orin_private.claim_next_hcs_vault_approved_draft_job(text, text, integer)
  from public, anon, authenticated;
revoke all on function orin_private.get_hcs_vault_approved_draft_context(uuid, text)
  from public, anon, authenticated;
revoke all on function orin_private.complete_hcs_vault_approved_draft_job(uuid, text, jsonb)
  from public, anon, authenticated;
revoke all on function orin_private.defer_hcs_vault_approved_draft_job(uuid, text, jsonb)
  from public, anon, authenticated;

grant execute on function orin_private.materialize_next_hcs_vault_approved_draft_decision(text)
  to orin_oauth_draft_worker;
grant execute on function orin_private.claim_next_hcs_vault_approved_draft_job(text, text, integer)
  to orin_oauth_draft_worker;
grant execute on function orin_private.get_hcs_vault_approved_draft_context(uuid, text)
  to orin_oauth_draft_worker;
grant execute on function orin_private.complete_hcs_vault_approved_draft_job(uuid, text, jsonb)
  to orin_oauth_draft_worker;
grant execute on function orin_private.defer_hcs_vault_approved_draft_job(uuid, text, jsonb)
  to orin_oauth_draft_worker;

comment on function orin_private.get_hcs_vault_approved_draft_context(uuid, text) is
  'Lease-bound HCS unpublished-draft context; decrypts only its existing Vault access token.';
