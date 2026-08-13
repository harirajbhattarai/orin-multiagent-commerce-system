-- Route every privileged onboarding mutation through the authenticated Edge
-- Function. Direct browser RPC execution is revoked even for operators.

revoke execute on function public.create_client_onboarding_request(
  text, text, text, text, text, text, text, text[]
) from authenticated;
revoke execute on function public.store_onboarding_shopify_connection(uuid, text, text, text)
  from authenticated;
revoke execute on function public.update_client_onboarding_scope(uuid, jsonb)
  from authenticated;
revoke execute on function public.provision_client_from_onboarding(uuid)
  from authenticated;

create or replace function orin_private.assume_verified_operator(p_operator_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not exists (
    select 1
    from public.platform_operators operator
    where operator.user_id = p_operator_id
      and operator.active
  ) then
    raise exception 'active platform operator required' using errcode = '42501';
  end if;
  perform set_config('request.jwt.claim.sub', p_operator_id::text, true);
end;
$$;

revoke all on function orin_private.assume_verified_operator(uuid)
  from public, anon, authenticated;

create or replace function public.service_create_client_onboarding_request(
  p_operator_id uuid,
  p_client_id text,
  p_display_name text,
  p_owner_email text,
  p_shopify_store_domain text,
  p_market_country text,
  p_timezone text,
  p_brand_voice text,
  p_content_categories text[]
)
returns table (
  request_id uuid,
  client_id text,
  status text,
  credential_status text,
  commissioning_status text
)
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  return query
  select result.request_id, result.client_id, result.status,
    result.credential_status, result.commissioning_status
  from public.create_client_onboarding_request(
    p_client_id, p_display_name, p_owner_email, p_shopify_store_domain,
    p_market_country, p_timezone, p_brand_voice, p_content_categories
  ) result;
end;
$$;

create or replace function public.service_store_onboarding_shopify_connection(
  p_operator_id uuid,
  p_request_id uuid,
  p_access_token text,
  p_shopify_blog_gid text,
  p_shopify_blog_title text
)
returns table (
  request_id uuid,
  credential_status text,
  status text,
  shopify_blog_gid text,
  shopify_blog_title text
)
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  return query
  select result.request_id, result.credential_status, result.status,
    result.shopify_blog_gid, result.shopify_blog_title
  from public.store_onboarding_shopify_connection(
    p_request_id, p_access_token, p_shopify_blog_gid, p_shopify_blog_title
  ) result;
end;
$$;

create or replace function public.service_update_client_onboarding_scope(
  p_operator_id uuid,
  p_request_id uuid,
  p_product_scope jsonb
)
returns table (request_id uuid, status text, product_scope jsonb)
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  return query
  select result.request_id, result.status, result.product_scope
  from public.update_client_onboarding_scope(p_request_id, p_product_scope) result;
end;
$$;

create or replace function public.service_provision_client_from_onboarding(
  p_operator_id uuid,
  p_request_id uuid
)
returns table (
  request_id uuid,
  client_id text,
  status text,
  commissioning_status text
)
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  return query
  select result.request_id, result.client_id, result.status, result.commissioning_status
  from public.provision_client_from_onboarding(p_request_id) result;
end;
$$;

revoke all on function public.service_create_client_onboarding_request(
  uuid, text, text, text, text, text, text, text, text[]
) from public, anon, authenticated;
revoke all on function public.service_store_onboarding_shopify_connection(
  uuid, uuid, text, text, text
) from public, anon, authenticated;
revoke all on function public.service_update_client_onboarding_scope(
  uuid, uuid, jsonb
) from public, anon, authenticated;
revoke all on function public.service_provision_client_from_onboarding(uuid, uuid)
  from public, anon, authenticated;

grant execute on function public.service_create_client_onboarding_request(
  uuid, text, text, text, text, text, text, text, text[]
) to service_role;
grant execute on function public.service_store_onboarding_shopify_connection(
  uuid, uuid, text, text, text
) to service_role;
grant execute on function public.service_update_client_onboarding_scope(
  uuid, uuid, jsonb
) to service_role;
grant execute on function public.service_provision_client_from_onboarding(uuid, uuid)
  to service_role;
