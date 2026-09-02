begin;
create extension if not exists pgtap with schema extensions;
select plan(12);

select has_table('public', 'subscription_plans', 'subscription plan catalogue exists');
select has_table('public', 'client_subscriptions', 'client subscriptions exist');
select has_view('public', 'client_subscription_summary', 'customer subscription summary exists');

select ok(
  (select relrowsecurity from pg_class where oid = 'public.subscription_plans'::regclass)
  and (select relrowsecurity from pg_class where oid = 'public.client_subscriptions'::regclass),
  'subscription tables have RLS enabled'
);

select ok(
  coalesce(
    (select reloptions @> array['security_invoker=true']
     from pg_class
     where oid = 'public.client_subscription_summary'::regclass),
    false
  ),
  'subscription summary is security invoker'
);

select ok(
  has_column_privilege('authenticated', 'public.client_subscriptions', 'client_id', 'SELECT')
  and not has_table_privilege('authenticated', 'public.client_subscriptions', 'INSERT')
  and not has_table_privilege('authenticated', 'public.client_subscriptions', 'UPDATE')
  and not has_table_privilege('authenticated', 'public.client_subscriptions', 'DELETE'),
  'customers can read but cannot mutate subscriptions'
);

select ok(
  has_table_privilege('authenticated', 'public.client_subscription_summary', 'SELECT')
  and not has_table_privilege('anon', 'public.client_subscription_summary', 'SELECT'),
  'subscription summary is authenticated-only'
);

select is(
  (select count(*) from public.clients client
   where not exists (
     select 1 from public.client_subscriptions subscription
     where subscription.client_id = client.client_id
   )),
  0::bigint,
  'every existing client has a subscription'
);

insert into auth.users (id)
values ('12121212-1212-4212-8212-121212121212');

insert into public.client_onboarding_requests (
  request_id,
  created_by,
  client_id,
  display_name,
  owner_email,
  shopify_store_domain,
  content_categories,
  shopify_blog_gid,
  shopify_blog_title,
  shopify_credential_secret_id,
  credential_status,
  status
) values (
  '13131313-1313-4313-8313-131313131313',
  '12121212-1212-4212-8212-121212121212',
  'hoverboard_store',
  'Hoverboard Store',
  'owner@example.com',
  'hoverboard-store.myshopify.com',
  array['Product education'],
  'gid://shopify/Blog/1',
  'Journal',
  '14141414-1414-4414-8414-141414141414',
  'stored',
  'database_provisioned'
);

insert into public.client_profiles (
  client_id,
  onboarding_request_id,
  owner_email,
  shopify_store_domain,
  shopify_blog_gid,
  shopify_blog_title,
  market_country,
  timezone,
  brand_voice,
  content_categories,
  product_scope,
  shopify_credential_secret_id
) values (
  'hoverboard_store',
  '13131313-1313-4313-8313-131313131313',
  'owner@example.com',
  'hoverboard-store.myshopify.com',
  'gid://shopify/Blog/1',
  'Journal',
  'GB',
  'Europe/London',
  'Helpful and clear',
  array['Product education'],
  '[]'::jsonb,
  '14141414-1414-4414-8414-141414141414'
);

insert into public.client_members (client_id, user_id, role)
values ('hoverboard_store', '12121212-1212-4212-8212-121212121212', 'owner');

select set_config('request.jwt.claim.sub', '12121212-1212-4212-8212-121212121212', true);
set local role authenticated;

select is(
  (select count(*) from public.client_subscription_summary),
  1::bigint,
  'a member sees only their subscription tenant'
);

select is(
  (select can_publish_live from public.client_subscription_summary),
  false,
  'no subscription can grant live publishing'
);

select lives_ok(
  $$
    select * from public.plan_next_content_article(
      'hoverboard_store',
      'Subscription entitlement contract test',
      'subscription entitlement contract test keyword',
      'Product education',
      ((statement_timestamp() at time zone 'Europe/London')::date + 30),
      'pgtap entitlement verification'
    )
  $$,
  'an active entitled owner can plan content'
);

reset role;
update public.client_subscriptions
set status = 'suspended'
where client_id = 'hoverboard_store';
set local role authenticated;

select throws_ok(
  $$
    select * from public.plan_next_content_article(
      'hoverboard_store',
      'Suspended subscription contract test',
      'suspended subscription contract test keyword',
      'Product education',
      ((statement_timestamp() at time zone 'Europe/London')::date + 31),
      'must fail closed'
    )
  $$,
  '42501',
  'content planning is paused because this subscription is not active',
  'inactive subscriptions cannot add content'
);

select * from finish();
rollback;
