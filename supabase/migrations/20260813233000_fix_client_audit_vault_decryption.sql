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

  select secret.decrypted_secret into v_secret
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

revoke all on function public.service_get_client_shopify_audit_connection(uuid, text)
  from public, anon, authenticated;
grant execute on function public.service_get_client_shopify_audit_connection(uuid, text)
  to service_role;

comment on function public.service_get_client_shopify_audit_connection(uuid, text) is
  'Service-role-only Vault bridge for a fail-closed, read-only Shopify identity audit.';
