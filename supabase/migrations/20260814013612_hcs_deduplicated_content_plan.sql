-- Seed the first authoritative HCS plan only while every execution and
-- Shopify gate is closed. The migration is intentionally a no-op on fresh
-- schema environments where the GUI-provisioned HCS tenant does not exist.

create unique index if not exists content_plan_items_global_keyword_identity_idx
on public.content_plan_items (
  btrim(lower(regexp_replace(target_keyword, '[^[:alnum:]]+', ' ', 'g')))
)
where target_keyword is not null and btrim(target_keyword) <> '';

do $migration$
declare
  v_existing_count integer;
  v_inserted_count integer;
  v_source_document constant text := 'docs/HCS_CONTENT_PLAN.md';
  v_source_revision constant text := 'a7d335cb18098c338ed1285f525d90a4eae42f8ede9294570335321c36653029';
begin
  if not exists (
    select 1 from public.clients client where client.client_id = 'hcs_gadgets'
  ) then
    raise notice 'hcs_gadgets is not provisioned; content-plan seed skipped';
    return;
  end if;

  if not exists (
    select 1
    from public.clients client
    join public.client_runtime_settings settings using (client_id)
    where client.client_id = 'hcs_gadgets'
      and client.status = 'maintenance'
      and not settings.request_intake_enabled
      and not settings.automation_enabled
      and not settings.shopify_writes_enabled
      and not settings.approved_draft_writes_enabled
      and settings.allowed_mode = 'dry-run'
  ) then
    raise exception 'HCS content plan can only be seeded with every execution and Shopify gate closed'
      using errcode = '55000';
  end if;

  select count(*) into v_existing_count
  from public.content_plan_items item
  where item.client_id = 'hcs_gadgets';

  if v_existing_count > 0 then
    if v_existing_count = 30 and not exists (
      select 1
      from public.content_plan_items item
      where item.client_id = 'hcs_gadgets'
        and (
          item.source_document is distinct from v_source_document
          or item.source_revision is distinct from v_source_revision
        )
    ) then
      return;
    end if;

    raise exception 'HCS already has a different or partial content plan; refusing to merge automatically'
      using errcode = '23505';
  end if;

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
    source_document,
    source_revision
  )
  select
    'hcs_gadgets',
    plan.item_number,
    plan.target_date,
    plan.cluster,
    'create_new',
    'planned',
    plan.topic,
    plan.target_keyword,
    'clients/hcs_gadgets/content_engine/drafts/' || plan.slug || '.html',
    'Accepted by the 2026-08-14 cross-tenant intent audit. Verify all current HCS product facts, compatibility, availability, specifications and safety claims before drafting.',
    v_source_document,
    v_source_revision
  from jsonb_to_recordset($hcs_plan$[
    {"item_number":1,"target_date":"2026-08-28","cluster":"Adult scooters / Buyer education","topic":"Adult Electric Scooter Suspension: What UK Buyers Should Compare","target_keyword":"adult electric scooter suspension guide","slug":"adult-electric-scooter-suspension-uk-buyers-guide"},
    {"item_number":2,"target_date":"2026-08-31","cluster":"Adult scooters / Product education","topic":"Electric Scooter IP Ratings and Water Resistance Explained","target_keyword":"electric scooter IP rating explained","slug":"electric-scooter-ip-ratings-water-resistance-explained"},
    {"item_number":3,"target_date":"2026-09-03","cluster":"Adult scooters / Feature guide","topic":"App-Enabled Electric Scooters: Useful Features, Privacy and Setup Checks","target_keyword":"app enabled electric scooter features","slug":"app-enabled-electric-scooters-features-privacy-setup"},
    {"item_number":4,"target_date":"2026-09-06","cluster":"Adult scooters / Maintenance","topic":"Electric Scooter Folding Mechanisms: Safety Checks Before Every Fold","target_keyword":"electric scooter folding mechanism checks","slug":"electric-scooter-folding-mechanism-safety-checks"},
    {"item_number":5,"target_date":"2026-09-09","cluster":"Adult scooters / Fit guide","topic":"Electric Scooter Deck Size and Riding Position: Comfort Checks for Adults","target_keyword":"electric scooter deck size for adults","slug":"electric-scooter-deck-size-riding-position-adults"},
    {"item_number":6,"target_date":"2026-09-12","cluster":"Adult scooters / Safety features","topic":"Electric Scooter Lights and Reflectors: Visibility Features to Compare","target_keyword":"electric scooter lights and reflectors","slug":"electric-scooter-lights-reflectors-visibility-features"},
    {"item_number":7,"target_date":"2026-09-15","cluster":"Adult scooters / Maintenance","topic":"Adult Electric Scooter Maintenance Schedule: Weekly and Monthly Checks","target_keyword":"adult electric scooter maintenance schedule","slug":"adult-electric-scooter-maintenance-schedule"},
    {"item_number":8,"target_date":"2026-09-18","cluster":"Kids scooters / Comparison","topic":"3-Wheel Push Scooter vs Kids Electric Scooter: A Parent's Comparison","target_keyword":"3 wheel scooter vs electric scooter kids","slug":"3-wheel-push-scooter-vs-kids-electric-scooter"},
    {"item_number":9,"target_date":"2026-09-21","cluster":"Kids ride-ons / Comparison","topic":"Kids Electric Motorcycle vs Electric Scooter: Which Ride-On Fits?","target_keyword":"kids electric motorcycle vs scooter","slug":"kids-electric-motorcycle-vs-electric-scooter"},
    {"item_number":10,"target_date":"2026-09-24","cluster":"Kids scooters / Feature guide","topic":"Speed Modes on Kids Electric Scooters: What Parents Should Check","target_keyword":"kids electric scooter speed modes","slug":"kids-electric-scooter-speed-modes-parent-guide"},
    {"item_number":11,"target_date":"2026-09-27","cluster":"Kids scooters / Product comparison","topic":"Revix Nova S150 vs X1 Kids Electric Scooter: Parent Buying Checks","target_keyword":"Revix Nova S150 vs X1 scooter","slug":"revix-nova-s150-vs-x1-kids-electric-scooter"},
    {"item_number":12,"target_date":"2026-09-30","cluster":"Kids ride-ons / Product comparison","topic":"Evercross EV12M vs RCB R9X Kids Electric Motorcycle: What to Compare","target_keyword":"Evercross EV12M vs RCB R9X","slug":"evercross-ev12m-vs-rcb-r9x-kids-electric-motorcycle"},
    {"item_number":13,"target_date":"2026-10-03","cluster":"Hoverkarts / Product comparison","topic":"R1 vs R2 Hoverkart Seats: Fit, Suspension and Buyer Checks","target_keyword":"R1 vs R2 hoverkart seat","slug":"r1-vs-r2-hoverkart-seats-comparison"},
    {"item_number":14,"target_date":"2026-10-06","cluster":"Hoverkarts / Buyer guide","topic":"Dual-Seat Hoverkarts: Space, Supervision and Setup Questions","target_keyword":"dual seat hoverkart buying guide","slug":"dual-seat-hoverkart-buying-guide"},
    {"item_number":15,"target_date":"2026-10-09","cluster":"Hoverkarts / Parts support","topic":"Hoverkart Replacement Wheel: How to Identify Wear and Correct Fit","target_keyword":"hoverkart replacement wheel guide","slug":"hoverkart-replacement-wheel-wear-fit-guide"},
    {"item_number":16,"target_date":"2026-10-12","cluster":"Hoverkarts / Parts support","topic":"Hoverkart Assembly Screw Kits: When Fasteners Need Replacement","target_keyword":"hoverkart replacement screw kit","slug":"hoverkart-assembly-screw-kit-fastener-replacement"},
    {"item_number":17,"target_date":"2026-10-15","cluster":"Hoverkarts / Maintenance","topic":"Hoverkart Replacement Parts Checklist: Wheels, Straps and Fasteners","target_keyword":"hoverkart replacement parts checklist","slug":"hoverkart-replacement-parts-checklist"},
    {"item_number":18,"target_date":"2026-10-18","cluster":"Hoverkarts / Fit support","topic":"How to Measure a Hoverkart Frame Before Ordering Replacement Parts","target_keyword":"measure hoverkart frame for parts","slug":"measure-hoverkart-frame-replacement-parts"},
    {"item_number":19,"target_date":"2026-10-21","cluster":"Hoverboards / Product comparison","topic":"G1 Lite vs Revix RX2: 6.5-Inch Hoverboard Comparison","target_keyword":"G1 Lite vs Revix RX2 hoverboard","slug":"g1-lite-vs-revix-rx2-hoverboard-comparison"},
    {"item_number":20,"target_date":"2026-10-24","cluster":"Hoverboards / Product guide","topic":"Revix RX1 8.5-Inch Off-Road Hoverboard: Buyer Fit and Checks","target_keyword":"Revix RX1 off road hoverboard guide","slug":"revix-rx1-off-road-hoverboard-buyer-guide"},
    {"item_number":21,"target_date":"2026-10-27","cluster":"Hoverboards / Buyer support","topic":"Refurbished Hoverboards: Condition, Battery and Warranty Checklist","target_keyword":"refurbished hoverboard buying checklist","slug":"refurbished-hoverboard-condition-battery-warranty-checklist"},
    {"item_number":22,"target_date":"2026-10-30","cluster":"Hoverboards / Parts support","topic":"Hoverboard Replacement Battery Compatibility: Voltage, Connector and Safety Checks","target_keyword":"hoverboard replacement battery compatibility","slug":"hoverboard-replacement-battery-compatibility-guide"},
    {"item_number":23,"target_date":"2026-11-02","cluster":"Hoverboards / Accessories","topic":"Choosing a Carry Bag for a 6.5-Inch Hoverboard: Fit and Protection","target_keyword":"6.5 inch hoverboard carry bag","slug":"choosing-6-5-inch-hoverboard-carry-bag"},
    {"item_number":24,"target_date":"2026-11-05","cluster":"Floor care / Comparison","topic":"Spin Mop vs Spray Mop: Which Floor-Cleaning System Fits Your Home?","target_keyword":"spin mop vs spray mop","slug":"spin-mop-vs-spray-mop-comparison"},
    {"item_number":25,"target_date":"2026-11-08","cluster":"Home heating / Comparison","topic":"Portable Ceramic Heater vs Electric Fireplace Heater: What to Compare","target_keyword":"ceramic heater vs electric fireplace heater","slug":"ceramic-heater-vs-electric-fireplace-heater"},
    {"item_number":26,"target_date":"2026-11-11","cluster":"Home fragrance / Product education","topic":"Waterless Essential Oil Diffusers: How They Work and Where They Fit","target_keyword":"waterless essential oil diffuser guide","slug":"waterless-essential-oil-diffuser-guide"},
    {"item_number":27,"target_date":"2026-11-14","cluster":"Kitchen storage / Buyer guide","topic":"Ceramic Canister Sets: Airtight Lids, Counter Space and Care","target_keyword":"ceramic canister set buying guide","slug":"ceramic-canister-set-buying-guide"},
    {"item_number":28,"target_date":"2026-11-17","cluster":"Home cooling / Comparison","topic":"Portable Air Cooler vs Pedestal Fan: Which Fits a UK Room?","target_keyword":"portable air cooler vs pedestal fan","slug":"portable-air-cooler-vs-pedestal-fan"},
    {"item_number":29,"target_date":"2026-11-20","cluster":"Family games / Comparison","topic":"Magnetic Dartboard vs Soft-Tip Dartboard: A Family Buying Guide","target_keyword":"magnetic vs soft tip dartboard","slug":"magnetic-vs-soft-tip-dartboard-family-guide"},
    {"item_number":30,"target_date":"2026-11-23","cluster":"Fitness and recovery / Buyer guide","topic":"Portable Ice Bath Tubs: Capacity, Setup and Care Checks","target_keyword":"portable ice bath tub buying guide","slug":"portable-ice-bath-tub-capacity-setup-care"}
  ]$hcs_plan$::jsonb) as plan (
    item_number integer,
    target_date date,
    cluster text,
    topic text,
    target_keyword text,
    slug text
  );

  get diagnostics v_inserted_count = row_count;
  if v_inserted_count <> 30 then
    raise exception 'expected to seed 30 HCS content items, inserted %', v_inserted_count
      using errcode = '23514';
  end if;
end
$migration$;
