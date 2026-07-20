# HCS HTML Design System v2 — Migration Report

**Date:** 2026-07-04
**Validator version:** 2.0
**Contract:** `hcs_html_design_contract_v2.md`
**Status:** COMPLETE — Local files only. No Shopify articles updated.

---

## What Changed: v1 → v2

### Breaking structural change
- **Every `<table class="hcs-table">` must now be wrapped in `<div class="hcs-table-scroll">`.** This is mandatory. A bare `hcs-table` without the scroll wrapper now fails validation.

### New structural requirements
| # | Change | Reason |
|---|--------|--------|
| 1 | `hcs-table-scroll` mandatory wrapper around every `hcs-table` | CSS scroll container for table overflow |
| 2 | `<div class="hcs-do">` h2 must have `id="good-bad"` | Consistent anchor targeting for the positive column |
| 3 | Full HTML document wrappers (`<!DOCTYPE>`, `<html>`, `<head>`, `<body>`) rejected | Shopify article body_html must not contain document chrome |
| 4 | `<style>` tags rejected | All styling via CSS classes only |
| 5 | CTA URL validated against `hcs_verified_link_map.json` when link map supplied | Product truth enforcement |
| 6 | FAQ `<details>`/`<summary>` explicitly rejected | FAQ must use static `div.hcs-faq-item` |
| 7 | `hcs-do`/`hcs-dont` icon injection via CSS only | No manual icons in HTML |
| 8 | BlogPosting headline must match H1 exactly | Schema-content consistency |
| 9 | FAQPage schema questions and answers must match visible `h3`/`p` content | Schema-content consistency |
| 10 | Comments containing `</article>` warned against | Validator regex false-positive avoidance |

### Product truth validation (new mode)
The validator now accepts optional product truth arguments:
```
--product-catalog <product_catalog.json>
--collections <collections_inventory.json>
--link-map <hcs_verified_link_map.json>
```
When `--link-map` is provided, all internal `https://hcsgadgets.com/` hrefs are checked against the verified link map. Unverified URLs produce `[product truth]` failures.

---

## Files Created

| File | Purpose |
|------|---------|
| `rules/hcs_html_design_contract_v2.md` | New canonical contract (v2.0) |
| `rules/hcs_article_skeleton_v2.html` | v2 article skeleton — copy-paste starting point |
| `rules/hcs_article_skeleton_v2_test.html` | v2 test fixture — passes validator |

## Files Modified

| File | Change |
|------|--------|
| `rules/hcs_html_design_contract_v1.md` | Status changed to `SUPERSEDED — Do not use for new articles` |
| `tools/shopify_publisher/orin/hcs_html_contract_validator.py` | Upgraded from v1.1 to v2.0 — all new checks above |

## Files NOT Modified (Phase 2 scope only)

- `rules/hcs_html_design_contract_v1.md` — marked superseded but not deleted
- Job 02 BBQ draft — read-only audit only, no edits

---

## v2 Test Fixture Result

**File:** `rules/hcs_article_skeleton_v2_test.html`
**Validator:** v2.0
**Result:** **PASS** ✓
- 42 checks, 42 passed, 0 failures, 0 warnings

---

## Job 02 HTML Audit Result

**File:** `drafts/portable-bbq-chimney-starter-guide-uk-gardens.html`
**Validator:** v2.0
**Result:** **FAIL** ✗
- 42 checks, 40 passed, 4 failures

### Failures

| # | Check | Detail |
|---|-------|--------|
| 1 | `hcs-do h2 has id='good-bad'` | Currently uses `id="good-signs"` — does not match required `id="good-bad"` |
| 2 | `hcs-do h2` missing `id='good-bad'` | Same as above |
| 3 | `Every hcs-table wrapped in hcs-table-scroll` | 0/1 tables wrapped — bare `hcs-table` without `hcs-table-scroll` |
| 4 | `hcs-table-scroll` mandatory | 1 bare `hcs-table` found without `hcs-table-scroll` wrapper |

### Notes on Job 02
- CTA URL (`https://hcsgadgets.com/collections/all-product`) is the verified fallback — no product truth failure
- No `<details>`/`<summary>` — correct for v2
- No inline styles — clean
- No document wrappers — clean
- Schema headline matches H1 — consistent

### Shopify Impact
**None.** This phase does not update Shopify articles. Job 02 must be rebuilt to v2 spec before the next Shopify push.

---

## Migration Proof

```
1. v2 design contract path: clients/hcs_gadgets/content_engine/rules/hcs_html_design_contract_v2.md
2. v1 marked superseded: YES
3. v2 skeleton path: clients/hcs_gadgets/content_engine/rules/hcs_article_skeleton_v2.html
4. validator updated: YES (v1.1 → v2.0)
5. hcs-table-scroll requirement added: YES
6. product truth validation added: YES (--link-map, --product-catalog, --collections)
7. v2 test fixture path: clients/hcs_gadgets/content_engine/rules/hcs_article_skeleton_v2_test.html
8. v2 test result: PASS (42/42 checks)
9. Job 02 v2 result: FAIL (40/42 checks, 4 failures)
10. Job 02 failures:
    - hcs-do h2 uses id="good-signs" instead of id="good-bad"
    - 1 bare hcs-table without hcs-table-scroll wrapper
11. Shopify touched: NO
12. Queue touched: NO
13. Migration report path: clients/hcs_gadgets/content_engine/hcs_html_design_v2_migration_report.md
14. Recommended next step:
    Phase 2 — Rewrite Job 02 to v2 spec:
    a. Add id="good-bad" to hcs-do h2 (change from id="good-signs")
    b. Wrap the hcs-table in <div class="hcs-table-scroll">
    Then re-validate before next Shopify draft push.
```

---

## How to Validate a New Article Against v2

```bash
# Structural validation only
python3 tools/shopify_publisher/orin/hcs_html_contract_validator.py \
  --file clients/hcs_gadgets/content_engine/drafts/your-article.html

# Full validation with product truth
python3 tools/shopify_publisher/orin/hcs_html_contract_validator.py \
  --file clients/hcs_gadgets/content_engine/drafts/your-article.html \
  --product-catalog clients/hcs_gadgets/content_engine/product_catalog.json \
  --collections clients/hcs_gadgets/content_engine/collections_inventory.json \
  --link-map clients/hcs_gadgets/content_engine/hcs_verified_link_map.json
```

---

## Phase 2 Scope (Not Done in Phase 1)

- [ ] Rewrite Job 02 BBQ article to v2 spec
- [ ] Rebuild any other existing drafts to v2 spec
- [ ] Update skeleton test runner to automate v2 validation
- [ ] Update ORIN workflow docs to reference v2 contract
