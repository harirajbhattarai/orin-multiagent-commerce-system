begin;
create extension if not exists pgtap with schema extensions;
select plan(9);

select ok(
  exists (
    select 1 from pg_trigger
    where tgrelid = 'public.content_decisions'::regclass
      and tgname = 'content_decisions_queue_consumed_revision'
      and not tgisinternal
  ),
  'consumed revision decisions have an automatic queue handoff'
);

insert into auth.users (id) values ('71717171-7171-4717-8717-717171717171');
insert into public.client_members (client_id, user_id, role)
values ('hoverboard_store', '71717171-7171-4717-8717-717171717171', 'operator');

insert into public.content_plan_items (
  content_item_id, client_id, item_number, target_date, cluster, decision,
  status, topic, target_keyword, draft_path, notes, source_document,
  source_revision, version
) values (
  '72727272-7272-4727-8727-727272727272', 'hoverboard_store', 997,
  '2026-12-29', 'Test', 'create_new', 'local_draft_created',
  'Version-bound revision regeneration test', 'revision regeneration test',
  'clients/hoverboard_store/content_engine/drafts/revision-regeneration-test.html',
  '- Preserve the verified safety guidance.', 'supabase-test', repeat('7', 64), 2
);

update public.clients set status = 'active' where client_id = 'hoverboard_store';
update public.client_runtime_settings
set request_intake_enabled = true,
    automation_enabled = true,
    shopify_writes_enabled = false,
    approved_draft_writes_enabled = false,
    allowed_mode = 'dry-run'
where client_id = 'hoverboard_store';

select set_config('request.jwt.claim.sub', '71717171-7171-4717-8717-717171717171', true);
set local role authenticated;
insert into public.content_decisions (
  client_id, content_item_id, content_item_version, decision, note,
  requested_by, request_id
) values (
  'hoverboard_store', '72727272-7272-4727-8727-727272727272', 2,
  'request_changes', 'Correct the technical explanation and regenerate.',
  '71717171-7171-4717-8717-717171717171',
  '73737373-7373-4737-8737-737373737373'
);
reset role;

set local role orin_worker;
select * from orin_private.materialize_next_content_decision_for_client('hoverboard_store');
reset role;

select is(
  (select processing_status from public.content_decisions
   where request_id = '73737373-7373-4737-8737-737373737373'),
  'consumed',
  'revision decision is consumed'
);
select ok(
  (select content_job_id is not null from public.content_decisions
   where request_id = '73737373-7373-4737-8737-737373737373'),
  'revision decision is linked to an execution job'
);
select results_eq(
  $$ select requested_mode, status, payload
     from public.content_jobs
     where request_id = '73737373-7373-4737-8737-737373737373' $$,
  $$ values ('dry-run'::text, 'queued'::text, '{}'::jsonb) $$,
  'revision queues one empty-payload dry-run job'
);
select results_eq(
  $$ select status, version from public.content_plan_items
     where content_item_id = '72727272-7272-4727-8727-727272727272' $$,
  $$ values ('in_progress'::text, 3::integer) $$,
  'revision reserves the incremented content version for drafting'
);
select is(
  (select outcome from public.content_decisions
   where request_id = '73737373-7373-4737-8737-737373737373'),
  'Revision draft-generation job queued.',
  'revision receipt reports the queued regeneration honestly'
);
select ok(
  not (select shopify_writes_enabled from public.client_runtime_settings
       where client_id = 'hoverboard_store'),
  'revision generation leaves Shopify writes closed'
);

set local role orin_worker;
select * from orin_private.claim_next_job_for_client(
  'worker:revision-test', 'hoverboard_store', 1200
);
reset role;

create temporary table revision_snapshot as
select orin_private.get_content_plan_snapshot(
  (select content_job_id from public.content_decisions
   where request_id = '73737373-7373-4737-8737-737373737373'),
  'worker:revision-test'
) as value;

select is(
  (select value ->> 'revision_request' from revision_snapshot),
  'Correct the technical explanation and regenerate.',
  'lease-bound snapshot exposes the exact revision request'
);
select like(
  (select item ->> 'notes'
   from revision_snapshot,
        jsonb_array_elements(value -> 'items') item
   where (item ->> 'item_number')::integer = 997),
  '%Human revision request (must be applied):%Correct the technical explanation and regenerate.%',
  'selected worker notes require the human revision'
);
select is(
  (select count(*)::integer from public.content_jobs
   where request_id = '73737373-7373-4737-8737-737373737373'),
  1,
  'one revision decision creates exactly one job'
);

select * from finish();
rollback;
