# HCS Gadgets deduplicated content plan

## Purpose

This is the first database-owned content plan for `hcs_gadgets`. It is designed
to give HCS a distinct search footprint without copying the Hoverboard Store
library or recreating HCS articles that are already live.

The plan is content intake only. Seeding it must not activate a client,
scheduler, worker, request intake, automation, or either Shopify write gate.

## Audit inputs

The deduplication audit was completed on 2026-08-14 against:

- the live HCS Shopify blog sitemap: 34 article URLs;
- the live HCS Shopify product sitemap: 86 readable product URLs;
- the live HCS collection sitemap: 14 collection URLs;
- all 60 authoritative Hoverboard Store plan records in Supabase;
- the legacy six-item HCS Markdown queue, including two live articles and one
  existing unpublished Shopify draft; and
- the onboarding scope stored for `hcs_gadgets` in Supabase.

Exact normalized topic identity is also protected by the global database unique
index. The audit additionally rejects near-duplicate intent even where wording
is different.

## Rejected overlap

The following legacy or obvious ideas are intentionally excluded:

- broad useful-gadget and under-£50 roundups, because HCS already has broad
  useful-gadget and seasonal gift articles;
- generic household-gadget online-buying checklists, because they overlap each
  other and the existing broad HCS guides;
- hoverboard law, beginner, safety, battery-life, beeping, wet-weather,
  certification, price, and wheel-size guides, because HCS or Hoverboard Store
  already covers those intents;
- generic kids-electric-scooter buying, fit, tyre, storage, brake, range, and
  teenager guides, because Hoverboard Store items 31-38 own those intents; and
- generic hoverkart compatibility, setup, strap, seating, steering, and storage
  guides, because Hoverboard Store already owns those intents.

## Accepted 30-item plan

Target dates are spaced three days apart. Item 1 has an expected-draft date of
2026-08-14, allowing a controlled dry-run after HCS commissioning. No item may
contact Shopify without a later exact-version human approval and separately
opened unpublished-draft gates.

| # | Target date | Cluster | Topic | Target keyword |
|---:|:---|:---|:---|:---|
| 1 | 2026-08-28 | Adult scooters / Buyer education | Adult Electric Scooter Suspension: What UK Buyers Should Compare | adult electric scooter suspension guide |
| 2 | 2026-08-31 | Adult scooters / Product education | Electric Scooter IP Ratings and Water Resistance Explained | electric scooter IP rating explained |
| 3 | 2026-09-03 | Adult scooters / Feature guide | App-Enabled Electric Scooters: Useful Features, Privacy and Setup Checks | app enabled electric scooter features |
| 4 | 2026-09-06 | Adult scooters / Maintenance | Electric Scooter Folding Mechanisms: Safety Checks Before Every Fold | electric scooter folding mechanism checks |
| 5 | 2026-09-09 | Adult scooters / Fit guide | Electric Scooter Deck Size and Riding Position: Comfort Checks for Adults | electric scooter deck size for adults |
| 6 | 2026-09-12 | Adult scooters / Safety features | Electric Scooter Lights and Reflectors: Visibility Features to Compare | electric scooter lights and reflectors |
| 7 | 2026-09-15 | Adult scooters / Maintenance | Adult Electric Scooter Maintenance Schedule: Weekly and Monthly Checks | adult electric scooter maintenance schedule |
| 8 | 2026-09-18 | Kids scooters / Comparison | 3-Wheel Push Scooter vs Kids Electric Scooter: A Parent's Comparison | 3 wheel scooter vs electric scooter kids |
| 9 | 2026-09-21 | Kids ride-ons / Comparison | Kids Electric Motorcycle vs Electric Scooter: Which Ride-On Fits? | kids electric motorcycle vs scooter |
| 10 | 2026-09-24 | Kids scooters / Feature guide | Speed Modes on Kids Electric Scooters: What Parents Should Check | kids electric scooter speed modes |
| 11 | 2026-09-27 | Kids scooters / Product comparison | Revix Nova S150 vs X1 Kids Electric Scooter: Parent Buying Checks | Revix Nova S150 vs X1 scooter |
| 12 | 2026-09-30 | Kids ride-ons / Product comparison | Evercross EV12M vs RCB R9X Kids Electric Motorcycle: What to Compare | Evercross EV12M vs RCB R9X |
| 13 | 2026-10-03 | Hoverkarts / Product comparison | R1 vs R2 Hoverkart Seats: Fit, Suspension and Buyer Checks | R1 vs R2 hoverkart seat |
| 14 | 2026-10-06 | Hoverkarts / Buyer guide | Dual-Seat Hoverkarts: Space, Supervision and Setup Questions | dual seat hoverkart buying guide |
| 15 | 2026-10-09 | Hoverkarts / Parts support | Hoverkart Replacement Wheel: How to Identify Wear and Correct Fit | hoverkart replacement wheel guide |
| 16 | 2026-10-12 | Hoverkarts / Parts support | Hoverkart Assembly Screw Kits: When Fasteners Need Replacement | hoverkart replacement screw kit |
| 17 | 2026-10-15 | Hoverkarts / Maintenance | Hoverkart Replacement Parts Checklist: Wheels, Straps and Fasteners | hoverkart replacement parts checklist |
| 18 | 2026-10-18 | Hoverkarts / Fit support | How to Measure a Hoverkart Frame Before Ordering Replacement Parts | measure hoverkart frame for parts |
| 19 | 2026-10-21 | Hoverboards / Product comparison | G1 Lite vs Revix RX2: 6.5-Inch Hoverboard Comparison | G1 Lite vs Revix RX2 hoverboard |
| 20 | 2026-10-24 | Hoverboards / Product guide | Revix RX1 8.5-Inch Off-Road Hoverboard: Buyer Fit and Checks | Revix RX1 off road hoverboard guide |
| 21 | 2026-10-27 | Hoverboards / Buyer support | Refurbished Hoverboards: Condition, Battery and Warranty Checklist | refurbished hoverboard buying checklist |
| 22 | 2026-10-30 | Hoverboards / Parts support | Hoverboard Replacement Battery Compatibility: Voltage, Connector and Safety Checks | hoverboard replacement battery compatibility |
| 23 | 2026-11-02 | Hoverboards / Accessories | Choosing a Carry Bag for a 6.5-Inch Hoverboard: Fit and Protection | 6.5 inch hoverboard carry bag |
| 24 | 2026-11-05 | Floor care / Comparison | Spin Mop vs Spray Mop: Which Floor-Cleaning System Fits Your Home? | spin mop vs spray mop |
| 25 | 2026-11-08 | Home heating / Comparison | Portable Ceramic Heater vs Electric Fireplace Heater: What to Compare | ceramic heater vs electric fireplace heater |
| 26 | 2026-11-11 | Home fragrance / Product education | Waterless Essential Oil Diffusers: How They Work and Where They Fit | waterless essential oil diffuser guide |
| 27 | 2026-11-14 | Kitchen storage / Buyer guide | Ceramic Canister Sets: Airtight Lids, Counter Space and Care | ceramic canister set buying guide |
| 28 | 2026-11-17 | Home cooling / Comparison | Portable Air Cooler vs Pedestal Fan: Which Fits a UK Room? | portable air cooler vs pedestal fan |
| 29 | 2026-11-20 | Family games / Comparison | Magnetic Dartboard vs Soft-Tip Dartboard: A Family Buying Guide | magnetic vs soft tip dartboard |
| 30 | 2026-11-23 | Fitness and recovery / Buyer guide | Portable Ice Bath Tubs: Capacity, Setup and Care Checks | portable ice bath tub buying guide |

## Content safeguards

- Verify every model, compatibility, price, specification, stock statement, and
  collection link against the current HCS catalogue during the run.
- Do not infer road legality, age limits, speed, range, weight capacity,
  waterproofing, certification, health outcomes, or safety guarantees.
- Product comparisons must describe verified differences, not declare a
  universal winner.
- Maintenance content must direct readers to the exact manufacturer guidance
  and professional support where inspection or repair is required.
- Every draft remains unpublished and requires exact-version approval before
  the separately gated Shopify draft step.
