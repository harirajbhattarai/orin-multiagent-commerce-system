begin;
create extension if not exists pgtap with schema extensions;
select plan(18);

select ok(
  (
    select
      not rolcanlogin
      and not rolsuper
      and not rolcreaterole
      and not rolcreatedb
      and not rolbypassrls
    from pg_roles
    where rolname = 'orin_worker'
  ),
  'orin_worker is a non-login, non-admin, RLS-bound role'
);

select ok(
  not has_table_privilege('orin_worker', 'public.content_jobs', 'SELECT')
  and not has_table_privilege('orin_worker', 'public.content_jobs', 'INSERT')
  and not has_table_privilege('orin_worker', 'public.content_jobs', 'UPDATE')
  and not has_table_privilege('orin_worker', 'public.content_jobs', 'DELETE')
  and not has_table_privilege('orin_worker', 'public.runs', 'SELECT')
  and not has_table_privilege('orin_worker', 'public.runs', 'INSERT'),
  'orin_worker has no direct job or run table privileges'
);

select ok(
  has_function_privilege(
    'orin_worker',
    'orin_private.claim_next_job_for_client(text,text,integer)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_worker',
    'orin_private.claim_next_job(text,integer)',
    'EXECUTE'
  )
  and has_function_privilege(
    'orin_worker',
    'orin_private.renew_job_lease(uuid,text,integer)',
    'EXECUTE'
  )
  and has_function_privilege(
    'orin_worker',
    'orin_private.complete_job(uuid,text,jsonb)',
    'EXECUTE'
  )
  and has_function_privilege(
    'orin_worker',
    'orin_private.defer_job(uuid,text,jsonb)',
    'EXECUTE'
  ),
  'orin_worker can execute only the worker capability functions'
);

select ok(
  exists (
    select 1 from pg_indexes
    where schemaname = 'public'
      and tablename = 'content_jobs'
      and indexname = 'content_jobs_one_active_per_client_idx'
      and indexdef like 'CREATE UNIQUE INDEX%'
  ),
  'database enforces at most one active job per client'
);

select ok(
  exists (
    select 1
    from pg_constraint
    where conrelid = 'public.runs'::regclass
      and conname = 'runs_dry_run_has_no_mutation'
  ),
  'database rejects mutation claims in dry-run run records'
);

create temporary table worker_results (
  test_name text primary key,
  passed boolean not null
) on commit drop;
create temporary table worker_claims (
  job_id uuid,
  client_id text,
  request_id uuid,
  requested_mode text,
  attempt_count smallint,
  payload jsonb,
  lease_expires_at timestamptz
) on commit drop;
create temporary table worker_completions (
  run_id text,
  status text,
  replayed boolean
) on commit drop;
create temporary table worker_payload (payload jsonb not null) on commit drop;

grant insert, select on worker_results to orin_worker;
grant insert, select on worker_claims to orin_worker;
grant insert, select on worker_completions to orin_worker;
grant select on worker_payload to orin_worker;

insert into public.content_jobs (
  client_id,
  source_job_key,
  request_id,
  requested_mode,
  scheduled_for,
  payload
) values (
  'hoverboard_store',
  'worker-test',
  '55555555-5555-4555-8555-555555555555',
  'dry-run',
  now(),
  '{}'::jsonb
);

set local role orin_worker;
insert into worker_results
select
  'disabled_claim',
  not exists (
    select 1 from orin_private.claim_next_job_for_client(
      'worker:test:one', 'hoverboard_store', 1200
    )
  );
reset role;

select ok(
  (select passed from worker_results where test_name = 'disabled_claim'),
  'maintenance and automation gates prevent claims'
);

update public.clients
set status = 'active'
where client_id = 'hoverboard_store';

update public.client_runtime_settings
set request_intake_enabled = true,
    automation_enabled = true
where client_id = 'hoverboard_store';

set local role orin_worker;
insert into worker_claims
select * from orin_private.claim_next_job_for_client(
  'worker:test:one', 'hoverboard_store', 1200
);
reset role;

select is(
  (select count(*) from worker_claims),
  1::bigint,
  'one due dry-run job is claimed'
);

select ok(
  (
    select
      status = 'leased'
      and attempt_count = 1
      and lock_owner = 'worker:test:one'
      and lease_expires_at > locked_at
    from public.content_jobs
    where request_id = '55555555-5555-4555-8555-555555555555'
  ),
  'claim records ownership, attempt, and lease expiry atomically'
);

set local role orin_worker;
insert into worker_claims
select * from orin_private.claim_next_job_for_client(
  'worker:test:two', 'hoverboard_store', 1200
);
reset role;

select is(
  (select count(*) from worker_claims),
  1::bigint,
  'a second worker cannot claim another job for the active client'
);

set local role orin_worker;
insert into worker_results
select
  'wrong_renewal',
  not orin_private.renew_job_lease(
    (select job_id from worker_claims limit 1),
    'worker:test:two',
    1200
  );
insert into worker_results
select
  'own_renewal',
  orin_private.renew_job_lease(
    (select job_id from worker_claims limit 1),
    'worker:test:one',
    1200
  );
reset role;

select ok(
  (select passed from worker_results where test_name = 'wrong_renewal'),
  'a different worker cannot renew the lease'
);

select ok(
  (select passed from worker_results where test_name = 'own_renewal'),
  'the lease owner can renew an unexpired lease'
);

insert into worker_payload values (
  jsonb_build_object(
    'schema', 'orin.final-result/v2',
    'run_id', 'hb_20260722T180000Z_12345678',
    'request_id', '55555555-5555-4555-8555-555555555555',
    'client_id', 'hoverboard_store',
    'job_id', null,
    'attempt', 1,
    'requested_mode', 'dry-run',
    'effective_mode', 'dry-run',
    'status', 'completed',
    'decision', 'no_job_due',
    'code_version', 'test-sha',
    'config_version', null,
    'idempotency_key', 'hoverboard_store:55555555-5555-4555-8555-555555555555',
    'replay_disposition', 'terminal',
    'shopify_write_state', 'not_attempted',
    'shopify_article_id', null,
    'shopify_create_count', 0,
    'shopify_published', false,
    'queue_changed', false,
    'reconciliation_status', 'not_required',
    'started_at', '2026-07-22T18:00:00+00:00',
    'finished_at', '2026-07-22T18:00:01+00:00',
    'artifact_uri', '/private/evidence/run',
    'error_code', null,
    'pipeline_exit_code', 0
  )
);

set local role orin_worker;
do $$
begin
  begin
    perform * from orin_private.complete_job(
      (select job_id from worker_claims limit 1),
      'worker:test:one',
      jsonb_set(
        (select payload from worker_payload),
        '{shopify_create_count}',
        '1'::jsonb
      )
    );
    insert into worker_results values ('mutation_rejected', false);
  exception when check_violation then
    insert into worker_results values ('mutation_rejected', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from worker_results where test_name = 'mutation_rejected'),
  'worker completion rejects a Shopify mutation claim in dry-run mode'
);

set local role orin_worker;
insert into worker_completions
select * from orin_private.complete_job(
  (select job_id from worker_claims limit 1),
  'worker:test:one',
  (select payload from worker_payload)
);
reset role;

select ok(
  (
    select
      run_id = 'hb_20260722T180000Z_12345678'
      and status = 'completed'
      and not replayed
    from worker_completions
    limit 1
  ),
  'lease owner records the first completion'
);

select ok(
  (
    select
      status = 'completed'
      and lock_owner is null
      and locked_at is null
      and lease_expires_at is null
    from public.content_jobs
    where request_id = '55555555-5555-4555-8555-555555555555'
  ),
  'completion makes the job terminal and clears its lease'
);

select ok(
  (
    select
      job_id = (select job_id from worker_claims limit 1)
      and requested_mode = 'dry-run'
      and shopify_create_count = 0
      and not shopify_published
      and not queue_changed
      and final_result = (select payload from worker_payload)
    from public.runs
    where request_id = '55555555-5555-4555-8555-555555555555'
  ),
  'run is linked to the database job with the exact no-mutation result'
);

set local role orin_worker;
insert into worker_completions
select * from orin_private.complete_job(
  (select job_id from worker_claims limit 1),
  'worker:test:one',
  (select payload from worker_payload)
);
reset role;

select ok(
  (
    select replayed
    from worker_completions
    order by replayed desc
    limit 1
  )
  and (select count(*) from public.runs where request_id = '55555555-5555-4555-8555-555555555555') = 1,
  'repeating an identical completion is idempotent'
);

insert into public.content_jobs (
  client_id,
  source_job_key,
  request_id,
  requested_mode,
  scheduled_for,
  payload
) values (
  'hoverboard_store',
  'worker-cached-terminal',
  '99999999-9999-4999-8999-999999999999',
  'dry-run',
  now(),
  '{}'::jsonb
);

set local role orin_worker;
insert into worker_claims
select * from orin_private.claim_next_job_for_client(
  'worker:test:cached-one', 'hoverboard_store', 1200
);
reset role;

update public.content_jobs
set locked_at = statement_timestamp() - interval '2 minutes',
    lease_expires_at = statement_timestamp() - interval '1 second'
where request_id = '99999999-9999-4999-8999-999999999999';

set local role orin_worker;
insert into worker_claims
select * from orin_private.claim_next_job_for_client(
  'worker:test:cached-two', 'hoverboard_store', 1200
);
reset role;

select is(
  (
    select max(attempt_count)
    from worker_claims
    where request_id = '99999999-9999-4999-8999-999999999999'
  ),
  2::smallint,
  'an expired lease creates a second database claim attempt'
);

set local role orin_worker;
insert into worker_completions
select * from orin_private.complete_job(
  (
    select job_id
    from worker_claims
    where request_id = '99999999-9999-4999-8999-999999999999'
    limit 1
  ),
  'worker:test:cached-two',
  jsonb_build_object(
    'schema', 'orin.final-result/v2',
    'run_id', 'hb_20260723T130000Z_11223344',
    'request_id', '99999999-9999-4999-8999-999999999999',
    'client_id', 'hoverboard_store',
    'job_id', null,
    'attempt', 1,
    'requested_mode', 'dry-run',
    'effective_mode', 'dry-run',
    'status', 'completed',
    'decision', 'no_job_due',
    'code_version', 'test-sha',
    'config_version', null,
    'idempotency_key', 'hoverboard_store:99999999-9999-4999-8999-999999999999',
    'replay_disposition', 'terminal',
    'shopify_write_state', 'not_attempted',
    'shopify_article_id', null,
    'shopify_create_count', 0,
    'shopify_published', false,
    'queue_changed', false,
    'reconciliation_status', 'not_required',
    'started_at', '2026-07-23T13:00:00+00:00',
    'finished_at', '2026-07-23T13:00:01+00:00',
    'artifact_uri', '/private/evidence/cached-run',
    'error_code', null,
    'pipeline_exit_code', 0
  )
);
reset role;

select ok(
  (
    select
      attempt = 1
      and status = 'completed'
      and replay_disposition = 'terminal'
    from public.runs
    where request_id = '99999999-9999-4999-8999-999999999999'
  ),
  'a cached terminal result from the prior lease can finalize after reclaim'
);

select * from finish();
rollback;
