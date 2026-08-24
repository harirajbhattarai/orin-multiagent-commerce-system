-- Qualify the onboarding status predicate in the operator-only rollout
-- recovery. The function returns a column named status, so an unqualified
-- table column is ambiguous inside PL/pgSQL.

create or replace function orin_private.recover_generic_pilot_success(
  p_job_id uuid,
  p_worker_id text,
  p_expected_request_id uuid,
  p_final_result jsonb,
  p_review_draft jsonb
)
returns table (run_id text, status text, replayed boolean)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.content_jobs%rowtype;
  v_item public.content_plan_items%rowtype;
  v_new_request_id uuid := gen_random_uuid();
  v_rebound_result jsonb;
  v_completion record;
begin
  select * into v_job from public.content_jobs where job_id = p_job_id for update;
  if not found
     or v_job.client_id in ('hoverboard_store', 'hcs_gadgets')
     or v_job.source_job_key not like 'pilot:' || v_job.client_id || ':%'
     or v_job.status not in ('leased', 'running')
     or v_job.lock_owner is distinct from p_worker_id
     or v_job.request_id is distinct from p_expected_request_id
     or v_job.requested_mode <> 'dry-run'
     or v_job.attempt_count <> v_job.max_attempts
     or v_job.attempt_count <> 2 then
    raise exception 'generic pilot artifact recovery boundary failed'
      using errcode = '55000';
  end if;
  perform orin_private.assert_generic_pilot_boundary(v_job.client_id, false);

  if not exists (
    select 1 from public.runs prior
    where prior.client_id = v_job.client_id
      and prior.job_id = v_job.job_id
      and prior.request_id = p_expected_request_id
      and prior.attempt = 1
      and prior.status = 'failed'
      and prior.error_code = 'ORIN_GENERIC_PILOT_DRAFT_FAILED'
      and prior.shopify_write_state = 'not_attempted'
      and prior.shopify_create_count = 0
  ) or exists (
    select 1 from public.job_attempts attempt
    where attempt.job_id = v_job.job_id and attempt.attempt = 2
  ) then
    raise exception 'generic pilot artifact recovery history is not exact'
      using errcode = '55000';
  end if;

  select * into v_item from public.content_plan_items item
  where item.client_id = v_job.client_id
    and item.content_item_id = v_job.content_plan_item_id
  for update;
  if not found
     or v_item.status <> 'checks_failed'
     or p_final_result ->> 'status' <> 'completed'
     or p_final_result ->> 'decision' <> 'GENERIC_PILOT_REVIEW_DRAFT_CREATED'
     or p_final_result ->> 'request_id' is distinct from p_expected_request_id::text
     or (p_final_result ->> 'attempt')::integer <> 2
     or p_final_result ->> 'requested_mode' <> 'dry-run'
     or p_final_result ->> 'effective_mode' <> 'dry-run'
     or p_final_result ->> 'replay_disposition' <> 'terminal'
     or p_final_result ->> 'shopify_write_state' <> 'not_attempted'
     or coalesce((p_final_result ->> 'shopify_create_count')::integer, 1) <> 0
     or coalesce((p_final_result ->> 'shopify_published')::boolean, true)
     or coalesce((p_final_result ->> 'queue_changed')::boolean, true)
     or p_review_draft ->> 'content_item_id' is distinct from v_item.content_item_id::text
     or (p_review_draft ->> 'content_item_version')::integer is distinct from v_item.version then
    raise exception 'generic pilot passing artifact is not version-bound'
      using errcode = '23514';
  end if;

  v_rebound_result := jsonb_set(
    jsonb_set(
      p_final_result,
      '{request_id}',
      to_jsonb(v_new_request_id::text)
    ),
    '{idempotency_key}',
    to_jsonb(v_job.client_id || ':' || v_new_request_id::text)
  );

  update public.content_jobs
  set request_id = v_new_request_id,
      lease_expires_at = statement_timestamp() + interval '20 minutes'
  where job_id = v_job.job_id;
  update public.content_plan_items
  set status = 'in_progress'
  where client_id = v_job.client_id and content_item_id = v_item.content_item_id;
  update public.clients set status = 'active' where client_id = v_job.client_id;
  update public.client_runtime_settings
  set request_intake_enabled = true,
      automation_enabled = true,
      shopify_writes_enabled = false,
      approved_draft_writes_enabled = false,
      max_concurrency = 1,
      allowed_mode = 'dry-run'
  where client_id = v_job.client_id;
  update public.scheduler_health
  set state = 'disabled', scheduler_owner = null
  where client_id = v_job.client_id;
  update public.client_onboarding_requests onboarding
  set commissioning_status = 'dry_run_pending', last_error = ''
  where onboarding.client_id = v_job.client_id
    and onboarding.status = 'database_provisioned';

  select * into v_completion
  from orin_private.complete_generic_pilot_job(
    p_job_id, p_worker_id, v_rebound_result, p_review_draft
  );
  return query select v_completion.run_id, v_completion.status, v_completion.replayed;
end;
$$;

revoke all on function orin_private.recover_generic_pilot_success(uuid, text, uuid, jsonb, jsonb)
  from public, anon, authenticated, orin_pilot_worker;

comment on function orin_private.recover_generic_pilot_success(uuid, text, uuid, jsonb, jsonb) is
  'Operator-only, one-state recovery for the pre-fix generic-pilot retry artifact; never permits Shopify work.';
