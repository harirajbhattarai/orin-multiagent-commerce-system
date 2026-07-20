# HCS Gadgets HTML Article Template

Use this structure for HCS blog articles.

Important:
- Use wrapper class: hcs-article
- Do not use Hoverboard Store wrapper/class names.
- Keep the design clean, marketplace-friendly, and practical.

## Base HTML Structure

<article class="hcs-article">

  <section class="hcs-hero">
    <p class="hcs-eyebrow">HCS Gadgets Guide</p>
    <h1>{{ARTICLE_TITLE}}</h1>
    <p class="hcs-intro">{{SHORT_INTRO}}</p>
  </section>

  <section class="hcs-quick-answer">
    <h2>Quick answer</h2>
    <p>{{QUICK_ANSWER}}</p>
  </section>

  <section class="hcs-toc">
    <h2>In this guide</h2>
    <ul>
      {{TABLE_OF_CONTENTS}}
    </ul>
  </section>

  <section class="hcs-content">
    {{MAIN_ARTICLE_SECTIONS}}
  </section>

  <section class="hcs-checklist">
    <h2>Quick checklist</h2>
    {{CHECKLIST_CONTENT}}
  </section>

  <section class="hcs-cta">
    <h2>Explore useful products at HCS Gadgets</h2>
    <p>{{SOFT_CTA_TEXT}}</p>
  </section>

  <section class="hcs-faq">
    <h2>FAQs</h2>
    {{FAQ_CONTENT}}
  </section>

  {{FAQ_SCHEMA_JSON_LD}}

</article>

## Design Direction
This template should be styled inside the HCS Shopify theme CSS.

Suggested class prefix:
- .hcs-article
- .hcs-hero
- .hcs-quick-answer
- .hcs-toc
- .hcs-checklist
- .hcs-cta
- .hcs-faq
