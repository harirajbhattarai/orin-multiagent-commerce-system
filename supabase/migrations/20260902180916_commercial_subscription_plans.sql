-- Commercial subscription catalogue and Shopify billing lifecycle.
--
-- Billing changes entitlement only. It cannot enable automation, scheduler
-- ownership, either Shopify write gate, or live publishing.

alter table public.subscription_plans
  add column monthly_price_cents integer not null default 0
    check (monthly_price_cents between 0 and 10000000),
  add column currency_code text not null default 'USD'
    check (currency_code ~ '^[A-Z]{3}$'),
  add column trial_days smallint not null default 0
    check (trial_days between 0 and 90);

alter table public.client_subscriptions
  add column pending_plan_key text
    references public.subscription_plans(plan_key) on delete restrict,
  add column current_period_started_at timestamptz,
  add column cancelled_at timestamptz,
  add constraint client_subscriptions_period_order_check check (
    current_period_started_at is null
    or current_period_ends_at is null
    or current_period_ends_at > current_period_started_at
  );

create table public.subscription_checkout_attempts (
  attempt_id uuid primary key default gen_random_uuid(),
  client_id text not null references public.clients(client_id) on delete cascade,
  requested_plan_key text not null
    references public.subscription_plans(plan_key) on delete restrict,
  requested_by uuid not null references auth.users(id) on delete restrict,
  request_id uuid not null,
  status text not null default 'created'
    check (status in ('created', 'confirmation_required', 'active', 'declined', 'failed', 'cancelled')),
  provider_subscription_id text,
  confirmation_url text,
  trial_days smallint not null default 0 check (trial_days between 0 and 90),
  failure_reason text not null default '' check (char_length(failure_reason) <= 1000),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (client_id, requested_by, request_id)
);

create unique index subscription_checkout_attempts_provider_id_idx
  on public.subscription_checkout_attempts(provider_subscription_id)
  where provider_subscription_id is not null;

create index subscription_checkout_attempts_client_created_idx
  on public.subscription_checkout_attempts(client_id, created_at desc);

create trigger subscription_checkout_attempts_set_updated_at
before update on public.subscription_checkout_attempts
for each row execute function orin_private.set_updated_at();

alter table public.subscription_checkout_attempts enable row level security;

revoke all on table public.subscription_checkout_attempts
  from public, anon, authenticated;

grant select (
  attempt_id, client_id, requested_plan_key, status, trial_days,
  failure_reason, created_at, updated_at
) on table public.subscription_checkout_attempts to authenticated;

create policy subscription_checkout_attempts_select_for_members
on public.subscription_checkout_attempts for select to authenticated
using (
  exists (
    select 1
    from public.client_members membership
    where membership.client_id = subscription_checkout_attempts.client_id
      and membership.user_id = (select auth.uid())
  )
);

grant select (
  monthly_price_cents, currency_code, trial_days
) on table public.subscription_plans to authenticated;

grant select (
  pending_plan_key, current_period_started_at, cancelled_at
) on table public.client_subscriptions to authenticated;

insert into public.subscription_plans (
  plan_key, display_name, description, monthly_article_limit,
  team_member_limit, can_create_unpublished_drafts, can_publish_live,
  publicly_selectable, active, features, sort_order,
  monthly_price_cents, currency_code, trial_days
) values
  (
    'trial', '7-day trial',
    'Prove the complete ORIN workflow before your first Shopify charge.',
    2, 1, true, false, false, true,
    '["One connected Shopify store", "Two planned articles", "One approval-only unpublished draft", "Read-only monitoring"]'::jsonb,
    10, 0, 'USD', 7
  ),
  (
    'starter', 'Starter',
    'A simple monthly content workflow for a single-store owner.',
    4, 1, true, false, true, true,
    '["One connected Shopify store", "Four articles every 30 days", "No-code planning and drafting", "Approval-only unpublished drafts", "Basic monitoring"]'::jsonb,
    20, 2900, 'USD', 7
  ),
  (
    'growth', 'Growth',
    'Consistent automatic content operations for a growing Shopify store.',
    12, 3, true, false, true, true,
    '["One connected Shopify store", "Twelve articles every 30 days", "Automatic content scheduling", "Approval-only unpublished drafts", "Watchdog monitoring", "Priority processing"]'::jsonb,
    30, 7900, 'USD', 7
  ),
  (
    'scale', 'Scale',
    'Higher-volume content operations with advanced controls and support.',
    30, 5, true, false, true, true,
    '["One connected Shopify store", "Thirty articles every 30 days", "Advanced scheduling", "Custom content rules", "Approval-only unpublished drafts", "Priority support"]'::jsonb,
    40, 14900, 'USD', 7
  ),
  (
    'pilot', 'Pilot access',
    'Grandfathered founding-client access while self-serve billing launches.',
    30, 3, true, false, false, true,
    '["No-code Shopify onboarding", "Thirty planned articles each month", "Approval-only unpublished drafts", "Daily dry-run automation", "Read-only watchdog"]'::jsonb,
    90, 0, 'USD', 0
  )
on conflict (plan_key) do update set
  display_name = excluded.display_name,
  description = excluded.description,
  monthly_article_limit = excluded.monthly_article_limit,
  team_member_limit = excluded.team_member_limit,
  can_create_unpublished_drafts = excluded.can_create_unpublished_drafts,
  can_publish_live = false,
  publicly_selectable = excluded.publicly_selectable,
  active = excluded.active,
  features = excluded.features,
  sort_order = excluded.sort_order,
  monthly_price_cents = excluded.monthly_price_cents,
  currency_code = excluded.currency_code,
  trial_days = excluded.trial_days;

-- New workspaces receive seven days. Existing trials keep the date promised
-- when they started; their exact trial_ends_at remains authoritative.
create or replace function orin_private.create_trial_subscription_for_client()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.client_subscriptions (
    client_id, plan_key, status, billing_provider,
    trial_ends_at, current_period_started_at, current_period_ends_at
  ) values (
    new.client_id, 'trial', 'trialing', 'pilot',
    statement_timestamp() + interval '7 days',
    statement_timestamp(),
    statement_timestamp() + interval '7 days'
  )
  on conflict (client_id) do nothing;
  return new;
end;
$$;

create or replace function orin_private.subscription_period_start(
  p_current_period_started_at timestamptz,
  p_current_period_ends_at timestamptz
)
returns timestamptz
language sql
stable
security invoker
set search_path = ''
as $$
  select coalesce(
    p_current_period_started_at,
    case
      when p_current_period_ends_at is not null
        then p_current_period_ends_at - interval '30 days'
      else date_trunc(
        'month', statement_timestamp() at time zone 'Europe/London'
      ) at time zone 'Europe/London'
    end
  );
$$;

revoke all on function orin_private.subscription_period_start(timestamptz, timestamptz)
  from public, anon, authenticated;
grant execute on function orin_private.subscription_period_start(timestamptz, timestamptz)
  to authenticated;

create or replace function orin_private.enforce_content_planning_entitlement()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_subscription public.client_subscriptions%rowtype;
  v_plan public.subscription_plans%rowtype;
  v_period_start timestamptz;
  v_period_end timestamptz;
  v_articles_used integer;
begin
  if new.source_document <> 'dashboard:manual-content-plan' then
    return new;
  end if;
  if (select auth.uid()) is null then
    raise exception 'authenticated user required' using errcode = '42501';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('orin-subscription:' || new.client_id, 0));
  select subscription.* into v_subscription
  from public.client_subscriptions subscription
  where subscription.client_id = new.client_id
  for update;

  if not found then
    raise exception 'an active ORIN Commerce plan is required to add content'
      using errcode = '42501';
  end if;

  if v_subscription.status not in ('trialing', 'active') then
    raise exception 'content planning is paused because this subscription is not active'
      using errcode = '42501';
  end if;
  if v_subscription.status = 'trialing'
     and v_subscription.trial_ends_at <= statement_timestamp() then
    raise exception 'the ORIN Commerce trial has ended; choose a plan to add content'
      using errcode = '42501';
  end if;
  if v_subscription.cancel_at_period_end
     and v_subscription.current_period_ends_at is not null
     and v_subscription.current_period_ends_at <= statement_timestamp() then
    raise exception 'this ORIN Commerce subscription has ended'
      using errcode = '42501';
  end if;

  select plan.* into v_plan
  from public.subscription_plans plan
  where plan.plan_key = v_subscription.plan_key and plan.active;
  if not found then
    raise exception 'the selected ORIN Commerce plan is unavailable'
      using errcode = '42501';
  end if;

  v_period_start := orin_private.subscription_period_start(
    v_subscription.current_period_started_at,
    v_subscription.current_period_ends_at
  );
  v_period_end := coalesce(
    v_subscription.current_period_ends_at,
    v_period_start + interval '1 month'
  );
  select count(*)::integer into v_articles_used
  from public.content_plan_items item
  where item.client_id = new.client_id
    and item.created_at >= v_period_start
    and item.created_at < v_period_end;

  if v_articles_used >= v_plan.monthly_article_limit then
    raise exception 'article allowance reached; choose a larger plan to add more content'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

-- Service-role functions form the only credential and lifecycle boundary used
-- by the billing Edge Function. Browser roles cannot execute them.
create or replace function public.service_get_client_shopify_billing_connection(
  p_user_id uuid,
  p_client_id text
)
returns table (
  store_domain text,
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
  if not exists (
    select 1 from public.client_members membership
    where membership.client_id = p_client_id
      and membership.user_id = p_user_id
      and membership.role = 'owner'
  ) then
    raise exception 'client owner access is required' using errcode = '42501';
  end if;

  select profile.* into v_profile
  from public.client_profiles profile
  where profile.client_id = p_client_id;
  if not found or v_profile.shopify_connection_method <> 'oauth' then
    raise exception 'Shopify billing requires a no-code OAuth connection'
      using errcode = '42501';
  end if;

  select secret.decrypted_secret into v_access_token
  from vault.decrypted_secrets secret
  where secret.id = v_profile.shopify_credential_secret_id;
  select secret.decrypted_secret into v_refresh_token
  from vault.decrypted_secrets secret
  where secret.id = v_profile.shopify_refresh_secret_id;
  if nullif(v_access_token, '') is null or nullif(v_refresh_token, '') is null then
    raise exception 'encrypted Shopify OAuth credentials are unavailable'
      using errcode = '55000';
  end if;

  return query select
    v_profile.shopify_store_domain, v_access_token,
    v_profile.shopify_connection_method, v_refresh_token,
    v_profile.shopify_access_token_expires_at,
    v_profile.shopify_refresh_token_expires_at;
end;
$$;

create or replace function public.service_rotate_client_shopify_billing_tokens(
  p_user_id uuid,
  p_client_id text,
  p_previous_refresh_token text,
  p_access_token text,
  p_refresh_token text,
  p_access_token_expires_at timestamptz,
  p_refresh_token_expires_at timestamptz
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_profile public.client_profiles%rowtype;
  v_stored_refresh_token text;
begin
  if not exists (
    select 1 from public.client_members membership
    where membership.client_id = p_client_id
      and membership.user_id = p_user_id
      and membership.role = 'owner'
  ) then
    raise exception 'client owner access is required' using errcode = '42501';
  end if;
  select profile.* into v_profile from public.client_profiles profile
  where profile.client_id = p_client_id for update;
  if not found or v_profile.shopify_connection_method <> 'oauth'
     or v_profile.shopify_refresh_secret_id is null then
    raise exception 'OAuth-connected client profile not found' using errcode = 'P0002';
  end if;
  select secret.decrypted_secret into v_stored_refresh_token
  from vault.decrypted_secrets secret where secret.id = v_profile.shopify_refresh_secret_id;
  if v_stored_refresh_token is distinct from p_previous_refresh_token then
    raise exception 'Shopify OAuth refresh credential was already rotated'
      using errcode = '40001';
  end if;
  if nullif(btrim(p_access_token), '') is null
     or nullif(btrim(p_refresh_token), '') is null
     or p_access_token_expires_at <= statement_timestamp()
     or p_refresh_token_expires_at <= p_access_token_expires_at then
    raise exception 'valid refreshed Shopify credentials are required'
      using errcode = '22023';
  end if;

  perform vault.update_secret(
    v_profile.shopify_credential_secret_id, p_access_token, null,
    'ORIN Shopify OAuth access token for ' || p_client_id, null
  );
  perform vault.update_secret(
    v_profile.shopify_refresh_secret_id, p_refresh_token, null,
    'ORIN Shopify OAuth refresh token for ' || p_client_id, null
  );
  update public.client_profiles profile
  set shopify_access_token_expires_at = p_access_token_expires_at,
      shopify_refresh_token_expires_at = p_refresh_token_expires_at
  where profile.client_id = p_client_id;
end;
$$;

revoke all on function public.service_get_client_shopify_billing_connection(uuid, text)
  from public, anon, authenticated;
revoke all on function public.service_rotate_client_shopify_billing_tokens(
  uuid, text, text, text, text, timestamptz, timestamptz
) from public, anon, authenticated;
grant execute on function public.service_get_client_shopify_billing_connection(uuid, text)
  to service_role;
grant execute on function public.service_rotate_client_shopify_billing_tokens(
  uuid, text, text, text, text, timestamptz, timestamptz
) to service_role;

create or replace function public.service_activate_shopify_subscription(
  p_user_id uuid,
  p_attempt_id uuid,
  p_provider_subscription_id text,
  p_current_period_end timestamptz,
  p_trial_days smallint
)
returns table (
  client_id text,
  plan_key text,
  status text,
  current_period_ends_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_attempt public.subscription_checkout_attempts%rowtype;
  v_now timestamptz := statement_timestamp();
  v_trial_ends_at timestamptz;
begin
  if nullif(btrim(p_provider_subscription_id), '') is null
     or p_current_period_end <= v_now
     or p_trial_days < 0 or p_trial_days > 7 then
    raise exception 'valid Shopify subscription confirmation is required'
      using errcode = '22023';
  end if;

  select attempt.* into v_attempt
  from public.subscription_checkout_attempts attempt
  where attempt.attempt_id = p_attempt_id
    and attempt.requested_by = p_user_id
    and attempt.provider_subscription_id = p_provider_subscription_id
    and attempt.status in ('confirmation_required', 'active')
  for update;
  if not found then
    raise exception 'subscription checkout attempt not found' using errcode = 'P0002';
  end if;
  if not exists (
    select 1 from public.client_members membership
    where membership.client_id = v_attempt.client_id
      and membership.user_id = p_user_id
      and membership.role = 'owner'
  ) then
    raise exception 'client owner access is required' using errcode = '42501';
  end if;
  if not exists (
    select 1 from public.subscription_plans plan
    where plan.plan_key = v_attempt.requested_plan_key
      and plan.publicly_selectable and plan.active
      and plan.monthly_price_cents > 0
      and not plan.can_publish_live
  ) then
    raise exception 'requested subscription plan is unavailable' using errcode = '42501';
  end if;

  v_trial_ends_at := case
    when p_trial_days > 0 then v_now + make_interval(days => p_trial_days)
    else null
  end;
  update public.client_subscriptions subscription
  set plan_key = v_attempt.requested_plan_key,
      pending_plan_key = null,
      status = 'active',
      billing_provider = 'shopify',
      provider_subscription_id = p_provider_subscription_id,
      trial_ends_at = v_trial_ends_at,
      current_period_started_at = v_now,
      current_period_ends_at = p_current_period_end,
      cancel_at_period_end = false,
      cancelled_at = null
  where subscription.client_id = v_attempt.client_id;

  update public.subscription_checkout_attempts attempt
  set status = 'active', failure_reason = ''
  where attempt.attempt_id = p_attempt_id;

  return query
  select subscription.client_id, subscription.plan_key,
         subscription.status, subscription.current_period_ends_at
  from public.client_subscriptions subscription
  where subscription.client_id = v_attempt.client_id;
end;
$$;

create or replace function public.service_schedule_shopify_subscription_cancellation(
  p_user_id uuid,
  p_client_id text,
  p_provider_subscription_id text,
  p_current_period_end timestamptz
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not exists (
    select 1 from public.client_members membership
    where membership.client_id = p_client_id
      and membership.user_id = p_user_id
      and membership.role = 'owner'
  ) then
    raise exception 'client owner access is required' using errcode = '42501';
  end if;
  update public.client_subscriptions subscription
  set cancel_at_period_end = true,
      cancelled_at = statement_timestamp(),
      current_period_ends_at = greatest(
        coalesce(subscription.current_period_ends_at, p_current_period_end),
        p_current_period_end
      )
  where subscription.client_id = p_client_id
    and subscription.billing_provider = 'shopify'
    and subscription.provider_subscription_id = p_provider_subscription_id
    and subscription.status in ('trialing', 'active');
  if not found then
    raise exception 'active Shopify subscription not found' using errcode = 'P0002';
  end if;
  update public.subscription_checkout_attempts attempt
  set status = 'cancelled'
  where attempt.provider_subscription_id = p_provider_subscription_id;
end;
$$;

revoke all on function public.service_activate_shopify_subscription(
  uuid, uuid, text, timestamptz, smallint
) from public, anon, authenticated;
revoke all on function public.service_schedule_shopify_subscription_cancellation(
  uuid, text, text, timestamptz
) from public, anon, authenticated;
grant execute on function public.service_activate_shopify_subscription(
  uuid, uuid, text, timestamptz, smallint
) to service_role;
grant execute on function public.service_schedule_shopify_subscription_cancellation(
  uuid, text, text, timestamptz
) to service_role;

drop view public.client_subscription_summary;

create view public.client_subscription_summary
with (security_invoker = true)
as
select
  subscription.client_id,
  subscription.plan_key,
  subscription.pending_plan_key,
  plan.display_name as plan_name,
  pending_plan.display_name as pending_plan_name,
  plan.description,
  subscription.status,
  subscription.billing_provider,
  subscription.trial_ends_at,
  subscription.current_period_started_at,
  subscription.current_period_ends_at,
  subscription.cancel_at_period_end,
  subscription.cancelled_at,
  plan.monthly_article_limit,
  plan.team_member_limit,
  plan.can_create_unpublished_drafts,
  false as can_publish_live,
  plan.features,
  plan.monthly_price_cents,
  plan.currency_code,
  orin_private.subscription_period_start(
    subscription.current_period_started_at,
    subscription.current_period_ends_at
  ) as usage_period_started_at,
  coalesce(subscription.current_period_ends_at,
    orin_private.subscription_period_start(
      subscription.current_period_started_at,
      subscription.current_period_ends_at
    ) + interval '1 month'
  ) as usage_period_ends_at,
  coalesce((
    select count(*)::integer
    from public.content_plan_items item
    where item.client_id = subscription.client_id
      and item.created_at >= orin_private.subscription_period_start(
        subscription.current_period_started_at,
        subscription.current_period_ends_at
      )
      and item.created_at < coalesce(
        subscription.current_period_ends_at,
        orin_private.subscription_period_start(
          subscription.current_period_started_at,
          subscription.current_period_ends_at
        ) + interval '1 month'
      )
  ), 0) as articles_used_this_period
from public.client_subscriptions subscription
join public.subscription_plans plan using (plan_key)
left join public.subscription_plans pending_plan
  on pending_plan.plan_key = subscription.pending_plan_key;

revoke all on table public.client_subscription_summary
  from public, anon, authenticated;
grant select on table public.client_subscription_summary to authenticated;

comment on table public.subscription_checkout_attempts is
  'Idempotent, tenant-bound Shopify subscription checkout ledger; token and payment data are never stored.';
comment on view public.client_subscription_summary is
  'Security-invoker customer entitlement and exact billing-period usage projection.';
comment on function orin_private.enforce_content_planning_entitlement() is
  'Fail-closed billing-period content allowance check; never changes execution or Shopify gates.';
