# Hoverboard Store — Topic Opportunities

Purpose:
This file decides what ORIN should do next based on Shopify inventory, duplicate risks, and cluster map.

## Current Inventory Summary

- Total Shopify articles checked: 20
- Published articles: 13
- Draft articles: 7
- Duplicate/similarity risks found: 4

## High-Risk Drafts

### 1. How to Charge Hoverboard Safely – UK Guide 2026

Status:
- High duplicate risk

Reason:
- Similar to already published article: How to Charge Hoverboard Safely UK 2026 – Complete Guide
- Title similarity: high
- Body topic similarity: high
- Body phrase similarity: high

Recommended action:
- Do not publish as a separate article.
- Merge any useful sections into the published article or delete/archive draft after review.

Decision:
- merge_draft / needs_human_review

---

## Saturated Clusters

These clusters already have enough broad content. Avoid creating more generic blogs here.

### Hoverboard Safety

Existing related content:
- Hoverboard Safety Guide UK 2026
- How to Ride a Hoverboard for the First Time
- Hoverboard Weight Limits Explained
- Hoverboard Safety Laws draft
- Where to Ride Hoverboards Legally draft
- What Age Is Right for a Hoverboard draft

Recommended action:
- Do not create broad safety blogs.
- Prefer updating existing articles or creating narrow FAQs/product-support content.

### Charging / Battery

Existing related content:
- How to Charge Hoverboard Safely UK 2026
- Hoverboard Battery Guide
- Hoverboard Troubleshooting Guide
- Duplicate charging draft

Recommended action:
- Do not create new broad charging/battery posts.
- Prefer update or merge.

### Hoverkart

Existing related content:
- Hoverkart Safety Guide
- Hoverkart Compatibility Guide
- Hoverboard & Hoverkart Bundles Guide
- Hoverkart vs Go Kart draft

Recommended action:
- Avoid generic hoverkart safety/compatibility topics.
- Only create specific commercial/support content.

---

## Safer New Topic Opportunities

These topics are safer because they support collection/product pages and avoid broad duplicate overlap.

### Opportunity 1: Hoverboard Gift Guide for Kids

Decision:
- create_new

Reason:
- Seasonal/gift cluster is a gap.
- Strong parent/gift-buyer intent.
- Can internally link to hoverboards, bundles, hoverkarts, and kids electric scooters.

Target keyword:
- hoverboard gift for kids

Suggested title:
- Hoverboard Gift Guide for Kids UK

Risk:
- Avoid unsupported “best gift” claims.
- Avoid inventing age or safety claims.

---

### Opportunity 2: 6.5 Inch vs 8.5 Inch Hoverboards

Decision:
- create_new

Reason:
- Product/collection support gap.
- Helps buyers compare actual product types.
- Supports collection/product internal links.

Target keyword:
- 6.5 inch vs 8.5 inch hoverboard

Suggested title:
- 6.5 Inch vs 8.5 Inch Hoverboards: Which Size Is Right?

Risk:
- Must use confirmed product specs before publishing.

---

### Opportunity 3: Hoverboard Bundle Buying Guide by Rider Type

Decision:
- create_new

Reason:
- Supports hoverboard bundle collection.
- Commercial buyer intent.
- Different angle from broad bundle guide if focused by rider type.

Target keyword:
- hoverboard bundle guide

Suggested title:
- Hoverboard Bundle Buying Guide by Rider Type

Risk:
- Avoid repeating existing bundle article too closely.
- Check duplicate risk before publishing.

---

### Opportunity 4: Hoverboard Accessories Checklist for New Riders

Decision:
- create_new

Reason:
- Accessories cluster has opportunity.
- Supports upsell and safety education.
- Can internally link to accessories and safety content.

Target keyword:
- hoverboard accessories checklist

Suggested title:
- Hoverboard Accessories Checklist for New Riders

Risk:
- Avoid unsupported safety guarantees.

---

## Best Next Action

Recommended next action:
1. Do not publish duplicate charging draft.
2. Build Shopify draft publisher.
3. Test by creating ONE draft article from a safe opportunity.
4. Recommended first test topic:
   - Hoverboard Gift Guide for Kids UK

Why:
- It is a gap cluster.
- Lower duplicate risk.
- Strong commercial/gift intent.
- Good internal linking opportunity.

## Rule Before Publishing

Before any article is generated or published:

1. Run Shopify inventory fetch.
2. Run duplicate checker.
3. Check cluster_map.md.
4. Check safe_topic_rules.md.
5. Check this topic_opportunities.md.
6. Run ORIN Guard.
7. Publish as draft first.
