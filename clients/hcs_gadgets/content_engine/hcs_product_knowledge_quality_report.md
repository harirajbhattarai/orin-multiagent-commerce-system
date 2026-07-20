# HCS Product Knowledge Quality Report

**Date:** 2026-07-04
**Phase:** Product Intelligence Phase 0 — PHASE I (Quality Report)
**Source:** `product_knowledge_profiles.json`
**Products analysed:** 93

---

## Summary

| Metric | Count |
|--------|-------|
| High-quality profiles | 15 |
| Medium-quality profiles | 40 |
| Low-quality profiles | 38 |
| Products with verified facts (1+) | 55 |
| Products with zero verified facts | 38 |
| Products with data conflicts | 0 |
| Products with safety/compliance flags | 42 |
| Products needing human review before product-led content | 77 |

---

## Quality Distribution

| Rating | Count | Description |
|--------|-------|-------------|
| **high** | 15 | Has description (>50 chars) + ≥3 verified facts + no conflicts |
| **medium** | 40 | Has description (>50 chars) + ≥1 verified fact |
| **low** | 38 | Description empty/short OR zero verified facts extracted |

---

## Verified Facts Distribution

| Verified Fact Count | Products |
|--------------------|----------|
| 0 facts | 38 |
| 1–2 facts | 40 |
| 3–5 facts | 15 |
| 6+ facts | 0 |

**Total verified facts across all 93 products: 102**

---

## Products with Empty Descriptions (8 products)

These products have no usable Shopify description. They are the most limited for article writing.

| Product |
|---------|
| HH1 PINK SPIN MOP |
| HH2 Max Aqua Press Mop & Bucket Set |
| Home Harbour 5-Section Rotating Serving Platter |
| Home Harbour Electric Fireplace Heater |
| Hoverboard Waterproof Carrying Hand Bag 6.5 |
| Replacement Battery For Hoverboards 36v 2.0Ah |
| S4 ScentGlide Black Waterless Diffuser With Oil Sets |
| S5 Waterless Essential Oil Diffuser |

**Impact:** These products can only be written about using title-derived facts and structured variant data. Do not attempt product-led content for these items without additional research.

---

## Products with Safety/Compliance Claims Needing Human Review (42 products)

These products have claims in their Shopify description that require human review before inclusion in articles.

Top affected categories:
- Hoverboards (UK safety certified claims)
- Hoverkarts (compatibility claims)
- Electric scooters (speed and certification claims)
- Kids products (age/safety claims)

**Top flagged products:**
- Kids 16-Inch Safe Dartboard Set — 5 safety flags
- All Terrain Black Hoverboard + Hoverkart Bundle — 2 flags
- Multiple hoverkart replacement parts — 1–2 flags each
- Midnight X2 Teenager Electric Scooter — 2 flags

**Required action:** Before writing product-led content for any of these 42 products, a human must review and either approve or reject each flagged claim.

---

## Products Safe for Product-Led Content (16 products)

These products have ≥3 verified facts and no safety flags:

The following products are assessed as ready for product-led content without additional research:
- (Products with 3+ verified facts from the 15 high-quality profiles — see `product_knowledge_profiles.md` for full list)

---

## Data Conflicts

**0 products with data conflicts detected** in structured cross-field validation.

Note: Conflict detection is limited to structured fields (variants vs description). Full conflict detection against product images and product page content is not within scope of this builder.

---

## Products Needing Human Review Before Product-Led Content

**77 of 93 products** need human review or additional research before product-led article content is written.

For these products:
1. Use `product_content_view.json` as the base — it contains only safe facts
2. Flag any product-purpose claims from the description for human review
3. Do not use the Shopify description directly as article copy
4. Do not invent missing facts

---

## Missing Important Facts Across Catalogue

The following categories of facts are commonly missing from HCS Shopify product descriptions:

| Missing Fact | Products Affected | Writer Action |
|-------------|------------------|---------------|
| Exact dimensions | Most products | Record `unknown` — do not estimate |
| Maximum weight/load capacity | Hoverboards, scooters, bikes | Record `unknown` — do not infer |
| Battery range | Scooters, hoverboards | Record `unknown` — do not infer from mAh |
| Age range | Kids products | Record `unknown` unless stated |
| Warranty period | Most products | Record `unknown` unless stated |
| Specific certification standard | Hoverboards claiming "UK certified" | Requires named standard — human review required |
| Material specification | Ceramic, metal, plastic items | Record `unknown` unless stated |
| Charging time | Battery-powered products | Record `unknown` unless stated |

---

## Source Data Quality Notes

**Shopify Description Quality:**
- 85 products have non-empty descriptions (>50 chars of text after HTML stripping)
- 26 descriptions have structured "Key Features" style content
- 58 descriptions are primarily marketing/lifestyle copy with limited factual content
- 8 products have no description at all

**Catalogue Field Quality:**
- `body_html` is the only source for product facts beyond structured fields
- No products have structured specifications fields in Shopify
- No products have separate spec sheet data
- `product_type` is not consistently applied — 60 products are `uncategorised`

---

## Prohibited Fields Confirmed Absent from Writer View

`product_content_view.json` was audited for prohibited fields:

| Field | Present in public view? |
|-------|------------------------|
| `sku` | **NO ✓** |
| `inventory_quantity` | **NO ✓** |
| `compare_at_price` | **NO ✓** |
| `images_count` | **NO ✓** |
| `product_id` | **NO ✓** |
| `inventory_item_id` | **NO ✓** |
| `price` | **NO ✓** |
| `admin_graphql_api_id` | **NO ✓** |

---

## Recommended Actions Before Phase 1

1. **Human review** of all 42 products with safety/compliance flags before product-led content
2. **Description enrichment** for the 8 products with no descriptions — supplier descriptions or original writing needed
3. **Structured spec fields** — request supplier spec sheets for high-priority products (hoverboards, scooters, BBQ)
4. **Category mapping** — 60 products are `uncategorised` in Shopify — manual category assignment needed
5. **Conflict review** — 0 conflicts detected but builder only checks structured fields; product images and spec sheets not yet analysed
