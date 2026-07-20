# HCS Shopify Draft Update Safety Rules

**Version:** 1.0
**Date:** 2026-07-03
**Applies to:** All HCS Gadgets Shopify draft article updates

---

## Core Principle

**Never trust the API update response alone.** A successful HTTP response from Shopify does not guarantee the update was written correctly. Always fetch and verify after every update.

---

## Pre-Update Rules

### 1. Validate Local HTML Before Any Update

- [ ] Run HTML validator: `python3 tools/shopify_publisher/orin/hcs_html_contract_validator.py --file <local_html_path>`
- [ ] HTML validator must score 42/42 PASS before proceeding
- [ ] If validator fails: STOP — do not update Shopify

### 2. Product Truth Checks

- [ ] Verify local HTML contains only HCS products from `product_catalog.json`
- [ ] Verify no unsupported accessory mentions (tongs, thermometers, brushes, grill baskets, aprons, smoker boxes, tool sets, storage carts, etc.)
- [ ] Verify no old/generic content that was previously flagged for removal
- [ ] Verify hcs-article wrapper exists
- [ ] Verify BlogPosting JSON-LD exists
- [ ] Verify FAQPage JSON-LD exists
- [ ] Verify broken links count = 0
- [ ] If any check fails: STOP — do not update Shopify

### 3. Backup Shopify State Before Update

- [ ] Fetch current Shopify article and save to `backups/article_<id>_before_<reason>.json`
- [ ] Record current body SHA256 in the backup log
- [ ] If backup fails: STOP — do not update Shopify

### 4. Verify Article Exists

- [ ] Confirm article ID exists in Shopify before attempting update
- [ ] Confirm it is the correct blog (Blog ID 89150259452)

---

## During Update Rules

### 5. PUT Request Requirements

- [ ] Use existing article ID only — never create a new article via PUT
- [ ] Include full body_html in every PUT request — never omit it
- [ ] Always set `published_at: null` to maintain draft status
- [ ] Always include the correct handle
- [ ] Always include the correct title

---

## Post-Update Rules (Mandatory — Do Not Skip)

### 6. Fetch Article After Update

- [ ] Re-fetch the article from Shopify immediately after PUT
- [ ] Use GET request, not the PUT response, as source of truth

### 7. Verify Article ID

- [ ] Confirm article ID is unchanged from before the update
- [ ] If ID changed: STOP — this should never happen

### 8. Verify Title

- [ ] Confirm title matches the intended title exactly
- [ ] If title does not match: STOP

### 9. Verify Handle

- [ ] Confirm handle matches the intended handle exactly
- [ ] If handle does not match: STOP

### 10. Verify published_at Is Null

- [ ] Confirm published_at is exactly `null`
- [ ] If published_at has a value: STOP — do not proceed
- [ ] Never allow a draft article to be accidentally published

### 11. Verify Body Hash — THE DEFINITIVE CHECK

- [ ] Compute SHA256 of Shopify body_html
- [ ] Compute SHA256 of local draft HTML
- [ ] If hashes do not match: STOP — do not continue
- [ ] This is the only definitive proof that the body was written correctly

### 12. Verify No Old Content Remains

- [ ] Search Shopify body for any previously removed terms (e.g., old product names, old accessory mentions)
- [ ] If old content found: STOP — body was not updated correctly

### 13. Verify Supported Products Present

- [ ] Confirm all intended HCS products appear in the live Shopify body
- [ ] If any product is missing: STOP

### 14. Verify Unsupported Terms Are Absent

- [ ] Confirm unsupported accessory terms are not in the live Shopify body
- [ ] If any unsupported term found: STOP

### 15. Verify No Duplicate Title

- [ ] Scan all Shopify articles for duplicate title
- [ ] If duplicate found: STOP

### 16. Verify No Duplicate Handle

- [ ] Scan all Shopify articles for duplicate handle
- [ ] If duplicate found: STOP

### 17. Verify Broken Links

- [ ] Extract all href attributes from Shopify body
- [ ] Confirm all links are valid http/https or anchor only
- [ ] If broken links found: STOP

---

## Stop Conditions

**STOP and do not proceed if ANY of the following occur:**

| # | Condition | Action |
|---|-----------|--------|
| 1 | HTML validator fails | Do not update Shopify |
| 2 | Product truth check fails | Do not update Shopify |
| 3 | Backup fails | Do not update Shopify |
| 4 | Body hash mismatch after update | Do not continue — report failure |
| 5 | published_at is not null | Do not continue — report failure |
| 6 | Old content still present | Do not continue — body was not updated |
| 7 | Article ID changes | IMPOSSIBLE — stop and investigate |
| 8 | Title mismatch | Do not continue |
| 9 | Handle mismatch | Do not continue |
| 10 | Duplicate title found | Do not continue |
| 11 | Duplicate handle found | Do not continue |
| 12 | Unsupported terms in body | Do not continue |
| 13 | Missing verified products | Do not continue |
| 14 | Broken links present | Do not continue |

---

## Proof Requirements

Every Shopify draft update must produce a proof report that includes:

```
1. Article ID verified
2. Title correct
3. Handle correct
4. published_at null
5. Body hash matches local HTML hash
6. Unsupported mentions count = 0
7. Broken links count = 0
8. Duplicate title count = 0
9. Duplicate handle count = 0
10. Verified products present
11. Shopify touched (PUT sent)
12. Published = NO
```

---

## Use the Safe Updater Script

The safe updater script enforces all rules above automatically:
- `tools/shopify_publisher/orin/hcs_safe_update_existing_draft.py`

**Do not use raw curl or manual PUT requests for Shopify draft updates.** Use the safe updater script.

---

## Rule Exceptions

There are no exceptions to these rules. If a situation arises that appears to require an exception, stop and report to the operator.

---

*Safety rules by ORIN — 2026-07-03*
*These rules are mandatory for all HCS Gadgets Shopify draft updates.*
