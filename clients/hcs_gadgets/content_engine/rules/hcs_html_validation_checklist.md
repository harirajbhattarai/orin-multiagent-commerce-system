# HCS Gadgets — HTML Validation Checklist

**Contract:** hcs_html_design_contract_v1.md
**Validator script:** `tools/shopify_publisher/orin/hcs_html_contract_validator.py`
**Updated:** 2026-07-01

---

## How to Use This Checklist

Run the validator before submitting any article as a Shopify draft:

```bash
python3 tools/shopify_publisher/orin/hcs_html_contract_validator.py \
  --file clients/hcs_gadgets/content_engine/drafts/[article-name].html
```

For automated pre-flight, use the `--strict` flag:

```bash
python3 tools/shopify_publisher/orin/hcs_html_contract_validator.py \
  --file [path] --strict
```

---

## Pre-Submission Validation Checklist

Complete ALL items before submitting an article draft.

### Structural Checks

| # | Check | Expected | Why |
|---|-------|---------|-----|
| 1 | `article.hcs-article` wrapper exists | Exactly one `<article class="hcs-article">` | Contract R4 — mandatory wrapper |
| 2 | `section.hcs-hero` exists | Exactly one | Required hero header |
| 3 | `section.hcs-hero` contains `h1` | At least one `h1` inside hero | Hero must have title |
| 4 | `section.hcs-hero` contains `p.hcs-eyebrow` | At least one | Category label |
| 5 | `section.hcs-hero` contains `p.hcs-intro` | At least one | Introduction hook |
| 6 | `div.hcs-top-grid` exists | Exactly one | Top split grid |
| 7 | `hcs-top-grid` contains `section.hcs-quick-answer` | At least one | Snippet-ready answer |
| 8 | `hcs-top-grid` contains `section.hcs-toc` | At least one | Table of contents |
| 9 | `section.hcs-content` exists | At least one | Mandatory reading content wrapper |
| 10 | `section.hcs-content` contains at least one `h2` | At least one | Content must have headings |
| 11 | `section.hcs-cta` exists | At least one | Mandatory CTA |
| 12 | `section.hcs-cta` contains `a.hcs-button` | At least one | Button link |

### FAQ Checks (if FAQs used)

| # | Check | Expected | Why |
|---|-------|---------|-----|
| 13 | `section.hcs-faq` exists when FAQs present | If FAQ content, section must exist | FAQ must be in dedicated section |
| 14 | `hcs-faq` does NOT contain `<details>` | Zero `<details>` or `<summary>` elements | Contract: must use div/h3/p |
| 15 | `hcs-faq-item` children use `h3` + `p` | Each FAQ item: `h3` question + `p` answer | FAQ structure contract |
| 16 | FAQ `h3` questions end with `?` | All FAQ h3 elements end with `?` | Question format for schema |
| 17 | FAQPage JSON-LD present when FAQs exist | If `hcs-faq` present, schema must exist | Required schema for SEO |

### Table Checks

| # | Check | Expected | Why |
|---|-------|---------|-----|
| 18 | Tables wrapped in `section.hcs-table-wrapper` | All `<table>` elements wrapped | Table wrapper contract |
| 19 | Tables use `table.hcs-table` | All tables have `class="hcs-table"` | Required table class |
| 20 | Highlighted cells use `hcs-table--highlight` | No inline `style=` for cell colour | R1 — no inline styles |

### Do's/Don'ts Checks

| # | Check | Expected | Why |
|---|-------|---------|-----|
| 21 | `div.hcs-split` children are `div.hcs-do` and `div.hcs-dont` | Only these children inside `.hcs-split` | Required structure |
| 22 | No custom icon markup inside `hcs-do` or `hcs-dont` | No `✓`, `✗`, `✔`, `✘`, emoji, or icon HTML | CSS handles icons |

### TOC / Anchor Link Checks

| # | Check | Expected | Why |
|---|-------|---------|-----|
| 23 | All `h2` elements inside `.hcs-content` have `id` attributes | All `h2` inside `.hcs-content` have `id` | TOC anchor targets |
| 24 | All `id` attributes on `h2` are unique | No duplicate `id` values | HTML validity |
| 25 | All TOC `href="#id"` links resolve to existing `h2#id` | Every TOC anchor has a matching `h2` target | Functional navigation |
| 26 | IDs are lowercase hyphen-separated | e.g., `id="safety-tips"` not `id="Safety Tips"` | URL compatibility |

### JSON-LD Schema Checks

| # | Check | Expected | Why |
|---|-------|---------|-----|
| 27 | `BlogPosting` JSON-LD exists | Exactly one `BlogPosting` schema block | Required for all articles |
| 28 | `BlogPosting` is inside `<script type="application/ld+json">` | Correct script tag type | Schema specification |
| 29 | `BlogPosting` has `headline` | Non-empty string | Required field |
| 30 | `BlogPosting` has `datePublished` | ISO 8601 date format | Required field |
| 31 | `BlogPosting` has `dateModified` | ISO 8601 date format | Required field |
| 32 | `BlogPosting` has `author.name` | "HCS Gadgets" | Required field |
| 33 | `BlogPosting` has `publisher.name` | "HCS Gadgets" | Required field |
| 34 | `FAQPage` schema has `mainEntity` array | Array of Question objects | Required for FAQPage |
| 35 | FAQPage `name` matches `h3` question text exactly | Schema Q must equal HTML Q | Google rich result validation |
| 36 | FAQPage `text` matches `p` answer text exactly | Schema A must equal HTML A | Google rich result validation |

### Forbidden Pattern Checks

| # | Check | Expected | Why |
|---|-------|---------|-----|
| 37 | No `style="..."` attributes anywhere | Zero inline style attributes | Contract R1 |
| 38 | No `class="row"` or `class="col-*"` | Zero Bootstrap/grid classes | Contract R2 |
| 39 | No `class="custom-grid"` or similar | Zero ad-hoc layout classes | Contract R2 |
| 40 | No `<details>` or `<summary>` elements | Zero | FAQ must use div structure |
| 41 | `BlogPosting` schema placed before `</article>` | Schema inside article wrapper | HTML validity |
| 42 | `FAQPage` schema placed before `</article>` | Schema inside article wrapper | HTML validity |

### CTA Checks

| # | Check | Expected | Why |
|---|-------|---------|-----|
| 43 | CTA link uses `class="hcs-button"` | Exactly `class="hcs-button"` | Contract: required button class |
| 44 | CTA link is `<a>` not `<button>` | `<a href="..." class="hcs-button">` | Button must be anchor element |
| 45 | CTA href is valid HCS Gadgets URL | Starts with `https://hcsgadgets.com/` | Brand link requirement |

---

## Quick Pass / Fail Summary

| Status | Meaning |
|--------|---------|
| ✅ All 45 checks pass | Ready for Shopify draft submission |
| ⚠️ Warnings only | Review warnings before submission |
| ❌ Any hard failure | Fix failures before submission |
| ❌ Check 37 (inline styles) | Hard failure — never bypass |
| ❌ Check 41-42 (schema placement) | Hard failure — schema must be inside article |
| ❌ Check 38-40 (forbidden patterns) | Hard failure — never bypass |
