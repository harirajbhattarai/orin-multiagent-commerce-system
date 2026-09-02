-- The first subscription summary filtered usage by source_document, a column
-- intentionally omitted from the authenticated content-plan grant. Count all
-- tenant content plans instead so the customer projection remains usable
-- without broadening the existing data-access boundary.

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
    and item.created_at >= v_period_start
    and item.created_at < v_period_start + interval '1 month';

  if v_articles_used >= v_plan.monthly_article_limit then
    raise exception 'monthly article allowance reached; choose a larger plan to add more content'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

create or replace view public.client_subscription_summary
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

comment on view public.client_subscription_summary is
  'Security-invoker customer plan and current-month tenant content usage projection.';
comment on function orin_private.enforce_content_planning_entitlement() is
  'Fail-closed monthly tenant content allowance check for manual planning; never changes execution or Shopify gates.';
