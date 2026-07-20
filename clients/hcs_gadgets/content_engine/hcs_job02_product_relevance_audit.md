# HCS Job 02 — Product Relevance Audit

**Article:** BBQ Accessories UK: How to Choose the Right Gear for Your Garden
**Shopify Draft ID:** 1001998647670
**Status:** Draft (hidden, `published_at` set to null — confirmed safe)
**Audit date:** 2026-07-03
**Audit type:** Product Truth — Post-Incident

---

## Executive Summary

| Item | Finding |
|------|---------|
| **Product relevance score** | **2/10 — Critically misaligned** |
| **Broken links** | 4 of 4 collection links broken |
| **Unsupported product claims** | Extensive — article recommends BBQ accessories HCS does not sell |
| **Recommended action** | **Do not publish — full rewrite required** |

---

## What the Article Claims

The article "BBQ Accessories UK: How to Choose the Right Gear for Your Garden" was written as a buyer's guide for BBQ accessories covering:

- Grilling tongs and spatulas
- Meat thermometers
- Grill cleaning brushes
- Weather-resistant BBQ covers
- Fuel options (charcoal/briquettes)
- Tool sets
- Skewers and baskets

It recommends these as products a UK garden BBQ owner should buy.

---

## What HCS Gadgets Actually Sells

**Total BBQ-related products at HCS: 2**

| Product | Handle | Price |
|---------|--------|-------|
| HeatRise Chimney Starter | `bbq-chimney-starter-charcoal-barbecue` | £8.99 |
| Portable BBQ Grill – Foldable Charcoal Barbecue | `foldable-stainless-steel-bbq-grill` | £22.99 |

**HCS does not sell:**
- Grilling tongs or spatulas
- Meat thermometers
- Grill cleaning brushes
- BBQ covers
- Fuel (charcoal/briquettes)
- Tool sets
- Skewers or baskets

The article's core recommendations — the products it tells readers to prioritse — are **products HCS does not carry**.

---

## Broken Links Found

All 4 collection links in the article are broken:

| Link URL (as written) | Status | Correct Handle |
|----------------------|--------|----------------|
| `https://hcsgadgets.com/collections/bbq-garden` | ❌ BROKEN — collection does not exist | N/A |
| `https://hcsgadgets.com/collections/home-and-garden` | ❌ BROKEN — handle is `home-garden` | `home-garden` |
| `https://hcsgadgets.com/collections/outdoor-living` | ❌ BROKEN — collection does not exist | N/A |
| `https://hcsgadgets.com/collections/all` | ❌ BROKEN — handle is `all-product` | `all-product` |

The internal blog link (Job 01 article) is **valid**:
| Link URL | Status |
|----------|--------|
| `https://hcsgadgets.com/blogs/gadget-blog/useful-home-gadgets-that-make-daily-life-easier` | ✅ Valid — Job 01 published article |

**Broken links: 4 out of 5 total links**

---

## Collection Availability at HCS

The following valid collections exist at HCS (from `collections_inventory.json`):

| Valid Handle | Title | Relevant for BBQ/Garden? |
|-------------|-------|--------------------------|
| `sports-outdoor` | Sport & Outdoor | ✅ Yes — closest match for outdoor |
| `home-garden` | Home & Modern Decor Accessories | ⚠️ Partial — includes ceramics, heaters |
| `gadgets` | Gadgets | ⚠️ Partial — some outdoor-adjacent gadgets |
| `all-product` | All Product | ✅ Safe fallback |

**Collections the writer assumed existed:**
- `bbq-garden` — ❌ Does not exist
- `home-and-garden` — ❌ Does not exist (handle is `home-garden`)
- `outdoor-living` — ❌ Does not exist

---

## Product Relevance Scoring

| Criterion | Score | Detail |
|-----------|-------|--------|
| Article topic matches HCS product catalogue | 1/10 | Only 2 of 7 accessory categories exist at HCS |
| Specific HCS product mentions | 0/10 | Zero named HCS products |
| Valid collection links | 0/4 | 0 of 4 links point to valid collections |
| Valid product links | 0/1 | No HCS product links |
| CTA collection valid | 0/1 | CTA uses `/collections/all` which does not exist |
| HCS product angle present | 0/10 | No HCS-specific product data used |

**Overall score: 2/30 → 2/10**

---

## Shopify Draft Status

| Field | Value |
|-------|-------|
| Article ID | 1001998647670 |
| Handle | `bbq-accessories-uk-how-to-choose-the-right-gear` |
| Title | BBQ Accessories UK: How to Choose the Right Gear for Your Garden |
| `published` | `None` (unpublished) |
| `published_at` | `None` (confirmed null — article is hidden) |
| Body matches local draft | Yes (links are identical) |
| Broken links in Shopify draft | 4 (same as local draft) |

**Safety note:** `published_at` was initially set to a timestamp from an earlier API call. It has been corrected to `null`. The article is confirmed hidden.

---

## Root Cause

The draft was written using generic e-commerce content assumptions for a "BBQ accessories UK" topic. The writer:

1. Did not check `product_catalog.json` before planning the article
2. Did not verify collection URLs against `collections_inventory.json`
3. Assumed a full BBQ accessories product range exists at HCS
4. Linked to collection handles without confirming they exist

---

## Options and Recommended Next Action

### Option A — Full Rewrite (Recommended)

Rewrite the article to focus exclusively on the 2 BBQ products HCS actually sells:
- HeatRise Chimney Starter
- Portable BBQ Grill – Foldable Charcoal Barbecue

Angle: "Making the most of your garden BBQ setup — 2 products that earn their place"

This would be a genuine, product-grounded article with:
- Real HCS product mentions
- Valid collection links (`sports-outdoor`, `home-garden`)
- No broken URLs
- No generic accessory recommendations for products HCS does not sell

**Time estimate:** New draft required. Do not update the existing Shopify draft until new draft is validated.

### Option B — Topic Replacement

Replace the BBQ topic entirely. HCS has strong product clusters in:
- Hoverboards and safety guides
- Hoverkarts and bundles
- Kids electric scooters
- Adult electric scooters
- Home and garden gadgets (ice bath, BBQ grill, BBQ chimney, heaters, ceramics)

Replace with a topic from one of these verified clusters.

### Option C — Reject

If no HCS-relevant angle can be found for the BBQ topic, reject it and do not publish.

---

## Immediate Actions Required

| Priority | Action | Owner |
|----------|--------|-------|
| 1 | Do NOT publish Job 02 draft in current form | Operator |
| 2 | Fix broken collection links in local HTML draft if rewriting | ORIN |
| 3 | Run product truth check on replacement topic before planning | ORIN |
| 4 | Apply `product_truth_rules.md` to all future queue jobs | ORIN |
| 5 | Review `hcs_3_month_content_strategy_method.md` and rebuild queue from product catalogue | Operator |

---

## Files Relevant to This Audit

- Local draft: `clients/hcs_gadgets/content_engine/drafts/bbq-accessories-uk-how-to-choose-the-right-gear.html`
- Shopify draft: `https://hcsgadgets-com.myshopify.com/admin/articles/1001998647670`
- Product catalogue: `clients/hcs_gadgets/content_engine/product_catalog.json`
- Collections inventory: `clients/hcs_gadgets/content_engine/collections_inventory.json`
- Verified link map: `clients/hcs_gadgets/content_engine/hcs_verified_link_map.json`
- Product truth rules: `clients/hcs_gadgets/content_engine/rules/product_truth_rules.md`
- 3-month strategy: `clients/hcs_gadgets/content_engine/hcs_3_month_content_strategy_method.md`

---

*Audit conducted by ORIN Product Truth Phase 0 — 2026-07-03*
