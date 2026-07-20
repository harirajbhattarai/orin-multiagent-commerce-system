# HCS Gadgets — Product Source Field Audit

**Date:** 2026-07-04
**Phase:** Product Intelligence Phase 0 — PHASE A
**Purpose:** Audit every field in `product_catalog_raw.json` and `product_catalog.json`, classify each for writer safety.

---

## Source Files

| File | Description |
|------|-------------|
| `product_catalog_raw.json` | Full Shopify Admin API product response — all raw fields |
| `product_catalog.json` | ORIN sanitised product catalogue — reduced field set |

---

## RAW Catalog — Product-Level Fields

| Field | Type | Example | Source | Public/Internal | Stable/Volatile | Useful for Writer | Safe for Direct Writer Access | Notes |
|-------|------|---------|--------|-----------------|-----------------|--------------------|------------------------------|-------|
| `admin_graphql_api_id` | string | `gid://shopify/Product/15119636922742` | Shopify Admin API | **Internal** | Stable | No | **NO** | Shopify internal graph ID |
| `body_html` | string | Full HTML product description | Shopify Admin API | **Public** | Stable (but may contain stale info) | Yes (with review) | **NO — requires extraction rules** | Contains useful product facts but also marketing, price language, safety claims |
| `created_at` | string (ISO) | `2025-03-15T20:51:36+00:00` | Shopify Admin API | Internal | Stable | Advisory only | No | Product creation date — not customer relevant |
| `handle` | string | `3-wheel-kids-push-foldable-scooter-...` | Shopify Admin API | Public (URL component) | Stable | Yes | **YES** | Used for URL construction |
| `id` | integer | `15119636922742` | Shopify Admin API | **Internal** | Stable | No | **NO** | Shopify product ID |
| `image` | dict | Single primary image | Shopify Admin API | Public | Volatile | Advisory | No | Not used in ORIN sanitised catalog |
| `images` | list[dict] | Full image array | Shopify Admin API | Public | Volatile | No | **NO** | Shopify product images |
| `options` | list | `[{name: "Title", values: ["Default Title"]}]` | Shopify Admin API | Public | Stable | No | No | Variant option definitions |
| `product_type` | string | `Kids Push Scooters` | Shopify Admin API | Public | Stable | Yes | **YES** | Product category classification |
| `published_at` | string (ISO) | `2025-03-15T20:50:55+00:00` | Shopify Admin API | Internal | Stable | No | No | Shopify publish date |
| `published_scope` | string | `web` | Shopify Admin API | Internal | Stable | No | No | Shopify visibility setting |
| `status` | string | `active` | Shopify Admin API | Internal | Volatile | No | No | Product status — operational |
| `tags` | string | `electric scooter, kids scooter, push scooter` | Shopify Admin API | Public | Volatile | Advisory | No | Shopify tags — internal taxonomy only |
| `template_suffix` | null/string | `null` | Shopify Admin API | Internal | Stable | No | No | Shopify theme template |
| `title` | string | `3-Wheel Foldable Kids Scooter...` | Shopify Admin API | **Public** | Stable | Yes | **YES** | Primary product name |
| `updated_at` | string (ISO) | `2026-06-26T10:24:13+01:00` | Shopify Admin API | Internal | Volatile | No | No | Last update — operational |
| `variants` | list[dict] | See variant fields below | Shopify Admin API | Mixed | Mixed | See variant fields | Mixed | Contains both useful and prohibited fields |
| `vendor` | string | `Hoverboard Store` / `HCS GADGETS` / `hcsgadgets.com` | Shopify Admin API | **Public** | Stable | Yes | **YES** | Brand/supplier name |

---

## RAW Catalog — Variant-Level Fields

| Field | Type | Example | Source | Public/Internal | Stable/Volatile | Useful | Safe | Notes |
|-------|------|---------|--------|-----------------|-----------------|--------|------|-------|
| `admin_graphql_api_id` | string | `gid://shopify/ProductVariant/55385287917942` | Shopify Admin API | **Internal** | Stable | No | **NO** | Shopify internal variant ID |
| `barcode` | string | `5061020190701` | Shopify Admin API | Public | Stable | Advisory | No | Product barcode — not customer facing in articles |
| `compare_at_price` | string | `99.99` | Shopify Admin API | **Public but commercial** | Volatile | No | **NO** | Markdown/sale price — volatile, commercial |
| `created_at` | string (ISO) | `2025-03-15T20:51:36+00:00` | Shopify Admin API | Internal | Stable | No | No | Variant creation date |
| `fulfillment_service` | string | `manual` | Shopify Admin API | **Internal** | Stable | No | No | Fulfilment method — internal |
| `grams` | integer | `5000` | Shopify Admin API | **Public** | Stable | Yes | **YES** | Weight in grams — useful for shipping/portability |
| `id` | integer | `55385287917942` | Shopify Admin API | **Internal** | Stable | No | **NO** | Shopify variant ID |
| `image_id` | string/null | `null` | Shopify Admin API | **Internal** | Stable | No | No | Image association |
| `inventory_item_id` | integer | `53812303069558` | Shopify Admin API | **Internal** | Stable | No | **NO** | Shopify inventory item ID |
| `inventory_management` | string | `shopify` | Shopify Admin API | **Internal** | Stable | No | No | Shopify inventory tracking |
| `inventory_policy` | string | `deny` | Shopify Admin API | Internal | Stable | No | No | Inventory policy — operational |
| `inventory_quantity` | integer | `0` | Shopify Admin API | **Internal** | **Volatile** | No | **NO** | Real-time stock — never for evergreen articles |
| `old_inventory_quantity` | integer | `0` | Shopify Admin API | **Internal** | Volatile | No | No | Operational delta |
| `option1` / `option2` / `option3` | string/null | `Default Title` | Shopify Admin API | Public | Stable | Advisory | No | Variant options — size, colour etc. |
| `position` | integer | `1` | Shopify Admin API | **Internal** | Stable | No | No | Variant display order |
| `price` | string | `59.99` | Shopify Admin API | **Public but volatile** | **Volatile** | Conditional | **Separate approval only** | Current price — volatile, requires approval for use |
| `product_id` | integer | `15119636922742` | Shopify Admin API | **Internal** | Stable | No | No | Shopify product ID |
| `requires_shipping` | boolean | `true` | Shopify Admin API | Public | Stable | Yes | **YES** | Shipping requirement |
| `sku` | string | `MINI1PROSCOOTER-BLUE` | Shopify Admin API | **Internal** | Stable | No | **NO** | Internal SKU — never customer facing |
| `taxable` | boolean | `false` | Shopify Admin API | **Internal** | Stable | No | No | Tax setting |
| `title` | string | `Default Title` | Shopify Admin API | Public | Stable | Yes | **YES** | Variant title |
| `updated_at` | string (ISO) | `2026-10-27T01:48:00+00:00` | Shopify Admin API | Internal | Volatile | No | No | Last update |
| `weight` | float | `5.0` | Shopify Admin API | **Public** | Stable | Yes | **YES** | Product weight — useful |
| `weight_unit` | string | `kg` | Shopify Admin API | **Public** | Stable | Yes | **YES** | Weight unit |

---

## Sanitised Catalog — Product-Level Fields

| Field | Source | Public/Internal | Stable/Volatile | Useful | Safe for Writer | Notes |
|-------|--------|-----------------|-----------------|--------|-----------------|-------|
| `body_html_summary` | Derived from `body_html` | **Public** | Stable (but needs review) | Yes | **NO — requires extraction** | First 300 chars of description with HTML stripped |
| `created_at` | RAW | Internal | Stable | No | No | — |
| `handle` | RAW | Public | Stable | Yes | **YES** | URL-safe handle |
| `image_alts` | Derived from `images` | **Public** | Stable | Yes | **YES** | Alt text for accessibility — useful |
| `images_count` | RAW `images` count | **Internal** | Volatile | No | **NO** | Image count — volatile operational |
| `product_id` | RAW `id` | **Internal** | Stable | No | **NO** | Shopify product ID |
| `product_type` | RAW | Public | Stable | Yes | **YES** | Product category |
| `status` | RAW | Internal | Volatile | No | No | Active/archived status |
| `tags` | RAW | Internal | Volatile | No | No | Internal taxonomy only |
| `title` | RAW | **Public** | Stable | Yes | **YES** | Official product name |
| `updated_at` | RAW | Internal | Volatile | No | No | — |
| `url` | Derived | **Public** | Stable | Yes | **YES** | Canonical product URL |
| `variants` | Derived (subset) | Mixed | Mixed | Mixed | Mixed | See variant fields below |
| `vendor` | RAW | **Public** | Stable | Yes | **YES** | Brand/supplier |

---

## Sanitised Catalog — Variant-Level Fields

| Field | Source | Public/Internal | Stable/Volatile | Useful | Safe for Writer | Notes |
|-------|--------|-----------------|-----------------|--------|-----------------|-------|
| `available` | Derived | **Internal** | **Volatile** | No | **NO** | Computed availability — volatile |
| `compare_at_price` | RAW | **Commercial/Internal** | **Volatile** | No | **NO** | Never use in evergreen articles |
| `id` | RAW `id` | **Internal** | Stable | No | **NO** | Shopify variant ID |
| `inventory_policy` | RAW | Internal | Stable | No | No | — |
| `inventory_quantity` | RAW | **Internal** | **Volatile** | No | **NO** | Real-time stock — never in articles |
| `price` | RAW | **Public but volatile** | **Volatile** | Conditional | **Separate approval only** | Use only in explicitly price-led content |
| `sku` | RAW | **Internal** | Stable | No | **NO** | SKU — never customer facing |
| `title` | RAW | **Public** | Stable | Yes | **YES** | Variant name |

---

## Shopify Description (`body_html`) Availability

| Metric | Count |
|--------|-------|
| Total active products | 93 |
| Products with usable descriptions (>50 chars text) | 85 |
| Products with empty/null descriptions | 8 |
| Products with "Key Features" style structured content | 26 |
| Products with pure marketing/lifestyle copy | 58 |

### Products with Empty Descriptions

1. HH1 PINK SPIN MOP
2. HH2 Max Aqua Press Mop & Bucket Set
3. Home Harbour 5-Section Rotating Serving Platter
4. Home Harbour Electric Fireplace Heater
5. Hoverboard Waterproof Carrying Hand Bag 6.5
6. Replacement Battery For Hoverboards 36v 2.0Ah
7. S4 ScentGlide Black Waterless Diffuser With Oil Sets
8. S5 Waterless Essential Oil Diffuser

---

## Shopify Description — Quality Issues

### Price Language in Descriptions
**45 products** contain price-related language in descriptions: `£`, `price`, `save`, `deal`, `% off`, `was`, `now`, `cost`.

**Rule:** Price language in descriptions is volatile. Never copy price claims into evergreen article content.

### Stock/Availability Language in Descriptions
**49 products** contain stock language: `in stock`, `out of stock`, `available`, `limited`, `selling fast`, `only`, `left`, `remaining`, `units`.

**Rule:** Stock language is volatile. Never include in evergreen content.

### Safety/Compliance Claims in Descriptions
**74 products** contain safety/compliance language.

| Pattern | Products |
|---------|---------|
| `safe` | 60 |
| `certified` | 12 |
| `standard` | 9 |
| `waterproof` | 5 |
| `fire` | 1 |
| `flame` | 1 |
| `compliant` | 1 |
| `approved` | 1 |

**Rule:** Safety and compliance claims require stronger evidence. Most are unsupported marketing language. Human review required before including in articles.

### Superlative Marketing Language in Descriptions
**26 products** contain unsupported superlative claims.

| Pattern | Products |
|---------|---------|
| `powerful` | 29 |
| `ultimate` | 14 |
| `premium` | 11 |
| `best` | 3 |
| `unmatched` | 2 |
| `innovative` | 2 |

**Rule:** Superlatives are marketing language, not verified facts. They must not become verified claims without supporting data.

### Description Content Patterns

**Pattern A — Supplier template (hoverboards, scooters):**
> "Product Overview Experience the ultimate in personal transport with our UK safety certified G1 Plus Hoverboard. Combining British safety standards with cutting-edge technology..."

**Pattern B — Feature-list (some gadgets):**
> "Key Features: • 4400mAh Li-Ion battery • Up to 2 hours continuous riding time • Quick 2-3 hour charge • LED lights • Bluetooth"

**Pattern C — Lifestyle/marketing only:**
> "Bold. Refined. Unforgettable. Introducing the Aroma Haven Luxury Men's Soy Wax Melts Set of 3 — a powerful trio designed for those who prefer deeper, woody, and exotic fragrance profiles."

**Pattern D — Practical/useful (BBQ, some heaters):**
> "Barbecuing, without the faff. Lighter fluid is slow, smells of chemicals and can taint your food. The Home Harbour HeatRise Chimney Starter does it the clean way..."

**Pattern E — Empty:**
> "" (8 products)

---

## Field Exposure Summary

| Category | Fields |
|----------|--------|
| **Prohibited — Never in writer view** | `admin_graphql_api_id`, `id` (Shopify IDs), `product_id`, `inventory_item_id`, `variant_id`, `sku`, `inventory_quantity`, `old_inventory_quantity`, `images_count`, `inventory_policy`, `inventory_management`, `barcode`, `fulfillment_service`, `published_at`, `published_scope`, `template_suffix`, `status`, `tags`, `available`, `compare_at_price` |
| **Volatile — Separate approval only** | `price`, `inventory_quantity` (real-time stock) |
| **Requires extraction + review** | `body_html` (product description) |
| **Safe — Writer direct access OK** | `title`, `handle`, `vendor`, `product_type`, `url`, `body_html_summary` (advisory), `variants[].title`, `variants[].price` (conditional), `variants[].weight`, `variants[].weight_unit`, `variants[].requires_shipping`, `grams` |
| **Internal only — not in writer files** | `created_at`, `updated_at`, `published_at`, `status`, `tags`, `template_suffix`, `published_scope` |

---

## Key Conclusion

`product_catalog.json` is NOT writer-safe for direct article use because:
1. It contains `compare_at_price` — volatile commercial field
2. It contains `inventory_quantity` — volatile internal field
3. It contains `sku` — internal operational field
4. It contains `images_count` — volatile operational field
5. Its `body_html_summary` requires extraction rules before use

**Writer must use `product_content_view.json` only.**
