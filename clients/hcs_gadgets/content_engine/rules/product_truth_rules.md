# HCS Gadgets — Product Truth Rules

**Version:** 1.0
**Date:** 2026-07-03
**Status:** LOCKED — Must be followed before any HCS article is planned or drafted

---

## Purpose

These rules exist to prevent a repeat of the Job 02 BBQ draft problem: content was written using generic e-commerce assumptions about BBQ accessories, without verifying that HCS Gadgets actually sells those products or has those collections. This resulted in an article with broken internal links and product claims unsupported by the real Shopify catalogue.

**No article about HCS products may be planned or drafted without first consulting the verified product and collection catalogues.**

---

## Core Rules

### PT1 — Verify Before You Write

Before any article topic is approved or any draft is started:

1. Read `product_catalog.json` — check that HCS sells products relevant to the topic
2. Read `collections_inventory.json` — check that target collection URLs are valid
3. Read `hcs_verified_link_map.json` — use only verified collection and product URLs
4. If the topic requires products that HCS does not sell, the topic must be **rejected, reframed, or replaced** — not approximated

**Do not invent product categories, product types, or collections that do not exist in the Shopify catalogue.**

---

### PT2 — Only Link to Verified URLs

Every internal link in an article must match a URL in `hcs_verified_link_map.json`.

**Verified URL sources:**
- `hcs_verified_link_map.json` → `verified_products`, `verified_collections`, `verified_blog_articles`
- Fallback: `https://hcsgadgets.com/collections/all-product` (the only safe universal fallback)

**Never use:**
- `bbq-garden` — does not exist
- `home-and-garden` — does not exist (correct handle is `home-garden`)
- `outdoor-living` — does not exist
- `/collections/all` — does not exist (correct handle is `all-product`)

---

### PT3 — Product Relevance Check

For every article that mentions specific products or categories:

| Situation | Action |
|-----------|--------|
| HCS sells matching products | Write about those specific products, using real product titles, prices, and descriptions from `product_catalog.json` |
| HCS sells partial match | Write general educational content; do not claim HCS sells items it does not; link only to verified products and collections |
| HCS sells no matching products | Reject the topic or replace with one that matches the catalogue |
| Topic is purely educational (no product recommendation) | Allowed, but must still use verified collection links |

---

### PT4 — Product Claims Must Come from Shopify Data

- Do not make claims about product features, materials, prices, or availability that are not confirmed in `product_catalog.json`
- If a product description is needed, extract it from the Shopify product data
- Do not use generic e-commerce copy templates that assume a product catalogue that does not match HCS

---

### PT5 — Collection URL Verification

Before an article links to a collection:

| Collection (Invalid) | Use Instead |
|---------------------|-------------|
| `/collections/bbq-garden` | `/collections/sports-outdoor` or `/collections/all-product` |
| `/collections/home-and-garden` | `/collections/home-garden` |
| `/collections/outdoor-living` | `/collections/sports-outdoor` |
| `/collections/all` | `/collections/all-product` |

---

### PT6 — Pre-Draft Checklist

Before any HTML draft is created, the following must be confirmed:

- [ ] Topic verified against `product_catalog.json` — HCS sells relevant products
- [ ] All internal links checked against `hcs_verified_link_map.json`
- [ ] All collection URLs use valid handles from `collections_inventory.json`
- [ ] All product mentions are backed by real product data
- [ ] CTA link uses a verified collection URL
- [ ] No broken or unverified URLs in the draft

---

### PT7 — BBQ-Specific Guidance (Post-Incident Rule)

The Job 02 BBQ draft identified the following HCS-specific facts:

**HCS sells exactly 2 BBQ-related products:**
1. HeatRise Chimney Starter | `bbq-chimney-starter-charcoal-barbecue` | £8.99
2. Portable BBQ Grill – Foldable Charcoal Barbecue | `foldable-stainless-steel-bbq-grill` | £22.99

**No BBQ collection exists at HCS.** The `bbq-garden` handle does not exist.

**Valid HCS collections relevant to outdoor/garden content:**
- `sports-outdoor` — Sport & Outdoor
- `home-garden` — Home & Modern Decor Accessories
- `gadgets` — Gadgets

**Rule:** Any future BBQ or outdoor article at HCS must be scoped to only what HCS actually sells. If the article recommends accessories HCS does not carry, it must be reframed as general educational content with no product-specific claims, or the topic must be replaced.

---

## HCS Gadgets — Real Product Catalogue Summary

**Total products:** 93 active
**Total collections:** 14 (via custom_collections API)

### Products by Category

| Category | Product Type | Count | Notes |
|----------|-------------|-------|-------|
| Hoverboards | Hoverboards | 6 | 6.5" and G1 Lite models |
| Hoverkarts | Hoverkarts | 8 | Multiple colour variants |
| Hoverboard Bundles | Hoverboard Bundles | 1 | G1 Pro bundle |
| G1 Lite Bundles | G1 Lite Bundles | 3 | Hoverboard + Hoverkart combos |
| Kids Electric Scooters | Kids Scooters | 7 | Evercross, X1, X2, Midnight models |
| Adult Electric Scooters | Adult Scooters | 2 | EV10K Pro, H7 |
| Gadgets | GADGETS | 4 | Protein shaker, skipping rope, mask, bag |
| Uncategorised | uncategorised | 60 | Includes ice bath, ceramic accessories, BBQ grill, BBQ chimney, space heaters, electric bikes, kids motorcycles, mops, wax melts, travel bags |

### Valid Collection Handles

```
adult-e-scooters      → Adult Electric Scooters UK
all-product           → All Product  ← USE FOR FALLBACK
sale                  → Christmas Sale
new-arrivals          → Diffusers
e-scooters            → Electric Bikes
gadgets               → Gadgets
home-garden           → Home & Modern Decor Accessories  ← VALID (not home-and-garden)
hoverboard-bundles    → Hoverboard Bundle
hoverkarts            → Hoverboard Go-Karts (Hoverkarts)
uks-best-hoverboard-deals-all-terrain-hoverboards → Hoverboards for Kids & Adults
kids-e-scooters       → Kids Electric Scooters UK
refurbish             → REFURBISH
replacement-parts-accessories → Replacement Parts & Accessories (UK)
sports-outdoor        → Sport & Outdoor  ← VALID outdoor/garden collection
```

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-07-03 | Initial locked rules — created after Job 02 BBQ product truth audit |

---

*Locked by ORIN Product Truth Phase 0 — 2026-07-03*
