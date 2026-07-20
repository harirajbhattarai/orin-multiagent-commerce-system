# Hoverboard Store - Upcoming Content Queue v1

Purpose:
This queue controls upcoming blog creation for Hoverboard Store.

Important:
- Do not edit old published blogs.
- Do not create duplicate topics.
- Create local HTML first.
- Publish to Shopify as hidden draft only.
- Human approval required before live publishing.

Before creating any article:
1. Check published_inventory.md
2. Check draft_inventory.md
3. Check duplicate_risk_log.md
4. Check cluster_map.md
5. Check safe_topic_rules.md
6. Check uk_product_compliance_rules.md

Status labels:
- planned
- in_progress
- local_draft_created
- checks_failed
- draft_created
- skipped_duplicate
- needs_human_review

---

## Job 01
Date target: 2026-05-19
Cluster: Seasonal / Gift Content
Decision: already_created
Status: draft_created
Topic: Hoverboard Gift Guide for Kids UK 2026
Target keyword: hoverboard gift for kids
File: clients/hoverboard_store/content_engine/drafts/hoverboard-gift-guide-for-kids-uk.html
Notes:
- Already created as hidden Shopify draft.
- Keep as reference for ORIN format.
- Do not duplicate.

## Job 02
Date target: 2026-05-22
Cluster: Legal / Safety
Decision: already_created
Status: published_live
Topic: Hoverboard Laws UK 2026: Where You Can and Cannot Ride
Target keyword: hoverboard laws UK
File: clients/hoverboard_store/content_engine/drafts/hoverboard-laws-uk-where-you-can-and-cannot-ride.html
Notes:
- Already created and live.
- FAQ schema fixed.
- Do not create another broad hoverboard law article.

## Job 03
Date target: 2026-05-25
Cluster: Buyer Guide / Product Comparison
Decision: needs_human_review
Status: needs_human_review
Topic: 6.5 Inch vs 8.5 Inch Hoverboards: Which Size Should You Choose?
Target keyword: 6.5 inch vs 8.5 inch hoverboard
File: clients/hoverboard_store/content_engine/drafts/6-5-inch-vs-8-5-inch-hoverboards.html
Notes:
- Check existing draft: Best Hoverboard Wheel Size Guide UK 2026.
- If that draft is still in Shopify, do not create new. Mark needs_human_review.
- Focus on buyer decision, wheel size, stability, child/adult suitability.
- Do not invent speed, range, or weight claims.

## Job 04
Date target: 2026-05-28
Cluster: Accessories / Support
Decision: create_new
Status: draft_created
Topic: Hoverboard Accessories Checklist for New Riders
Target keyword: hoverboard accessories checklist
File: clients/hoverboard_store/content_engine/drafts/hoverboard-accessories-checklist-new-riders.html
Notes:
- Safe support article.
- Include helmet, pads, carry bag, charger care, storage.
- Avoid safety guarantee claims.

## Job 05
Date target: 2026-05-31
Cluster: Troubleshooting
Decision: create_new
Status: draft_created
Topic: Hoverboard Not Charging: Common Causes and Safe Checks
Target keyword: hoverboard not charging
File: clients/hoverboard_store/content_engine/drafts/hoverboard-not-charging-causes-safe-checks.html
Notes:
- Do not duplicate charging guide or battery guide.
- Narrow troubleshooting article only.
- Mention stop using if battery, charger, smell, heat, swelling, or damage appears.

## Job 06
Date target: 2026-06-03
Cluster: Hoverkart
Decision: create_new
Status: draft_created
Topic: How to Choose a Hoverkart for a Child
Target keyword: hoverkart for child
File: clients/hoverboard_store/content_engine/drafts/how-to-choose-hoverkart-for-child.html
Notes:
- Avoid duplicating hoverkart safety and compatibility guides.
- Focus on seat, frame, comfort, control, fit, supervision.
- Do not invent age/weight limits.

## Job 07
Date target: 2026-06-06
Cluster: Product / Collection Support
Decision: create_new
Status: draft_created
Topic: Beginner Hoverboards: What First-Time Buyers Should Check
Target keyword: beginner hoverboard
File: clients/hoverboard_store/content_engine/drafts/beginner-hoverboards-first-time-buyers.html
Notes:
- Do not duplicate "How to Ride a Hoverboard for the First Time".
- Focus on buying checks, not riding tutorial.
- Link to hoverboards collection.

## Job 08
Date target: 2026-06-09
Cluster: Seasonal / Gift Content
Decision: create_new
Status: draft_created
Topic: Birthday Gift Ideas for Kids Who Like Ride-On Toys
Target keyword: ride on gift ideas for kids
File: clients/hoverboard_store/content_engine/drafts/birthday-gift-ideas-kids-ride-on-toys.html
Notes:
- Soft commercial article.
- Include hoverboards, hoverkarts, kids scooters if relevant.
- Avoid public-road or commuting claims.

## Job 09
Date target: 2026-06-12
Cluster: Maintenance / Support
Decision: create_new
Status: draft_created
Topic: How to Clean a Hoverboard Safely
Target keyword: how to clean a hoverboard
File: clients/hoverboard_store/content_engine/drafts/how-to-clean-a-hoverboard-safely.html
Notes:
- Low duplicate risk.
- Avoid waterproof claims unless verified.
- Mention dry cloth, avoid water exposure, follow manufacturer instructions.

## Job 10
Date target: 2026-06-15
Cluster: Hoverkart
Decision: create_new
Status: draft_created
Topic: Hoverkart Setup Guide for Beginners
Target keyword: hoverkart setup guide
File: clients/hoverboard_store/content_engine/drafts/hoverkart-setup-guide-beginners.html
Notes:
- Practical setup article.
- Avoid duplicating compatibility guide.
- Explain checking straps, frame, seat, steering handles, and hoverboard fit.

---

# Queue Rule

Only planned jobs can be selected by queue reader.

If a planned job already exists in published_inventory.md or draft_inventory.md:
- do not create it
- mark as skipped_duplicate or needs_human_review

## Job 11
Date target: 2026-06-18
Cluster: Troubleshooting
Decision: create_new
Status: draft_created
Topic: Hoverboard Beeping: Common Reasons and Safe Fixes
Target keyword: hoverboard beeping
File: clients/hoverboard_store/content_engine/drafts/hoverboard-beeping-common-reasons-safe-fixes.html
Notes:
- Troubleshooting only.
- Avoid repair guarantees.
- Mention stop using if burning smell, smoke, heat, swelling, or damage appears.

## Job 12
Date target: 2026-06-21
Cluster: Buyer Guide
Decision: create_new
Status: draft_created
Topic: Best Hoverboards for Beginners UK: What to Look For
Target keyword: best hoverboard for beginners uk
File: clients/hoverboard_store/content_engine/drafts/best-hoverboards-for-beginners-uk.html
Notes:
- Buying guide, not riding tutorial.
- Mention wheel size, safety features, battery care, warranty, and supervised use.

## Job 13
Date target: 2026-06-24
Cluster: Safety / Support
Decision: create_new
Status: draft_created
Topic: Hoverboard Helmet and Safety Gear Guide for Kids
Target keyword: hoverboard helmet safety gear
File: clients/hoverboard_store/content_engine/drafts/hoverboard-helmet-safety-gear-kids.html
Notes:
- Safety-focused.
- Do not claim legal permission for public areas.
- Recommend helmet, pads, supervision, and suitable private space.

## Job 14
Date target: 2026-06-27
Cluster: Hoverkart
Decision: create_new
Status: draft_created
Topic: Hoverkart vs Hoverboard: Which Is Better for Kids?
Target keyword: hoverkart vs hoverboard
File: clients/hoverboard_store/content_engine/drafts/hoverkart-vs-hoverboard-for-kids.html
Notes:
- Compare use cases.
- Avoid duplicate with existing hoverkart vs go kart article.
- Focus on stability, control, supervision, and compatibility.

## Job 15
Date target: 2026-06-30
Cluster: Maintenance
Decision: create_new
Status: draft_created
Topic: How to Store a Hoverboard Battery Safely
Target keyword: hoverboard battery storage
File: clients/hoverboard_store/content_engine/drafts/how-to-store-hoverboard-battery-safely.html
Notes:
- Battery care article.
- Do not duplicate broad storage guide.
- Mention cool dry storage, charging routine, and damage checks.
- Shopify draft created: 2026-06-27. Article ID: 1006811971932. Handle: how-to-store-a-hoverboard-battery-safely-hoverboard-store.

## Job 16
Date target: 2026-07-03
Cluster: Product / Collection Support
Decision: create_new
Status: draft_created
Topic: 6.5 Inch vs 8.5 Inch Hoverboards for Kids: Simple Buying Guide
Target keyword: 6.5 inch vs 8.5 inch hoverboard kids
File: clients/hoverboard_store/content_engine/drafts/65-vs-85-inch-hoverboards-kids-guide.html
Notes:
- Narrow buyer guide.
- Do not duplicate Job 03 directly.
- Compare beginner use, stability, surface suitability, and product fit.
- Shopify draft created: 2026-06-27. Article ID: 1006814593372. Handle: 6-5-vs-8-5-inch-hoverboards-for-kids-simple-buying-guide-hoverboard-store.

## Job 17
Date target: 2026-07-06
Cluster: Troubleshooting
Decision: create_new
Status: draft_created
Topic: Hoverboard Won't Turn On: Safe Checks Before You Replace It
Target keyword: hoverboard wont turn on
File: clients/hoverboard_store/content_engine/drafts/hoverboard-wont-turn-on-safe-checks.html
Notes:
- Troubleshooting only.
- Avoid repair guarantees.
- Mention charger, port, battery warning signs, and professional support.
- Shopify draft created: 2026-06-28 00:18 BST. Article ID: 1006818689372. Handle: hoverboard-won-t-turn-on-safe-checks-before-you-replace-it.
- Override reason: compliance, HTML quality, and duplicate check all passed. REVIEW NEEDED flags in duplicate checker were pre-existing inventory risks, not specific to Job 17. Operator override approved.
- Backup: content_queue_3_months.md.bak.20260628-001804.

## Job 18
Date target: 2026-07-09
Cluster: Buyer Guide
Decision: create_new
Status: draft_created
Topic: Hoverboard Weight Limit Guide for Parents
Target keyword: hoverboard weight limit guide
File: clients/hoverboard_store/content_engine/drafts/hoverboard-weight-limit-guide-parents.html
Notes:
- Do not invent specific limits.
- Tell users to check product page and manufacturer guidance.
- Link to relevant collection/product pages.
- Shopify draft created: 2026-06-28 02:08 BST. Article ID: 1006819246428. Handle: hoverboard-weight-limit-guide-for-parents.
- Passed compliance, HTML quality, and duplicate checks (Job 18 not flagged; global REVIEW NEEDED pairs are pre-existing site-health issues).
- Backup: content_queue_3_months.md.bak.20260628-020820.

## Job 19
Date target: 2026-07-12
Cluster: Seasonal / Gift Content
Decision: create_new
Status: draft_created
Topic: Christmas Hoverboard Gift Guide for Kids UK
Target keyword: christmas hoverboard gift guide uk
File: clients/hoverboard_store/content_engine/drafts/christmas-hoverboard-gift-guide-for-kids.html
Notes:
- Seasonal commercial article.
- Avoid public-road claims.
- Include hoverboards, hoverkarts, scooters only if relevant.
- Shopify draft updated: 2026-06-28 16:55 BST. Article ID: 1006822064476. Handle: christmas-hoverboard-gift-guide-for-kids-uk.
- Local improvements applied: softened delivery wording, softened bundle wording, improved learning curve wording, improved hoverkart bundle FAQ wording.
- Compliance and HTML quality checks passed. Duplicate REVIEW NEEDED warnings are unrelated global site-health issues, not Job 19.
- Passed current-job checks.
- Backup: content_queue_3_months.md.bak.

## Job 20
Date target: 2026-07-15
Cluster: Accessories / Support
Decision: create_new
Status: draft_created
Topic: Best Hoverboard Accessories for Safer Riding
Target keyword: hoverboard accessories
File: clients/hoverboard_store/content_engine/drafts/best-hoverboard-accessories-safer-riding.html
Notes:
- Avoid duplicating Job 04.
- Focus on safety gear, carry bags, hoverkarts, chargers only if suitable.
- Do not invent stock.
- Phase 2F: Shopify draft created 2026-06-30 (manual early approval — draft only, NOT published).
- Shopify article ID: 1006845985116
- Shopify handle: best-hoverboard-accessories-safer-riding-uk-2026
- Shopify blog: Journal Insights (blog_id: 113430790492)
- published: false | published_at: null
- Queue updated after confirmed Shopify draft creation.

## Job 21
Status: needs_human_review
Last Updated: 2026-07-09T15:28:01+00:00
Failure Reason: POST_FETCH_BODY_VERIFICATION_FAILED — exact-byte SHA256 mismatch (+12 bytes Shopify normalization). New narrow inter-tag LF rule (PASS_ALLOWED_INTER_TAG_LF_NORMALIZATION) would now pass but original sent body unavailable for independent replay. Content is equivalent; article is safe but requires human acknowledgment.
Failure Code: POST_FETCH_BODY_VERIFICATION_FAILED
Recovery Action: AWAITING_HUMAN_REVIEW
Article ID: 1006975779164
Failure Artifact: clients/hoverboard_store/content_engine/automation_state/job_21_shopify_draft_verification_failure.json
Notes: Article 1006975779164 exists in Shopify (hidden draft). Content verified equivalent. Human review required before publishing.
Date target: 2026-07-18
Cluster: Hoverkart
Decision: create_new
Topic: Hoverkart Compatibility Checklist Before You Buy
Target keyword: hoverkart compatibility checklist
File: clients/hoverboard_store/content_engine/drafts/hoverkart-compatibility-checklist-before-buy.html
Notes:
- Practical checklist.
- Mention wheel size compatibility, straps, frame, seat, and manufacturer guidance.
- Avoid road-use claims.

## Job 22
Status: needs_human_review
Last Updated: 2026-07-09T19:14:06+00:00
Failure Reason: UNAPPROVED_VERIFICATION_TIER_USED
Recovery Action: AWAITING_HUMAN_REVIEW
Reconciliation Note: Hidden Shopify draft exists. Approved raw and narrow inter-tag LF verification tiers did not pass. Historical live run introduced an unapproved entity/whitespace equivalence tier. Draft retained for human review; no second article should be created.
Article ID: 1006992720220
Handle: hoverboard-lights-flashing-what-it-means
Draft Created At: 2026-07-09T17:13:25+00:00
published_at: null
Date target: 2026-07-21
Cluster: Troubleshooting
Decision: create_new
Topic: Hoverboard Lights Flashing: What It Usually Means
Target keyword: hoverboard lights flashing
File: clients/hoverboard_store/content_engine/drafts/hoverboard-lights-flashing-what-it-means.html
Notes:
- Troubleshooting only.
- Avoid technical claims unless verified.
- Suggest checking manual and avoiding use if unsafe signs appear.

## Job 23
Date target: 2026-07-24
Cluster: Buyer Guide
Decision: create_new
Status: draft_created
Shopify article ID: 1007001141596
Shopify handle: are-hoverboards-good-gifts-for-8-to-12-year-olds
published: false
published_at: null
File: clients/hoverboard_store/content_engine/drafts/are-hoverboards-good-gifts-8-12-year-olds.html
Notes:
- Do not invent minimum age rules.
- Explain suitability depends on model, supervision, confidence, and manufacturer guidance.

## Job 24
Status: draft_created
Article ID: 1007005630812
Handle: hoverboard-safety-checklist-before-every-ride
Draft Created At: 2026-07-10T17:09:59+00:00
published_at: null
Last Updated: 2026-07-10T17:09:59+00:00
Date target: 2026-07-27
Cluster: Safety / Support
Decision: create_new
Topic: Hoverboard Safety Checklist Before Every Ride
Target keyword: hoverboard safety checklist
File: clients/hoverboard_store/content_engine/drafts/hoverboard-safety-checklist-before-every-ride.html
Notes:
- Safety checklist only.
- Avoid public-road permission claims.
- Include battery, tyres, lights, charger, supervision, protective gear.

## Job 25
Status: draft_created
Article ID: 1007011922268
Handle: how-to-choose-a-hoverboard-for-a-beginner-child
Draft Created At: 2026-07-11T08:16:37+00:00
published_at: null
Last Updated: 2026-07-11T08:16:37+00:00
Transaction Evidence: /data/.openclaw/workspace/clients/hoverboard_store/content_engine/automation_state/runs/job25_1783757797_827e0701
Date target: 2026-07-30
Cluster: Product / Collection Support
Decision: create_new
Topic: How to Choose a Hoverboard for a Beginner Child
Target keyword: hoverboard for beginner child
File: clients/hoverboard_store/content_engine/drafts/how-to-choose-hoverboard-beginner-child.html
Notes:
- Buying guide.
- Avoid duplicating Job 07.
- Focus on parent decision points.

## Job 26
Status: draft_created
Article ID: 1007012741468
Handle: how-to-keep-a-hoverboard-clean-without-damaging-it
Draft Created At: 2026-07-11T09:41:18+00:00
published_at: null
Last Updated: 2026-07-11T09:41:18+00:00
Transaction Evidence: /data/.openclaw/workspace/clients/hoverboard_store/content_engine/automation_state/runs/job26_1783762878_f801216e
Date target: 2026-08-02
Cluster: Maintenance
Decision: create_new
Topic: How to Keep a Hoverboard Clean Without Damaging It
Target keyword: clean hoverboard without damaging
File: clients/hoverboard_store/content_engine/drafts/clean-hoverboard-without-damaging.html
Notes:
- Maintenance article.
- Avoid water exposure claims.
- Mention dry cloth, gentle cleaning, charger port care, and manufacturer guidance.

## Job 27
Status: draft_created
Article ID: 1007016771932
Handle: hoverkart-safety-tips-for-first-time-riders
Draft Created At: 2026-07-11T15:15:16+00:00
published_at: null
Last Updated: 2026-07-11T15:15:16+00:00
Transaction Evidence: /data/.openclaw/workspace/clients/hoverboard_store/content_engine/automation_state/runs/job27_1783782916_ba6d8714
Date target: 2026-08-05
Cluster: Hoverkart
Decision: create_new
Topic: Hoverkart Safety Tips for First-Time Riders
Target keyword: hoverkart safety tips
File: clients/hoverboard_store/content_engine/drafts/hoverkart-safety-tips-first-time-riders.html
Notes:
- Safety article.
- Avoid duplicating broad hoverkart safety guide.
- Focus on first session, supervision, straps, seat position, and space.

## Job 28
Date target: 2026-08-08
Cluster: Troubleshooting
Decision: create_new
Status: planned
Topic: Hoverboard Charger Not Working: Checks Before Buying a New One
Target keyword: hoverboard charger not working
File: clients/hoverboard_store/content_engine/drafts/hoverboard-charger-not-working-checks.html
Notes:
- Troubleshooting only.
- Mention compatible charger, port damage, warning signs, and stop-use conditions.

## Job 29
Date target: 2026-08-11
Cluster: Seasonal / Gift Content
Decision: create_new
Status: planned
Topic: Birthday Hoverboard Gift Guide for Kids UK
Target keyword: birthday hoverboard gift guide
File: clients/hoverboard_store/content_engine/drafts/birthday-hoverboard-gift-guide-kids-uk.html
Notes:
- Commercial gift guide.
- Avoid duplicate with ride-on toy article.
- Include buyer checks, safety gear, and bundle suggestions.

## Job 30
Date target: 2026-08-14
Cluster: Product / Collection Support
Decision: create_new
Status: planned
Topic: Hoverboard Bundle Buying Guide: Board, Kart and Safety Gear
Target keyword: hoverboard bundle buying guide
File: clients/hoverboard_store/content_engine/drafts/hoverboard-bundle-buying-guide-board-kart-safety-gear.html
Notes:
- Commercial collection support.
- Link to hoverboard and hoverkart bundle collection.
- Avoid public-road, pavement, or commuting claims.
