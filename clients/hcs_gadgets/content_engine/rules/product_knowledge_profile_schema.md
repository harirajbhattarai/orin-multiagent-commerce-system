# HCS Gadgets — Product Knowledge Profile Schema

**Version:** 1.0
**Date:** 2026-07-04
**Phase:** Product Intelligence Phase 0 — PHASE B
**Status:** APPROVED — Use for all Product Knowledge Profile generation

---

## Purpose

A Product Knowledge Profile (PKP) is a structured, source-proven record of everything known about a Shopify product at HCS Gadgets. Every fact in a PKP is traceable to a source, classified by confidence, and flagged for compliance.

The PKP is the intermediate layer between raw Shopify data and the writer-safe Public Content View.

---

## Profile Schema

```json
{
  "product_name": "string",
  "product_handle": "string",
  "public_product_url": "string",
  "public_brand_or_vendor": "string | null",
  "product_category": "string",
  "product_type": "string | null",
  "product_purpose": "string | null",
  "verified_features": [ClaimRecord],
  "verified_specifications": [ClaimRecord],
  "verified_dimensions": [ClaimRecord],
  "verified_materials": [ClaimRecord],
  "included_items": [ClaimRecord],
  "verified_compatibility": [ClaimRecord],
  "verified_use_cases": [ClaimRecord],
  "care_guidance": [ClaimRecord],
  "setup_guidance": [ClaimRecord],
  "support_relevant_facts": [ClaimRecord],
  "article_topic_opportunities": ["string"],
  "source_provenance": {
    "catalog_source": "product_catalog.json | product_catalog_raw.json",
    "description_source": "product_catalog_raw.json body_html",
    "variant_source": "product_catalog.json variants",
    "url_source": "hcs_verified_link_map.json | derived",
    "profile_generated": "ISO-8601 timestamp"
  },
  "claims_needing_review": [ClaimRecord],
  "data_conflicts": [ConflictRecord],
  "missing_important_fields": ["string"],
  "volatile_fields": ["string"],
  "internal_fields": ["string"],
  "prohibited_writer_fields": ["string"],
  "profile_quality": "high | medium | low",
  "profile_notes": "string | null"
}
```

---

## ClaimRecord

Every verified fact is recorded as a ClaimRecord:

```json
{
  "claim": "string — the factual claim",
  "source_type": "title | description | variant_field | structured_spec | catalog_field",
  "source_field": "string — exact field path or name",
  "source_evidence": "string — excerpt or structured value",
  "confidence": "high | medium | low",
  "stability": "stable | volatile",
  "exposure": "public | internal | review",
  "compliance_risk": "low | medium | high",
  "category": "feature | specification | dimension | material | compatibility | use_case | care | setup | support | other"
}
```

### Confidence Guide

| Level | Meaning |
|-------|---------|
| **high** | Directly stated in source, unambiguous, not contradicted by other fields |
| **medium** | Implied by source, requires interpretation, or partially supported |
| **low** | Inferred from context, may not be explicitly confirmed by source |

### Stability Guide

| Level | Meaning |
|-------|---------|
| **stable** | Will not change without a product redesign or update (dimensions, materials, capacity) |
| **volatile** | May change frequently (price, stock, availability, included items) |

### Exposure Guide

| Level | Meaning |
|-------|---------|
| **public** | Safe for customer-facing article content |
| **internal** | Not appropriate for customer-facing content (SKUs, stock counts, internal IDs) |
| **review** | Needs human review before customer-facing use (safety claims, compliance claims, superlatives) |

### Compliance Risk Guide

| Level | Meaning |
|-------|---------|
| **low** | No regulatory or compliance concern |
| **medium** | May require verification (performance claims, compatibility claims) |
| **high** | Requires supporting evidence or human review (safety certifications, legal claims, health claims) |

---

## ConflictRecord

```json
{
  "conflict_type": "capacity_mismatch | dimension_mismatch | material_mismatch | included_item_mismatch | age_mismatch | speed_mismatch | range_mismatch | weight_limit_mismatch | warranty_mismatch | specification_contradiction",
  "conflicted_facts": ["string — the two conflicting claims"],
  "source_a": "string — where fact A comes from",
  "source_b": "string — where fact B comes from",
  "resolution": "string — how the conflict should be handled",
  "writer_action": "string — what the writer should do with this conflict"
}
```

**Rule:** Conflicted facts must NOT be added to `verified_features` or `verified_specifications`. They must be recorded in `data_conflicts` and excluded from the writer-safe view.

---

## Category Definitions

| Category | Description |
|----------|-------------|
| `feature` | A capability, function, or attribute of the product |
| `specification` | A measurable technical value (speed, power, capacity) |
| `dimension` | Physical size measurements (height, width, length, weight) |
| `material` | What the product is made from |
| `compatibility` | What the product works with |
| `use_case` | Situations or contexts where the product is used |
| `care` | How to maintain or clean the product |
| `setup` | How to assemble or begin using the product |
| `support` | Facts relevant to customer support (warranty, returns, troubleshooting) |
| `other` | Miscellaneous facts that don't fit other categories |

---

## Required Fields in Every Profile

Every PKP must contain:

1. `product_name` — exact title from Shopify
2. `product_handle` — URL handle from Shopify
3. `public_product_url` — verified URL from link map or derived
4. `product_category` — from `product_type` or derived category
5. `source_provenance` — complete audit trail of where each data point came from
6. `volatile_fields` — all volatile fields present in the source data
7. `internal_fields` — all internal-only fields excluded from writer view
8. `prohibited_writer_fields` — explicit list of what was removed
9. `profile_quality` — self-assessed quality rating
10. `article_topic_opportunities` — at least one relevant article topic

---

## Quality Ratings

| Rating | Criteria |
|--------|---------|
| **high** | Has a usable product description (>100 chars), at least 3 verified features, no unresolved critical conflicts |
| **medium** | Has a description (>50 chars) OR at least 2 verified features, some conflicts or missing data |
| **low** | Empty description, fewer than 2 verifiable facts, significant missing data, or many conflicts requiring human review |

---

## Source Provenance Requirements

Every profile must record:
- Which source file(s) were used
- Which specific fields provided which facts
- Whether the product description was analysed
- When the profile was generated

---

## Missing Data Rule

**MISSING DATA != PERMISSION TO INFER.**

If a fact cannot be confirmed from any source, the profile must record `unknown` for that field — never guess, estimate, or fill in plausible-sounding information.

Fields that are commonly missing and must NOT be inferred:
- Maximum speed (if not stated)
- Range/ battery life (if not stated)
- Weight capacity (if not stated)
- Material composition (if not stated)
- Warranty period (if not stated)
- Age range (if not stated)
- Certification details (if not confirmed by cert number or standard)
