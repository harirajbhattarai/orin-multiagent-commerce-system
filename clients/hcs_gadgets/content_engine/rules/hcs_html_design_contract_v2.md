# HCS Gadgets — HTML Article Design Contract v2

**Version:** 2.0
**Client:** HCS Gadgets
**Date:** 2026-07-04
**Status:** CURRENT CANONICAL CONTRACT
**Supersedes:** `hcs_html_design_contract_v1.md` (marked SUPERSEDED — do not use for new articles)

---

## Purpose

This contract defines the mandatory HTML structure, class names, and composition rules for all blog articles generated for HCS Gadgets by the ORIN pipeline. All new articles must conform to this contract before being submitted as Shopify drafts.

**No deviations are permitted without updating this contract.**

---

## Core HTML Rules

| Rule | Description |
|------|-------------|
| R1 | Never use inline styles (`style="..."`) |
| R2 | Never use ad-hoc grid or layout divs (`row`, `column`, `col-md-`, `custom-grid`, `layout-grid`, `card-grid`, etc.) |
| R3 | All content must use HCS-approved classes only (see Section 14) |
| R4 | Parent wrapper must be exactly `<article class="hcs-article">` — one per file, no nesting |
| R5 | All reading content must be inside `<section class="hcs-content">` |
| R6 | Every `<table class="hcs-table">` must be wrapped in `<div class="hcs-table-scroll">` — mandatory, no exceptions |
| R7 | Shopify article `body_html` must begin with `<article class="hcs-article">` and end with `</article>` — no HTML document wrappers |

---

## Article HTML Structure

```
<article class="hcs-article">

  <!-- A: HERO HEADER -->
  <section class="hcs-hero">
    <p class="hcs-eyebrow">[Category/Topic Name]</p>
    <h1>[Main Article Title — must match approved title]</h1>
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

  </section>

  <!-- D: DO'S AND DON'TS — when relevant -->
  <div class="hcs-split">
    <div class="hcs-do">
      <h2 id="good-bad">Good signs</h2>
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

  <!-- E: TABLE — when relevant -->
  <section class="hcs-table-wrapper">
    <h2 id="compare">Quick comparison</h2>
    <div class="hcs-table-scroll">
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
    </div>
  </section>

  <!-- F: CHECKLIST — when relevant -->
  <section class="hcs-checklist">
    <h2 id="checklist">Quick checklist</h2>
    <ul>
      <li>Checklist item text...</li>
    </ul>
  </section>

  <!-- G: FAQ — when relevant -->
  <section class="hcs-faq">
    <h2 id="faq">FAQs</h2>
    <div class="hcs-faq-item">
      <h3>Question description text here?</h3>
      <p>Answer paragraph response details...</p>
    </div>
  </section>

  <!-- H: CTA — required on all product-led articles -->
  <section class="hcs-cta">
    <h2>[Product-relevant CTA heading]</h2>
    <p>[Product-relevant CTA text]</p>
    <a href="[VERIFIED URL FROM LINK MAP]" class="hcs-button">[CTA label]</a>
  </section>

  <!-- I: JSON-LD SCHEMA — immediately before closing </article> -->
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    "headline": "[Article Title — must match H1 exactly]",
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
        "name": "[FAQ Question 1 — must match h3 exactly]",
        "acceptedAnswer": {
          "@type": "Answer",
          "text": "[FAQ Answer 1 — must match p exactly]"
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

**Required wrapper:** `<section class="hcs-hero">`
**Required children:**
- `p.hcs-eyebrow` — category or topic label (e.g., "Garden & Outdoor")
- `h1` — article main title, must match the approved article title
- `p.hcs-intro` — 2-3 sentence introduction hook

**Rules:**
- Eyebrow should be a short category/topic label, not a URL or brand name
- Intro should be engaging, benefit-led, and 2-3 sentences max
- Do not put CTA links in the hero
- H1 must match the BlogPosting JSON-LD `headline` exactly

---

### B — Top Split Grid (`hcs-top-grid`)

**Required wrapper:** `<div class="hcs-top-grid">`
**Children:**
- `section.hcs-quick-answer` — direct, snippet-ready answer (1-2 sentences)
- `section.hcs-toc` — table of contents with anchor links

**TOC Rules:**
- Each `<a href="#id-x">` in the TOC must match exactly an `id` attribute on an `<h2>` inside `.hcs-content`
- IDs must be lowercase, hyphen-separated (e.g., `id="safety-tips"`)
- IDs must be unique within the article
- TOC must list all major sections in order
- Do not create dead TOC anchors — every href must resolve to a real h2 id

---

### C — Standard Reading Sections (`hcs-content`)

**Required wrapper:** `<section class="hcs-content">`
**Use for:** Normal article content grouped by topic

**Allowed elements inside `hcs-content`:**
- `h2` (must have unique `id` attribute)
- `h3`
- `p`
- `ul` / `ol`
- `li`
- `blockquote`
- `strong`
- `em`
- `a`

**Forbidden inside `hcs-content`:**
- Row, column, grid, card, or layout divs
- Inline styles
- Custom CSS classes not listed in Section 14

**Rules:**
- Each `h2` inside `hcs-content` must have a unique `id` attribute
- IDs must be lowercase hyphen-separated

---

### D — Do's and Don'ts (`hcs-split`)

**Required wrapper:** `<div class="hcs-split">`
**Children:**
- `div.hcs-do` — positive examples/behaviours
- `div.hcs-dont` — negative examples/behaviours

**Rules:**
- `hcs-do` div must contain `<h2 id="good-bad">` (the id `good-bad` is required)
- Each div must contain an `<h2>` and `<ul>`
- Do NOT manually add check icons, cross icons, emoji bullets, or SVG icons — CSS injects visual markers
- Do NOT use `<details>` or `<summary>` here

---

### E — Table (`hcs-table-wrapper`)

**Required structure:**
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

**Mandatory v2 requirement:** Every `<table class="hcs-table">` must be wrapped in `<div class="hcs-table-scroll">`. This is non-negotiable. Do not output a bare `hcs-table` without the scroll wrapper.

**Rules:**
- Always wrap `<table class="hcs-table">` inside `<div class="hcs-table-scroll">`
- Use `class="hcs-table--highlight"` on `<td>` cells for emphasis (price, recommendation, etc.)
- Use `<thead>` and `<tbody>` correctly
- Do not use inline styles for cell colouring — use `hcs-table--highlight` only

---

### F — Checklist (`hcs-checklist`)

**Required wrapper:** `<section class="hcs-checklist">`
**Children:**
- `h2` with `id` attribute
- `<ul>` containing checklist items

**Rules:**
- Checklist items should be actionable, specific statements
- Use active voice ("Check the battery indicator" not "Battery should be checked")
- h2 must have an `id` matching the TOC anchor
- Do NOT manually insert checkmark symbols — CSS injects visual markers

---

### G — FAQ (`hcs-faq`)

**Required wrapper:** `<section class="hcs-faq">`
**Children:**
- `h2` with `id="faq"` matching TOC
- Multiple `div.hcs-faq-item` children
- Each FAQ item: `h3` (question) + `p` (answer)

**Rules:**
- Do NOT use `<details>` or `<summary>` elements
- Do NOT add custom icons to FAQ questions — CSS handles this
- h3 must be a direct question (ends with `?`)
- Answer must be at least one `<p>` paragraph
- `h3` questions become FAQPage schema `name` fields
- FAQPage JSON-LD `mainEntity` questions and answers must match visible h3/p content exactly

---

### H — CTA (`hcs-cta`)

**Required wrapper:** `<section class="hcs-cta">`
**Children:**
- `h2`
- `p` (description text)
- `a.hcs-button` (button link)

**Rules:**
- Button must use exactly `class="hcs-button"` — no other classes
- Button href must come from `hcs_verified_link_map.json` — never invent a URL
- If no directly relevant verified product/collection URL exists, use `https://hcsgadgets.com/collections/all-product`
- Do not use `https://hcsgadgets.com/collections/all` (it does not exist)
- h2 should be benefit-led, not brand-first
- Do not add multiple CTA buttons

---

### I — JSON-LD Schema

**Required placement:** Immediately before closing `</article>`
**Required schemas:**
1. `BlogPosting` — always required
2. `FAQPage` — required when article contains an `hcs-faq` section

**BlogPosting fields:**
- `headline`: Exact article title — must match the H1 exactly
- `datePublished`: ISO 8601 date (article publish date)
- `dateModified`: ISO 8601 date (last update)
- `author.name`: "HCS Gadgets"
- `publisher.name`: "HCS Gadgets"
- `publisher.url`: "https://hcsgadgets.com"
- `url`: Canonical URL
- `description`: Meta description (150-160 chars)

**FAQPage fields:**
- `mainEntity`: Array of Question objects
- `name`: Exact question text from h3 (no extra punctuation changes)
- `text`: Exact answer text from p

**Schema placement warning:** Do not place comments containing a literal closing `</article>` string before the closing tag — the validator regex may incorrectly detect it as the actual closing article tag.

---

## Forbidden Patterns

| Pattern | Why Forbidden |
|---------|--------------|
| `style="..."` | Inline styles break design system |
| `class="row"`, `class="col-*"`, `class="column"` | Custom grid classes |
| `class="custom-grid"`, `class="layout-grid"`, `class="card-grid"` | Ad-hoc layout divs |
| `<details>`, `<summary>` | FAQ must use div/h3/p static cards |
| Custom icons (✓, ✗, 🗸, ❌, SVG icons) | Icons injected by CSS |
| `<!DOCTYPE html>`, `<html>`, `<head>`, `<body>` | Shopify article must not contain document wrappers |
| `<style>` tags | All styling via CSS classes |
| Bare `<table class="hcs-table">` without `hcs-table-scroll` wrapper | v2 mandatory — CSS scroll container |
| `hcs-button` on `<button>` element | CTA must use `<a class="hcs-button">` |
| Unverified collection URLs in CTA | Must use `hcs_verified_link_map.json` URLs only |
| Comments containing `</article>` | May break validator regex |

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| v1 | 2026-07-01 | Initial locked contract |
| v2 | 2026-07-04 | Mandatory `hcs-table-scroll` wrapper; document wrapper removal; CTA URL product truth rule; FAQ static cards only; schema-content consistency; comment-`</article>` warning |
