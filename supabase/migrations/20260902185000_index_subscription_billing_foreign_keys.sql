-- Cover commercial subscription foreign keys used by plan lifecycle and
-- customer checkout history.

create index client_subscriptions_pending_plan_key_idx
  on public.client_subscriptions(pending_plan_key)
  where pending_plan_key is not null;

create index subscription_checkout_attempts_requested_plan_key_idx
  on public.subscription_checkout_attempts(requested_plan_key);

create index subscription_checkout_attempts_requested_by_idx
  on public.subscription_checkout_attempts(requested_by);
