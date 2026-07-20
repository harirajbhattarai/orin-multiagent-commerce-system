# Job 02 HTML v2 Audit

**Article:** Portable BBQ and Chimney Starter Guide: Simple Gear for UK Gardens
**File:** `clients/hcs_gadgets/content_engine/drafts/portable-bbq-chimney-starter-guide-uk-gardens.html`
**Audit date:** 2026-07-04
**Validator:** v2.0 (`hcs_html_contract_validator.py`)
**Audit status:** READ-ONLY — No edits made

---

## Summary

The Job 02 article was written against HCS HTML Design Contract v1 and predates Design System v2. When validated against v2, it **fails** with **4 failures**.

**No Shopify articles were updated.** This is a read-only audit.

---

## v2 Validation Result

```
Validator: HCS HTML Contract Validator v2.0
Contract: hcs_html_design_contract_v2.md
Total checks: 42
Passed: 40
Failures: 4
Warnings: 0
RESULT: FAIL
```

---

## Failures

### Failure 1 — `hcs-do h2 has id='good-bad'`

| Field | Value |
|-------|-------|
| Expected | `id="good-bad"` on the h2 inside `div.hcs-do` |
| Actual | `id="good-signs"` |
| Location | Line in `div.hcs-do` — `<h2 id="good-signs">Good signs</h2>` |
| Fix | Change `id="good-signs"` to `id="good-bad"` |

**Why this matters:** v2 requires the positive do/don't split h2 to use `id="good-bad"` as the canonical anchor. The old v1 contract used `id="good-signs"` which is non-standard.

---

### Failure 2 — `hcs-do h2` missing `id='good-bad'` (same issue)

This is the same failure expressed twice in different validator checks.

---

### Failure 3 — `Every hcs-table wrapped in hcs-table-scroll`

| Field | Value |
|-------|-------|
| Expected | Every `<table class="hcs-table">` wrapped in `<div class="hcs-table-scroll">` |
| Actual | 0/1 tables wrapped |
| Location | The comparison table section |

**Current structure (fails v2):**
```html
<section class="hcs-table-wrapper">
  <h2 id="compare">Quick comparison</h2>
  <table class="hcs-table">
    ...
  </table>
</section>
```

**Required v2 structure:**
```html
<section class="hcs-table-wrapper">
  <h2 id="compare">Quick comparison</h2>
  <div class="hcs-table-scroll">
    <table class="hcs-table">
      ...
    </table>
  </div>
</section>
```

**Why this matters:** The `hcs-table-scroll` div is the mandatory CSS scroll container for table overflow. Without it, tables may break layout on mobile or narrow viewports.

---

### Failure 4 — `hcs-table-scroll` mandatory (same issue, expressed differently)

Same as Failure 3 — 1 bare `hcs-table` found without the mandatory `hcs-table-scroll` wrapper.

---

## What Is Already Correct (40 checks passed)

| Check | Status |
|-------|--------|
| Exactly one `article.hcs-article` wrapper | ✓ |
| No HTML document wrappers (DOCTYPE/html/head/body) | ✓ |
| No `<style>` tags | ✓ |
| No inline `style=` attributes | ✓ |
| `section.hcs-hero` with h1, hcs-eyebrow, hcs-intro | ✓ |
| `div.hcs-top-grid` with `hcs-quick-answer` and `hcs-toc` | ✓ |
| TOC links resolve to real h2#id targets | ✓ |
| `section.hcs-content` exists | ✓ |
| All h2 inside hcs-content have id attributes | ✓ |
| h2 ids are unique | ✓ |
| IDs are lowercase hyphen-separated | ✓ |
| `div.hcs-split` with `hcs-do` and `hcs-dont` | ✓ |
| No custom icon markup in hcs-do/hcs-dont | ✓ |
| `hcs-checklist` with `<ul>` | ✓ |
| `section.hcs-faq` with `h3` + `p` per item | ✓ |
| No `<details>` or `<summary>` in FAQ | ✓ |
| FAQ h3 questions end with `?` | ✓ |
| `section.hcs-cta` with `a.hcs-button` | ✓ |
| CTA button is `<a>` not `<button>` | ✓ |
| CTA href uses `https://hcsgadgets.com/collections/all-product` (verified fallback) | ✓ |
| No forbidden grid/layout classes | ✓ |
| `BlogPosting` JSON-LD inside article wrapper | ✓ |
| `FAQPage` JSON-LD inside article wrapper | ✓ |
| BlogPosting headline matches H1 exactly | ✓ |
| FAQPage schema consistent with visible FAQ content | ✓ |
| Schema inside article wrapper | ✓ |

---

## Product Truth Check

When validated with `--link-map clients/hcs_gadgets/content_engine/hcs_verified_link_map.json`:

**CTA URL:** `https://hcsgadgets.com/collections/all-product` — this is the verified fallback URL confirmed in the link map. No product truth failure.

**Internal links:** The article does not contain internal product links — it only links to the all-product collection in the CTA. No broken link failures.

---

## Required Actions Before Next Shopify Push

| Priority | Action | Detail |
|----------|--------|--------|
| P1 | Wrap table in `hcs-table-scroll` | Add `<div class="hcs-table-scroll">` wrapper around the `hcs-table` |
| P1 | Fix `hcs-do` h2 id | Change `id="good-signs"` to `id="good-bad"` |
| — | Re-validate after fixes | Run validator v2.0 and confirm PASS before Shopify push |

**Total edits required:** 2 (both are simple attribute changes)

---

## Phase Restriction

**This audit did not edit the file.** Per migration rules:
- No Shopify article updates in this phase
- No editing queue statuses
- No publishing
- No enabling cron
- No generating new articles

Job 02 rewrite to v2 spec is a **Phase 2 action**.
