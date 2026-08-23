-- Self-serve Shopify OAuth for client onboarding.
--
-- The browser never receives an Admin API token. A short-lived, one-time
-- state record binds the Shopify callback to the authenticated operator and
-- onboarding request. The Edge Function exchanges the code, discovers the
-- store/catalogue, and stores the resulting offline token in Vault.

alter table public.client_onboarding_requests
  drop constraint client_onboarding_requests_status_check;

alter table public.client_onboarding_requests
  add constraint client_onboarding_requests_status_check
  check (status in (
    'draft', 'oauth_connected', 'connection_verified',
    'ready_to_provision', 'database_provisioned', 'failed', 'cancelled'
  ));

alter table public.client_onboarding_requests
  add column shopify_connection_method text not null default 'manual_token'
    check (shopify_connection_method in ('manual_token', 'oauth')),
  add column shopify_discovery jsonb not null default '{}'::jsonb
    check (jsonb_typeof(shopify_discovery) = 'object'),
  add column shopify_oauth_connected_at timestamptz,
  add column shopify_refresh_secret_id uuid,
  add column shopify_access_token_expires_at timestamptz,
  add column shopify_refresh_token_expires_at timestamptz;

alter table public.client_profiles
  add column shopify_connection_method text not null default 'manual_token'
    check (shopify_connection_method in ('manual_token', 'oauth')),
  add column shopify_refresh_secret_id uuid,
  add column shopify_access_token_expires_at timestamptz,
  add column shopify_refresh_token_expires_at timestamptz;

grant select (
  shopify_connection_method, shopify_discovery, shopify_oauth_connected_at,
  shopify_access_token_expires_at, shopify_refresh_token_expires_at
) on table public.client_onboarding_requests to authenticated;

create or replace function orin_private.copy_onboarding_shopify_oauth_metadata()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.client_onboarding_requests%rowtype;
begin
  select onboarding.* into v_request
  from public.client_onboarding_requests onboarding
  where onboarding.request_id = new.onboarding_request_id;
  if found then
    new.shopify_connection_method := v_request.shopify_connection_method;
    new.shopify_refresh_secret_id := v_request.shopify_refresh_secret_id;
    new.shopify_access_token_expires_at := v_request.shopify_access_token_expires_at;
    new.shopify_refresh_token_expires_at := v_request.shopify_refresh_token_expires_at;
  end if;
  return new;
end;
$$;

create trigger copy_onboarding_shopify_oauth_metadata
before insert on public.client_profiles
for each row execute function orin_private.copy_onboarding_shopify_oauth_metadata();

revoke all on function orin_private.copy_onboarding_shopify_oauth_metadata()
  from public, anon, authenticated;

create table public.shopify_oauth_states (
  state_id uuid primary key default gen_random_uuid(),
  state_hash text not null unique check (state_hash ~ '^[0-9a-f]{64}$'),
  operator_id uuid not null references auth.users(id) on delete cascade,
  request_id uuid not null references public.client_onboarding_requests(request_id) on delete cascade,
  store_domain text not null
    check (store_domain ~ '^[a-z0-9][a-z0-9-]*\.myshopify\.com$'),
  return_url text not null check (char_length(return_url) between 1 and 2048),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  check (expires_at > created_at)
);

create index shopify_oauth_states_request_idx
  on public.shopify_oauth_states(request_id, created_at desc);
create index shopify_oauth_states_operator_idx
  on public.shopify_oauth_states(operator_id, created_at desc);
create index shopify_oauth_states_expiry_idx
  on public.shopify_oauth_states(expires_at)
  where consumed_at is null;

alter table public.shopify_oauth_states enable row level security;
revoke all on table public.shopify_oauth_states from public, anon, authenticated;

create or replace function public.service_create_shopify_oauth_state(
  p_operator_id uuid,
  p_request_id uuid,
  p_state_hash text,
  p_return_url text
)
returns table (state_id uuid, expires_at timestamptz)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.client_onboarding_requests%rowtype;
  v_state public.shopify_oauth_states%rowtype;
begin
  perform orin_private.assume_verified_operator(p_operator_id);

  select onboarding.* into v_request
  from public.client_onboarding_requests onboarding
  where onboarding.request_id = p_request_id
    and onboarding.created_by = p_operator_id
    and onboarding.status not in ('database_provisioned', 'cancelled')
  for update;
  if not found then
    raise exception 'editable onboarding request not found' using errcode = 'P0002';
  end if;
  if p_state_hash !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid OAuth state digest' using errcode = '22023';
  end if;
  if char_length(coalesce(p_return_url, '')) not between 1 and 2048 then
    raise exception 'invalid OAuth return URL' using errcode = '22023';
  end if;

  delete from public.shopify_oauth_states oauth
  where oauth.request_id = p_request_id
    and (oauth.consumed_at is not null or oauth.expires_at <= statement_timestamp());

  insert into public.shopify_oauth_states (
    state_hash, operator_id, request_id, store_domain, return_url, expires_at
  ) values (
    p_state_hash, p_operator_id, p_request_id,
    v_request.shopify_store_domain, p_return_url,
    statement_timestamp() + interval '10 minutes'
  )
  returning * into v_state;

  return query select v_state.state_id, v_state.expires_at;
end;
$$;

create or replace function public.service_consume_shopify_oauth_state(
  p_state_hash text,
  p_store_domain text
)
returns table (
  operator_id uuid,
  request_id uuid,
  store_domain text,
  return_url text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_state public.shopify_oauth_states%rowtype;
begin
  select oauth.* into v_state
  from public.shopify_oauth_states oauth
  where oauth.state_hash = p_state_hash
    and oauth.consumed_at is null
    and oauth.expires_at > statement_timestamp()
  for update;
  if not found then
    raise exception 'OAuth request expired or was already used' using errcode = '22023';
  end if;
  if v_state.store_domain <> lower(btrim(p_store_domain)) then
    raise exception 'Shopify store does not match the OAuth request' using errcode = '42501';
  end if;

  update public.shopify_oauth_states oauth
  set consumed_at = statement_timestamp()
  where oauth.state_id = v_state.state_id;

  return query select v_state.operator_id, v_state.request_id,
    v_state.store_domain, v_state.return_url;
end;
$$;

create or replace function public.service_store_onboarding_shopify_oauth_connection(
  p_operator_id uuid,
  p_request_id uuid,
  p_access_token text,
  p_refresh_token text,
  p_access_token_expires_at timestamptz,
  p_refresh_token_expires_at timestamptz,
  p_shopify_discovery jsonb,
  p_selected_blog_gid text default null
)
returns table (
  request_id uuid,
  credential_status text,
  status text,
  shopify_blog_gid text,
  shopify_blog_title text,
  shopify_discovery jsonb
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_request public.client_onboarding_requests%rowtype;
  v_secret_id uuid;
  v_secret_name text;
  v_refresh_secret_id uuid;
  v_refresh_secret_name text;
  v_blog_gid text;
  v_blog_title text;
  v_blogs jsonb;
begin
  perform orin_private.assume_verified_operator(p_operator_id);

  select onboarding.* into v_request
  from public.client_onboarding_requests onboarding
  where onboarding.request_id = p_request_id
    and onboarding.created_by = p_operator_id
    and onboarding.status not in ('database_provisioned', 'cancelled')
  for update;
  if not found then
    raise exception 'editable onboarding request not found' using errcode = 'P0002';
  end if;
  if nullif(btrim(p_access_token), '') is null or char_length(p_access_token) > 512 then
    raise exception 'a valid Shopify OAuth token is required' using errcode = '22023';
  end if;
  if nullif(btrim(p_refresh_token), '') is null or char_length(p_refresh_token) > 512 then
    raise exception 'a valid Shopify OAuth refresh token is required' using errcode = '22023';
  end if;
  if p_access_token_expires_at <= statement_timestamp()
     or p_refresh_token_expires_at <= p_access_token_expires_at then
    raise exception 'valid Shopify OAuth token expiries are required' using errcode = '22023';
  end if;
  if jsonb_typeof(p_shopify_discovery) <> 'object'
     or jsonb_typeof(p_shopify_discovery -> 'blogs') <> 'array'
     or jsonb_array_length(p_shopify_discovery -> 'blogs') = 0 then
    raise exception 'Shopify discovery must include at least one blog' using errcode = '22023';
  end if;
  if lower(p_shopify_discovery #>> '{shop,domain}') <> v_request.shopify_store_domain then
    raise exception 'Shopify discovery store does not match onboarding request' using errcode = '42501';
  end if;

  v_blogs := p_shopify_discovery -> 'blogs';
  if nullif(btrim(coalesce(p_selected_blog_gid, '')), '') is not null then
    select blog ->> 'id', blog ->> 'title'
    into v_blog_gid, v_blog_title
    from jsonb_array_elements(v_blogs) blog
    where blog ->> 'id' = p_selected_blog_gid
    limit 1;
    if v_blog_gid is null then
      raise exception 'selected blog was not returned by Shopify' using errcode = '22023';
    end if;
  elsif jsonb_array_length(v_blogs) = 1 then
    v_blog_gid := v_blogs -> 0 ->> 'id';
    v_blog_title := v_blogs -> 0 ->> 'title';
  end if;
  if v_blog_gid is not null and v_blog_gid !~ '^gid://shopify/Blog/[0-9]+$' then
    raise exception 'Shopify returned an invalid blog identity' using errcode = '22023';
  end if;

  v_secret_name := 'orin_shopify_' || v_request.client_id || '_'
    || replace(v_request.request_id::text, '-', '');
  if v_request.shopify_credential_secret_id is null then
    select vault.create_secret(
      p_access_token,
      v_secret_name,
      'ORIN Shopify OAuth offline token for onboarding request ' || v_request.request_id::text,
      null
    ) into v_secret_id;
  else
    v_secret_id := v_request.shopify_credential_secret_id;
    perform vault.update_secret(
      v_secret_id,
      p_access_token,
      v_secret_name,
      'ORIN Shopify OAuth offline token for onboarding request ' || v_request.request_id::text,
      null
    );
  end if;

  v_refresh_secret_name := 'orin_shopify_refresh_' || v_request.client_id || '_'
    || replace(v_request.request_id::text, '-', '');
  if v_request.shopify_refresh_secret_id is null then
    select vault.create_secret(
      p_refresh_token,
      v_refresh_secret_name,
      'ORIN Shopify OAuth refresh token for onboarding request ' || v_request.request_id::text,
      null
    ) into v_refresh_secret_id;
  else
    v_refresh_secret_id := v_request.shopify_refresh_secret_id;
    perform vault.update_secret(
      v_refresh_secret_id,
      p_refresh_token,
      v_refresh_secret_name,
      'ORIN Shopify OAuth refresh token for onboarding request ' || v_request.request_id::text,
      null
    );
  end if;

  update public.client_onboarding_requests onboarding
  set shopify_blog_gid = v_blog_gid,
      shopify_blog_title = v_blog_title,
      shopify_credential_secret_id = v_secret_id,
      shopify_connection_method = 'oauth',
      shopify_refresh_secret_id = v_refresh_secret_id,
      shopify_access_token_expires_at = p_access_token_expires_at,
      shopify_refresh_token_expires_at = p_refresh_token_expires_at,
      shopify_discovery = p_shopify_discovery,
      shopify_oauth_connected_at = statement_timestamp(),
      credential_status = 'stored',
      status = case when v_blog_gid is null then 'oauth_connected' else 'connection_verified' end,
      last_error = ''
  where onboarding.request_id = p_request_id
  returning onboarding.* into v_request;

  return query select v_request.request_id, v_request.credential_status,
    v_request.status, v_request.shopify_blog_gid, v_request.shopify_blog_title,
    v_request.shopify_discovery;
end;
$$;

create or replace function public.service_select_onboarding_shopify_blog(
  p_operator_id uuid,
  p_request_id uuid,
  p_shopify_blog_gid text
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
declare
  v_request public.client_onboarding_requests%rowtype;
  v_blog_title text;
begin
  perform orin_private.assume_verified_operator(p_operator_id);

  select onboarding.* into v_request
  from public.client_onboarding_requests onboarding
  where onboarding.request_id = p_request_id
    and onboarding.created_by = p_operator_id
    and onboarding.credential_status = 'stored'
    and onboarding.shopify_connection_method = 'oauth'
    and onboarding.status = 'oauth_connected'
  for update;
  if not found then
    raise exception 'OAuth-connected onboarding request not found' using errcode = 'P0002';
  end if;

  select blog ->> 'title' into v_blog_title
  from jsonb_array_elements(v_request.shopify_discovery -> 'blogs') blog
  where blog ->> 'id' = p_shopify_blog_gid
  limit 1;
  if v_blog_title is null then
    raise exception 'selected blog was not returned by Shopify' using errcode = '22023';
  end if;

  update public.client_onboarding_requests onboarding
  set shopify_blog_gid = p_shopify_blog_gid,
      shopify_blog_title = v_blog_title,
      status = 'connection_verified',
      last_error = ''
  where onboarding.request_id = p_request_id
  returning onboarding.* into v_request;

  return query select v_request.request_id, v_request.credential_status,
    v_request.status, v_request.shopify_blog_gid, v_request.shopify_blog_title;
end;
$$;

revoke all on function public.service_create_shopify_oauth_state(uuid, uuid, text, text)
  from public, anon, authenticated;
revoke all on function public.service_consume_shopify_oauth_state(text, text)
  from public, anon, authenticated;
revoke all on function public.service_store_onboarding_shopify_oauth_connection(
  uuid, uuid, text, text, timestamptz, timestamptz, jsonb, text
) from public, anon, authenticated;
revoke all on function public.service_select_onboarding_shopify_blog(uuid, uuid, text)
  from public, anon, authenticated;

grant execute on function public.service_create_shopify_oauth_state(uuid, uuid, text, text)
  to service_role;
grant execute on function public.service_consume_shopify_oauth_state(text, text)
  to service_role;
grant execute on function public.service_store_onboarding_shopify_oauth_connection(
  uuid, uuid, text, text, timestamptz, timestamptz, jsonb, text
) to service_role;
grant execute on function public.service_select_onboarding_shopify_blog(uuid, uuid, text)
  to service_role;

comment on table public.shopify_oauth_states is
  'One-time, ten-minute OAuth state bindings. Raw state and Shopify tokens are never stored here.';
comment on function public.service_consume_shopify_oauth_state(text, text) is
  'Service-role-only one-time Shopify callback binding; no browser role has execute access.';
comment on column public.client_onboarding_requests.shopify_discovery is
  'Sanitized store, blog, collection, and product catalogue summary returned during OAuth.';
