# HCS Job 02 — Product Truth Rewrite Decision Report

**Article:** BBQ Accessories UK: How to Choose the Right Gear for Your Garden
**Rewrite plan:** `job_02_product_truth_rewrite_plan.md`
**Decision date:** 2026-07-03
**Status:** QUARANTINED — Rewrite approved

---

## Why the Current Draft is Not Publishable

The current Job 02 draft was written using generic e-commerce content assumptions about a full-range BBQ accessories store. Product Truth Phase 0 (2026-07-03) revealed the following critical failures:

### Failure 1 — Product Catalogue Mismatch

The article recommends 7 categories of BBQ accessories as buyer's guide content:
- Grilling tongs and spatulas
- Meat thermometers
- Grill cleaning brushes
- Weather-resistant BBQ covers
- Fuel (charcoal/briquettes)
- Tool sets
- Skewers and baskets

**HCS Gadgets sells exactly 2 BBQ-related products:**
1. HeatRise Chimney Starter — £8.99
2. Portable BBQ Grill – Foldable Charcoal Barbecue — £22.99

The article's core content — the recommendations readers are meant to act on — describes products HCS does not carry. This is not a minor misalignment. The article is fundamentally a buyer's guide for products that do not exist at this store.

**Product relevance score: 2/10**

### Failure 2 — All 4 Collection Links Broken

| Link URL | Status |
|----------|--------|
| `https://hcsgadgets.com/collections/bbq-garden` | ❌ Collection does not exist |
| `https://hcsgadgets.com/collections/home-and-garden` | ❌ Handle should be `home-garden` |
| `https://hcsgadgets.com/collections/outdoor-living` | ❌ Collection does not exist |
| `https://hcsgadgets.com/collections/all` | ❌ Handle should be `all-product` |

Publishing this article would mean live broken links on the HCS Gadgets storefront.

### Failure 3 — Generic Content Written Without Product Truth Check

The writer (ORIN Phase 2C) did not consult `product_catalog.json` before planning the article. This is now addressed by `product_truth_rules.md`.

---

## Verified HCS BBQ Products

| Product | Handle | Price | Verified |
|---------|--------|-------|----------|
| HeatRise Chimney Starter | `bbq-chimney-starter-charcoal-barbecue` | £8.99 | ✅ |
| Portable BBQ Grill | `foldable-stainless-steel-bbq-grill` | £22.99 | ✅ |

Source: `product_catalog.json` — fetched from Shopify Admin API, 2026-07-03

---

## Broken Links Found — Summary

| # | Broken URL | Anchor text | Fix |
|---|-----------|-------------|-----|
| 1 | `bbq-garden` (collection) | BBQ accessories at HCS Gadgets | Use `sports-outdoor` collection or product URLs |
| 2 | `home-and-garden` (wrong handle) | home and garden products | Use `home-garden` |
| 3 | `outdoor-living` (collection) | outdoor living products | Use `sports-outdoor` |
| 4 | `all` (wrong handle) | Explore HCS Gadgets (CTA) | Use `all-product` |

---

## Approved Rewrite Direction

**New article title:**
> Portable BBQ and Chimney Starter Guide: Simple Gear for UK Gardens

**Scope:** Strictly limited to the 2 verified HCS BBQ products. No generic BBQ accessories content.

**Content approach:**
- 1 article covering 2 products
- Product-grounded facts only (from Shopify product descriptions)
- No invented product categories
- No broken links — verified URLs only
- Internal links to verified product pages and the `sports-outdoor` collection

**Slug:** Unchanged — `bbq-accessories-uk-how-to-choose-the-right-gear`

**Note:** The URL slug in Shopify must NOT be changed. The existing Shopify draft handle remains `bbq-accessories-uk-how-to-choose-the-right-gear`. The HTML draft body will be replaced, but the Shopify article handle stays the same.

---

## Queue State After Quarantine

| Field | Before | After |
|-------|--------|-------|
| Queue status | `draft_created` | `needs_revision_product_mismatch` |
| Draft location | `...drafts/bbq-accessories-uk-how-to-choose-the-right-gear.html` | Unchanged — quarantined |
| Shopify draft | `1001998647670` | Unchanged — quarantined, hidden |
| Target date | 2026-07-21 | Unchanged — 2026-07-21 |
| Notes | Phase 2D-2F completion notes | Updated with product truth findings and rewrite plan reference |

---

## Next Action

**Rewrite the existing Shopify draft — do not create a second draft article.**

The existing Shopify draft (ID: 1001998647670) must be updated with the new product-accurate HTML content. Do not create a new Shopify article. Updating the existing draft preserves the article ID and handle.

**Step sequence:**
1. Write new local HTML draft using `job_02_product_truth_rewrite_plan.md`
2. Run HTML contract validator and quality checks
3. Run broken link check against `hcs_verified_link_map.json`
4. Run product truth check — confirm only 2 verified HCS products are mentioned
5. If all checks pass, push updated HTML to existing Shopify draft ID 1001998647670
6. Verify Shopify `published_at` remains `null`
7. Confirm all broken links are fixed in the Shopify draft
8. Update queue status to `draft_updated`

**Do not publish.** Publishing remains manual after rewrite validation.

---

## Files

- Rewrite plan: `clients/hcs_gadgets/content_engine/plans/job_02_product_truth_rewrite_plan.md`
- Product truth rules: `clients/hcs_gadgets/content_engine/rules/product_truth_rules.md`
- Verified link map: `clients/hcs_gadgets/content_engine/hcs_verified_link_map.json`
- Product catalogue: `clients/hcs_gadgets/content_engine/product_catalog.json`
- Original quarantined draft: `clients/hcs_gadgets/content_engine/drafts/bbq-accessories-uk-how-to-choose-the-right-gear.html`
- Queue backup: `clients/hcs_gadgets/content_engine/content_queue_3_months.md.bak.2026-07-03`

---

*Decision report by ORIN Product Truth Phase 0.1 — 2026-07-03*
