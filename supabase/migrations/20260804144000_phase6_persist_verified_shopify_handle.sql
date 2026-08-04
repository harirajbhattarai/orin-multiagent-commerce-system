-- Phase 6: retain the verified Shopify handle with the terminal content item.
--
-- The article ID was already durable. The handle now travels in the signed-off
-- final result and is validated before the run trigger stores it.

create or replace function orin_private.apply_content_plan_run_result()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_item_id uuid;
  v_item_number integer;
  v_reported_number text;
  v_verified_handle text;
begin
  if new.job_id is null then return new; end if;

  select job.content_plan_item_id into v_item_id
  from public.content_jobs job
  where job.client_id = new.client_id and job.job_id = new.job_id;
  if v_item_id is null then return new; end if;

  select item.item_number into v_item_number
  from public.content_plan_items item
  where item.client_id = new.client_id and item.content_item_id = v_item_id;

  v_reported_number := new.final_result ->> 'job_id';
  if v_reported_number is not null and v_reported_number is distinct from v_item_number::text then
    raise exception 'run result content item does not match database ownership'
      using errcode = '23514';
  end if;

  if new.requested_mode = 'hidden-draft'
     and new.shopify_create_count = 1
     and new.shopify_article_id is not null
     and new.reconciliation_status = 'reconciled'
     and not new.shopify_published then
    v_verified_handle := new.final_result ->> 'shopify_handle';
    if new.decision = 'APPROVED_REVIEW_DRAFT_CREATED_VERIFICATION_PASSED'
       and (
         v_verified_handle is null
         or v_verified_handle !~ '^[a-z0-9]+(-[a-z0-9]+)*$'
       ) then
      raise exception 'approved review result has no canonical verified Shopify handle'
        using errcode = '23514';
    end if;

    update public.content_plan_items item
    set status = 'draft_created',
        shopify_article_id = new.shopify_article_id,
        shopify_handle = coalesce(v_verified_handle, item.shopify_handle),
        last_run_id = new.run_id,
        version = item.version + 1
    where item.client_id = new.client_id
      and item.content_item_id = v_item_id
      and (
        item.status = 'local_draft_created'
        or (item.status = 'draft_created' and item.shopify_article_id = new.shopify_article_id)
      );
    if not found then
      raise exception 'content-plan state transition rejected' using errcode = '23514';
    end if;
  end if;
  return new;
end;
$$;

revoke all on function orin_private.apply_content_plan_run_result()
  from public, anon, authenticated, orin_api, orin_worker;

-- Job 33 was independently verified against Shopify before this migration:
-- exactly one marker-owned article, ID 1007318892892, handle below, and
-- published_at null. Backfill only that exact terminal row if still missing.
update public.content_plan_items
set shopify_handle = 'foldable-vs-fixed-kids-electric-scooters'
where client_id = 'hoverboard_store'
  and item_number = 33
  and status = 'draft_created'
  and shopify_article_id = '1007318892892'
  and shopify_handle is null;

