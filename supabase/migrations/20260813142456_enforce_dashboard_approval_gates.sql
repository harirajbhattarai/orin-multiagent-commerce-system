-- Make the database enforce the same maintenance boundary shown by the
-- dashboard. Safe review notes remain available while maintenance is active,
-- but approvals cannot accumulate behind closed execution or Shopify gates.

create or replace function orin_private.validate_content_decision()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_item public.content_plan_items%rowtype;
  v_client_status text;
  v_settings public.client_runtime_settings%rowtype;
begin
  if v_uid is null then
    raise exception 'authenticated user required' using errcode = '42501';
  end if;

  if not exists (
    select 1
    from public.client_members membership
    where membership.client_id = new.client_id
      and membership.user_id = v_uid
      and membership.role in ('owner', 'operator')
  ) then
    raise exception 'client operator membership required' using errcode = '42501';
  end if;

  select item.*
  into v_item
  from public.content_plan_items item
  where item.client_id = new.client_id
    and item.content_item_id = new.content_item_id;

  if not found then
    raise exception 'content item not found' using errcode = 'P0002';
  end if;
  if new.content_item_version is distinct from v_item.version then
    raise exception 'content item version changed; refresh before deciding'
      using errcode = '40001';
  end if;

  if new.decision = 'approve_concept' and v_item.status <> 'planned' then
    raise exception 'concept approval requires a planned item' using errcode = '23514';
  elsif new.decision = 'approve_hidden_draft' then
    if v_item.status <> 'local_draft_created' or not exists (
      select 1
      from public.content_drafts draft
      where draft.client_id = new.client_id
        and draft.content_item_id = new.content_item_id
        and draft.content_item_version = new.content_item_version
    ) then
      raise exception 'hidden-draft approval requires the matching review draft'
        using errcode = '23514';
    end if;
  elsif new.decision = 'request_changes'
    and v_item.status not in ('planned', 'local_draft_created', 'checks_failed', 'needs_human_review') then
    raise exception 'change request is not valid for the current content stage'
      using errcode = '23514';
  end if;

  if new.decision in ('approve_concept', 'approve_hidden_draft') then
    select client.status
    into v_client_status
    from public.clients client
    where client.client_id = new.client_id;

    select settings.*
    into v_settings
    from public.client_runtime_settings settings
    where settings.client_id = new.client_id;

    if v_client_status <> 'active'
       or not v_settings.request_intake_enabled
       or not v_settings.automation_enabled then
      raise exception 'content approvals are paused while client execution gates are closed'
        using errcode = '55000';
    end if;

    if new.decision = 'approve_hidden_draft'
       and not (
         (
           v_settings.approved_draft_writes_enabled
           and not v_settings.shopify_writes_enabled
           and v_settings.allowed_mode = 'dry-run'
         )
         or (
           v_settings.shopify_writes_enabled
           and not v_settings.approved_draft_writes_enabled
           and v_settings.allowed_mode = 'hidden-draft'
         )
       ) then
      raise exception 'Shopify draft approval is paused while Shopify write gates are closed'
        using errcode = '55000';
    end if;
  end if;

  new.requested_by := v_uid;
  new.processing_status := 'recorded';
  new.consumed_at := null;
  new.content_job_id := null;
  new.outcome := '';
  return new;
end;
$$;

revoke all on function orin_private.validate_content_decision()
  from public, anon, authenticated;

comment on function orin_private.validate_content_decision() is
  'Validates tenant/version/stage bindings and rejects approvals while the matching execution or Shopify gates are closed.';
