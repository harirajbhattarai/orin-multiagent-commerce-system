# HCS Gadgets — 3-Month Content Strategy Method

**Version:** 1.0 draft
**Date:** 2026-07-03
**Status:** DRAFT — For review before queue finalisation

---

## Context

The existing HCS content queue was built before HCS Gadgets' real Shopify product catalogue was audited. As a result:

- Job 02 (BBQ Accessories) was written for a generic BBQ e-commerce store, not HCS's actual product range
- Internal links pointed to non-existent collections (`bbq-garden`, `home-and-garden`, `outdoor-living`)
- No product truth verification was done before drafting

This document establishes the correct method for planning HCS content going forward.

---

## The Core Principle

**Plan from the product catalogue, not from keyword theory.**

Before any article topic is added to the queue, verify that:
1. HCS sells products relevant to the topic
2. Verified collection URLs exist for internal linking
3. The topic angle can be supported by real HCS product data

If any of these fail, the topic must be **rejected, reframed, or replaced.**

---

## HCS Product Truth Baseline (as of 2026-07-03)

### What HCS Actually Sells

| Cluster | Real Products | Valid Collections |
|---------|--------------|-------------------|
| Hoverboards | 6 products (6.5" Chrome, G1 Lite) | `hoverboards-for-kids-adults`, `hoverboard-bundles` |
| Hoverkarts | 8 products (multiple colours) | `hoverkarts` |
| Hoverboard Bundles | 1 product (G1 Pro + Hoverkart) | `hoverboard-bundles` |
| Electric Scooters (Kids) | 7 products (Evercross, X1, X2, Midnight) | `kids-e-scooters` |
| Electric Scooters (Adult) | 2 products (EV10K Pro, H7) | `adult-e-scooters` |
| Gadgets | 4 products (shaker, jump rope, mask, bag) | `gadgets` |
| Outdoor/Garden | Ice bath, BBQ grill, BBQ chimney, space heater, heated throw | `sports-outdoor`, `home-garden` |
| Home Decor | Ceramic bathroom accessories, mops | `home-garden` |
| Wax Melts | Aroma Haven (multiple variants) | `gadgets` or `new-arrivals` |
| Electric Bikes | Evercross EK30 | `e-scooters` |
| Kids Motorcycles | RCB R9X (Blue, Green, Red) | `kids-e-scooters` |

### What HCS Does NOT Sell

- Generic BBQ accessories (tongs, thermometers, grill brushes, covers) — only 2 BBQ products exist
- Full garden furniture range
- Clothing or lifestyle products
- Generic "home gadgets" as a broad category

---

## Content Cadence

| Parameter | Value |
|-----------|-------|
| Shopify draft frequency | 1 draft every 4 days |
| Approximate monthly output | ~7 drafts |
| 3-month target | 20–22 draft articles |
| Publishing | Manual only — no automatic publishing |
| Review gate | Product truth check before every draft |

---

## Queue Rhythm

The `content_queue_3_months.md` file is the source of truth for rhythm.

**Queue controls the cadence:**
- A job becomes active when its date target is reached or when explicitly approved
- A daily check (manual or cron) reads the queue and identifies the next due job
- Only one job is active at a time
- After a draft is created and validated, the queue status is updated before moving to the next job

**Cron (future, not yet enabled):**
- Daily check: read queue, identify next due job, send a notification
- Cron does NOT create drafts automatically
- Cron does NOT publish
- Human operator triggers each step

---

## Cluster Planning Method

Clusters should be built from the **verified product catalogue**, not from generic topic clusters.

### Step 1 — Identify the Product Cluster

Look at `product_catalog.json` and `collections_inventory.json`. Identify a product cluster with:
- At least 3 related products, OR
- A valid collection with a URL, OR
- A coherent buyer intent that matches HCS products

### Step 2 — Check Product Truth

For each proposed article topic in the cluster:
- Does HCS sell products relevant to this topic?
- Are the collection URLs valid?
- Can the article recommend specific HCS products?
- If not, can it be reframed as general educational content?

### Step 3 — Verify Internal Link Opportunities

Before writing, check:
- Does a published article already exist that can link to this new article?
- Does the new article have valid collection URLs to link to?
- Are there product-specific URLs to include?

### Step 4 — Add to Queue with Notes

Each queue entry must include:
- Product verification note (e.g., "3 HCS hoverboard products confirmed")
- Collection URLs to use (from `hcs_verified_link_map.json`)
- Any topic reframing required

---

## Cluster Priorities for Next 3 Months

Based on the verified product catalogue, the following clusters are available:

### Tier 1 — Strong HCS Product Match

| Cluster | Products | Articles possible |
|---------|---------|------------------|
| Hoverboards & Safety | 6 hoverboards | 3–4 (safety, buying guide, comparison, kids) |
| Hoverkarts & Bundles | 8 hoverkarts + 1 bundle | 2–3 (what is a hoverkart, bundle vs separate) |
| Kids Electric Scooters | 7 products | 2–3 (safety, buying guide, age guide) |
| Adult Electric Scooters | 2 products | 1–2 (choosing, safety) |

### Tier 2 — Partial Match (need reframing)

| Cluster | Products | Articles possible |
|---------|---------|------------------|
| Gadgets | 4 products (shaker, rope, mask, bag) | 1–2 (use as examples, not product roundup) |
| Home & Garden | Ice bath, BBQ grill, BBQ chimney, ceramics, heaters | 2–3 (general educational, not product-specific roundup) |
| Wax Melts / Aroma | Aroma Haven variants | 1 (if lifestyle content is approved) |

### Tier 3 — Requires Rejection or Replacement

| Proposed topic | Issue | Recommended action |
|---------------|-------|-------------------|
| Generic BBQ accessories buying guide | HCS only sells 2 BBQ products | Replace with "Outdoor gadget finds for UK summer" scoped to real HCS products |
| Generic home gadgets roundup | 60 uncategorised products, not all are gadgets | Reframe per sub-category |
| Hoverboard-only articles | HCS already has 35 published hoverboard articles | Avoid over-producing hoverboard content |

---

## Anti-Patterns to Avoid

- **Do not** plan articles around product categories HCS does not sell
- **Do not** create generic buying guide templates and apply them to HCS without verifying the products exist
- **Do not** link to collection handles that are not in `collections_inventory.json`
- **Do not** use `/collections/all` — it does not exist; use `/collections/all-product`
- **Do not** over-produce hoverboard content — HCS already has significant hoverboard coverage
- **Do not** queue articles faster than they can be verified — the 4-day cadence is a maximum, not a minimum

---

## Publishing Rules

- Every draft requires a product truth check before it is marked ready for publishing
- Publishing is always manual — human operator reviews and publishes
- No article may be published with broken links or non-existent collection URLs
- If a product truth issue is found in a live article, it must be flagged and fixed before the article is updated

---

## Queue File Format

Each job in `content_queue_3_months.md` must include:

```
## Job XX
Date target: YYYY-MM-DD
Cluster: [from product catalogue]
Decision: create_new | replace | reject
Status: planned | draft_created | review_needed | published_live
Topic: [specific, product-grounded]
Target keyword: [verified keyword]
File: clients/hcs_gadgets/content_engine/drafts/[slug].html
Product truth notes: [What HCS products exist, what collections to link to]
Collection URLs verified: [Yes/No + which ones]
```

---

## Status

This is a draft method document. It should be reviewed and approved before the queue is rebuilt.

---

*Created by ORIN Product Truth Phase 0 — 2026-07-03*
