-- Phase 6: move the SEO content plan from Markdown transaction state into Postgres.
-- This migration creates no scheduler, network path, credential, or Shopify-write grant.

create table public.content_plan_items (
  content_item_id uuid primary key default gen_random_uuid(),
  client_id text not null references public.clients(client_id) on delete cascade,
  item_number integer not null check (item_number > 0),
  target_date date,
  expected_draft_date date generated always as (target_date - 14) stored,
  cluster text,
  decision text,
  status text not null
    check (
      status in (
        'planned',
        'in_progress',
        'local_draft_created',
        'checks_failed',
        'draft_created',
        'published_live',
        'skipped_duplicate',
        'needs_human_review',
        'archived'
      )
    ),
  topic text,
  target_keyword text,
  draft_path text,
  notes text not null default '',
  shopify_article_id text,
  shopify_handle text,
  source_document text not null,
  source_revision text not null check (source_revision ~ '^[0-9a-f]{64}$'),
  version integer not null default 1 check (version >= 1),
  last_run_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (client_id, item_number),
  unique (client_id, content_item_id),
  foreign key (client_id, last_run_id)
    references public.runs(client_id, run_id) on delete restrict,
  check (
    status <> 'planned'
    or (
      target_date is not null
      and nullif(btrim(topic), '') is not null
      and nullif(btrim(target_keyword), '') is not null
      and nullif(btrim(draft_path), '') is not null
    )
  ),
  check (
    draft_path is null
    or draft_path like 'clients/' || client_id || '/content_engine/%'
  )
);

create index content_plan_items_due_idx
  on public.content_plan_items(client_id, expected_draft_date, item_number)
  where status = 'planned';

create index content_plan_items_last_run_idx
  on public.content_plan_items(client_id, last_run_id)
  where last_run_id is not null;

create trigger content_plan_items_set_updated_at
before update on public.content_plan_items
for each row execute function orin_private.set_updated_at();

alter table public.content_jobs
  add column content_plan_item_id uuid,
  add constraint content_jobs_content_plan_item_fkey
    foreign key (client_id, content_plan_item_id)
    references public.content_plan_items(client_id, content_item_id)
    on delete restrict;

create unique index content_jobs_one_active_plan_item_idx
  on public.content_jobs(client_id, content_plan_item_id)
  where status in ('leased', 'running')
    and content_plan_item_id is not null;

alter table public.content_plan_items enable row level security;

revoke all on table public.content_plan_items
  from public, anon, authenticated, orin_api, orin_worker;
grant select on table public.content_plan_items to authenticated;

create policy content_plan_items_select_for_members
on public.content_plan_items for select to authenticated
using (
  exists (
    select 1
    from public.client_members membership
    where membership.client_id = content_plan_items.client_id
      and membership.user_id = (select auth.uid())
  )
);

create or replace function orin_private.get_content_plan_snapshot(
  p_job_id uuid,
  p_worker_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_job public.content_jobs%rowtype;
  v_selected public.content_plan_items%rowtype;
  v_items jsonb;
begin
  select *
  into v_job
  from public.content_jobs job
  where job.job_id = p_job_id
  for update;

  if not found then
    raise exception 'job not found' using errcode = 'P0002';
  end if;

  if v_job.status not in ('leased', 'running')
     or v_job.lock_owner is distinct from p_worker_id
     or v_job.lease_expires_at <= statement_timestamp() then
    raise exception 'worker does not own an active job lease' using errcode = '42501';
  end if;

  if v_job.content_plan_item_id is not null then
    select *
    into v_selected
    from public.content_plan_items item
    where item.client_id = v_job.client_id
      and item.content_item_id = v_job.content_plan_item_id;
  else
    select *
    into v_selected
    from public.content_plan_items item
    where item.client_id = v_job.client_id
      and item.status = 'planned'
      and item.expected_draft_date <=
        (statement_timestamp() at time zone 'Europe/London')::date
    order by item.item_number, item.content_item_id
    for update skip locked
    limit 1;

    if found then
      update public.content_jobs job
      set content_plan_item_id = v_selected.content_item_id
      where job.job_id = v_job.job_id;
    end if;
  end if;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'content_item_id', item.content_item_id,
        'item_number', item.item_number,
        'target_date', item.target_date,
        'expected_draft_date', item.expected_draft_date,
        'cluster', item.cluster,
        'decision', item.decision,
        'status', item.status,
        'topic', item.topic,
        'target_keyword', item.target_keyword,
        'draft_path', item.draft_path,
        'notes', item.notes,
        'shopify_article_id', item.shopify_article_id,
        'shopify_handle', item.shopify_handle,
        'version', item.version
      )
      order by item.item_number
    ),
    '[]'::jsonb
  )
  into v_items
  from public.content_plan_items item
  where item.client_id = v_job.client_id;

  return jsonb_build_object(
    'schema', 'orin.content-plan-snapshot/v1',
    'client_id', v_job.client_id,
    'execution_job_id', v_job.job_id,
    'selected_item_id', v_selected.content_item_id,
    'selected_item_number', v_selected.item_number,
    'generated_at', statement_timestamp(),
    'items', v_items
  );
end;
$$;

revoke all on function orin_private.get_content_plan_snapshot(uuid, text)
  from public, anon, authenticated, orin_api;
grant execute on function orin_private.get_content_plan_snapshot(uuid, text)
  to orin_worker;

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
begin
  if new.job_id is null then
    return new;
  end if;

  select job.content_plan_item_id
  into v_item_id
  from public.content_jobs job
  where job.client_id = new.client_id
    and job.job_id = new.job_id;

  if v_item_id is null then
    return new;
  end if;

  select item.item_number
  into v_item_number
  from public.content_plan_items item
  where item.client_id = new.client_id
    and item.content_item_id = v_item_id;

  v_reported_number := new.final_result ->> 'job_id';
  if v_reported_number is not null
     and v_reported_number is distinct from v_item_number::text then
    raise exception 'run result content item does not match database ownership'
      using errcode = '23514';
  end if;

  if new.requested_mode = 'hidden-draft'
     and new.shopify_create_count = 1
     and new.shopify_article_id is not null
     and new.reconciliation_status = 'reconciled'
     and not new.shopify_published then
    update public.content_plan_items item
    set status = 'draft_created',
        shopify_article_id = new.shopify_article_id,
        last_run_id = new.run_id,
        version = item.version + 1
    where item.client_id = new.client_id
      and item.content_item_id = v_item_id
      and (
        item.status = 'planned'
        or (
          item.status = 'draft_created'
          and item.shopify_article_id = new.shopify_article_id
        )
      );

    if not found then
      raise exception 'content-plan state transition rejected'
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

revoke all on function orin_private.apply_content_plan_run_result()
  from public, anon, authenticated, orin_api, orin_worker;

create trigger runs_apply_content_plan_result
after insert on public.runs
for each row execute function orin_private.apply_content_plan_run_result();

with seed as (
  select *
  from jsonb_to_recordset($content_plan$[{"item_number":1,"target_date":"2026-05-19","cluster":"Seasonal / Gift Content","decision":"already_created","status":"draft_created","topic":"Hoverboard Gift Guide for Kids UK 2026","target_keyword":"hoverboard gift for kids","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-gift-guide-for-kids-uk.html","notes":"- Already created as hidden Shopify draft.\n- Keep as reference for ORIN format.\n- Do not duplicate.","shopify_article_id":null,"shopify_handle":null},{"item_number":2,"target_date":"2026-05-22","cluster":"Legal / Safety","decision":"already_created","status":"published_live","topic":"Hoverboard Laws UK 2026: Where You Can and Cannot Ride","target_keyword":"hoverboard laws UK","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-laws-uk-where-you-can-and-cannot-ride.html","notes":"- Already created and live.\n- FAQ schema fixed.\n- Do not create another broad hoverboard law article.","shopify_article_id":null,"shopify_handle":null},{"item_number":3,"target_date":"2026-05-25","cluster":"Buyer Guide / Product Comparison","decision":"needs_human_review","status":"needs_human_review","topic":"6.5 Inch vs 8.5 Inch Hoverboards: Which Size Should You Choose?","target_keyword":"6.5 inch vs 8.5 inch hoverboard","draft_path":"clients/hoverboard_store/content_engine/drafts/6-5-inch-vs-8-5-inch-hoverboards.html","notes":"- Check existing draft: Best Hoverboard Wheel Size Guide UK 2026.\n- If that draft is still in Shopify, do not create new. Mark needs_human_review.\n- Focus on buyer decision, wheel size, stability, child/adult suitability.\n- Do not invent speed, range, or weight claims.","shopify_article_id":null,"shopify_handle":null},{"item_number":4,"target_date":"2026-05-28","cluster":"Accessories / Support","decision":"create_new","status":"draft_created","topic":"Hoverboard Accessories Checklist for New Riders","target_keyword":"hoverboard accessories checklist","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-accessories-checklist-new-riders.html","notes":"- Safe support article.\n- Include helmet, pads, carry bag, charger care, storage.\n- Avoid safety guarantee claims.","shopify_article_id":null,"shopify_handle":null},{"item_number":5,"target_date":"2026-05-31","cluster":"Troubleshooting","decision":"create_new","status":"draft_created","topic":"Hoverboard Not Charging: Common Causes and Safe Checks","target_keyword":"hoverboard not charging","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-not-charging-causes-safe-checks.html","notes":"- Do not duplicate charging guide or battery guide.\n- Narrow troubleshooting article only.\n- Mention stop using if battery, charger, smell, heat, swelling, or damage appears.","shopify_article_id":null,"shopify_handle":null},{"item_number":6,"target_date":"2026-06-03","cluster":"Hoverkart","decision":"create_new","status":"draft_created","topic":"How to Choose a Hoverkart for a Child","target_keyword":"hoverkart for child","draft_path":"clients/hoverboard_store/content_engine/drafts/how-to-choose-hoverkart-for-child.html","notes":"- Avoid duplicating hoverkart safety and compatibility guides.\n- Focus on seat, frame, comfort, control, fit, supervision.\n- Do not invent age/weight limits.","shopify_article_id":null,"shopify_handle":null},{"item_number":7,"target_date":"2026-06-06","cluster":"Product / Collection Support","decision":"create_new","status":"draft_created","topic":"Beginner Hoverboards: What First-Time Buyers Should Check","target_keyword":"beginner hoverboard","draft_path":"clients/hoverboard_store/content_engine/drafts/beginner-hoverboards-first-time-buyers.html","notes":"- Do not duplicate \"How to Ride a Hoverboard for the First Time\".\n- Focus on buying checks, not riding tutorial.\n- Link to hoverboards collection.","shopify_article_id":null,"shopify_handle":null},{"item_number":8,"target_date":"2026-06-09","cluster":"Seasonal / Gift Content","decision":"create_new","status":"draft_created","topic":"Birthday Gift Ideas for Kids Who Like Ride-On Toys","target_keyword":"ride on gift ideas for kids","draft_path":"clients/hoverboard_store/content_engine/drafts/birthday-gift-ideas-kids-ride-on-toys.html","notes":"- Soft commercial article.\n- Include hoverboards, hoverkarts, kids scooters if relevant.\n- Avoid public-road or commuting claims.","shopify_article_id":null,"shopify_handle":null},{"item_number":9,"target_date":"2026-06-12","cluster":"Maintenance / Support","decision":"create_new","status":"draft_created","topic":"How to Clean a Hoverboard Safely","target_keyword":"how to clean a hoverboard","draft_path":"clients/hoverboard_store/content_engine/drafts/how-to-clean-a-hoverboard-safely.html","notes":"- Low duplicate risk.\n- Avoid waterproof claims unless verified.\n- Mention dry cloth, avoid water exposure, follow manufacturer instructions.","shopify_article_id":null,"shopify_handle":null},{"item_number":10,"target_date":"2026-06-15","cluster":"Hoverkart","decision":"create_new","status":"draft_created","topic":"Hoverkart Setup Guide for Beginners","target_keyword":"hoverkart setup guide","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverkart-setup-guide-beginners.html","notes":"- Practical setup article.\n- Avoid duplicating compatibility guide.\n- Explain checking straps, frame, seat, steering handles, and hoverboard fit.\n\n---\n\n# Queue Rule\n\nOnly planned jobs can be selected by queue reader.\n\nIf a planned job already exists in published_inventory.md or draft_inventory.md:\n- do not create it\n- mark as skipped_duplicate or needs_human_review","shopify_article_id":null,"shopify_handle":null},{"item_number":11,"target_date":"2026-06-18","cluster":"Troubleshooting","decision":"create_new","status":"draft_created","topic":"Hoverboard Beeping: Common Reasons and Safe Fixes","target_keyword":"hoverboard beeping","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-beeping-common-reasons-safe-fixes.html","notes":"- Troubleshooting only.\n- Avoid repair guarantees.\n- Mention stop using if burning smell, smoke, heat, swelling, or damage appears.","shopify_article_id":null,"shopify_handle":null},{"item_number":12,"target_date":"2026-06-21","cluster":"Buyer Guide","decision":"create_new","status":"draft_created","topic":"Best Hoverboards for Beginners UK: What to Look For","target_keyword":"best hoverboard for beginners uk","draft_path":"clients/hoverboard_store/content_engine/drafts/best-hoverboards-for-beginners-uk.html","notes":"- Buying guide, not riding tutorial.\n- Mention wheel size, safety features, battery care, warranty, and supervised use.","shopify_article_id":null,"shopify_handle":null},{"item_number":13,"target_date":"2026-06-24","cluster":"Safety / Support","decision":"create_new","status":"draft_created","topic":"Hoverboard Helmet and Safety Gear Guide for Kids","target_keyword":"hoverboard helmet safety gear","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-helmet-safety-gear-kids.html","notes":"- Safety-focused.\n- Do not claim legal permission for public areas.\n- Recommend helmet, pads, supervision, and suitable private space.","shopify_article_id":null,"shopify_handle":null},{"item_number":14,"target_date":"2026-06-27","cluster":"Hoverkart","decision":"create_new","status":"draft_created","topic":"Hoverkart vs Hoverboard: Which Is Better for Kids?","target_keyword":"hoverkart vs hoverboard","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverkart-vs-hoverboard-for-kids.html","notes":"- Compare use cases.\n- Avoid duplicate with existing hoverkart vs go kart article.\n- Focus on stability, control, supervision, and compatibility.","shopify_article_id":null,"shopify_handle":null},{"item_number":15,"target_date":"2026-06-30","cluster":"Maintenance","decision":"create_new","status":"draft_created","topic":"How to Store a Hoverboard Battery Safely","target_keyword":"hoverboard battery storage","draft_path":"clients/hoverboard_store/content_engine/drafts/how-to-store-hoverboard-battery-safely.html","notes":"- Battery care article.\n- Do not duplicate broad storage guide.\n- Mention cool dry storage, charging routine, and damage checks.\n- Shopify draft created: 2026-06-27. Article ID: 1006811971932. Handle: how-to-store-a-hoverboard-battery-safely-hoverboard-store.","shopify_article_id":"1006811971932","shopify_handle":"how-to-store-a-hoverboard-battery-safely-hoverboard-store"},{"item_number":16,"target_date":"2026-07-03","cluster":"Product / Collection Support","decision":"create_new","status":"draft_created","topic":"6.5 Inch vs 8.5 Inch Hoverboards for Kids: Simple Buying Guide","target_keyword":"6.5 inch vs 8.5 inch hoverboard kids","draft_path":"clients/hoverboard_store/content_engine/drafts/65-vs-85-inch-hoverboards-kids-guide.html","notes":"- Narrow buyer guide.\n- Do not duplicate Job 03 directly.\n- Compare beginner use, stability, surface suitability, and product fit.\n- Shopify draft created: 2026-06-27. Article ID: 1006814593372. Handle: 6-5-vs-8-5-inch-hoverboards-for-kids-simple-buying-guide-hoverboard-store.","shopify_article_id":"1006814593372","shopify_handle":"6-5-vs-8-5-inch-hoverboards-for-kids-simple-buying-guide-hoverboard-store"},{"item_number":17,"target_date":"2026-07-06","cluster":"Troubleshooting","decision":"create_new","status":"draft_created","topic":"Hoverboard Won't Turn On: Safe Checks Before You Replace It","target_keyword":"hoverboard wont turn on","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-wont-turn-on-safe-checks.html","notes":"- Troubleshooting only.\n- Avoid repair guarantees.\n- Mention charger, port, battery warning signs, and professional support.\n- Shopify draft created: 2026-06-28 00:18 BST. Article ID: 1006818689372. Handle: hoverboard-won-t-turn-on-safe-checks-before-you-replace-it.\n- Override reason: compliance, HTML quality, and duplicate check all passed. REVIEW NEEDED flags in duplicate checker were pre-existing inventory risks, not specific to Job 17. Operator override approved.\n- Backup: content_queue_3_months.md.bak.20260628-001804.","shopify_article_id":"1006818689372","shopify_handle":"hoverboard-won-t-turn-on-safe-checks-before-you-replace-it"},{"item_number":18,"target_date":"2026-07-09","cluster":"Buyer Guide","decision":"create_new","status":"draft_created","topic":"Hoverboard Weight Limit Guide for Parents","target_keyword":"hoverboard weight limit guide","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-weight-limit-guide-parents.html","notes":"- Do not invent specific limits.\n- Tell users to check product page and manufacturer guidance.\n- Link to relevant collection/product pages.\n- Shopify draft created: 2026-06-28 02:08 BST. Article ID: 1006819246428. Handle: hoverboard-weight-limit-guide-for-parents.\n- Passed compliance, HTML quality, and duplicate checks (Job 18 not flagged; global REVIEW NEEDED pairs are pre-existing site-health issues).\n- Backup: content_queue_3_months.md.bak.20260628-020820.","shopify_article_id":"1006819246428","shopify_handle":"hoverboard-weight-limit-guide-for-parents"},{"item_number":19,"target_date":"2026-07-12","cluster":"Seasonal / Gift Content","decision":"create_new","status":"draft_created","topic":"Christmas Hoverboard Gift Guide for Kids UK","target_keyword":"christmas hoverboard gift guide uk","draft_path":"clients/hoverboard_store/content_engine/drafts/christmas-hoverboard-gift-guide-for-kids.html","notes":"- Seasonal commercial article.\n- Avoid public-road claims.\n- Include hoverboards, hoverkarts, scooters only if relevant.\n- Shopify draft updated: 2026-06-28 16:55 BST. Article ID: 1006822064476. Handle: christmas-hoverboard-gift-guide-for-kids-uk.\n- Local improvements applied: softened delivery wording, softened bundle wording, improved learning curve wording, improved hoverkart bundle FAQ wording.\n- Compliance and HTML quality checks passed. Duplicate REVIEW NEEDED warnings are unrelated global site-health issues, not Job 19.\n- Passed current-job checks.\n- Backup: content_queue_3_months.md.bak.","shopify_article_id":"1006822064476","shopify_handle":"christmas-hoverboard-gift-guide-for-kids-uk"},{"item_number":20,"target_date":"2026-07-15","cluster":"Accessories / Support","decision":"create_new","status":"draft_created","topic":"Best Hoverboard Accessories for Safer Riding","target_keyword":"hoverboard accessories","draft_path":"clients/hoverboard_store/content_engine/drafts/best-hoverboard-accessories-safer-riding.html","notes":"- Avoid duplicating Job 04.\n- Focus on safety gear, carry bags, hoverkarts, chargers only if suitable.\n- Do not invent stock.\n- Phase 2F: Shopify draft created 2026-06-30 (manual early approval — draft only, NOT published).\n- Shopify article ID: 1006845985116\n- Shopify handle: best-hoverboard-accessories-safer-riding-uk-2026\n- Shopify blog: Journal Insights (blog_id: 113430790492)\n- published: false | published_at: null\n- Queue updated after confirmed Shopify draft creation.","shopify_article_id":"1006845985116","shopify_handle":"best-hoverboard-accessories-safer-riding-uk-2026"},{"item_number":21,"target_date":"2026-07-18","cluster":"Hoverkart","decision":"create_new","status":"needs_human_review","topic":"Hoverkart Compatibility Checklist Before You Buy","target_keyword":"hoverkart compatibility checklist","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverkart-compatibility-checklist-before-buy.html","notes":"- Practical checklist.\n- Mention wheel size compatibility, straps, frame, seat, and manufacturer guidance.\n- Avoid road-use claims.","shopify_article_id":null,"shopify_handle":null},{"item_number":22,"target_date":"2026-07-21","cluster":"Troubleshooting","decision":"create_new","status":"needs_human_review","topic":"Hoverboard Lights Flashing: What It Usually Means","target_keyword":"hoverboard lights flashing","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-lights-flashing-what-it-means.html","notes":"- Troubleshooting only.\n- Avoid technical claims unless verified.\n- Suggest checking manual and avoiding use if unsafe signs appear.","shopify_article_id":null,"shopify_handle":null},{"item_number":23,"target_date":"2026-07-24","cluster":"Buyer Guide","decision":"create_new","status":"draft_created","topic":null,"target_keyword":null,"draft_path":"clients/hoverboard_store/content_engine/drafts/are-hoverboards-good-gifts-8-12-year-olds.html","notes":"- Do not invent minimum age rules.\n- Explain suitability depends on model, supervision, confidence, and manufacturer guidance.","shopify_article_id":null,"shopify_handle":null},{"item_number":24,"target_date":"2026-07-27","cluster":"Safety / Support","decision":"create_new","status":"draft_created","topic":"Hoverboard Safety Checklist Before Every Ride","target_keyword":"hoverboard safety checklist","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-safety-checklist-before-every-ride.html","notes":"- Safety checklist only.\n- Avoid public-road permission claims.\n- Include battery, tyres, lights, charger, supervision, protective gear.","shopify_article_id":null,"shopify_handle":null},{"item_number":25,"target_date":"2026-07-30","cluster":"Product / Collection Support","decision":"create_new","status":"draft_created","topic":"How to Choose a Hoverboard for a Beginner Child","target_keyword":"hoverboard for beginner child","draft_path":"clients/hoverboard_store/content_engine/drafts/how-to-choose-hoverboard-beginner-child.html","notes":"- Buying guide.\n- Avoid duplicating Job 07.\n- Focus on parent decision points.","shopify_article_id":null,"shopify_handle":null},{"item_number":26,"target_date":"2026-08-02","cluster":"Maintenance","decision":"create_new","status":"draft_created","topic":"How to Keep a Hoverboard Clean Without Damaging It","target_keyword":"clean hoverboard without damaging","draft_path":"clients/hoverboard_store/content_engine/drafts/clean-hoverboard-without-damaging.html","notes":"- Maintenance article.\n- Avoid water exposure claims.\n- Mention dry cloth, gentle cleaning, charger port care, and manufacturer guidance.","shopify_article_id":null,"shopify_handle":null},{"item_number":27,"target_date":"2026-08-05","cluster":"Hoverkart","decision":"create_new","status":"draft_created","topic":"Hoverkart Safety Tips for First-Time Riders","target_keyword":"hoverkart safety tips","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverkart-safety-tips-first-time-riders.html","notes":"- Safety article.\n- Avoid duplicating broad hoverkart safety guide.\n- Focus on first session, supervision, straps, seat position, and space.","shopify_article_id":null,"shopify_handle":null},{"item_number":28,"target_date":"2026-08-08","cluster":"Troubleshooting","decision":"create_new","status":"draft_created","topic":"Hoverboard Charger Not Working: Checks Before Buying a New One","target_keyword":"hoverboard charger not working","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-charger-not-working-checks.html","notes":"- Troubleshooting only.\n- Mention compatible charger, port damage, warning signs, and stop-use conditions.","shopify_article_id":"1007164260700","shopify_handle":null},{"item_number":29,"target_date":"2026-08-11","cluster":"Seasonal / Gift Content","decision":"create_new","status":"draft_created","topic":"Birthday Hoverboard Gift Guide for Kids UK","target_keyword":"birthday hoverboard gift guide","draft_path":"clients/hoverboard_store/content_engine/drafts/birthday-hoverboard-gift-guide-kids-uk.html","notes":"- Commercial gift guide.\n- Avoid duplicate with ride-on toy article.\n- Include buyer checks, safety gear, and bundle suggestions.","shopify_article_id":"1007195390300","shopify_handle":null},{"item_number":30,"target_date":"2026-08-14","cluster":"Product / Collection Support","decision":"create_new","status":"draft_created","topic":"Hoverboard Bundle Buying Guide: Board, Kart and Safety Gear","target_keyword":"hoverboard bundle buying guide","draft_path":"clients/hoverboard_store/content_engine/drafts/hoverboard-bundle-buying-guide-board-kart-safety-gear.html","notes":"- Commercial collection support.\n- Link to hoverboard and hoverkart bundle collection.\n- Avoid public-road, pavement, or commuting claims.","shopify_article_id":"1007206334812","shopify_handle":null}]$content_plan$::jsonb) as item (
    item_number integer,
    target_date date,
    cluster text,
    decision text,
    status text,
    topic text,
    target_keyword text,
    draft_path text,
    notes text,
    shopify_article_id text,
    shopify_handle text
  )
)
insert into public.content_plan_items (
  client_id,
  item_number,
  target_date,
  cluster,
  decision,
  status,
  topic,
  target_keyword,
  draft_path,
  notes,
  shopify_article_id,
  shopify_handle,
  source_document,
  source_revision
)
select
  'hoverboard_store',
  seed.item_number,
  seed.target_date,
  seed.cluster,
  seed.decision,
  seed.status,
  seed.topic,
  seed.target_keyword,
  seed.draft_path,
  seed.notes,
  seed.shopify_article_id,
  seed.shopify_handle,
  'clients/hoverboard_store/content_engine/content_queue_3_months.md',
  '019511c51f6189b9d79e793d739cc70274b391e36c6566febf2e0d841c11abeb'
from seed;

with latest_reconciled as (
  select distinct on ((run.final_result ->> 'job_id')::integer)
    (run.final_result ->> 'job_id')::integer as item_number,
    run.run_id,
    run.shopify_article_id
  from public.runs run
  where run.client_id = 'hoverboard_store'
    and run.requested_mode = 'hidden-draft'
    and run.shopify_create_count = 1
    and not run.shopify_published
    and run.reconciliation_status = 'reconciled'
    and run.final_result ->> 'job_id' ~ '^[1-9][0-9]*$'
  order by (run.final_result ->> 'job_id')::integer, run.finished_at desc
)
update public.content_plan_items item
set status = 'draft_created',
    shopify_article_id = latest.shopify_article_id,
    last_run_id = latest.run_id
from latest_reconciled latest
where item.client_id = 'hoverboard_store'
  and item.item_number = latest.item_number;
