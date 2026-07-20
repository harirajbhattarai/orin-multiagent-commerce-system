# Hoverboard Store — HTML/CSS Blog Design System

The Shopify theme already includes custom article styling in article.css.

All generated blog articles must use the existing Hoverboard Store HTML class system.

## Main Wrapper

Use:

<div class="hs-article">
  <div class="hs-container">
    [article content]
  </div>
</div>

## Supported CSS Classes

Use only these approved article classes:

- hs-article
- hs-container
- hs-meta
- hs-quick-answer
- hs-highlights
- hs-highlight
- hs-note
- hs-table-wrap
- hs-table
- hs-faq-item
- hs-faq-q
- hs-faq-a
- hs-authority
- hs-related
- hs-cta
- hs-btn
- hs-products
- hs-products-grid
- hs-product-card
- hs-product-badges
- hs-product-badge
- hs-product-actions
- hs-product-link
- hs-compare-grid
- hs-compare-card
- hs-compare-meta
- hs-compare-pill
- hs-proscons
- hs-pros
- hs-cons

## Required Blog Structure

Every full blog article should follow this structure:

1. SEO metadata comment
2. hs-article wrapper
3. hs-container wrapper
4. H1
5. Updated date/meta line
6. Quick answer box
7. Intro paragraphs
8. Highlights block
9. H2/H3 sections
10. Notes/warnings where useful
11. Tables where useful
12. Pros/cons blocks where useful
13. Product recommendation blocks where useful
14. FAQ section
15. Related guides
16. CTA
17. Authority section

## Quick Answer Block

<div class="hs-quick-answer">
  <p><strong>Quick Answer:</strong> [short answer]</p>
</div>

## Highlights Block

<div class="hs-highlights">
  <div class="hs-highlight">[Highlight 1]</div>
  <div class="hs-highlight">[Highlight 2]</div>
  <div class="hs-highlight">[Highlight 3]</div>
  <div class="hs-highlight">[Highlight 4]</div>
</div>

## Note Block

<div class="hs-note">
  <p><strong>Important Note:</strong> [verified note]</p>
</div>

## Table Block

<div class="hs-table-wrap">
  <table class="hs-table">
    <thead>
      <tr>
        <th>[Column]</th>
        <th>[Column]</th>
        <th>[Column]</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>[Data]</td>
        <td>[Data]</td>
        <td>[Data]</td>
      </tr>
    </tbody>
  </table>
</div>

## FAQ Block

<div class="hs-faq-item">
  <h3 class="hs-faq-q">[Question]</h3>
  <p class="hs-faq-a">[Answer]</p>
</div>

## Related Guides Block

<div class="hs-related">
  <h2>Related Guides</h2>
  <ul>
    <li><a href="[URL]">[Guide Title]</a></li>
    <li><a href="[URL]">[Guide Title]</a></li>
    <li><a href="[URL]">[Guide Title]</a></li>
  </ul>
</div>

## CTA Block

<div class="hs-cta">
  <p>[CTA sentence]</p>
  <a href="[Collection URL]" class="hs-btn">[CTA Button]</a>
</div>

## Product Recommendation Block

<div class="hs-products">
  <div class="hs-products-grid">
    <div class="hs-product-card">
      <h3>[Product Name]</h3>
      <p>[Short product description]</p>
      <div class="hs-product-badges">
        <span class="hs-product-badge">[Badge]</span>
        <span class="hs-product-badge">[Badge]</span>
      </div>
      <div class="hs-product-actions">
        <a href="[Product URL]" class="hs-product-link">View Product</a>
      </div>
    </div>
  </div>
</div>

## Pros / Cons Block

<div class="hs-proscons">
  <div class="hs-pros">
    <h3>✅ Pros</h3>
    <ul>
      <li>[Pro]</li>
    </ul>
  </div>
  <div class="hs-cons">
    <h3>❌ Cons</h3>
    <ul>
      <li>[Con]</li>
    </ul>
  </div>
</div>

## Authority Block

<div class="hs-authority">
  <p><strong>About the Author:</strong> Hoverboard Store Team helps UK shoppers make informed decisions about hoverboards, hoverkarts, electric scooters and rideables. Guides should be reviewed and updated when product data or UK guidance changes.</p>
</div>

## Rules

- Do not generate new CSS.
- Do not invent new class names unless requested.
- Use the existing article.css class system.
- Keep HTML clean and Shopify-ready.
- Avoid inline styles.
- Avoid scripts.
- Do not include unsupported legal, safety, delivery, warranty, certification, price, stock or return claims.
- Put unverified claims under Verification Needed, not inside the final article body.

## Shopify Theme FAQ Schema Compatibility Rule

The Shopify theme automatically creates FAQPage schema from article FAQ blocks.

For Hoverboard Store articles, every FAQ item must use this exact format:

<div class="hs-faq-item">
  <div class="hs-faq-q">Question text only</div>
  <div class="hs-faq-a">Answer text only</div>
</div>

Do NOT use:
- <h3 class="hs-faq-q">
- <p class="hs-faq-a">

Reason:
The Shopify theme parser expects div.hs-faq-q and div.hs-faq-a. If ORIN uses h3/p, Google Rich Results may show question and answer merged together.

## Final FAQ Schema Rule for Hoverboard Store

Use the Shopify theme FAQ schema system, not manual FAQPage JSON-LD.

For every FAQ item, ORIN must output:

<div class="hs-faq-item">
  <div class="hs-faq-q">Question text only</div>
  <div class="hs-faq-a">Answer text only</div>
</div>

Do not use:
- <h3 class="hs-faq-q">
- <p class="hs-faq-a">
- <div class="faq-item">
- manual FAQPage JSON-LD inside article HTML

Reason:
The Shopify theme already creates FAQPage schema from hs-faq-item blocks. The theme expects div.hs-faq-q and div.hs-faq-a.
