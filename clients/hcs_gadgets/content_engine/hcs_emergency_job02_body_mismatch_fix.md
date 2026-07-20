# HCS Emergency Fix — Job 02 Shopify Draft Body Mismatch Audit & Repair

**Date:** 2026-07-03
**Status:** COMPLETE
**Article ID:** 1001998647670

---

## What Was Wrong

The Phase 0.2 update to Shopify Article ID 1001998647670 updated the article **title** correctly but appears to have **failed to update the body_html and handle**.

| Field | Expected | Found Before Fix |
|-------|----------|-----------------|
| Title | Portable BBQ and Chimney Starter Guide: Simple Gear for UK Gardens | ✅ Already correct |
| Handle | portable-bbq-chimney-starter-guide-uk-gardens | ❌ bbq-accessories-uk-how-to-choose-the-right-gear |
| published_at | null | ❌ 2026-07-03T19:25:23+01:00 |
| Body | Local draft HTML with 2 verified HCS products | ❌ Old generic BBQ accessories content |

**Root cause:** The PUT request likely updated title and handle but did not overwrite body_html, or there was a partial success that committed title but not body_html.

---

## Audit Trail

### Step 1 — Shopify Live Fetch (Before Fix)

| Property | Value |
|----------|-------|
| Article ID | 1001998647670 |
| Title | Portable BBQ and Chimney Starter Guide: Simple Gear for UK Gardens ✅ |
| Handle | bbq-accessories-uk-how-to-choose-the-right-gear ❌ |
| published_at | 2026-07-03T19:25:23+01:00 ❌ |
| Body length | 16,303 chars |
| Word count | 2,357 |
| SHA256 body | b17d1f3c151400f6c98c29eebac21960c39e87adfa4429c7a97d70c321b23533 |

### Step 2 — Backup Saved

- Path: `clients/hcs_gadgets/content_engine/backups/article_1001998647670_before_body_mismatch_fix.json`
- Confirmed: backup contains full Shopify article JSON before any changes

### Step 3 — Local Draft Analysis

| Property | Value |
|----------|-------|
| Draft file | `clients/hcs_gadgets/content_engine/drafts/portable-bbq-chimney-starter-guide-uk-gardens.html` |
| Body length | 16,361 chars |
| Word count | 2,453 |
| SHA256 | 40f1e0c14434c6166dc8c29561f16f5fd0010ba1aedb7c02a2fc9a5930e987f1 |
| HTML validator | 42/42 PASS ✅ |

### Step 4 — Body Comparison

| Check | Result |
|-------|--------|
| Hashes match | ❌ NO — Shopify SHA256 ≠ Local SHA256 |
| Shopify body contains old "BBQ Accessories UK" | ✅ YES — old content confirmed |
| Shopify body contains "tongs" | ✅ YES — unsupported accessory confirmed |
| Shopify body contains "thermometer" | ✅ YES — unsupported accessory confirmed |
| Shopify body contains "grilling tongs" | ✅ YES — old generic content confirmed |
| Shopify body contains "HeatRise Chimney Starter" | ❌ NO — correct product not present |
| Shopify body contains "Portable BBQ" | ❌ NO — correct product not present |
| Local draft contains HeatRise Chimney Starter | ✅ YES |
| Local draft contains Portable BBQ | ✅ YES |
| Local draft contains unsupported accessories | ❌ NO |

**Conclusion:** Shopify body was the old generic BBQ accessories guide. Local draft is the correct product-truth version. Shopify body was replaced.

---

## Repair Action

### Validation Before Shopify Update

**HTML Validator:** 42/42 PASS ✅

**Product Truth Checks:**

| Check | Result |
|-------|--------|
| hcs-article wrapper | ✅ PASS |
| BlogPosting JSON-LD | ✅ PASS |
| FAQPage JSON-LD | ✅ PASS |
| Only verified HCS BBQ products | ✅ PASS — HeatRise Chimney Starter + Home Harbour H1 Portable |
| Unsupported BBQ accessory mentions | ✅ PASS — 0 found |
| Broken links | ✅ PASS — 0 found |
| Old/generic BBQ content | ✅ PASS — 0 old terms found |
| H1 title correct | ✅ PASS |

### Shopify PUT Update

- **Endpoint:** PUT `/admin/api/2026-01/blogs/89150259452/articles/1001998647670.json`
- **Article ID:** 1001998647670 (unchanged) ✅
- **Title set:** Portable BBQ and Chimney Starter Guide: Simple Gear for UK Gardens
- **Handle set:** portable-bbq-chimney-starter-guide-uk-gardens
- **body_html set:** full local draft HTML
- **published_at set:** null
- **Status:** draft

---

## Post-Update Verification

### Shopify Live Fetch (After Fix)

| Property | Expected | Found | Match |
|----------|----------|-------|-------|
| Article ID | 1001998647670 | 1001998647670 | ✅ |
| Title | Portable BBQ and Chimney Starter Guide: Simple Gear for UK Gardens | Portable BBQ and Chimney Starter Guide: Simple Gear for UK Gardens | ✅ |
| Handle | portable-bbq-chimney-starter-guide-uk-gardens | portable-bbq-chimney-starter-guide-uk-gardens | ✅ |
| published_at | null | null | ✅ |
| Body SHA256 | 40f1e0c14434c6166dc8c29561f16f5fd0010ba1aedb7c02a2fc9a5930e987f1 | 40f1e0c14434c6166dc8c29561f16f5fd0010ba1aedb7c02a2fc9a5930e987f1 | ✅ |
| Body length | 16,361 | 16,361 | ✅ |
| HeatRise Chimney Starter in body | Yes | ✅ Yes | ✅ |
| Portable BBQ in body | Yes | ✅ Yes | ✅ |
| Old "BBQ Accessories UK" | No | ✅ Not found | ✅ |
| Old "tongs" | No | ✅ Not found | ✅ |
| Old "thermometer" | No | ✅ Not found | ✅ |
| Old "grilling tongs" | No | ✅ Not found | ✅ |
| £8.99 in body | Yes | ✅ Yes | ✅ |
| £22.99 in body | Yes | ✅ Yes | ✅ |

### Duplicate Check

| Check | Result |
|-------|--------|
| Duplicate title | ✅ None found |
| Duplicate handle | ✅ None found |
| Total articles scanned | 37 |

---

## Proof of Fix

| # | Check | Result |
|---|-------|--------|
| 1 | Shopify article ID | 1001998647670 ✅ |
| 2 | Backup path | `clients/hcs_gadgets/content_engine/backups/article_1001998647670_before_body_mismatch_fix.json` ✅ |
| 3 | Shopify body hash before | b17d1f3c151400f6c98c29eebac21960c39e87adfa4429c7a97d70c321b23533 |
| 4 | Local draft hash | 40f1e0c14434c6166dc8c29561f16f5fd0010ba1aedb7c02a2fc9a5930e987f1 |
| 5 | Body matched before | ❌ NO |
| 6 | Body mismatch found | ✅ YES — old generic BBQ accessories content in Shopify, correct product-truth content in local draft |
| 7 | Shopify body updated | ✅ YES |
| 8 | Shopify body hash after | 40f1e0c14434c6166dc8c29561f16f5fd0010ba1aedb7c02a2fc9a5930e987f1 |
| 9 | Body hash now matches local | ✅ YES |
| 10 | Title correct | ✅ YES |
| 11 | Handle correct | ✅ YES — updated from bbq-accessories-uk-how-to-choose-the-right-gear to portable-bbq-chimney-starter-guide-uk-gardens |
| 12 | published_at null | ✅ YES — was 2026-07-03T19:25:23+01:00, now null |
| 13 | Verified product mentions found | ✅ YES — HeatRise Chimney Starter, Portable BBQ, £8.99, £22.99 all confirmed |
| 14 | Unsupported product mentions count | 0 ✅ |
| 15 | Broken links count | 0 ✅ |
| 16 | Shopify touched | ✅ YES — PUT request sent to Article ID 1001998647670 |
| 17 | Published | ❌ NO ✅ |
| 18 | Final decision | **SHOPIFY DRAFT UPDATED AND VERIFIED — READY FOR OPERATOR PUBLISH REVIEW** |

---

## What Was Fixed

1. **Body_html** — replaced old generic BBQ accessories guide (16,303 chars, 2,357 words, SHA256 b17d1f3c...) with correct product-truth draft (16,361 chars, 2,453 words, SHA256 40f1e0c1...)
2. **Handle** — updated from `bbq-accessories-uk-how-to-choose-the-right-gear` to `portable-bbq-chimney-starter-guide-uk-gardens`
3. **published_at** — reset from `2026-07-03T19:25:23+01:00` to `null` (draft status restored)
4. **Unsupported accessory content removed** — tongs, thermometers, brushes, grilling tongs, BBQ Accessories UK title all removed
5. **Verified HCS products added** — HeatRise Chimney Starter (£8.99) and Portable BBQ (£22.99) now present in article body

---

## Next Step

Operator can now publish Job 02 at their discretion. To publish:

1. Review Shopify draft at: `https://hcsgadgets-com.myshopify.com/admin/blogs/89150259452/articles/1001998647670`
2. Set `published_at` to `2026-07-21` (or desired date)
3. Publish

---

*Emergency fix by ORIN — 2026-07-03*
