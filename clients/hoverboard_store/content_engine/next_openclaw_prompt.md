CLIENT: Hoverboard Store

TASK TYPE:
Create upcoming Shopify blog article as a local HTML file only.

IMPORTANT:
Do NOT publish to Shopify.
Do NOT update Shopify.
Do NOT call Shopify API.
Do NOT edit existing published articles.
Only create the local HTML draft file.

QUEUE JOB:
Job 20

TOPIC:
Best Hoverboard Accessories for Safer Riding

TARGET KEYWORD:
hoverboard accessories

CLUSTER:
Accessories / Support

DECISION:
create_new

TARGET FILE:
clients/hoverboard_store/content_engine/drafts/best-hoverboard-accessories-safer-riding.html

NOTES:
- Avoid duplicating Job 04.
- Focus on safety gear, carry bags, hoverkarts, chargers only if suitable.
- Do not invent stock.

READ THESE RULE FILES BEFORE WRITING:
- agents/orin_core/rules.md
- agents/orin_seo/rules.md
- agents/orin_content/rules.md
- agents/orin_guard/rules.md
- clients/hoverboard_store/business.md
- clients/hoverboard_store/brand.md
- clients/hoverboard_store/seo.md
- clients/hoverboard_store/rules.md
- clients/hoverboard_store/content_engine/html_blocks.md
- clients/hoverboard_store/content_engine/cluster_map.md
- clients/hoverboard_store/content_engine/cluster_rules.md
- clients/hoverboard_store/content_engine/safe_topic_rules.md
- clients/hoverboard_store/content_engine/topic_opportunities.md
- clients/hoverboard_store/content_engine/publishing_rules.md
- clients/hoverboard_store/compliance/uk_product_compliance_rules.md
- clients/hoverboard_store/content_engine/published_inventory.md
- clients/hoverboard_store/content_engine/draft_inventory.md

STRICT RULES:
- Existing published Shopify articles are read-only.
- New articles must become hidden Shopify drafts only after checks.
- Do not create duplicate content.
- Do not mention ORIN, AISEO, TOOXIC, ChatGPT, AI author, or autonomous SEO system in public article content.
- Public byline must be: By Hoverboard Store
- Authority section must say: Hoverboard Store Team
- SEO metadata must only appear inside an HTML comment at the top.
- Do not show SEO Title, Meta Title, Meta Description, or URL Slug visibly in the article body.

FAQ FORMAT:
Use this exact FAQ format:

<div class="hs-faq-item">
  <div class="hs-faq-q">Question text only</div>
  <div class="hs-faq-a">Answer text only</div>
</div>

Do NOT use:
- <h3 class="hs-faq-q">
- <p class="hs-faq-a">
- manual FAQPage JSON-LD

COMPLIANCE:
- Avoid unsupported public-road, pavement, cycle-lane, commuting, or legal-use claims.
- Do not invent product specs, certifications, warranty, stock, or delivery claims.
- Use careful wording if anything needs verification.

ARTICLE STRUCTURE:
Use the Hoverboard Store hs-article design system:
1. SEO metadata comment
2. <div class="hs-article">
3. <div class="hs-container">
4. H1
5. hs-meta
6. hs-quick-answer
7. intro paragraphs
8. hs-highlights
9. H2/H3 sections
10. FAQ section
11. related guides
12. soft CTA
13. hs-authority

OUTPUT:
Use the write tool to create:
clients/hoverboard_store/content_engine/drafts/best-hoverboard-accessories-safer-riding.html

After writing, reply with:
1. File created path
2. Meta title
3. Meta description
4. URL slug
5. Guard check summary
6. Compliance warnings if any
7. Verification needed before Shopify draft publishing

Do not publish.
