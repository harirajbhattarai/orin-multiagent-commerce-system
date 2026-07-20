# Hoverboard Store — Cluster Rules

Purpose:
These rules control how ORIN chooses whether to create, update, merge, or skip content.

## Core Rule

Never create a new blog only because a keyword exists.

First check:
1. Existing published articles
2. Existing draft articles
3. Duplicate risk log
4. Content patterns
5. Cluster map
6. Safe topic rules

## Decision Types

ORIN must classify every topic as one of:

- create_new
- update_existing
- merge_draft
- skip_duplicate
- create_collection_content
- create_product_faq
- needs_human_review

## When to Create New Content

Create a new blog only if:

- the topic is not already covered
- the angle is clearly unique
- it supports a collection/product/internal link goal
- duplicate risk is low
- it fits a gap or active cluster
- ORIN Guard does not flag major risk

## When to Update Existing Content

Update an existing article if:

- the topic already exists
- the current article is old or thin
- the new idea is mostly a refresh
- the article needs newer product data or legal guidance
- the duplicate checker shows similarity

## When to Merge Drafts

Merge a draft if:

- a draft duplicates a published article
- draft has useful sections not in the published article
- publishing it separately would create duplicate content

## When to Skip

Skip if:

- topic is already covered well
- title/slug/body similarity is high
- it adds no new buyer value
- it repeats FAQ sections from existing posts

## Cluster Saturation Rule

If a cluster is saturated:
- do not create broad new posts
- only create narrow supporting articles
- prefer updates, FAQs, product copy or collection content

If a cluster is a gap:
- create new content carefully
- connect it to collection/product pages
- add internal links into related clusters

## Internal Linking Rule

Every new blog must link to:
- at least one relevant collection page
- at least one related blog if it exists
- one buyer-action page where useful

Do not link to pages that do not exist.

## Guard Rule

Before publishing:
- ORIN Guard must check legal claims
- ORIN Guard must check safety claims
- ORIN Guard must check product claims
- ORIN Guard must check duplicate risk
- ORIN Guard must check metadata length
- ORIN Guard must check unsupported claims

If Guard status is not approved:
- do not publish live
- save as draft or needs_review
