begin;
create extension if not exists pgtap with schema extensions;
select plan(5);

select has_function(
  'orin_private',
  'classify_exhausted_attempt_incident',
  array[]::text[],
  'exhausted-attempt incidents are classified at the database boundary'
);

insert into public.incidents (
  client_id,
  severity,
  code,
  summary,
  details
) values (
  'hoverboard_store',
  'critical',
  'ORIN_RECONCILIATION_ATTEMPTS_EXHAUSTED',
  'Automatic replay ended with unresolved Shopify state',
  jsonb_build_object(
    'job_id', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'replay_disposition', 'retry',
    'shopify_write_state', 'not_attempted'
  )
);

select is(
  (
    select code
    from public.incidents
    where details ->> 'job_id' = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  ),
  'ORIN_JOB_ATTEMPTS_EXHAUSTED',
  'retry-only exhaustion is not labelled as Shopify reconciliation failure'
);

select is(
  (
    select severity
    from public.incidents
    where details ->> 'job_id' = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  ),
  'warning',
  'retry-only exhaustion is recorded as a warning'
);

insert into public.incidents (
  client_id,
  severity,
  code,
  summary,
  details
) values (
  'hoverboard_store',
  'critical',
  'ORIN_RECONCILIATION_ATTEMPTS_EXHAUSTED',
  'Automatic replay ended with unresolved Shopify state',
  jsonb_build_object(
    'job_id', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'replay_disposition', 'retry',
    'shopify_write_state', 'not_attempted'
  )
);

select is(
  (
    select count(*)
    from public.incidents
    where status = 'open'
      and code = 'ORIN_JOB_ATTEMPTS_EXHAUSTED'
      and details ->> 'job_id' = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  ),
  1::bigint,
  'duplicate retry-only exhaustion alerts collapse to one open incident'
);

insert into public.incidents (
  client_id,
  severity,
  code,
  summary,
  details
) values (
  'hoverboard_store',
  'critical',
  'ORIN_RECONCILIATION_ATTEMPTS_EXHAUSTED',
  'Automatic replay ended with unresolved Shopify state',
  jsonb_build_object(
    'job_id', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    'replay_disposition', 'reconcile',
    'shopify_write_state', 'unknown'
  )
);

select ok(
  exists (
    select 1
    from public.incidents
    where code = 'ORIN_RECONCILIATION_ATTEMPTS_EXHAUSTED'
      and severity = 'critical'
      and details ->> 'job_id' = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
  ),
  'unknown Shopify state remains a critical reconciliation incident'
);

select * from finish();
rollback;
