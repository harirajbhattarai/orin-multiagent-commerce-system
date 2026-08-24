begin;

select plan(15);

select ok(
  exists (select 1 from pg_roles where rolname = 'orin_commissioner'),
  'commissioner role exists'
);
select isnt(
  (select rolcanlogin from pg_roles where rolname = 'orin_commissioner'),
  true,
  'commissioner is NOLOGIN by default'
);
select isnt(
  (select rolsuper from pg_roles where rolname = 'orin_commissioner'),
  true,
  'commissioner is not superuser'
);
select isnt(
  (select rolbypassrls from pg_roles where rolname = 'orin_commissioner'),
  true,
  'commissioner cannot bypass RLS'
);
select has_column('public', 'client_commissioning_requests', 'worker_id');
select has_column('public', 'client_commissioning_requests', 'lease_expires_at');
select has_column('public', 'client_commissioning_requests', 'heartbeat_at');
select has_function('orin_private', 'claim_next_client_commissioning', array['text', 'integer']);
select has_function('orin_private', 'renew_client_commissioning_lease', array['uuid', 'text', 'integer']);
select has_function('orin_private', 'get_client_commissioning_context', array['uuid', 'text']);
select has_function('orin_private', 'client_commissioning_boundary_snapshot', array['uuid', 'text']);
select has_function('orin_private', 'record_client_commissioning_stage', array['uuid', 'text', 'text', 'text', 'jsonb']);
select has_function('orin_private', 'finish_client_commissioning', array['uuid', 'text', 'boolean', 'text', 'jsonb']);
select ok(
  has_function_privilege(
    'orin_commissioner',
    'orin_private.claim_next_client_commissioning(text,integer)',
    'EXECUTE'
  ),
  'commissioner can execute the private claim boundary'
);
select ok(
  not has_table_privilege(
    'orin_commissioner', 'public.client_commissioning_requests', 'SELECT'
  )
  and not has_table_privilege(
    'orin_commissioner', 'public.client_commissioning_requests', 'INSERT'
  )
  and not has_table_privilege(
    'orin_commissioner', 'public.client_commissioning_requests', 'UPDATE'
  )
  and not has_table_privilege(
    'orin_commissioner', 'public.client_commissioning_requests', 'DELETE'
  ),
  'commissioner has no direct commissioning table privileges'
);

select * from finish();
rollback;
