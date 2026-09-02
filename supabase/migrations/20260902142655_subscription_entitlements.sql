-- Customer subscription and entitlement foundation.
--
-- This migration makes commercial access an explicit, tenant-scoped database
-- contract. It does not create a payment, contact Shopify, change execution
-- gates, or add any live-publish capability.

create table public.subscription_plans (
  plan_key text primary key
    check (plan_key ~ '^[a-z0-9][a-z0-9_-]{1,62}$'),
  display_name text not null
    check (nullif(btrim(display_name), '') is not null),
  description text not null default ''
    check (char_length(description) <= 1000),
  monthly_article_limit integer not null
    check (monthly_article_limit between 1 and 1000),
  team_member_limit integer not null default 1
    check (team_member_limit between 1 and 1000),
  can_create_unpublished_drafts boolean not null default true,
  can_publish_live boolean not null default false
    check (not can_publish_live),
  publicly_selectable boolean not null default false,
  active boolean not null default true,
  features jsonb not null default '[]'::jsonb
    check (jsonb_typeof(features) = 'array'),
  sort_order integer not null default 100,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.client_subscriptions (
  subscription_id uuid primary key default gen_random_uuid(),
  client_id text not null unique
    references public.clients(client_id) on delete cascade,
  plan_key text not null
    references public.subscription_plans(plan_key) on delete restrict,
  status text not null
    check (status in ('trialing', 'active', 'past_due', 'cancelled', 'suspended')),
  billing_provider text not null default 'pilot'
    check (billing_provider in ('pilot', 'shopify')),
  provider_subscription_id text,
  trial_ends_at timestamptz,
  current_period_ends_at timestamptz,
  cancel_at_period_end boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    status <> 'trialing'
    or (trial_ends_at is not null and trial_ends_at > created_at)
  ),
  check (
    billing_provider <> 'shopify'
    or provider_subscription_id is not null
  )
);

create index client_subscriptions_plan_key_idx
  on public.client_subscriptions(plan_key);

create unique index client_subscriptions_provider_id_idx
  on public.client_subscriptions(billing_provider, provider_subscription_id)
  where provider_subscription_id is not null;

create trigger subscription_plans_set_updated_at
before update on public.subscription_plans
for each row execute function orin_private.set_updated_at();

create trigger client_subscriptions_set_updated_at
before update on public.client_subscriptions
for each row execute function orin_private.set_updated_at();

alter table public.subscription_plans enable row level security;
alter table public.client_subscriptions enable row level security;

revoke all on table public.subscription_plans
  from public, anon, authenticated;
revoke all on table public.client_subscriptions
  from public, anon, authenticated;

grant select (
  plan_key, display_name, description, monthly_article_limit,
  team_member_limit, can_create_unpublished_drafts, can_publish_live,
  publicly_selectable, features, sort_order
) on table public.subscription_plans to authenticated;

grant select (
  subscription_id, client_id, plan_key, status, billing_provider,
  trial_ends_at, current_period_ends_at, cancel_at_period_end,
  created_at, updated_at
) on table public.client_subscriptions to authenticated;

create policy subscription_plans_select_active
on public.subscription_plans for select to authenticated
using ((select auth.uid()) is not null and active);

create policy client_subscriptions_select_for_members
on public.client_subscriptions for select to authenticated
using (
  exists (
    select 1
    from public.client_members membership
    where membership.client_id = client_subscriptions.client_id
      and membership.user_id = (select auth.uid())
  )
);

insert into public.subscription_plans (
  plan_key,
  display_name,
  description,
  monthly_article_limit,
  team_member_limit,
  can_create_unpublished_drafts,
  publicly_selectable,
  features,
  sort_order
) values
  (
    'trial',
    '14-day trial',
    'A safe first workspace for connecting Shopify and proving the content workflow.',
    2,
    1,
    true,
    false,
    '["Shopify connection", "Two planned articles", "Approval-only unpublished drafts", "Read-only monitoring"]'::jsonb,
    10
  ),
  (
    'pilot',
    'Pilot access',
    'Founding-client access while ORIN Commerce billing is commissioned.',
    30,
    3,
    true,
    false,
    '["No-code Shopify onboarding", "Thirty planned articles each month", "Approval-only unpublished drafts", "Daily dry-run automation", "Read-only watchdog"]'::jsonb,
    20
  );

insert into public.client_subscriptions (
  client_id,
  plan_key,
  status,
  billing_provider
)
select client.client_id, 'pilot', 'active', 'pilot'
from public.clients client
on conflict (client_id) do nothing;

create or replace function orin_private.create_trial_subscription_for_client()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.client_subscriptions (
    client_id,
    plan_key,
    status,
    billing_provider,
    trial_ends_at
  ) values (
    new.client_id,
    'trial',
    'trialing',
    'pilot',
    statement_timestamp() + interval '14 days'
  )
  on conflict (client_id) do nothing;

  return new;
end;
$$;

revoke all on function orin_private.create_trial_subscription_for_client()
  from public, anon, authenticated;

create trigger clients_create_trial_subscription
after insert on public.clients
for each row execute function orin_private.create_trial_subscription_for_client();

create or replace function orin_private.enforce_content_planning_entitlement()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_subscription public.client_subscriptions%rowtype;
  v_plan public.subscription_plans%rowtype;
  v_period_start timestamptz := date_trunc(
    'month',
    statement_timestamp() at time zone 'Europe/London'
  ) at time zone 'Europe/London';
  v_articles_used integer;
begin
  if new.source_document <> 'dashboard:manual-content-plan' then
    return new;
  end if;

  if (select auth.uid()) is null then
    raise exception 'authenticated user required' using errcode = '42501';
  end if;

  perform pg_advisory_xact_lock(
    hashtextextended('orin-subscription:' || new.client_id, 0)
  );

  select subscription.*
  into v_subscription
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

  select plan.*
  into v_plan
  from public.subscription_plans plan
  where plan.plan_key = v_subscription.plan_key
    and plan.active;

  if not found then
    raise exception 'the selected ORIN Commerce plan is unavailable'
      using errcode = '42501';
  end if;

  select count(*)::integer
  into v_articles_used
  from public.content_plan_items item
  where item.client_id = new.client_id
    and item.source_document = 'dashboard:manual-content-plan'
    and item.created_at >= v_period_start
    and item.created_at < v_period_start + interval '1 month';

  if v_articles_used >= v_plan.monthly_article_limit then
    raise exception 'monthly article allowance reached; choose a larger plan to add more content'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

revoke all on function orin_private.enforce_content_planning_entitlement()
  from public, anon, authenticated;

create trigger content_plan_items_enforce_subscription
before insert on public.content_plan_items
for each row execute function orin_private.enforce_content_planning_entitlement();

create view public.client_subscription_summary
with (security_invoker = true)
as
select
  subscription.client_id,
  subscription.plan_key,
  plan.display_name as plan_name,
  plan.description,
  subscription.status,
  subscription.billing_provider,
  subscription.trial_ends_at,
  subscription.current_period_ends_at,
  subscription.cancel_at_period_end,
  plan.monthly_article_limit,
  plan.team_member_limit,
  plan.can_create_unpublished_drafts,
  plan.can_publish_live,
  plan.features,
  coalesce((
    select count(*)::integer
    from public.content_plan_items item
    where item.client_id = subscription.client_id
      and item.source_document = 'dashboard:manual-content-plan'
      and item.created_at >= (
        date_trunc('month', statement_timestamp() at time zone 'Europe/London')
        at time zone 'Europe/London'
      )
      and item.created_at < (
        date_trunc('month', statement_timestamp() at time zone 'Europe/London')
        at time zone 'Europe/London'
      ) + interval '1 month'
  ), 0) as articles_used_this_month
from public.client_subscriptions subscription
join public.subscription_plans plan using (plan_key);

revoke all on table public.client_subscription_summary
  from public, anon, authenticated;
grant select on table public.client_subscription_summary to authenticated;

comment on table public.subscription_plans is
  'Server-owned ORIN Commerce entitlement catalogue; commercial prices are configured separately.';
comment on table public.client_subscriptions is
  'Tenant subscription status and provider binding. Customer roles have read-only access.';
comment on view public.client_subscription_summary is
  'Security-invoker customer plan and monthly usage projection.';
comment on function orin_private.enforce_content_planning_entitlement() is
  'Fail-closed monthly content planning entitlement check; never changes execution or Shopify gates.';
