# HCS Gadgets Writing Rules

## Purpose
Create helpful ecommerce blog articles for HCS Gadgets that support product discovery, buyer confidence, and SEO growth.

## Website
hcsgadgets.com

## Core Writing Style
- Use simple UK English.
- Keep the tone practical and useful.
- Write like a helpful ecommerce buying guide.
- Avoid sounding too salesy.
- Avoid fake authority.
- Avoid exaggerated product claims.
- Avoid copying competitor wording.

## Article Structure
Each article should normally include:

1. H1 title
2. Short helpful intro
3. Quick answer box
4. Table of contents
5. Main H2 sections
6. Practical checklist or comparison block
7. Product/category guidance
8. Soft HCS Gadgets CTA
9. FAQ section
10. FAQ schema JSON-LD

## CTA Rules
Use soft CTAs only.

Good:
- Browse practical home and lifestyle products at HCS Gadgets.
- Explore useful gadgets and everyday essentials.
- Find practical products for your home, garden, travel, and daily routine.

Avoid:
- Buy now before it sells out
- Best in the UK
- Guaranteed cheapest
- Life-changing product
- Medical or health benefit claims

## Internal Linking
Only link where useful:
- relevant collections
- relevant products
- relevant support pages
- relevant blog posts

Do not force links.

---

## PRODUCT DATA USAGE — HCS GADGETS BLOGS

**Source file:** `clients/hcs_gadgets/content_engine/product_content_view.json`

Use `product_content_view.json` for ALL product information in blog articles.

**DO NOT use:** `product_truth_normalised.json` or `product_catalog.json` for blog content.

### RESTRICTED — Never include in article copy:

| Field | Examples | Severity |
|---|---|---|
| `price`, `display_price`, `price_min/max` | `£22.99`, `From £8` | BLOCK |
| `price_range` | `£8 to £23` | BLOCK |
| `compare_at_price` | `was £42.99` | BLOCK |
| `inventory_quantity` | `752 in stock` | BLOCK |
| `stock status` | `in stock`, `low stock`, `only 3 left` | BLOCK |
| `sku`, `barcode`, `EAN`, `GTIN` | `5051234567890` | BLOCK |
| `variant_id`, `product_id` | `58186880811382` | BLOCK |
| `supplier_code`, internal vendor | `SUPPLIER-001`, `Hoverboard Store` as supplier | BLOCK |
| Internal catalogue tags | `wholesale`, `bulk_order` | BLOCK |

### ALLOWED — Genuine specifications (not commerce fields):

- Dimensions: `85 x 85 x 73 cm`
- Capacity: `415L`, `330–340L`
- Weight: `5.0 kg`
- Speed: `12 KM/H`
- Battery: `4400mAh`
- Motor: `2 x 250W`
- Rider weight limit: `30KG - 120KG`
- Charging time: `2-3 hours`
- Riding time: `2 hours`

### Writer instruction:

DO NOT say `"From £X"`, `"£X.XX"`, `"in stock"`, `"low stock"`, `"only X left"`.
DO NOT include supplier codes, SKUs, or internal product IDs in copy.

If a job explicitly requires price content and human approval is recorded, price content may be included — but only for that specific job.
