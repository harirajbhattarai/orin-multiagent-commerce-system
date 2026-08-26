-- Allow an authenticated client owner/operator to plan one article from the
-- dashboard. The function only inserts a planned concept. It never creates a
-- job, changes scheduler ownership, opens execution gates, or contacts Shopify.

create or replace function public.plan_next_content_article(
  p_client_id text,
  p_topic text,
  p_target_keyword text,
  p_cluster text,
  p_target_date date,
  p_notes text default ''
)
returns table (
  content_item_id uuid,
  item_number integer,
  version integer,
  status text,
  topic text,
  target_keyword text,
  target_date date
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := auth.uid();
  v_item_number integer;
  v_slug text;
  v_source_revision text;
  v_today date := (statement_timestamp() at time zone 'Europe/London')::date;
begin
  if v_uid is null then
    raise exception 'authenticated user required' using errcode = '42501';
  end if;
  if not exists (
    select 1
    from public.client_members membership
    where membership.client_id = p_client_id
      and membership.user_id = v_uid
      and membership.role in ('owner', 'operator')
  ) then
    raise exception 'client owner or operator membership required'
      using errcode = '42501';
  end if;
  if not exists (
    select 1
    from public.clients client
    join public.client_profiles profile using (client_id)
    where client.client_id = p_client_id
  ) then
    raise exception 'commissioned client workspace required'
      using errcode = '55000';
  end if;
  if nullif(btrim(p_topic), '') is null or char_length(p_topic) > 240 then
    raise exception 'article title must be between 1 and 240 characters'
      using errcode = '22023';
  end if;
  if nullif(btrim(p_target_keyword), '') is null
     or char_length(p_target_keyword) > 160 then
    raise exception 'target keyword must be between 1 and 160 characters'
      using errcode = '22023';
  end if;
  if nullif(btrim(p_cluster), '') is null or char_length(p_cluster) > 160 then
    raise exception 'content category must be between 1 and 160 characters'
      using errcode = '22023';
  end if;
  if char_length(coalesce(p_notes, '')) > 4000 then
    raise exception 'planning guidance must not exceed 4000 characters'
      using errcode = '22023';
  end if;
  if p_target_date is null
     or p_target_date < v_today + 14
     or p_target_date > v_today + 365 then
    raise exception 'target publication date must be between 14 and 365 days from today'
      using errcode = '22023';
  end if;

  if exists (
    select 1
    from public.content_plan_items item
    where btrim(lower(regexp_replace(item.topic, '[^[:alnum:]]+', ' ', 'g')))
          = btrim(lower(regexp_replace(p_topic, '[^[:alnum:]]+', ' ', 'g')))
  ) then
    raise exception 'an article with this title is already planned'
      using errcode = '23505';
  end if;
  if exists (
    select 1
    from public.content_plan_items item
    where btrim(lower(regexp_replace(item.target_keyword, '[^[:alnum:]]+', ' ', 'g')))
          = btrim(lower(regexp_replace(p_target_keyword, '[^[:alnum:]]+', ' ', 'g')))
  ) then
    raise exception 'an article with this target keyword is already planned'
      using errcode = '23505';
  end if;

  perform pg_advisory_xact_lock(hashtextextended('orin-plan:' || p_client_id, 0));
  select coalesce(max(item.item_number), 0) + 1
  into v_item_number
  from public.content_plan_items item
  where item.client_id = p_client_id;

  v_slug := trim(both '-' from lower(regexp_replace(btrim(p_topic), '[^[:alnum:]]+', '-', 'g')));
  v_source_revision := encode(
    extensions.digest(
      convert_to(
        p_client_id || E'\n' || btrim(p_topic) || E'\n'
        || btrim(p_target_keyword) || E'\n' || btrim(p_cluster) || E'\n'
        || p_target_date::text || E'\n' || v_uid::text,
        'UTF8'
      ),
      'sha256'
    ),
    'hex'
  );

  return query
  insert into public.content_plan_items as inserted (
    client_id, item_number, target_date, cluster, decision, status, topic,
    target_keyword, draft_path, notes, source_document, source_revision
  ) values (
    p_client_id,
    v_item_number,
    p_target_date,
    btrim(p_cluster),
    'create_new',
    'planned',
    btrim(p_topic),
    btrim(p_target_keyword),
    'clients/' || p_client_id || '/content_engine/drafts/' || v_slug || '.html',
    btrim(coalesce(p_notes, '')),
    'dashboard:manual-content-plan',
    v_source_revision
  )
  returning
    inserted.content_item_id,
    inserted.item_number,
    inserted.version,
    inserted.status,
    inserted.topic,
    inserted.target_keyword,
    inserted.target_date;
end;
$$;

revoke all on function public.plan_next_content_article(text, text, text, text, date, text)
  from public, anon, authenticated;
grant execute on function public.plan_next_content_article(text, text, text, text, date, text)
  to authenticated;

comment on function public.plan_next_content_article(text, text, text, text, date, text) is
  'Creates one deduplicated planned concept for a client owner/operator; never opens gates, creates jobs, or contacts Shopify.';
