-- Server-side, read-only Shopify identity commissioning for newly provisioned
-- clients. Token material is returned only to the authenticated Edge Function's
-- service-role connection and is never exposed to dashboard users.

alter table public.client_onboarding_requests
  drop constraint client_onboarding_requests_commissioning_status_check;

alter table public.client_onboarding_requests
  add constraint client_onboarding_requests_commissioning_status_check
  check (
    commissioning_status in (
      'not_started',
      'gates_closed',
      'identity_verified',
      'worker_pending',
      'dry_run_pending',
      'pilot_pending',
      'ready'
    )
  );

create table public.client_commissioning_audits (
  audit_id uuid primary key default gen_random_uuid(),
  client_id text not null references public.clients(client_id) on delete cascade,
  audit_kind text not null check (audit_kind in ('shopify_identity')),
  status text not null check (status in ('passed', 'failed')),
  observed_store_domain text not null,
  observed_blog_gid text not null,
  observed_blog_title text not null,
  observed_product_count integer not null check (observed_product_count >= 0),
  audited_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now()
);

create index client_commissioning_audits_client_created_idx
  on public.client_commissioning_audits(client_id, created_at desc);

alter table public.client_commissioning_audits enable row level security;
revoke all on table public.client_commissioning_audits
  from public, anon, authenticated, orin_api, orin_worker;
grant select (
  audit_id, client_id, audit_kind, status, observed_store_domain,
  observed_blog_gid, observed_blog_title, observed_product_count,
  audited_by, created_at
) on table public.client_commissioning_audits to authenticated;

create policy client_commissioning_audits_select_for_operators
on public.client_commissioning_audits for select to authenticated
using (
  exists (
    select 1
    from public.platform_operators operator
    where operator.user_id = (select auth.uid())
      and operator.active
  )
);

create or replace function public.service_get_client_shopify_audit_connection(
  p_operator_id uuid,
  p_client_id text
)
returns table (
  store_domain text,
  blog_gid text,
  blog_title text,
  access_token text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_profile public.client_profiles%rowtype;
  v_client_status text;
  v_request_intake boolean;
  v_automation boolean;
  v_shopify_writes boolean;
  v_approved_draft_writes boolean;
  v_allowed_mode text;
  v_scheduler_state text;
  v_scheduler_owner text;
  v_secret text;
begin
  perform orin_private.assume_verified_operator(p_operator_id);

  select profile.* into v_profile
  from public.client_profiles profile
  where profile.client_id = p_client_id;
  if not found then
    raise exception 'provisioned client profile not found' using errcode = 'P0002';
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

  if v_client_status <> 'maintenance'
     or v_request_intake
     or v_automation
     or v_shopify_writes
     or v_approved_draft_writes
     or v_allowed_mode <> 'dry-run'
     or v_scheduler_state <> 'disabled'
     or v_scheduler_owner is not null then
    raise exception 'read-only audit requires every execution and Shopify gate closed'
      using errcode = '55000';
  end if;

  select secret.secret into v_secret
  from vault.decrypted_secrets secret
  where secret.id = v_profile.shopify_credential_secret_id;
  if nullif(v_secret, '') is null then
    raise exception 'encrypted Shopify credential is unavailable' using errcode = '55000';
  end if;

  return query select
    v_profile.shopify_store_domain,
    v_profile.shopify_blog_gid,
    v_profile.shopify_blog_title,
    v_secret;
end;
$$;

create or replace function public.service_record_client_shopify_identity_audit(
  p_operator_id uuid,
  p_client_id text,
  p_observed_store_domain text,
  p_observed_blog_gid text,
  p_observed_blog_title text,
  p_observed_product_count integer
)
returns table (
  client_id text,
  commissioning_status text,
  audit_id uuid,
  audited_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_profile public.client_profiles%rowtype;
  v_audit public.client_commissioning_audits%rowtype;
begin
  perform orin_private.assume_verified_operator(p_operator_id);
  select profile.* into v_profile
  from public.client_profiles profile
  where profile.client_id = p_client_id;
  if not found then
    raise exception 'provisioned client profile not found' using errcode = 'P0002';
  end if;
  if lower(btrim(p_observed_store_domain)) <> v_profile.shopify_store_domain
     or p_observed_blog_gid <> v_profile.shopify_blog_gid
     or nullif(btrim(p_observed_blog_title), '') is null
     or p_observed_product_count is null
     or p_observed_product_count < 0 then
    raise exception 'observed Shopify identity does not match the provisioned client'
      using errcode = '22023';
  end if;

  insert into public.client_commissioning_audits (
    client_id, audit_kind, status, observed_store_domain, observed_blog_gid,
    observed_blog_title, observed_product_count, audited_by
  ) values (
    p_client_id, 'shopify_identity', 'passed', lower(btrim(p_observed_store_domain)),
    p_observed_blog_gid, btrim(p_observed_blog_title), p_observed_product_count,
    p_operator_id
  ) returning * into v_audit;

  update public.client_onboarding_requests onboarding
  set commissioning_status = 'identity_verified', last_error = ''
  where onboarding.request_id = v_profile.onboarding_request_id
    and onboarding.status = 'database_provisioned';
  if not found then
    raise exception 'provisioned onboarding request not found' using errcode = 'P0002';
  end if;

  return query select p_client_id, 'identity_verified'::text,
    v_audit.audit_id, v_audit.created_at;
end;
$$;

revoke all on function public.service_get_client_shopify_audit_connection(uuid, text)
  from public, anon, authenticated;
revoke all on function public.service_record_client_shopify_identity_audit(
  uuid, text, text, text, text, integer
) from public, anon, authenticated;

grant execute on function public.service_get_client_shopify_audit_connection(uuid, text)
  to service_role;
grant execute on function public.service_record_client_shopify_identity_audit(
  uuid, text, text, text, text, integer
) to service_role;

comment on function public.service_get_client_shopify_audit_connection(uuid, text) is
  'Service-role-only Vault bridge for a fail-closed, read-only Shopify identity audit.';
comment on table public.client_commissioning_audits is
  'Non-secret durable evidence from client commissioning checks.';
