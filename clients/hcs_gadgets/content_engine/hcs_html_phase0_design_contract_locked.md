# HCS Gadgets HTML Phase 0 — Design Contract Lock

**Date:** 2026-07-01
**Phase:** HTML Phase 0
**Client:** HCS Gadgets
**Status:** LOCKED

---

## Contract Lock Summary

| Item | Status |
|------|--------|
| HCS HTML Design Contract | ✅ v1 LOCKED |
| Article Skeleton | ✅ v1 CREATED |
| Validation Checklist | ✅ CREATED |
| Validator Script | ✅ v1.1 CREATED + VALIDATED |
| Test Fixture | ✅ PASSES ALL 42 CHECKS |
| Shopify touched | ❌ NO |
| Queue touched | ❌ NO |

---

## Files Created

| File | Purpose |
|------|---------|
| `rules/hcs_html_design_contract_v1.md` | Canonical design contract — mandatory structure, classes, and rules |
| `rules/hcs_article_skeleton_v1.html` | Reusable article HTML skeleton — copy and fill in placeholders |
| `rules/hcs_html_validation_checklist.md` | Human-readable pre-submission validation checklist |
| `tools/shopify_publisher/orin/hcs_html_contract_validator.py` | Automated validator script (v1.1) |
| `rules/hcs_article_skeleton_test.html` | Test fixture — passes all 42 checks |

---

## Validator Results

```
HCS Gadgets — HTML Contract Validator v1.1
File: rules/hcs_article_skeleton_test.html
Strict mode: False

Total checks: 42
Passed: 42
Failures: None

RESULT: PASS — Article conforms to HCS HTML Design Contract v1
```

---

## Contract Rules Summary

### Mandatory Structure
```
<article class="hcs-article">
  <section class="hcs-hero">          ← h1, p.hcs-eyebrow, p.hcs-intro
  <div class="hcs-top-grid">        ← section.hcs-quick-answer + section.hcs-toc
  <section class="hcs-content">     ← all reading content
    [content h2s with ids matching TOC]
    <div class="hcs-split">        ← hcs-do + hcs-dont
    <section class="hcs-table-wrapper"><table class="hcs-table">...</table></section>
    <section class="hcs-checklist"> <ul><li>...</li></ul>
    <section class="hcs-faq">      ← div.hcs-faq-item: h3 + p pairs
    <section class="hcs-cta">     ← h2 + p + a.hcs-button
  </section>
  <script type="application/ld+json"> BlogPosting schema </script>
  <script type="application/ld+json"> FAQPage schema (if FAQs) </script>
</article>
```

### Forbidden Patterns
- `style="..."` — inline styles
- `row`, `col-*`, `custom-grid` — ad-hoc layout classes
- `<details>`, `<summary>` — FAQ must use div/h3/p
- Custom icon HTML in hcs-do/hcs-dont

### Required Classes
| Element | Class |
|---------|-------|
| Article wrapper | `hcs-article` |
| Hero | `hcs-hero` |
| Eyebrow label | `hcs-eyebrow` |
| Intro paragraph | `hcs-intro` |
| Top grid | `hcs-top-grid` |
| Quick answer | `hcs-quick-answer` |
| Table of contents | `hcs-toc` |
| Reading content wrapper | `hcs-content` |
| Do's/Don'ts split | `hcs-split` |
| Do's column | `hcs-do` |
| Don'ts column | `hcs-dont` |
| Table wrapper | `hcs-table-wrapper` |
| Table | `hcs-table` |
| Highlighted cell | `hcs-table--highlight` |
| Checklist | `hcs-checklist` |
| FAQ | `hcs-faq` |
| FAQ item | `hcs-faq-item` |
| CTA | `hcs-cta` |
| CTA button | `hcs-button` |

---

## How to Use the Skeleton

1. Copy `hcs_article_skeleton_v1.html` to the drafts folder
2. Replace all `[PLACEHOLDER]` values with actual content
3. Add `id` attributes to all `h2` elements inside `.hcs-content`
4. Ensure TOC links match those `id` attributes exactly
5. Update JSON-LD with real article title, date, and URL
6. Run validator: `python3 tools/shopify_publisher/orin/hcs_html_contract_validator.py --file [draft-path]`
7. Fix any failures before submitting as Shopify draft

---

## Validator Usage

```bash
# Basic check
python3 tools/shopify_publisher/orin/hcs_html_contract_validator.py \
  --file clients/hcs_gadgets/content_engine/drafts/my-article.html

# Strict mode (warnings treated as failures)
python3 tools/shopify_publisher/orin/hcs_html_contract_validator.py \
  --file my-article.html --strict

# JSON output for CI/automation
python3 tools/shopify_publisher/orin/hcs_html_contract_validator.py \
  --file my-article.html --json
```

---

## Output Proof

| # | Item | Result |
|---|------|--------|
| 1 | Design contract path | ✅ `rules/hcs_html_design_contract_v1.md` |
| 2 | Skeleton path | ✅ `rules/hcs_article_skeleton_v1.html` |
| 3 | Validation checklist path | ✅ `rules/hcs_html_validation_checklist.md` |
| 4 | Validator script path | ✅ `tools/shopify_publisher/orin/hcs_html_contract_validator.py` |
| 5 | Test fixture path | ✅ `rules/hcs_article_skeleton_test.html` |
| 6 | Validator result | ✅ **PASS — 42/42 checks passed** |
| 7 | Shopify touched | ❌ NO |
| 8 | Queue touched | ❌ NO |
| 9 | HCS HTML Phase 0 passed | ✅ **YES** |
