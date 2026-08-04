begin;
create extension if not exists pgtap with schema extensions;
select plan(15);

select has_table('public', 'content_drafts', 'versioned review draft table exists');
select ok(
  (select relrowsecurity from pg_class where oid = 'public.content_drafts'::regclass),
  'review drafts have RLS enabled'
);
select ok(
  has_table_privilege('authenticated', 'public.content_drafts', 'SELECT')
  and not has_table_privilege('authenticated', 'public.content_drafts', 'INSERT')
  and not has_table_privilege('anon', 'public.content_drafts', 'SELECT'),
  'review draft grants are read-only and authenticated'
);
select has_view('public', 'client_content_review_items', 'review projection exists');
select ok(
  coalesce(
    (select reloptions @> array['security_invoker=true']
     from pg_class where oid = 'public.client_content_review_items'::regclass),
    false
  ),
  'review projection obeys underlying RLS'
);
select ok(
  has_function_privilege('orin_worker', 'orin_private.materialize_next_content_decision()', 'EXECUTE')
  and not has_function_privilege('authenticated', 'orin_private.materialize_next_content_decision()', 'EXECUTE'),
  'only the narrow worker can consume decisions'
);

insert into auth.users (id) values ('abababab-abab-4bab-8bab-abababababab');
insert into public.client_members (client_id, user_id, role)
values ('hoverboard_store', 'abababab-abab-4bab-8bab-abababababab', 'operator');

insert into public.content_plan_items (
  content_item_id, client_id, item_number, target_date, cluster, decision,
  status, topic, target_keyword, draft_path, source_document, source_revision
) values (
  'dededede-dede-4ede-8ede-dededededede', 'hoverboard_store', 998,
  '2026-12-30', 'Test', 'create_new', 'planned', 'Durable review test concept',
  'durable review test concept',
  'clients/hoverboard_store/content_engine/drafts/durable-review-test-concept.html',
  'supabase-test', repeat('d', 64)
);

create temporary table phase6_jobs_before as
select count(*)::bigint as value from public.content_jobs;

select set_config('request.jwt.claim.sub', 'abababab-abab-4bab-8bab-abababababab', true);
set local role authenticated;
insert into public.content_decisions (
  client_id, content_item_id, content_item_version, decision, requested_by, request_id
)
select client_id, content_item_id, version, 'approve_concept',
       'abababab-abab-4bab-8bab-abababababab',
       'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd'
from public.content_plan_items
where client_id = 'hoverboard_store'
  and content_item_id = 'dededede-dede-4ede-8ede-dededededede';

select is(
  (select processing_status from public.content_decisions
   where request_id = 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd'),
  'recorded',
  'browser approval is an immutable recorded receipt'
);

reset role;
set local role orin_worker;
select * from orin_private.materialize_next_content_decision();
reset role;

select is(
  (select count(*)::bigint from public.content_jobs),
  (select value from phase6_jobs_before),
  'closed gates do not materialize concept approval'
);

update public.clients set status = 'active' where client_id = 'hoverboard_store';
update public.client_runtime_settings
set request_intake_enabled = true,
    automation_enabled = true,
    shopify_writes_enabled = false,
    allowed_mode = 'dry-run'
where client_id = 'hoverboard_store';

set local role orin_worker;
select * from orin_private.materialize_next_content_decision();
reset role;

select is(
  (select requested_mode from public.content_jobs
   where source_job_key = 'decision:' || (
     select decision_id::text from public.content_decisions
     where request_id = 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd'
   )),
  'dry-run',
  'concept approval can materialize only a dry-run job'
);
select is(
  (select processing_status from public.content_decisions
   where request_id = 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd'),
  'consumed',
  'materialized decision records its terminal processing state'
);
select is(
  (select status from public.content_plan_items
   where content_item_id = 'dededede-dede-4ede-8ede-dededededede'),
  'in_progress',
  'materialized concept advances to drafting'
);
select ok(
  not (select shopify_writes_enabled from public.client_runtime_settings
       where client_id = 'hoverboard_store'),
  'concept materialization never enables Shopify writes'
);

create temporary table phase6_materialized_job as
select job_id
from public.content_jobs
where source_job_key like 'decision:%'
  and content_plan_item_id = 'dededede-dede-4ede-8ede-dededededede';
grant select on phase6_materialized_job to orin_worker;

set local role orin_worker;
select * from orin_private.claim_next_job('worker:review-test', 1200);
select *
from orin_private.complete_job_with_review_draft(
  (select job_id from phase6_materialized_job),
  'worker:review-test',
  jsonb_build_object(
    'schema', 'orin.final-result/v2',
    'run_id', 'hb_20260804T120000Z_deadbeef',
    'request_id', 'cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd',
    'client_id', 'hoverboard_store',
    'job_id', '998',
    'attempt', 1,
    'requested_mode', 'dry-run',
    'effective_mode', 'dry-run',
    'status', 'completed',
    'decision', 'READY_TO_CREATE_SELECTED_JOB_DRAFT',
    'code_version', 'review-test',
    'config_version', null,
    'idempotency_key', 'hoverboard_store:cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd',
    'replay_disposition', 'terminal',
    'shopify_write_state', 'not_attempted',
    'shopify_idempotency_marker', null,
    'shopify_article_id', null,
    'shopify_create_count', 0,
    'shopify_published', false,
    'queue_changed', false,
    'reconciliation_status', 'not_required',
    'started_at', '2026-08-04T12:00:00Z',
    'finished_at', '2026-08-04T12:00:01Z',
    'artifact_uri', '/private/review-test',
    'error_code', null,
    'pipeline_exit_code', 0
  ),
  jsonb_build_object(
    'content_item_id', 'dededede-dede-4ede-8ede-dededededede',
    'content_item_version', 1,
    'title', 'Durable review test concept',
    'body_html', '<article><h1>Durable review</h1><p>Safe useful content.</p></article>',
    'body_sha256', repeat('a', 64),
    'word_count', 6,
    'meta_title', 'Durable review',
    'meta_description', 'A safe test draft.',
    'checks', jsonb_build_array('version bound', 'no Shopify write')
  )
);
reset role;

select is(
  (select count(*)::bigint from public.content_drafts
   where content_item_id = 'dededede-dede-4ede-8ede-dededededede'
     and content_item_version = 2),
  1::bigint,
  'successful dry-run stores exactly one immutable review draft'
);
select results_eq(
  $$ select status, version from public.content_plan_items
     where content_item_id = 'dededede-dede-4ede-8ede-dededededede' $$,
  $$ values ('local_draft_created'::text, 2::integer) $$,
  'draft persistence advances the exact content version to review'
);

set local role authenticated;
insert into public.content_decisions (
  client_id, content_item_id, content_item_version, decision, requested_by, request_id
) values (
  'hoverboard_store', 'dededede-dede-4ede-8ede-dededededede', 2,
  'approve_hidden_draft', 'abababab-abab-4bab-8bab-abababababab',
  'efefefef-efef-4fef-8fef-efefefefefef'
);
reset role;
set local role orin_worker;
select * from orin_private.materialize_next_content_decision();
reset role;

select is(
  (select processing_status from public.content_decisions
   where request_id = 'efefefef-efef-4fef-8fef-efefefefefef'),
  'recorded',
  'hidden-draft approval waits while Shopify write gates are closed'
);

select * from finish();
rollback;
