begin;
create extension if not exists pgtap with schema extensions;
select plan(20);

select has_table(
  'public',
  'shopify_draft_reconciliations',
  'durable Shopify reconciliation table exists'
);

select has_table(
  'public',
  'job_attempts',
  'durable worker-attempt ledger exists'
);

select ok(
  exists (
    select 1
    from pg_constraint
    where conrelid = 'public.runs'::regclass
      and conname = 'runs_hidden_draft_never_published'
  ),
  'run records enforce hidden-draft-only mutation'
);

select ok(
  not has_table_privilege(
    'orin_worker',
    'public.shopify_draft_reconciliations',
    'SELECT'
  )
  and not has_table_privilege(
    'orin_worker',
    'public.shopify_draft_reconciliations',
    'INSERT'
  )
  and not has_table_privilege(
    'orin_worker',
    'public.shopify_draft_reconciliations',
    'UPDATE'
  ),
  'worker has no direct reconciliation table privileges'
);

select ok(
  not has_table_privilege('orin_worker', 'public.job_attempts', 'SELECT')
  and not has_table_privilege('orin_worker', 'public.job_attempts', 'INSERT')
  and not has_table_privilege('orin_worker', 'public.job_attempts', 'UPDATE'),
  'worker can record attempts only through private stored functions'
);

create temporary table hidden_results (
  test_name text primary key,
  passed boolean not null
) on commit drop;
create temporary table hidden_claims (
  job_id uuid,
  client_id text,
  request_id uuid,
  requested_mode text,
  attempt_count smallint,
  payload jsonb,
  lease_expires_at timestamptz
) on commit drop;
create temporary table hidden_completions (
  run_id text,
  status text,
  replayed boolean
) on commit drop;
create temporary table hidden_payloads (
  request_id uuid primary key,
  payload jsonb not null
) on commit drop;

grant insert, select on hidden_results to orin_worker;
grant insert, select on hidden_claims to orin_worker;
grant insert, select on hidden_completions to orin_worker;
grant select on hidden_payloads to orin_worker;

update public.clients
set status = 'active'
where client_id = 'hoverboard_store';

update public.client_runtime_settings
set request_intake_enabled = true,
    automation_enabled = true,
    allowed_mode = 'hidden-draft',
    shopify_writes_enabled = false
where client_id = 'hoverboard_store';

insert into public.content_jobs (
  client_id,
  source_job_key,
  request_id,
  requested_mode,
  scheduled_for,
  payload
) values (
  'hoverboard_store',
  'hidden-draft-test-one',
  '66666666-6666-4666-8666-666666666666',
  'hidden-draft',
  now(),
  '{}'::jsonb
);

set local role orin_worker;
insert into hidden_results
select
  'write_gate_disabled',
  not exists (
    select 1 from orin_private.claim_next_job('worker:hidden:one', 1200)
  );
reset role;

select ok(
  (select passed from hidden_results where test_name = 'write_gate_disabled'),
  'disabled Shopify-write gate prevents hidden-draft claims'
);

update public.client_runtime_settings
set shopify_writes_enabled = true
where client_id = 'hoverboard_store';

set local role orin_worker;
insert into hidden_claims
select * from orin_private.claim_next_job('worker:hidden:one', 1200);
reset role;

select is(
  (select count(*) from hidden_claims),
  0::bigint,
  'the legacy broad write gate cannot claim an unapproved hidden-draft job'
);

with claimed as (
  update public.content_jobs job
  set status = 'leased',
      attempt_count = 1,
      lock_owner = 'worker:hidden:one',
      locked_at = statement_timestamp(),
      lease_expires_at = statement_timestamp() + interval '20 minutes'
  where job.request_id = '66666666-6666-4666-8666-666666666666'
  returning job_id, client_id, request_id, requested_mode, attempt_count,
            payload, lease_expires_at
)
insert into hidden_claims select * from claimed;

select is(
  (select requested_mode from hidden_claims limit 1),
  'hidden-draft',
  'worker claim preserves hidden-draft mode'
);

insert into hidden_payloads values (
  '66666666-6666-4666-8666-666666666666',
  jsonb_build_object(
    'schema', 'orin.final-result/v2',
    'run_id', 'hb_20260723T100000Z_12345678',
    'request_id', '66666666-6666-4666-8666-666666666666',
    'client_id', 'hoverboard_store',
    'job_id', null,
    'attempt', 1,
    'requested_mode', 'hidden-draft',
    'effective_mode', 'hidden-draft',
    'status', 'completed',
    'decision', 'DRAFT_CREATED_VERIFICATION_PASSED',
    'code_version', 'test-sha',
    'config_version', null,
    'idempotency_key', 'hoverboard_store:66666666-6666-4666-8666-666666666666',
    'replay_disposition', 'terminal',
    'shopify_write_state', 'article_observed',
    'shopify_idempotency_marker',
      'orin-v1:hoverboard_store:66666666-6666-4666-8666-666666666666',
    'shopify_article_id', '9001',
    'shopify_create_count', 1,
    'shopify_published', false,
    'queue_changed', false,
    'reconciliation_status', 'reconciled',
    'started_at', '2026-07-23T10:00:00+00:00',
    'finished_at', '2026-07-23T10:00:01+00:00',
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
      (select job_id from hidden_claims limit 1),
      'worker:hidden:one',
      jsonb_set(
        (select payload from hidden_payloads limit 1),
        '{shopify_published}',
        'true'::jsonb
      )
    );
    insert into hidden_results values ('published_rejected', false);
  exception when check_violation then
    insert into hidden_results values ('published_rejected', true);
  end;
end;
$$;

do $$
begin
  begin
    perform * from orin_private.complete_job(
      (select job_id from hidden_claims limit 1),
      'worker:hidden:one',
      jsonb_set(
        (select payload from hidden_payloads limit 1),
        '{queue_changed}',
        'true'::jsonb
      )
    );
    insert into hidden_results values ('queue_change_rejected', false);
  exception when check_violation then
    insert into hidden_results values ('queue_change_rejected', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from hidden_results where test_name = 'published_rejected'),
  'worker completion rejects published or scheduled Shopify state'
);

select ok(
  (select passed from hidden_results where test_name = 'queue_change_rejected'),
  'database-authoritative completion rejects Markdown queue mutation'
);

set local role orin_worker;
insert into hidden_completions
select * from orin_private.complete_job(
  (select job_id from hidden_claims limit 1),
  'worker:hidden:one',
  (select payload from hidden_payloads limit 1)
);
reset role;

select ok(
  (
    select
      run_id = 'hb_20260723T100000Z_12345678'
      and status = 'completed'
      and not replayed
    from hidden_completions
    limit 1
  ),
  'verified hidden draft completes exactly once'
);

select ok(
  (
    select
      idempotency_key =
        'hoverboard_store:66666666-6666-4666-8666-666666666666'
      and idempotency_marker =
        'orin-v1:hoverboard_store:66666666-6666-4666-8666-666666666666'
      and shopify_article_id = '9001'
      and status = 'reconciled'
      and observed_create_count = 1
      and not shopify_published
    from public.shopify_draft_reconciliations
    where request_id = '66666666-6666-4666-8666-666666666666'
  ),
  'completion records durable request ownership and the verified draft'
);

set local role orin_worker;
insert into hidden_completions
select * from orin_private.complete_job(
  (select job_id from hidden_claims limit 1),
  'worker:hidden:one',
  (select payload from hidden_payloads limit 1)
);
reset role;

select ok(
  (
    select replayed
    from hidden_completions
    order by replayed desc
    limit 1
  )
  and (
    select count(*)
    from public.shopify_draft_reconciliations
    where request_id = '66666666-6666-4666-8666-666666666666'
  ) = 1,
  'identical completion replay does not duplicate the reconciliation record'
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
  'hidden-draft-test-two',
  '77777777-7777-4777-8777-777777777777',
  'hidden-draft',
  now(),
  '{}'::jsonb
);

with claimed as (
  update public.content_jobs job
  set status = 'leased',
      attempt_count = 1,
      lock_owner = 'worker:hidden:two',
      locked_at = statement_timestamp(),
      lease_expires_at = statement_timestamp() + interval '20 minutes'
  where job.request_id = '77777777-7777-4777-8777-777777777777'
  returning job_id, client_id, request_id, requested_mode, attempt_count,
            payload, lease_expires_at
)
insert into hidden_claims select * from claimed;

insert into hidden_payloads values (
  '77777777-7777-4777-8777-777777777777',
  jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(
          (select payload from hidden_payloads
           where request_id = '66666666-6666-4666-8666-666666666666'),
          '{request_id}',
          '"77777777-7777-4777-8777-777777777777"'::jsonb
        ),
        '{run_id}',
        '"hb_20260723T100100Z_87654321"'::jsonb
      ),
      '{idempotency_key}',
      '"hoverboard_store:77777777-7777-4777-8777-777777777777"'::jsonb
    ),
    '{shopify_idempotency_marker}',
    '"orin-v1:hoverboard_store:77777777-7777-4777-8777-777777777777"'::jsonb
  )
);

set local role orin_worker;
do $$
begin
  begin
    perform * from orin_private.complete_job(
      (
        select job_id
        from hidden_claims
        where request_id = '77777777-7777-4777-8777-777777777777'
      ),
      'worker:hidden:two',
      (
        select payload
        from hidden_payloads
        where request_id = '77777777-7777-4777-8777-777777777777'
      )
    );
    insert into hidden_results values ('article_reuse_rejected', false);
  exception when unique_violation then
    insert into hidden_results values ('article_reuse_rejected', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from hidden_results where test_name = 'article_reuse_rejected'),
  'one Shopify article cannot be owned by two durable requests'
);

select is(
  (
    select count(*)
    from public.shopify_draft_reconciliations
    where shopify_article_id = '9001'
  ),
  1::bigint,
  'duplicate-article rejection leaves one authoritative owner'
);

update public.content_jobs
set status = 'failed',
    lock_owner = null,
    locked_at = null,
    lease_expires_at = null
where request_id = '77777777-7777-4777-8777-777777777777';

insert into public.content_jobs (
  client_id,
  source_job_key,
  request_id,
  requested_mode,
  scheduled_for,
  payload
) values (
  'hoverboard_store',
  'hidden-draft-needs-review',
  '88888888-8888-4888-8888-888888888888',
  'hidden-draft',
  now(),
  '{}'::jsonb
);

with claimed as (
  update public.content_jobs job
  set status = 'leased',
      attempt_count = 1,
      lock_owner = 'worker:hidden:three',
      locked_at = statement_timestamp(),
      lease_expires_at = statement_timestamp() + interval '20 minutes'
  where job.request_id = '88888888-8888-4888-8888-888888888888'
  returning job_id, client_id, request_id, requested_mode, attempt_count,
            payload, lease_expires_at
)
insert into hidden_claims select * from claimed;

insert into hidden_payloads values (
  '88888888-8888-4888-8888-888888888888',
  jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(
          jsonb_set(
            jsonb_set(
              jsonb_set(
                (select payload from hidden_payloads
                 where request_id = '66666666-6666-4666-8666-666666666666'),
                '{request_id}',
                '"88888888-8888-4888-8888-888888888888"'::jsonb
              ),
              '{run_id}',
              '"hb_20260723T100200Z_aabbccdd"'::jsonb
            ),
            '{idempotency_key}',
            '"hoverboard_store:88888888-8888-4888-8888-888888888888"'::jsonb
          ),
          '{shopify_idempotency_marker}',
          '"orin-v1:hoverboard_store:88888888-8888-4888-8888-888888888888"'::jsonb
        ),
        '{shopify_article_id}',
        '"9002"'::jsonb
      ),
      '{status}',
      '"blocked"'::jsonb
    ),
    '{replay_disposition}',
    '"reconcile"'::jsonb
  )
  || jsonb_build_object(
    'decision', 'DRAFT_CREATED_VERIFICATION_FAILED',
    'reconciliation_status', 'needs_review',
    'error_code', 'ORIN_PIPELINE_BLOCKED'
  )
);

set local role orin_worker;
do $$
begin
  begin
    perform * from orin_private.complete_job(
      (
        select job_id
        from hidden_claims
        where request_id = '88888888-8888-4888-8888-888888888888'
      ),
      'worker:hidden:three',
      (
        select payload
        from hidden_payloads
        where request_id = '88888888-8888-4888-8888-888888888888'
      )
    );
    insert into hidden_results values ('needs_review_terminal_rejected', false);
  exception when check_violation then
    insert into hidden_results values ('needs_review_terminal_rejected', true);
  end;
end;
$$;
reset role;

select ok(
  (select passed from hidden_results where test_name = 'needs_review_terminal_rejected'),
  'needs-review result cannot enter the terminal runs ledger'
);

set local role orin_worker;
insert into hidden_completions
select * from orin_private.defer_job(
  (
    select job_id
    from hidden_claims
    where request_id = '88888888-8888-4888-8888-888888888888'
  ),
  'worker:hidden:three',
  (
    select payload
    from hidden_payloads
    where request_id = '88888888-8888-4888-8888-888888888888'
  )
);
reset role;

select ok(
  (
    select status = 'queued' and not replayed
    from hidden_completions
    where run_id = 'hb_20260723T100200Z_aabbccdd'
  ),
  'reconciliation-required attempt is durably deferred'
);

select ok(
  (
    select
      status = 'queued'
      and lock_owner is null
      and locked_at is null
      and lease_expires_at is null
    from public.content_jobs
    where request_id = '88888888-8888-4888-8888-888888888888'
  ),
  'deferral clears the lease and returns the job to the queue'
);

select ok(
  (
    select
      replay_disposition = 'reconcile'
      and shopify_write_state = 'article_observed'
      and reconciliation_status = 'needs_review'
    from public.job_attempts
    where request_id = '88888888-8888-4888-8888-888888888888'
  )
  and not exists (
    select 1
    from public.runs
    where request_id = '88888888-8888-4888-8888-888888888888'
  ),
  'nonterminal evidence is retained without creating a terminal run'
);

select ok(
  not exists (
    select 1
    from public.shopify_draft_reconciliations
    where request_id = '88888888-8888-4888-8888-888888888888'
  ),
  'needs-review article is not recorded as reconciled ownership'
);

select * from finish();
rollback;
