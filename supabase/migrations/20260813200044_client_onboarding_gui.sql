-- Operator-only, fail-closed client onboarding for ORIN Commerce.
--
-- This migration creates the durable intake and tenant bootstrap boundary used
-- by the dashboard wizard. It deliberately does not create a scheduler, start
-- a worker, open request intake, or permit any Shopify write.

create table public.platform_operators (
  user_id uuid primary key references auth.users(id) on delete cascade,
  role text not null default 'operator'
    check (role in ('admin', 'operator')),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table public.client_onboarding_requests (
  request_id uuid primary key default gen_random_uuid(),
  created_by uuid not null references auth.users(id) on delete restrict,
  client_id text not null unique
    check (client_id ~ '^[a-z0-9][a-z0-9_]{1,62}$'),
  display_name text not null check (nullif(btrim(display_name), '') is not null),
  owner_email text not null check (owner_email ~* '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
  shopify_store_domain text not null
    check (shopify_store_domain ~ '^[a-z0-9][a-z0-9-]*\.myshopify\.com$'),
  market_country text not null default 'GB'
    check (market_country ~ '^[A-Z]{2}$'),
  timezone text not null default 'Europe/London'
    check (nullif(btrim(timezone), '') is not null),
  brand_voice text not null default '' check (char_length(brand_voice) <= 4000),
  content_categories text[] not null default '{}'::text[]
    check (cardinality(content_categories) between 1 and 12),
  product_scope jsonb not null default '[]'::jsonb
    check (jsonb_typeof(product_scope) = 'array'),
  shopify_blog_gid text,
  shopify_blog_title text,
  shopify_credential_secret_id uuid,
  credential_status text not null default 'not_connected'
    check (credential_status in ('not_connected', 'verified', 'stored')),
  status text not null default 'draft'
    check (status in ('draft', 'connection_verified', 'ready_to_provision', 'database_provisioned', 'failed', 'cancelled')),
  commissioning_status text not null default 'not_started'
    check (commissioning_status in ('not_started', 'gates_closed', 'worker_pending', 'dry_run_pending', 'pilot_pending', 'ready')),
  last_error text not null default '' check (char_length(last_error) <= 2000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (credential_status = 'stored' and shopify_credential_secret_id is not null)
    or (credential_status <> 'stored' and shopify_credential_secret_id is null)
  ),
  check (
    status not in ('connection_verified', 'ready_to_provision', 'database_provisioned')
    or (credential_status = 'stored' and shopify_blog_gid is not null)
  )
);

create index client_onboarding_requests_creator_idx
  on public.client_onboarding_requests(created_by, created_at desc);

create table public.client_profiles (
  client_id text primary key references public.clients(client_id) on delete cascade,
  onboarding_request_id uuid not null unique
    references public.client_onboarding_requests(request_id) on delete restrict,
  owner_email text not null,
  shopify_store_domain text not null,
  shopify_blog_gid text not null,
  shopify_blog_title text not null,
  market_country text not null,
  timezone text not null,
  brand_voice text not null default '',
  content_categories text[] not null,
  product_scope jsonb not null default '[]'::jsonb,
  shopify_credential_secret_id uuid not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger client_onboarding_requests_set_updated_at
before update on public.client_onboarding_requests
for each row execute function orin_private.set_updated_at();

create trigger client_profiles_set_updated_at
before update on public.client_profiles
for each row execute function orin_private.set_updated_at();

alter table public.platform_operators enable row level security;
alter table public.client_onboarding_requests enable row level security;
alter table public.client_profiles enable row level security;

revoke all on table public.platform_operators from public, anon, authenticated;
revoke all on table public.client_onboarding_requests from public, anon, authenticated;
revoke all on table public.client_profiles from public, anon, authenticated;

grant select (user_id, role, active, created_at)
  on table public.platform_operators to authenticated;
grant select (
  request_id, created_by, client_id, display_name, owner_email,
  shopify_store_domain, market_country, timezone, brand_voice,
  content_categories, product_scope, shopify_blog_gid, shopify_blog_title,
  credential_status, status, commissioning_status, last_error,
  created_at, updated_at
) on table public.client_onboarding_requests to authenticated;
grant select (
  client_id, onboarding_request_id, owner_email, shopify_store_domain,
  shopify_blog_gid, shopify_blog_title, market_country, timezone,
  brand_voice, content_categories, product_scope, created_at, updated_at
) on table public.client_profiles to authenticated;

create policy platform_operators_select_self
on public.platform_operators for select to authenticated
using (user_id = (select auth.uid()) and active);

create policy client_onboarding_requests_select_for_operators
on public.client_onboarding_requests for select to authenticated
using (
  exists (
    select 1
    from public.platform_operators operator
    where operator.user_id = (select auth.uid())
      and operator.active
  )
);

create policy client_profiles_select_for_members
on public.client_profiles for select to authenticated
using (
  exists (
    select 1
    from public.client_members membership
    where membership.client_id = client_profiles.client_id
      and membership.user_id = (select auth.uid())
  )
);

create or replace function orin_private.require_platform_operator()
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
begin
  if v_uid is null then
    raise exception 'authenticated user required' using errcode = '42501';
  end if;
  if not exists (
    select 1
    from public.platform_operators operator
    where operator.user_id = v_uid
      and operator.active
  ) then
    raise exception 'active platform operator required' using errcode = '42501';
  end if;
  return v_uid;
end;
$$;

revoke all on function orin_private.require_platform_operator()
  from public, anon, authenticated;

create or replace function public.create_client_onboarding_request(
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
declare
  v_uid uuid := orin_private.require_platform_operator();
  v_request public.client_onboarding_requests%rowtype;
  v_client_id text := lower(btrim(p_client_id));
  v_store_domain text := lower(regexp_replace(btrim(p_shopify_store_domain), '^https?://', '', 'i'));
begin
  v_store_domain := split_part(v_store_domain, '/', 1);
  if v_client_id !~ '^[a-z0-9][a-z0-9_]{1,62}$' then
    raise exception 'client id must use lowercase letters, numbers, and underscores' using errcode = '22023';
  end if;
  if v_store_domain !~ '^[a-z0-9][a-z0-9-]*\.myshopify\.com$' then
    raise exception 'use the permanent .myshopify.com store domain' using errcode = '22023';
  end if;
  if p_content_categories is null or cardinality(p_content_categories) not between 1 and 12 then
    raise exception 'choose between 1 and 12 content categories' using errcode = '22023';
  end if;
  if exists (select 1 from public.clients client where client.client_id = v_client_id) then
    raise exception 'client id is already in use' using errcode = '23505';
  end if;

  insert into public.client_onboarding_requests (
    created_by, client_id, display_name, owner_email, shopify_store_domain,
    market_country, timezone, brand_voice, content_categories
  ) values (
    v_uid, v_client_id, btrim(p_display_name), lower(btrim(p_owner_email)),
    v_store_domain, upper(btrim(p_market_country)), btrim(p_timezone),
    btrim(coalesce(p_brand_voice, '')),
    array(select distinct btrim(category) from unnest(p_content_categories) category where nullif(btrim(category), '') is not null)
  )
  returning * into v_request;

  return query select v_request.request_id, v_request.client_id, v_request.status,
    v_request.credential_status, v_request.commissioning_status;
end;
$$;

revoke all on function public.create_client_onboarding_request(
  text, text, text, text, text, text, text, text[]
) from public, anon;
grant execute on function public.create_client_onboarding_request(
  text, text, text, text, text, text, text, text[]
) to authenticated;

create or replace function public.store_onboarding_shopify_connection(
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
declare
  v_uid uuid := orin_private.require_platform_operator();
  v_request public.client_onboarding_requests%rowtype;
  v_secret_id uuid;
  v_secret_name text;
begin
  select onboarding.* into v_request
  from public.client_onboarding_requests onboarding
  where onboarding.request_id = p_request_id
    and onboarding.created_by = v_uid
  for update;
  if not found then
    raise exception 'onboarding request not found' using errcode = 'P0002';
  end if;
  if nullif(btrim(p_access_token), '') is null or char_length(p_access_token) > 512 then
    raise exception 'a valid Shopify Admin API token is required' using errcode = '22023';
  end if;
  if p_shopify_blog_gid !~ '^gid://shopify/Blog/[0-9]+$' then
    raise exception 'a verified Shopify blog is required' using errcode = '22023';
  end if;

  v_secret_name := 'orin_shopify_' || v_request.client_id || '_' || replace(v_request.request_id::text, '-', '');
  if v_request.shopify_credential_secret_id is null then
    select vault.create_secret(
      p_access_token,
      v_secret_name,
      'ORIN Shopify Admin API token for onboarding request ' || v_request.request_id::text,
      null
    ) into v_secret_id;
  else
    v_secret_id := v_request.shopify_credential_secret_id;
    perform vault.update_secret(
      v_secret_id,
      p_access_token,
      v_secret_name,
      'ORIN Shopify Admin API token for onboarding request ' || v_request.request_id::text,
      null
    );
  end if;

  update public.client_onboarding_requests onboarding
  set shopify_blog_gid = p_shopify_blog_gid,
      shopify_blog_title = btrim(p_shopify_blog_title),
      shopify_credential_secret_id = v_secret_id,
      credential_status = 'stored',
      status = 'connection_verified',
      last_error = ''
  where onboarding.request_id = p_request_id
  returning onboarding.* into v_request;

  return query select v_request.request_id, v_request.credential_status,
    v_request.status, v_request.shopify_blog_gid, v_request.shopify_blog_title;
end;
$$;

revoke all on function public.store_onboarding_shopify_connection(uuid, text, text, text)
  from public, anon;
grant execute on function public.store_onboarding_shopify_connection(uuid, text, text, text)
  to authenticated;

create or replace function public.update_client_onboarding_scope(
  p_request_id uuid,
  p_product_scope jsonb
)
returns table (request_id uuid, status text, product_scope jsonb)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := orin_private.require_platform_operator();
  v_request public.client_onboarding_requests%rowtype;
begin
  if jsonb_typeof(p_product_scope) <> 'array' or jsonb_array_length(p_product_scope) > 100 then
    raise exception 'product scope must be an array of at most 100 entries' using errcode = '22023';
  end if;
  update public.client_onboarding_requests onboarding
  set product_scope = p_product_scope,
      status = case when onboarding.credential_status = 'stored' then 'ready_to_provision' else onboarding.status end,
      last_error = ''
  where onboarding.request_id = p_request_id
    and onboarding.created_by = v_uid
    and onboarding.status not in ('database_provisioned', 'cancelled')
  returning onboarding.* into v_request;
  if not found then
    raise exception 'editable onboarding request not found' using errcode = 'P0002';
  end if;
  return query select v_request.request_id, v_request.status, v_request.product_scope;
end;
$$;

revoke all on function public.update_client_onboarding_scope(uuid, jsonb)
  from public, anon;
grant execute on function public.update_client_onboarding_scope(uuid, jsonb)
  to authenticated;

create or replace function public.provision_client_from_onboarding(p_request_id uuid)
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
declare
  v_uid uuid := orin_private.require_platform_operator();
  v_request public.client_onboarding_requests%rowtype;
begin
  select onboarding.* into v_request
  from public.client_onboarding_requests onboarding
  where onboarding.request_id = p_request_id
    and onboarding.created_by = v_uid
  for update;
  if not found then
    raise exception 'onboarding request not found' using errcode = 'P0002';
  end if;
  if v_request.credential_status <> 'stored'
     or v_request.shopify_blog_gid is null
     or v_request.status not in ('connection_verified', 'ready_to_provision') then
    raise exception 'verify Shopify and save the content scope before provisioning' using errcode = '55000';
  end if;

  insert into public.clients (client_id, display_name, status)
  values (v_request.client_id, v_request.display_name, 'maintenance');

  insert into public.client_runtime_settings (
    client_id, request_intake_enabled, automation_enabled,
    shopify_writes_enabled, approved_draft_writes_enabled,
    max_concurrency, allowed_mode
  ) values (
    v_request.client_id, false, false, false, false, 1, 'dry-run'
  );

  insert into public.scheduler_health (client_id, scheduler_owner, state, details)
  values (
    v_request.client_id, null, 'disabled',
    jsonb_build_object('onboarding_request_id', v_request.request_id, 'commissioning', 'not_started')
  );

  insert into public.client_members (client_id, user_id, role)
  values (v_request.client_id, v_uid, 'owner');

  insert into public.client_profiles (
    client_id, onboarding_request_id, owner_email, shopify_store_domain,
    shopify_blog_gid, shopify_blog_title, market_country, timezone,
    brand_voice, content_categories, product_scope, shopify_credential_secret_id
  ) values (
    v_request.client_id, v_request.request_id, v_request.owner_email,
    v_request.shopify_store_domain, v_request.shopify_blog_gid,
    v_request.shopify_blog_title, v_request.market_country, v_request.timezone,
    v_request.brand_voice, v_request.content_categories, v_request.product_scope,
    v_request.shopify_credential_secret_id
  );

  update public.client_onboarding_requests onboarding
  set status = 'database_provisioned',
      commissioning_status = 'gates_closed',
      last_error = ''
  where onboarding.request_id = p_request_id
  returning onboarding.* into v_request;

  return query select v_request.request_id, v_request.client_id,
    v_request.status, v_request.commissioning_status;
end;
$$;

revoke all on function public.provision_client_from_onboarding(uuid)
  from public, anon;
grant execute on function public.provision_client_from_onboarding(uuid)
  to authenticated;

-- Bootstrap current platform administration from the proven HBStore owner.
-- Future operators are added explicitly; client ownership alone does not grant
-- platform-wide onboarding access.
insert into public.platform_operators (user_id, role, active)
select membership.user_id, 'admin', true
from public.client_members membership
where membership.client_id = 'hoverboard_store'
  and membership.role = 'owner'
on conflict (user_id) do update
set role = excluded.role,
    active = excluded.active;

comment on table public.client_onboarding_requests is
  'Operator-only onboarding state. Shopify token material is stored in Vault and never exposed by table grants.';
comment on function public.provision_client_from_onboarding(uuid) is
  'Creates an isolated tenant with every execution, scheduler, and Shopify gate closed.';
