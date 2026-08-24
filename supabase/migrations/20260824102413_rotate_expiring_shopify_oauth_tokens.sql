-- Rotate Shopify expiring offline OAuth credentials before read-only audits or
-- no-code commissioning requests. Token material remains available only to the
-- service-role Edge Function and Vault-backed commissioner boundary.

revoke all on function public.service_get_client_shopify_audit_connection(uuid, text)
  from public, anon, authenticated, service_role;
drop function public.service_get_client_shopify_audit_connection(uuid, text);

create function public.service_get_client_shopify_audit_connection(
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
  perform orin_private.assert_commissioning_boundary_closed(p_client_id);

  select profile.* into v_profile
  from public.client_profiles profile
  where profile.client_id = p_client_id;
  if not found then
    raise exception 'provisioned client profile not found' using errcode = 'P0002';
  end if;

  select secret.decrypted_secret into v_access_token
  from vault.decrypted_secrets secret
  where secret.id = v_profile.shopify_credential_secret_id;
  if nullif(v_access_token, '') is null then
    raise exception 'encrypted Shopify credential is unavailable' using errcode = '55000';
  end if;

  if v_profile.shopify_connection_method = 'oauth' then
    select secret.decrypted_secret into v_refresh_token
    from vault.decrypted_secrets secret
    where secret.id = v_profile.shopify_refresh_secret_id;
    if nullif(v_refresh_token, '') is null
       or v_profile.shopify_access_token_expires_at is null
       or v_profile.shopify_refresh_token_expires_at is null then
      raise exception 'encrypted Shopify OAuth refresh credential is unavailable'
        using errcode = '55000';
    end if;
  end if;

  return query select
    v_profile.shopify_store_domain,
    v_profile.shopify_blog_gid,
    v_profile.shopify_blog_title,
    v_access_token,
    v_profile.shopify_connection_method,
    v_refresh_token,
    v_profile.shopify_access_token_expires_at,
    v_profile.shopify_refresh_token_expires_at;
end;
$$;

create function public.service_rotate_client_shopify_oauth_tokens(
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
  v_onboarding public.client_onboarding_requests%rowtype;
  v_stored_refresh_token text;
  v_access_secret_name text;
  v_refresh_secret_name text;
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  perform orin_private.assert_commissioning_boundary_closed(p_client_id);

  if nullif(btrim(p_previous_refresh_token), '') is null
     or nullif(btrim(p_access_token), '') is null
     or nullif(btrim(p_refresh_token), '') is null
     or char_length(p_previous_refresh_token) > 512
     or char_length(p_access_token) > 512
     or char_length(p_refresh_token) > 512 then
    raise exception 'valid Shopify OAuth rotation credentials are required'
      using errcode = '22023';
  end if;
  if p_access_token_expires_at <= statement_timestamp()
     or p_refresh_token_expires_at <= p_access_token_expires_at then
    raise exception 'valid Shopify OAuth rotation expiries are required'
      using errcode = '22023';
  end if;

  select profile.* into v_profile
  from public.client_profiles profile
  where profile.client_id = p_client_id
  for update;
  if not found or v_profile.shopify_connection_method <> 'oauth'
     or v_profile.shopify_refresh_secret_id is null then
    raise exception 'OAuth-connected client profile not found' using errcode = 'P0002';
  end if;

  select onboarding.* into v_onboarding
  from public.client_onboarding_requests onboarding
  where onboarding.request_id = v_profile.onboarding_request_id
    and onboarding.status = 'database_provisioned'
  for update;
  if not found or v_onboarding.shopify_connection_method <> 'oauth'
     or v_onboarding.shopify_credential_secret_id <> v_profile.shopify_credential_secret_id
     or v_onboarding.shopify_refresh_secret_id <> v_profile.shopify_refresh_secret_id then
    raise exception 'OAuth onboarding and client credentials are not aligned'
      using errcode = '55000';
  end if;

  select secret.decrypted_secret into v_stored_refresh_token
  from vault.decrypted_secrets secret
  where secret.id = v_profile.shopify_refresh_secret_id;
  if v_stored_refresh_token is distinct from p_previous_refresh_token then
    raise exception 'Shopify OAuth refresh credential was already rotated'
      using errcode = '40001';
  end if;

  v_access_secret_name := 'orin_shopify_' || v_profile.client_id || '_'
    || replace(v_profile.onboarding_request_id::text, '-', '');
  v_refresh_secret_name := 'orin_shopify_refresh_' || v_profile.client_id || '_'
    || replace(v_profile.onboarding_request_id::text, '-', '');

  perform vault.update_secret(
    v_profile.shopify_credential_secret_id,
    p_access_token,
    v_access_secret_name,
    'ORIN Shopify OAuth offline token for onboarding request '
      || v_profile.onboarding_request_id::text,
    null
  );
  perform vault.update_secret(
    v_profile.shopify_refresh_secret_id,
    p_refresh_token,
    v_refresh_secret_name,
    'ORIN Shopify OAuth refresh token for onboarding request '
      || v_profile.onboarding_request_id::text,
    null
  );

  update public.client_profiles profile
  set shopify_access_token_expires_at = p_access_token_expires_at,
      shopify_refresh_token_expires_at = p_refresh_token_expires_at
  where profile.client_id = p_client_id;

  update public.client_onboarding_requests onboarding
  set shopify_access_token_expires_at = p_access_token_expires_at,
      shopify_refresh_token_expires_at = p_refresh_token_expires_at,
      last_error = ''
  where onboarding.request_id = v_profile.onboarding_request_id;

  return query select p_client_id, p_access_token_expires_at, p_refresh_token_expires_at;
end;
$$;

revoke all on function public.service_get_client_shopify_audit_connection(uuid, text)
  from public, anon, authenticated;
revoke all on function public.service_rotate_client_shopify_oauth_tokens(
  uuid, text, text, text, text, timestamptz, timestamptz
) from public, anon, authenticated;

grant execute on function public.service_get_client_shopify_audit_connection(uuid, text)
  to service_role;
grant execute on function public.service_rotate_client_shopify_oauth_tokens(
  uuid, text, text, text, text, timestamptz, timestamptz
) to service_role;

comment on function public.service_get_client_shopify_audit_connection(uuid, text) is
  'Service-role-only Vault bridge for fail-closed Shopify audits and OAuth refresh.';
comment on function public.service_rotate_client_shopify_oauth_tokens(
  uuid, text, text, text, text, timestamptz, timestamptz
) is 'Service-role-only atomic Vault rotation for expiring Shopify offline OAuth credentials.';
