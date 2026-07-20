# HCS Gadgets — HTML Article Design Contract v1

**Version:** 1.0
**Client:** HCS Gadgets
**Date:** 2026-07-01
**Status:** SUPERSEDED — Do not use for new articles. Use `hcs_html_design_contract_v2.md`

---

## Purpose

This contract defines the mandatory HTML structure, class names, and composition rules for all blog articles generated for HCS Gadgets by the ORIN pipeline. All articles must conform to this contract before being submitted as Shopify drafts.

**No deviations are permitted without updating this contract.**

---

## Core HTML Rules

| Rule | Description |
|------|-------------|
| R1 | Never use inline styles (`style="..."`) |
| R2 | Never use ad-hoc grid or layout divs (`row`, `column`, `col-md-`, `custom-grid`, etc.) |
| R3 | All content must use HCS-approved classes only |
| R4 | Parent wrapper must be `<article class="hcs-article">` |
| R5 | All reading content must be inside `<section class="hcs-content">` |

---

## Article HTML Structure

```
<article class="hcs-article">

  <!-- A: HERO HEADER -->
  <section class="hcs-hero">
    <p class="hcs-eyebrow">[Category/Topic Name]</p>
    <h1>[Main Article Title]</h1>
    <p class="hcs-intro">[Engaging 2-3 sentence introduction hook]</p>
  </section>

  <!-- B: TOP SPLIT GRID -->
  <div class="hcs-top-grid">
    <section class="hcs-quick-answer">
      <h2>Quick answer</h2>
      <p>[Direct answer targeting featured snippets]</p>
    </section>
    <section class="hcs-toc">
      <h2>In this guide</h2>
      <ul>
        <li><a href="#id-1">Jump Link Label 1</a></li>
        <li><a href="#id-2">Jump Link Label 2</a></li>
      </ul>
    </section>
  </div>

  <!-- C: MAIN READING CONTENT -->
  <section class="hcs-content">

    <!-- Regular content: h2, h3, paragraphs, lists, blockquotes -->

    <!-- D: DO'S AND DON'TS -->
    <div class="hcs-split">
      <div class="hcs-do">
        <h2 id="good-signs">Good signs</h2>
        <ul>
          <li>List item text...</li>
        </ul>
      </div>
      <div class="hcs-dont">
        <h2>Things to avoid</h2>
        <ul>
          <li>List item text...</li>
        </ul>
      </div>
    </div>

    <!-- E: TABLE -->
    <section class="hcs-table-wrapper">
      <h2 id="compare">Quick comparison</h2>
      <table class="hcs-table">
        <thead>
          <tr>
            <th>Category</th>
            <th>Budget Range</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Item</td>
            <td class="hcs-table--highlight">£10–£30</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- F: CHECKLIST -->
    <section class="hcs-checklist">
      <h2 id="checklist">Quick checklist</h2>
      <ul>
        <li>Identify target tasks...</li>
      </ul>
    </section>

    <!-- G: FAQ -->
    <section class="hcs-faq">
      <h2 id="faq">FAQs</h2>
      <div class="hcs-faq-item">
        <h3>Question description text here?</h3>
        <p>Answer paragraph response details...</p>
      </div>
    </section>

    <!-- H: CTA -->
    <section class="hcs-cta">
      <h2>Find practical home gadgets at HCS Gadgets</h2>
      <p>Browse useful home and lifestyle products designed to make daily tasks easier.</p>
      <a href="https://hcsgadgets.com/collections/all" class="hcs-button">Explore HCS Gadgets</a>
    </section>

  </section><!-- end hcs-content -->

  <!-- I: JSON-LD SCHEMA — before closing </article> -->
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    "headline": "[Article Title]",
    "datePublished": "[YYYY-MM-DD]",
    "dateModified": "[YYYY-MM-DD]",
    "author": {
      "@type": "Organization",
      "name": "HCS Gadgets"
    },
    "publisher": {
      "@type": "Organization",
      "name": "HCS Gadgets",
      "url": "https://hcsgadgets.com"
    },
    "url": "[Canonical URL]",
    "description": "[Meta description]"
  }
  </script>

  <!-- FAQPage schema — only if FAQs exist in article -->
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      {
        "@type": "Question",
        "name": "[FAQ Question 1]",
        "acceptedAnswer": {
          "@type": "Answer",
          "text": "[FAQ Answer 1]"
        }
      }
    ]
  }
  </script>

</article>
```

---

## Section Definitions

### A — Hero Header (`hcs-hero`)

**Required classes:** `section hcs-hero`
**Required children:**
- `p.hcs-eyebrow` — category or topic label (e.g., "Garden & Outdoor")
- `h1` — article main title
- `p.hcs-intro` — 2-3 sentence introduction hook

**Rules:**
- Eyebrow should be a short category/topic label, not a URL or brand name
- Intro should be engaging, benefit-led, and 2-3 sentences max
- Do not put CTA links in the hero

---

### B — Top Split Grid (`hcs-top-grid`)

**Required classes:** `div hcs-top-grid`
**Children:**
- `section.hcs-quick-answer` — direct, snippet-ready answer (1-2 sentences)
- `section.hcs-toc` — table of contents with anchor links

**TOC Rules:**
- Each `<a href="#id-x">` in the TOC must match exactly an `id` attribute on an `<h2>` inside `.hcs-content`
- IDs must be lowercase, hyphen-separated (e.g., `id="safety-tips"`)
- IDs must be unique within the article
- TOC must list all major sections in order

---

### C — Do's and Don'ts (`hcs-split`)

**Required classes:** `div hcs-split`
**Children:**
- `div hcs-do` — positive examples/behaviours
- `div hcs-dont` — negative examples/behaviours

**Rules:**
- Do not use custom icon markup — CSS injects icons automatically
- Each div must contain an `<h2>` and `<ul>`
- The `hcs-do` h2 must have an `id` for anchor linking (e.g., `id="good-signs"`)

---

### D — Table (`hcs-table-wrapper`)

**Required classes:** `section hcs-table-wrapper` wrapping `table hcs-table`
**Rules:**
- Always wrap `<table class="hcs-table">` inside `<section class="hcs-table-wrapper">`
- Use `class="hcs-table--highlight"` on `<td>` cells for emphasis (price, recommendation, etc.)
- Use `<thead>` and `<tbody>` correctly
- Do not use inline styles for cell colouring — use `hcs-table--highlight` only

---

### E — Checklist (`hcs-checklist`)

**Required classes:** `section hcs-checklist`
**Children:**
- `h2` with `id` attribute
- `<ul>` containing checklist items

**Rules:**
- Checklist items should be actionable, specific statements
- Use active voice ("Check the battery indicator" not "Battery should be checked")
- h2 must have an `id` matching the TOC anchor

---

### F — FAQ (`hcs-faq`)

**Required classes:** `section hcs-faq`
**Children:**
- `h2` with `id="faq"` matching TOC
- Multiple `div hcs-faq-item` children
- Each FAQ item: `h3` (question) + `p` (answer)

**Rules:**
- Do NOT use `<details>` or `<summary>` elements
- Do NOT add custom icons to FAQ questions — CSS handles this
- h3 must be a direct question (ends with `?`)
- Answer must be a single `<p>` paragraph
- `h3` questions become FAQPage schema `name` fields

---

### G — CTA (`hcs-cta`)

**Required classes:** `section hcs-cta`
**Children:**
- `h2`
- `p` (description text)
- `a.hcs-button` (button link)

**Rules:**
- Button must use exactly `class="hcs-button"` — no other classes
- Button href must be a valid HCS Gadgets URL
- h2 should be benefit-led, not brand-first
- Do not add multiple CTA buttons

---

### H — JSON-LD Schema

**Required placement:** Immediately before closing `</article>`
**Required schemas:**
1. `BlogPosting` — always required
2. `FAQPage` — required when article contains an `hcs-faq` section

**BlogPosting fields:**
- `headline`: Exact article title
- `datePublished`: ISO 8601 date (article publish date)
- `dateModified`: ISO 8601 date (last update)
- `author.name`: "HCS Gadgets"
- `publisher.name`: "HCS Gadgets"
- `publisher.url`: "https://hcsgadgets.com"
- `url`: Canonical URL
- `description`: Meta description (150-160 chars)

**FAQPage fields:**
- `mainEntity`: Array of Question objects
- `name`: Exact question text from h3
- `text`: Exact answer text from p

---

## Forbidden Patterns

| Pattern | Why Forbidden |
|---------|--------------|
| `style="..."` | Inline styles break design system |
| `class="row"`, `class="col-*"` | Custom grid classes |
| `<details>`, `<summary>` | FAQ must use div/h3/p |
| Custom icons in HTML | Icons injected by CSS |
| `class="hcs-article"` on non-`<article>` element | Wrapper must be `<article>` |
| `<section class="hcs-content">` missing | All reading content must be inside this |
| JSON-LD after `</article>` | Schema must be inside article wrapper |

---

## Validation Checklist Summary

Before any article is submitted as a Shopify draft, ALL items must pass:

- [ ] `article.hcs-article` wrapper exists
- [ ] `section.hcs-hero` exists with `h1`, `p.hcs-eyebrow`, `p.hcs-intro`
- [ ] `div.hcs-top-grid` exists with `hcs-quick-answer` and `hcs-toc`
- [ ] `section.hcs-content` exists and contains all content sections
- [ ] `section.hcs-cta` exists with `h2`, `p`, `a.hcs-button`
- [ ] `section.hcs-faq` exists when FAQs are used
- [ ] `hcs-faq` h3 questions end with `?`
- [ ] `hcs-faq` does NOT use `<details>` or `<summary>`
- [ ] TOC anchor links match `id` attributes on target `h2` elements inside `.hcs-content`
- [ ] `hcs-table-wrapper` and `hcs-table` used for all tables
- [ ] `hcs-table--highlight` used for emphasised table cells (not inline styles)
- [ ] `hcs-split` uses `hcs-do` and `hcs-dont` children
- [ ] `hcs-checklist` uses `ul li` structure
- [ ] `BlogPosting` JSON-LD exists before `</article>`
- [ ] `FAQPage` JSON-LD exists when FAQs are present
- [ ] No inline `style="..."` attributes anywhere
- [ ] No forbidden grid/column/row classes
- [ ] `hcs-button` class used on CTA link (not `<button>` or other elements)
- [ ] All `h2` elements inside `.hcs-content` have unique `id` attributes
- [ ] All TOC links resolve to existing `id` attributes

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-07-01 | Initial locked contract |
