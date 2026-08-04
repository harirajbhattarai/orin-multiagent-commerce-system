begin;
create extension if not exists pgtap with schema extensions;
select plan(10);

select ok(
  (
    select
      not rolcanlogin
      and not rolsuper
      and not rolcreaterole
      and not rolcreatedb
      and not rolreplication
      and not rolbypassrls
    from pg_roles
    where rolname = 'orin_prefect_shadow'
  ),
  'orin_prefect_shadow is a non-login, non-admin, RLS-bound role'
);

select ok(
  not has_table_privilege('orin_prefect_shadow', 'public.clients', 'SELECT')
  and not has_table_privilege('orin_prefect_shadow', 'public.content_plan_items', 'SELECT')
  and not has_table_privilege('orin_prefect_shadow', 'public.runs', 'SELECT')
  and not has_table_privilege('orin_prefect_shadow', 'public.incidents', 'SELECT'),
  'Prefect shadow has no direct table read privileges'
);

select ok(
  not has_table_privilege('orin_prefect_shadow', 'public.content_jobs', 'INSERT')
  and not has_table_privilege('orin_prefect_shadow', 'public.content_jobs', 'UPDATE')
  and not has_table_privilege('orin_prefect_shadow', 'public.runs', 'INSERT')
  and not has_table_privilege('orin_prefect_shadow', 'public.runs', 'UPDATE'),
  'Prefect shadow cannot mutate jobs or runs'
);

select ok(
  has_function_privilege(
    'orin_prefect_shadow',
    'orin_private.get_prefect_shadow_snapshot(text)',
    'EXECUTE'
  ),
  'Prefect shadow can execute its sanitized snapshot function'
);

select ok(
  not has_function_privilege(
    'orin_prefect_shadow',
    'orin_private.enqueue_hoverboard_scheduled_job()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_prefect_shadow',
    'orin_private.claim_next_job(text, integer)',
    'EXECUTE'
  )
  and not has_function_privilege(
    'orin_prefect_shadow',
    'orin_private.complete_job(uuid, text, jsonb)',
    'EXECUTE'
  ),
  'Prefect shadow cannot enqueue, claim, or complete work'
);

create temporary table prefect_shadow_results (
  snapshot jsonb,
  cross_tenant_denied boolean
) on commit drop;
grant insert, select on prefect_shadow_results to orin_prefect_shadow;

set local role orin_prefect_shadow;
insert into prefect_shadow_results(snapshot)
select orin_private.get_prefect_shadow_snapshot('hoverboard_store');
do $$
begin
  begin
    perform orin_private.get_prefect_shadow_snapshot('not_hoverboard_store');
    insert into prefect_shadow_results(cross_tenant_denied) values (false);
  exception when insufficient_privilege then
    insert into prefect_shadow_results(cross_tenant_denied) values (true);
  end;
end;
$$;
reset role;

select is(
  (select snapshot ->> 'schema' from prefect_shadow_results where snapshot is not null),
  'orin.prefect-shadow-snapshot/v1',
  'snapshot has the versioned shadow schema'
);

select is(
  (select snapshot ->> 'client_id' from prefect_shadow_results where snapshot is not null),
  'hoverboard_store',
  'snapshot is fixed to Hoverboard Store'
);

select ok(
  (
    select
      jsonb_typeof(snapshot -> 'items') = 'array'
      and jsonb_typeof(snapshot -> 'runtime') = 'object'
      and jsonb_typeof(snapshot -> 'scheduler') = 'object'
      and not (snapshot ? 'client_members')
      and not (snapshot ? 'artifact_prefix')
    from prefect_shadow_results
    where snapshot is not null
  ),
  'snapshot contains only the sanitized planning and operational projection'
);

select ok(
  (select bool_and(cross_tenant_denied) from prefect_shadow_results where cross_tenant_denied is not null),
  'cross-tenant snapshot access is rejected'
);

select ok(
  (
    select not exists (
      select 1
      from jsonb_array_elements(snapshot -> 'items') item
      where item ? 'notes' or item ? 'draft_path' or item ? 'body_html'
    )
    from prefect_shadow_results
    where snapshot is not null
  ),
  'content projection excludes notes, paths, and draft bodies'
);

select * from finish();
rollback;
